import argparse
import csv
import glob
import math
import os
import re
import struct
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


DATA_ROOT = Path('data')
RAW_DIR = DATA_ROOT / 'raw'
CONVERTED_DIR = DATA_ROOT / 'converted'
PROCESSED_DIR = DATA_ROOT / 'processed'
AM15_PATH = Path('reference') / 'am15g_spectrum.csv'

FLOAT_TOL = 1e-12
DECAY_THRESHOLD = 0.01
MIN_PROCESS_WL_NM = 290.0
PEAK_MIN_WL = 290.0
PEAK_MAX_WL = 800.0


@dataclass
class MeasurementMeta:
    prefix: str
    hours: int
    sample_no: str
    group_key: str


def parse_dsw(file_path: str) -> Optional[List[Tuple[float, float]]]:
    with open(file_path, 'rb') as f:
        content = f.read()

    offset = 0
    start_offset = -1
    stride = 0

    while offset < len(content) - 16:
        try:
            val = struct.unpack('<f', content[offset:offset + 4])[0]
            if 799.0 < val < 801.0:
                val_next_4 = struct.unpack('<f', content[offset + 4:offset + 8])[0]
                if 798.0 < val_next_4 < 800.0 and val_next_4 < val:
                    start_offset = offset
                    stride = 4
                    break

                val_next_8 = struct.unpack('<f', content[offset + 8:offset + 12])[0]
                if 798.0 < val_next_8 < 800.0 and val_next_8 < val:
                    start_offset = offset
                    stride = 8
                    break
        except Exception:
            pass
        offset += 1

    if start_offset == -1:
        print(f'[{os.path.basename(file_path)}] Could not locate data pattern.')
        return None

    data: List[Tuple[float, float]] = []
    curr_offset = start_offset

    while curr_offset < len(content) - 4:
        wav = struct.unpack('<f', content[curr_offset:curr_offset + 4])[0]
        if wav < 199.0:
            break

        if stride == 8:
            abs_val = struct.unpack('<f', content[curr_offset + 4:curr_offset + 8])[0]
        else:
            print(f'[{os.path.basename(file_path)}] Planar format detected but not supported yet.')
            return None

        data.append((float(wav), float(abs_val)))
        curr_offset += stride

        if len(data) > 2000:
            break

    return data


def write_spectrum_csv(csv_path: Path, title: str, data: Sequence[Tuple[float, float]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([title, '', ''])
        writer.writerow(['Wavelength (nm)', 'Abs', ''])
        for wav, abs_val in data:
            writer.writerow([wav, abs_val, ''])


def convert_all_dsw(raw_dir: Path, converted_dir: Path) -> None:
    converted_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(converted_dir.glob('*.csv')):
        path.unlink(missing_ok=True)

    dsw_files = sorted(raw_dir.glob('*.DSW')) + sorted(raw_dir.glob('*.dsw'))
    print(f'Found {len(dsw_files)} DSW files in {raw_dir}')

    for dsw in dsw_files:
        data = parse_dsw(str(dsw))
        if not data:
            continue
        out = converted_dir / f'{dsw.stem}.csv'
        write_spectrum_csv(out, dsw.stem, data)
        print(f'Converted {dsw.name} -> {out.as_posix()}')


def read_spectrum_csv(path: Path) -> Tuple[List[float], List[float]]:
    wl: List[float] = []
    av: List[float] = []
    with open(path, 'r', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            try:
                w = float(row[0])
                a = float(row[1])
            except ValueError:
                continue
            wl.append(w)
            av.append(a)
    return wl, av


def _to_ascending(x: Sequence[float], y: Sequence[float]) -> Tuple[List[float], List[float]]:
    if not x:
        return [], []
    if x[0] <= x[-1]:
        return list(x), list(y)
    return list(reversed(x)), list(reversed(y))


def linear_interpolate(x_src: Sequence[float], y_src: Sequence[float], x_new: Sequence[float]) -> List[Optional[float]]:
    xs, ys = _to_ascending(x_src, y_src)
    if len(xs) < 2:
        return [None for _ in x_new]

    out: List[Optional[float]] = []
    n = len(xs)

    for x in x_new:
        if x < xs[0] or x > xs[-1]:
            out.append(None)
            continue

        idx = bisect_left(xs, x)
        if idx < n and abs(xs[idx] - x) <= FLOAT_TOL:
            out.append(ys[idx])
            continue

        if idx > 0 and abs(xs[idx - 1] - x) <= FLOAT_TOL:
            out.append(ys[idx - 1])
            continue

        if idx <= 0 or idx >= n:
            out.append(None)
            continue

        x0, x1 = xs[idx - 1], xs[idx]
        y0, y1 = ys[idx - 1], ys[idx]
        if abs(x1 - x0) <= FLOAT_TOL:
            out.append(y0)
            continue

        t = (x - x0) / (x1 - x0)
        out.append(y0 + t * (y1 - y0))

    return out


def trapz(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) < 2 or len(y) < 2:
        return 0.0
    xa, ya = _to_ascending(x, y)
    total = 0.0
    for i in range(len(xa) - 1):
        total += 0.5 * (ya[i] + ya[i + 1]) * (xa[i + 1] - xa[i])
    return total


def interpolate_crossing_time(times: Sequence[float], values: Sequence[float], target: float) -> Optional[float]:
    if len(times) != len(values) or len(times) < 2:
        return None

    pairs = sorted(zip(times, values), key=lambda p: p[0])
    for i in range(len(pairs) - 1):
        t0, v0 = pairs[i]
        t1, v1 = pairs[i + 1]

        if v0 == target:
            return float(t0)
        if v1 == target:
            return float(t1)

        d0 = v0 - target
        d1 = v1 - target
        if d0 * d1 > 0:
            continue
        if abs(v1 - v0) <= FLOAT_TOL:
            continue

        frac = (target - v0) / (v1 - v0)
        return float(t0 + frac * (t1 - t0))
    return None


def parse_measurement_name(stem: str) -> Optional[MeasurementMeta]:
    m = re.match(r'^(?P<prefix>.+)-t?(?P<hours>\d+)h-(?P<sample>\d+)$', stem, re.IGNORECASE)
    if not m:
        return None
    prefix = m.group('prefix')
    hours = int(m.group('hours'))
    sample_no = m.group('sample')
    return MeasurementMeta(prefix=prefix, hours=hours, sample_no=sample_no, group_key=f'{prefix}-{sample_no}')


def load_am15_reference(csv_path: Path) -> Tuple[List[float], List[float]]:
    wl: List[float] = []
    irr: List[float] = []

    with open(csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            try:
                wv = float(row[0])
                iv = float(row[1])
            except ValueError:
                continue
            wl.append(wv)
            irr.append(iv)

    return wl, irr


def write_table_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(list(header))
        for row in rows:
            w.writerow(list(row))


def build_group_outputs(group_key: str, files_by_time: Dict[int, Path], blank_csv: Path,
                        am15_wl: Sequence[float], am15_irr: Sequence[float]) -> None:
    out_dir = PROCESSED_DIR / group_key
    out_dir.mkdir(parents=True, exist_ok=True)

    blank_wl, blank_abs = read_spectrum_csv(blank_csv)
    if len(blank_wl) < 2:
        raise RuntimeError(f'Blank CSV has insufficient data: {blank_csv}')

    wl_mask = [i for i, wv in enumerate(blank_wl) if wv >= MIN_PROCESS_WL_NM]
    if len(wl_mask) < 2:
        raise RuntimeError(
            f'Blank spectrum has insufficient points >= {MIN_PROCESS_WL_NM} nm.'
        )
    blank_wl = [blank_wl[i] for i in wl_mask]
    blank_abs = [blank_abs[i] for i in wl_mask]

    times = sorted(files_by_time.keys())
    max_hours = max(times)
    file_tag = f"{group_key}_{max_hours}h"

    sample_interp: Dict[int, List[Optional[float]]] = {}
    corrected: Dict[int, List[Optional[float]]] = {}

    for t in times:
        wl, ab = read_spectrum_csv(files_by_time[t])
        interp_sample = linear_interpolate(wl, ab, blank_wl)
        sample_interp[t] = interp_sample

        corr: List[Optional[float]] = []
        for i, s in enumerate(interp_sample):
            b = blank_abs[i]
            corr.append(None if s is None else (s - b))
        corrected[t] = corr

    raw_header = ['wavelength_nm', 'blank'] + [f't{t}h' for t in times]
    raw_rows: List[List[object]] = []
    for i, wv in enumerate(blank_wl):
        row: List[object] = [wv, blank_abs[i]]
        for t in times:
            row.append(sample_interp[t][i])
        raw_rows.append(row)
    write_table_csv(out_dir / f'raw_{file_tag}.csv', raw_header, raw_rows)

    bc_header = ['wavelength_nm'] + [f't{t}h' for t in times]
    bc_rows: List[List[object]] = []
    for i, wv in enumerate(blank_wl):
        row = [wv]
        for t in times:
            row.append(corrected[t][i])
        bc_rows.append(row)
    write_table_csv(out_dir / f'baseline_corrected_{file_tag}.csv', bc_header, bc_rows)

    lambda_rows: List[List[object]] = []
    for t in times:
        pts = [(blank_wl[i], v) for i, v in enumerate(corrected[t]) if v is not None and PEAK_MIN_WL <= blank_wl[i] <= PEAK_MAX_WL]
        if not pts:
            pts = [(blank_wl[i], v) for i, v in enumerate(corrected[t]) if v is not None]
        if not pts:
            lambda_rows.append([t, None, None])
            continue
        peak_wl, peak_abs = max(pts, key=lambda x: x[1])
        lambda_rows.append([t, peak_wl, peak_abs])
    write_table_csv(
        out_dir / f'lambda_max_{file_tag}.csv',
        ['time_h', 'peak_wavelength_nm', 'peak_absorbance'],
        lambda_rows,
    )

    am15_interp = linear_interpolate(am15_wl, am15_irr, blank_wl)
    irr = [0.0 if v is None else max(0.0, v) for v in am15_interp]
    total_irr = trapz(blank_wl, irr)

    overlap_rows: List[List[object]] = []
    overlap_percent_by_time: Dict[int, float] = {}

    for t in times:
        abs_frac: List[float] = []
        absorbed_weighted: List[float] = []
        c = corrected[t]
        for i in range(len(blank_wl)):
            cv = c[i]
            if cv is None:
                af = 0.0
            else:
                af = 1.0 - math.pow(10.0, -cv)
            af_clamped = min(1.0, max(0.0, af))
            abs_frac.append(af_clamped)
            absorbed_weighted.append(irr[i] * af_clamped)

        absorbed_irr = trapz(blank_wl, absorbed_weighted)
        absorbed_pct = (absorbed_irr / total_irr * 100.0) if total_irr > 0 else 0.0
        overlap_percent_by_time[t] = absorbed_pct
        overlap_rows.append([t, total_irr, absorbed_irr, absorbed_pct, None])

    t0 = 0 if 0 in overlap_percent_by_time else times[0]
    baseline_pct = overlap_percent_by_time[t0]
    overlap_abs_change_pct_by_time: Dict[int, float] = {}
    for row in overlap_rows:
        row[4] = row[3] - baseline_pct
        if baseline_pct > 0:
            retention_pct = (row[3] / baseline_pct) * 100.0
        else:
            retention_pct = 0.0
        abs_change_pct = abs(retention_pct - 100.0)
        overlap_abs_change_pct_by_time[int(row[0])] = abs_change_pct
        row.extend([retention_pct, abs_change_pct])

    write_table_csv(
        out_dir / f'spectral_overlap_{file_tag}.csv',
        [
            'time_h',
            'total_irradiance_w_m2',
            'absorbed_irradiance_w_m2',
            'spectral_overlap_percent',
            'spectral_overlap_delta_vs_t0_percent',
            'retention_vs_t0_percent',
            'spectral_overlap_abs_change_vs_t0_percent',
        ],
        overlap_rows,
    )

    ref_time = 0 if 0 in corrected else times[0]
    ref = corrected[ref_time]
    norm = sum(max(v, 0.0) for v in ref if v is not None and v > DECAY_THRESHOLD)
    if norm <= 0:
        norm = 1.0

    decay_rows: List[List[object]] = []
    map_header = ['wavelength_nm'] + [f't{t}h_mag' for t in times] + [f't{t}h_signed' for t in times]
    map_rows: List[List[object]] = []

    per_time_mag: Dict[int, List[float]] = {t: [] for t in times}
    per_time_signed: Dict[int, List[float]] = {t: [] for t in times}
    per_time_pos: Dict[int, List[float]] = {t: [] for t in times}
    per_time_neg_abs: Dict[int, List[float]] = {t: [] for t in times}

    for i, wv in enumerate(blank_wl):
        ref_v = ref[i]
        row: List[object] = [wv]

        for t in times:
            cur = corrected[t][i]
            if ref_v is None or cur is None or ref_v <= DECAY_THRESHOLD:
                mag = 0.0
                signed = 0.0
            else:
                mag = abs(ref_v - cur) / norm
                signed = (cur - ref_v) / norm

            per_time_mag[t].append(mag)
            per_time_signed[t].append(signed)
            per_time_pos[t].append(max(signed, 0.0))
            per_time_neg_abs[t].append(max(-signed, 0.0))
            row.append(mag)

        for t in times:
            row.append(per_time_signed[t][-1])

        map_rows.append(row)

    decay_mag_by_time: Dict[int, float] = {}
    decay_signed_by_time: Dict[int, float] = {}
    decay_pos_by_time: Dict[int, float] = {}
    decay_neg_abs_by_time: Dict[int, float] = {}

    for t in times:
        decay_mag_by_time[t] = sum(per_time_mag[t])
        decay_signed_by_time[t] = sum(per_time_signed[t])
        decay_pos_by_time[t] = sum(per_time_pos[t])
        decay_neg_abs_by_time[t] = sum(per_time_neg_abs[t])

    # T80 from spectral decay magnitude only (index target = 0.20).
    t80_h = interpolate_crossing_time(
        times=[float(t) for t in times],
        values=[float(decay_mag_by_time[t]) for t in times],
        target=0.20,
    )

    for t in times:
        decay_rows.append([
            t,
            decay_mag_by_time[t],
            decay_signed_by_time[t],
            decay_pos_by_time[t],
            decay_neg_abs_by_time[t],
            overlap_abs_change_pct_by_time.get(t, 0.0),
            t80_h,
        ])

    write_table_csv(
        out_dir / f'spectral_decay_{file_tag}.csv',
        [
            'time_h',
            'decay_index_mag',
            'decay_index_signed',
            'decay_index_positive',
            'decay_index_negative_abs',
            'spectral_overlap_abs_change_vs_t0_percent',
            't80_h',
        ],
        decay_rows,
    )
    write_table_csv(out_dir / f'spectral_decay_map_{file_tag}.csv', map_header, map_rows)

    lambda_map = {int(r[0]): (r[1], r[2]) for r in lambda_rows}
    overlap_map = {int(r[0]): (r[1], r[2], r[3], r[4], r[5], r[6]) for r in overlap_rows}
    decay_map = {int(r[0]): (r[1], r[2], r[3], r[4], r[5], r[6]) for r in decay_rows}

    analysis_rows: List[List[object]] = []
    for t in times:
        pw, pa = lambda_map.get(t, (None, None))
        ti, ai, ap, dv, ret, oa = overlap_map.get(t, (None, None, None, None, None, None))
        dm, ds, dp, dn, oa2, t80 = decay_map.get(t, (None, None, None, None, None, None))
        analysis_rows.append([t, pw, pa, ap, dv, ret, oa, dm, ds, dp, dn, t80])

    write_table_csv(
        out_dir / f'analysis_{file_tag}.csv',
        [
            'time_h',
            'peak_wavelength_nm',
            'peak_absorbance',
            'spectral_overlap_percent',
            'spectral_overlap_delta_vs_t0_percent',
            'retention_vs_t0_percent',
            'spectral_overlap_abs_change_vs_t0_percent',
            'spectral_decay_mag',
            'spectral_decay_signed',
            'spectral_decay_positive',
            'spectral_decay_negative_abs',
            't80_h',
        ],
        analysis_rows,
    )


def run_pipeline(raw_dir: Path, converted_dir: Path, processed_dir: Path, am15_path: Path, skip_convert: bool) -> None:
    global PROCESSED_DIR
    PROCESSED_DIR = processed_dir

    if not skip_convert:
        convert_all_dsw(raw_dir, converted_dir)

    blank_csv = converted_dir / 'blank.csv'
    if not blank_csv.exists():
        raise FileNotFoundError(f'blank.csv not found in {converted_dir}')

    am15_wl, am15_irr = load_am15_reference(am15_path)
    if len(am15_wl) < 2:
        raise RuntimeError(f'Failed to load AM1.5 reference from {am15_path}')

    groups: Dict[str, Dict[int, Path]] = {}

    for csv_path in sorted(converted_dir.glob('*.csv')):
        stem = csv_path.stem
        if stem.lower() == 'blank':
            continue

        meta = parse_measurement_name(stem)
        if meta is None:
            print(f'Skipping unmatched filename: {csv_path.name}')
            continue

        groups.setdefault(meta.group_key, {})[meta.hours] = csv_path

    if not groups:
        raise RuntimeError(f'No valid sample csv files found in {converted_dir}')

    processed_dir.mkdir(parents=True, exist_ok=True)

    for group_key, by_time in sorted(groups.items()):
        if not by_time:
            continue
        print(f'Building outputs for {group_key} ({len(by_time)} time points)')
        build_group_outputs(group_key, by_time, blank_csv, am15_wl, am15_irr)


def main() -> None:
    parser = argparse.ArgumentParser(description='UV-Vis DSW to grouped analysis pipeline')
    parser.add_argument('--raw-dir', default=str(RAW_DIR))
    parser.add_argument('--converted-dir', default=str(CONVERTED_DIR))
    parser.add_argument('--processed-dir', default=str(PROCESSED_DIR))
    parser.add_argument('--am15-path', default=str(AM15_PATH))
    parser.add_argument('--skip-convert', action='store_true', help='Skip DSW->CSV conversion and use existing CSV files')
    args = parser.parse_args()

    run_pipeline(
        raw_dir=Path(args.raw_dir),
        converted_dir=Path(args.converted_dir),
        processed_dir=Path(args.processed_dir),
        am15_path=Path(args.am15_path),
        skip_convert=args.skip_convert,
    )


if __name__ == '__main__':
    main()
