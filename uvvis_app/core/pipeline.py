from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .dsw_io import (
    ensure_spectrum_csv,
    interpolate_crossing_time,
    linear_interpolate,
    load_am15_reference,
    read_spectrum_csv,
    trapz,
)
from .manifest_store import save_manifest
from .models import FILE_KIND_IGNORE, RunManifest, RunOptions


Logger = Optional[Callable[[str], None]]
Progress = Optional[Callable[[str, int], None]]


def write_table_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def _build_assumed_zero_blank(source_csv: Path, converted_dir: Path, logger: Logger = None) -> Path:
    wavelengths, _ = read_spectrum_csv(source_csv)
    if len(wavelengths) < 2:
        raise RuntimeError(
            "Cannot assume zero blank: a sample spectrum with at least two wavelength points is required."
        )

    zero_blank_path = converted_dir / "_assumed_zero_blank.csv"
    write_table_csv(
        zero_blank_path,
        ["Wavelength (nm)", "Abs"],
        [[wavelength, 0.0] for wavelength in wavelengths],
    )
    if logger:
        logger(f"No blank file selected; using assumed zero blank: {zero_blank_path.name}")
    return zero_blank_path


def build_group_outputs(
    group_key: str,
    files_by_time: Dict[int, Path],
    blank_csv: Path,
    am15_wl: Sequence[float],
    am15_irr: Sequence[float],
    output_root: Path,
    options: RunOptions,
) -> Path:
    out_dir = output_root / group_key
    out_dir.mkdir(parents=True, exist_ok=True)

    blank_wl, blank_abs = read_spectrum_csv(blank_csv)
    if len(blank_wl) < 2:
        raise RuntimeError(f"Blank CSV has insufficient data: {blank_csv}")

    wl_mask = [idx for idx, value in enumerate(blank_wl) if value >= options.min_wavelength_nm]
    if len(wl_mask) < 2:
        raise RuntimeError(
            f"Blank spectrum has insufficient points >= {options.min_wavelength_nm} nm."
        )
    blank_wl = [blank_wl[idx] for idx in wl_mask]
    blank_abs = [blank_abs[idx] for idx in wl_mask]

    times = sorted(files_by_time.keys())
    max_hours = max(times)
    file_tag = f"{group_key}_{max_hours}h"

    sample_interp: Dict[int, List[Optional[float]]] = {}
    corrected: Dict[int, List[Optional[float]]] = {}

    for time_h in times:
        wavelengths, absorbance = read_spectrum_csv(files_by_time[time_h])
        interpolated = linear_interpolate(wavelengths, absorbance, blank_wl)
        sample_interp[time_h] = interpolated

        corrected_values: List[Optional[float]] = []
        for idx, sample_value in enumerate(interpolated):
            blank_value = blank_abs[idx]
            corrected_values.append(None if sample_value is None else (sample_value - blank_value))
        corrected[time_h] = corrected_values

    raw_header = ["wavelength_nm", "blank"] + [f"t{time_h}h" for time_h in times]
    raw_rows: List[List[object]] = []
    for idx, wavelength in enumerate(blank_wl):
        row: List[object] = [wavelength, blank_abs[idx]]
        for time_h in times:
            row.append(sample_interp[time_h][idx])
        raw_rows.append(row)
    write_table_csv(out_dir / f"raw_{file_tag}.csv", raw_header, raw_rows)

    baseline_header = ["wavelength_nm"] + [f"t{time_h}h" for time_h in times]
    baseline_rows: List[List[object]] = []
    for idx, wavelength in enumerate(blank_wl):
        row = [wavelength]
        for time_h in times:
            row.append(corrected[time_h][idx])
        baseline_rows.append(row)
    write_table_csv(out_dir / f"baseline_corrected_{file_tag}.csv", baseline_header, baseline_rows)

    lambda_rows: List[List[object]] = []
    for time_h in times:
        points = [
            (blank_wl[idx], value)
            for idx, value in enumerate(corrected[time_h])
            if value is not None and options.peak_min_nm <= blank_wl[idx] <= options.peak_max_nm
        ]
        if not points:
            points = [
                (blank_wl[idx], value)
                for idx, value in enumerate(corrected[time_h])
                if value is not None
            ]
        if not points:
            lambda_rows.append([time_h, None, None])
            continue
        peak_wl, peak_abs = max(points, key=lambda item: item[1])
        lambda_rows.append([time_h, peak_wl, peak_abs])
    write_table_csv(
        out_dir / f"lambda_max_{file_tag}.csv",
        ["time_h", "peak_wavelength_nm", "peak_absorbance"],
        lambda_rows,
    )

    am15_interp = linear_interpolate(am15_wl, am15_irr, blank_wl)
    irradiance = [0.0 if value is None else max(0.0, value) for value in am15_interp]
    total_irradiance = trapz(blank_wl, irradiance)

    overlap_rows: List[List[object]] = []
    overlap_percent_by_time: Dict[int, float] = {}

    for time_h in times:
        absorbed_weighted: List[float] = []
        current = corrected[time_h]
        for idx in range(len(blank_wl)):
            corrected_value = current[idx]
            if corrected_value is None:
                absorbed_fraction = 0.0
            else:
                absorbed_fraction = 1.0 - math.pow(10.0, -corrected_value)
            clamped = min(1.0, max(0.0, absorbed_fraction))
            absorbed_weighted.append(irradiance[idx] * clamped)

        absorbed_irradiance = trapz(blank_wl, absorbed_weighted)
        absorbed_percent = (
            absorbed_irradiance / total_irradiance * 100.0 if total_irradiance > 0 else 0.0
        )
        overlap_percent_by_time[time_h] = absorbed_percent
        overlap_rows.append([time_h, total_irradiance, absorbed_irradiance, absorbed_percent, None])

    t0 = 0 if 0 in overlap_percent_by_time else times[0]
    baseline_percent = overlap_percent_by_time[t0]
    overlap_abs_change_pct_by_time: Dict[int, float] = {}
    for row in overlap_rows:
        row[4] = row[3] - baseline_percent
        if baseline_percent > 0:
            retention_pct = (row[3] / baseline_percent) * 100.0
        else:
            retention_pct = 0.0
        abs_change_pct = abs(retention_pct - 100.0)
        overlap_abs_change_pct_by_time[int(row[0])] = abs_change_pct
        row.extend([retention_pct, abs_change_pct])

    write_table_csv(
        out_dir / f"spectral_overlap_{file_tag}.csv",
        [
            "time_h",
            "total_irradiance_w_m2",
            "absorbed_irradiance_w_m2",
            "spectral_overlap_percent",
            "spectral_overlap_delta_vs_t0_percent",
            "retention_vs_t0_percent",
            "spectral_overlap_abs_change_vs_t0_percent",
        ],
        overlap_rows,
    )

    ref_time = 0 if 0 in corrected else times[0]
    reference = corrected[ref_time]
    norm = sum(
        max(value, 0.0)
        for value in reference
        if value is not None and value > options.decay_threshold
    )
    if norm <= 0:
        norm = 1.0

    decay_rows: List[List[object]] = []
    map_header = ["wavelength_nm"] + [f"t{time_h}h_mag" for time_h in times] + [
        f"t{time_h}h_signed" for time_h in times
    ]
    map_rows: List[List[object]] = []

    per_time_mag: Dict[int, List[float]] = {time_h: [] for time_h in times}
    per_time_signed: Dict[int, List[float]] = {time_h: [] for time_h in times}
    per_time_positive: Dict[int, List[float]] = {time_h: [] for time_h in times}
    per_time_negative_abs: Dict[int, List[float]] = {time_h: [] for time_h in times}

    for idx, wavelength in enumerate(blank_wl):
        ref_value = reference[idx]
        row: List[object] = [wavelength]

        for time_h in times:
            current = corrected[time_h][idx]
            if ref_value is None or current is None or ref_value <= options.decay_threshold:
                magnitude = 0.0
                signed = 0.0
            else:
                magnitude = abs(ref_value - current) / norm
                signed = (current - ref_value) / norm

            per_time_mag[time_h].append(magnitude)
            per_time_signed[time_h].append(signed)
            per_time_positive[time_h].append(max(signed, 0.0))
            per_time_negative_abs[time_h].append(max(-signed, 0.0))
            row.append(magnitude)

        for time_h in times:
            row.append(per_time_signed[time_h][-1])

        map_rows.append(row)

    decay_mag_by_time: Dict[int, float] = {}
    decay_signed_by_time: Dict[int, float] = {}
    decay_positive_by_time: Dict[int, float] = {}
    decay_negative_abs_by_time: Dict[int, float] = {}

    for time_h in times:
        decay_mag_by_time[time_h] = sum(per_time_mag[time_h])
        decay_signed_by_time[time_h] = sum(per_time_signed[time_h])
        decay_positive_by_time[time_h] = sum(per_time_positive[time_h])
        decay_negative_abs_by_time[time_h] = sum(per_time_negative_abs[time_h])

    t80_h = interpolate_crossing_time(
        times=[float(time_h) for time_h in times],
        values=[float(decay_mag_by_time[time_h]) for time_h in times],
        target=0.20,
    )

    for time_h in times:
        decay_rows.append(
            [
                time_h,
                decay_mag_by_time[time_h],
                decay_signed_by_time[time_h],
                decay_positive_by_time[time_h],
                decay_negative_abs_by_time[time_h],
                overlap_abs_change_pct_by_time.get(time_h, 0.0),
                t80_h,
            ]
        )

    write_table_csv(
        out_dir / f"spectral_decay_{file_tag}.csv",
        [
            "time_h",
            "decay_index_mag",
            "decay_index_signed",
            "decay_index_positive",
            "decay_index_negative_abs",
            "spectral_overlap_abs_change_vs_t0_percent",
            "t80_h",
        ],
        decay_rows,
    )
    write_table_csv(out_dir / f"spectral_decay_map_{file_tag}.csv", map_header, map_rows)

    lambda_map = {int(row[0]): (row[1], row[2]) for row in lambda_rows}
    overlap_map = {int(row[0]): (row[1], row[2], row[3], row[4], row[5], row[6]) for row in overlap_rows}
    decay_map = {int(row[0]): (row[1], row[2], row[3], row[4], row[5], row[6]) for row in decay_rows}

    analysis_rows: List[List[object]] = []
    for time_h in times:
        peak_wl, peak_abs = lambda_map.get(time_h, (None, None))
        _, _, absorbed_pct, delta_vs_t0, retention_pct, overlap_abs_change = overlap_map.get(
            time_h, (None, None, None, None, None, None)
        )
        decay_mag, decay_signed, decay_positive, decay_negative, _, t80_value = decay_map.get(
            time_h, (None, None, None, None, None, None)
        )
        analysis_rows.append(
            [
                time_h,
                peak_wl,
                peak_abs,
                absorbed_pct,
                delta_vs_t0,
                retention_pct,
                overlap_abs_change,
                decay_mag,
                decay_signed,
                decay_positive,
                decay_negative,
                t80_value,
            ]
        )

    write_table_csv(
        out_dir / f"analysis_{file_tag}.csv",
        [
            "time_h",
            "peak_wavelength_nm",
            "peak_absorbance",
            "spectral_overlap_percent",
            "spectral_overlap_delta_vs_t0_percent",
            "retention_vs_t0_percent",
            "spectral_overlap_abs_change_vs_t0_percent",
            "spectral_decay_mag",
            "spectral_decay_signed",
            "spectral_decay_positive",
            "spectral_decay_negative_abs",
            "t80_h",
        ],
        analysis_rows,
    )

    return out_dir


def run_manifest(
    manifest: RunManifest,
    logger: Logger = None,
    progress: Progress = None,
) -> Path:
    samples = manifest.selected_samples()
    blank_file = manifest.effective_blank_file
    if blank_file is None and not manifest.options.assume_zero_blank:
        raise RuntimeError("No blank file is selected.")

    processed_dir = manifest.processed_dir
    converted_dir = manifest.layout.converted_dir
    processed_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)

    if logger:
        logger(f"Output directory: {processed_dir}")
        if blank_file is not None:
            logger(f"Using blank file: {blank_file}")
        else:
            logger("Using assumed zero blank (no blank file selected).")

    if progress:
        progress("Preparing manifest", 5)

    save_manifest(manifest, processed_dir / "_manifest.json")

    am15_wl, am15_irr = load_am15_reference(manifest.reference_file)
    if len(am15_wl) < 2:
        raise RuntimeError(f"Failed to load AM1.5 reference from {manifest.reference_file}")

    if progress:
        progress("Resolving input spectra", 15)

    grouped_csv: Dict[str, Dict[int, Path]] = {}
    total_files = max(1, len(samples))
    for index, entry in enumerate(samples, start=1):
        if not entry.group_key or entry.time_h is None:
            raise RuntimeError(f"Invalid file mapping for {entry.filename}")
        csv_path = ensure_spectrum_csv(
            source_path=entry.path,
            converted_dir=converted_dir,
            skip_convert=manifest.options.skip_convert,
            logger=logger,
        )
        grouped_csv.setdefault(entry.group_key, {})[int(entry.time_h)] = csv_path
        if progress:
            progress(
                f"Prepared {index}/{total_files} input spectra",
                15 + int(index / total_files * 30),
            )

    if blank_file is not None:
        blank_csv = ensure_spectrum_csv(
            source_path=Path(blank_file),
            converted_dir=converted_dir,
            skip_convert=manifest.options.skip_convert,
            logger=logger,
        )
    else:
        first_group_key = sorted(grouped_csv.keys())[0]
        first_time = sorted(grouped_csv[first_group_key].keys())[0]
        source_csv = grouped_csv[first_group_key][first_time]
        blank_csv = _build_assumed_zero_blank(
            source_csv=source_csv,
            converted_dir=converted_dir,
            logger=logger,
        )

    total_groups = max(1, len(grouped_csv))
    group_dirs: List[Path] = []
    for index, (group_key, files_by_time) in enumerate(sorted(grouped_csv.items()), start=1):
        if logger:
            logger(f"Building outputs for {group_key} ({len(files_by_time)} time points)")
        group_dir = build_group_outputs(
            group_key=group_key,
            files_by_time=files_by_time,
            blank_csv=blank_csv,
            am15_wl=am15_wl,
            am15_irr=am15_irr,
            output_root=processed_dir,
            options=manifest.options,
        )
        group_dirs.append(group_dir)
        if progress:
            progress(
                f"Processed group {index}/{total_groups}: {group_key}",
                45 + int(index / total_groups * 35),
            )

    if manifest.options.generate_figures:
        from .plotting import plot_group

        total_plot_groups = max(1, len(group_dirs))
        for index, group_dir in enumerate(group_dirs, start=1):
            if logger:
                logger(f"Generating figures for {group_dir.name}")
            plot_group(group_dir, dpi=manifest.options.dpi)
            if progress:
                progress(
                    f"Generated figures for {group_dir.name}",
                    80 + int(index / total_plot_groups * 20),
                )
    elif progress:
        progress("Processing complete", 100)

    if logger:
        logger("Run complete.")
    return processed_dir


def convert_manifest_inputs(
    manifest: RunManifest,
    logger: Logger = None,
    progress: Progress = None,
) -> Path:
    converted_dir = manifest.layout.converted_dir
    converted_dir.mkdir(parents=True, exist_ok=True)

    inputs: List[Path] = []
    blank_file = manifest.effective_blank_file
    if blank_file:
        inputs.append(Path(blank_file))
    for entry in manifest.files:
        if entry.kind == FILE_KIND_IGNORE:
            continue
        inputs.append(entry.path)

    deduped_inputs: List[Path] = []
    seen = set()
    for path in inputs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped_inputs.append(path)

    total = max(1, len(deduped_inputs))
    for index, path in enumerate(deduped_inputs, start=1):
        ensure_spectrum_csv(
            source_path=path,
            converted_dir=converted_dir,
            skip_convert=False,
            logger=logger,
        )
        if progress:
            progress(
                f"Converted {index}/{total}: {path.name}",
                int(index / total * 100),
            )

    if logger:
        logger(f"Converted spectra written to {converted_dir}")
    return converted_dir
