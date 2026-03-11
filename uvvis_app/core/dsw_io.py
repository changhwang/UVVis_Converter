from __future__ import annotations

import csv
import struct
from bisect import bisect_left
from pathlib import Path
from shutil import copy2
from typing import Callable, List, Optional, Sequence, Tuple


FLOAT_TOL = 1e-12
Logger = Optional[Callable[[str], None]]


def parse_dsw(file_path: Path) -> Optional[List[Tuple[float, float]]]:
    with open(file_path, "rb") as handle:
        content = handle.read()

    offset = 0
    start_offset = -1
    stride = 0

    while offset < len(content) - 16:
        try:
            value = struct.unpack("<f", content[offset:offset + 4])[0]
            if 799.0 < value < 801.0:
                next_4 = struct.unpack("<f", content[offset + 4:offset + 8])[0]
                if 798.0 < next_4 < 800.0 and next_4 < value:
                    start_offset = offset
                    stride = 4
                    break

                next_8 = struct.unpack("<f", content[offset + 8:offset + 12])[0]
                if 798.0 < next_8 < 800.0 and next_8 < value:
                    start_offset = offset
                    stride = 8
                    break
        except Exception:
            pass
        offset += 1

    if start_offset == -1:
        return None

    data: List[Tuple[float, float]] = []
    cursor = start_offset

    while cursor < len(content) - 4:
        wavelength = struct.unpack("<f", content[cursor:cursor + 4])[0]
        if wavelength < 199.0:
            break

        if stride != 8:
            return None

        absorbance = struct.unpack("<f", content[cursor + 4:cursor + 8])[0]
        data.append((float(wavelength), float(absorbance)))
        cursor += stride

        if len(data) > 2000:
            break

    return data


def write_spectrum_csv(csv_path: Path, title: str, data: Sequence[Tuple[float, float]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([title, "", ""])
        writer.writerow(["Wavelength (nm)", "Abs", ""])
        for wavelength, absorbance in data:
            writer.writerow([wavelength, absorbance, ""])


def convert_dsw_file(source_path: Path, converted_dir: Path) -> Path:
    data = parse_dsw(source_path)
    if not data:
        raise RuntimeError(f"Could not parse DSW data from {source_path}")
    target_path = converted_dir / f"{source_path.stem}.csv"
    write_spectrum_csv(target_path, source_path.stem, data)
    return target_path


def ensure_spectrum_csv(
    source_path: Path,
    converted_dir: Path,
    skip_convert: bool,
    logger: Logger = None,
) -> Path:
    suffix = source_path.suffix.lower()
    if suffix == ".csv":
        if source_path.parent.resolve() == converted_dir.resolve():
            return source_path
        target_path = converted_dir / source_path.name
        if not target_path.exists():
            converted_dir.mkdir(parents=True, exist_ok=True)
            copy2(source_path, target_path)
        return target_path

    if suffix != ".dsw":
        raise RuntimeError(f"Unsupported source type: {source_path}")

    target_path = converted_dir / f"{source_path.stem}.csv"
    if skip_convert:
        if not target_path.exists():
            raise FileNotFoundError(
                f"Skip-convert requested but converted CSV is missing: {target_path}"
            )
        return target_path

    converted_dir.mkdir(parents=True, exist_ok=True)
    if logger:
        logger(f"Converting {source_path.name}")
    return convert_dsw_file(source_path, converted_dir)


def read_spectrum_csv(path: Path) -> Tuple[List[float], List[float]]:
    wavelengths: List[float] = []
    absorbance_values: List[float] = []

    with open(path, "r", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if len(row) < 2:
                continue
            try:
                wavelength = float(row[0])
                absorbance = float(row[1])
            except ValueError:
                continue
            wavelengths.append(wavelength)
            absorbance_values.append(absorbance)

    return wavelengths, absorbance_values


def load_am15_reference(csv_path: Path) -> Tuple[List[float], List[float]]:
    return read_spectrum_csv(csv_path)


def _to_ascending(
    x_values: Sequence[float], y_values: Sequence[float]
) -> Tuple[List[float], List[float]]:
    if not x_values:
        return [], []
    if x_values[0] <= x_values[-1]:
        return list(x_values), list(y_values)
    return list(reversed(x_values)), list(reversed(y_values))


def linear_interpolate(
    x_source: Sequence[float],
    y_source: Sequence[float],
    x_new: Sequence[float],
) -> List[Optional[float]]:
    xs, ys = _to_ascending(x_source, y_source)
    if len(xs) < 2:
        return [None for _ in x_new]

    output: List[Optional[float]] = []
    count = len(xs)

    for value in x_new:
        if value < xs[0] or value > xs[-1]:
            output.append(None)
            continue

        idx = bisect_left(xs, value)
        if idx < count and abs(xs[idx] - value) <= FLOAT_TOL:
            output.append(ys[idx])
            continue

        if idx > 0 and abs(xs[idx - 1] - value) <= FLOAT_TOL:
            output.append(ys[idx - 1])
            continue

        if idx <= 0 or idx >= count:
            output.append(None)
            continue

        x0, x1 = xs[idx - 1], xs[idx]
        y0, y1 = ys[idx - 1], ys[idx]
        if abs(x1 - x0) <= FLOAT_TOL:
            output.append(y0)
            continue

        ratio = (value - x0) / (x1 - x0)
        output.append(y0 + ratio * (y1 - y0))

    return output


def trapz(x_values: Sequence[float], y_values: Sequence[float]) -> float:
    if len(x_values) < 2 or len(y_values) < 2:
        return 0.0
    xs, ys = _to_ascending(x_values, y_values)
    total = 0.0
    for idx in range(len(xs) - 1):
        total += 0.5 * (ys[idx] + ys[idx + 1]) * (xs[idx + 1] - xs[idx])
    return total


def interpolate_crossing_time(
    times: Sequence[float], values: Sequence[float], target: float
) -> Optional[float]:
    if len(times) != len(values) or len(times) < 2:
        return None

    pairs = sorted(zip(times, values), key=lambda item: item[0])
    for idx in range(len(pairs) - 1):
        t0, v0 = pairs[idx]
        t1, v1 = pairs[idx + 1]

        if v0 == target:
            return float(t0)
        if v1 == target:
            return float(t1)

        delta0 = v0 - target
        delta1 = v1 - target
        if delta0 * delta1 > 0:
            continue
        if abs(v1 - v0) <= FLOAT_TOL:
            continue

        frac = (target - v0) / (v1 - v0)
        return float(t0 + frac * (t1 - t0))
    return None

