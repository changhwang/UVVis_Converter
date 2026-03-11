from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import matplotlib


def _patch_six_meta_importer_for_pyside() -> None:
    try:
        import six
    except Exception:
        return

    for hook in sys.meta_path:
        if isinstance(hook, six._SixMetaPathImporter) and not hasattr(hook, "_path"):
            hook._path = []  # type: ignore[attr-defined]


_patch_six_meta_importer_for_pyside()
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def parse_time_col(column: str) -> Optional[int]:
    match = re.fullmatch(r"t(\d+)h", column)
    if not match:
        return None
    return int(match.group(1))


def find_latest_csv(group_dir: Path, prefix: str) -> Optional[Path]:
    candidates = sorted(group_dir.glob(f"{prefix}_*.csv"))
    if not candidates:
        return None
    return candidates[-1]


def plot_group(group_dir: Path, dpi: int = 160) -> None:
    baseline_path = find_latest_csv(group_dir, "baseline_corrected")
    analysis_path = find_latest_csv(group_dir, "analysis")
    decay_path = find_latest_csv(group_dir, "spectral_decay")

    if baseline_path is None or analysis_path is None or decay_path is None:
        return

    fig_dir = group_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    baseline = pd.read_csv(baseline_path)
    analysis = pd.read_csv(analysis_path)
    decay = pd.read_csv(decay_path)
    baseline = baseline[baseline["wavelength_nm"] >= 290.0].copy()

    time_cols = []
    for column in baseline.columns:
        time_h = parse_time_col(column)
        if time_h is not None:
            time_cols.append((time_h, column))
    time_cols.sort(key=lambda item: item[0])
    max_time = max((time_h for time_h, _ in time_cols), default=0)
    file_tag = f"{group_dir.name}_{max_time}h"
    blues = plt.get_cmap("Blues")
    count = max(1, len(time_cols))
    time_colors = {
        time_h: blues(0.35 + 0.55 * (idx / max(1, count - 1)))
        for idx, (time_h, _) in enumerate(time_cols)
    }
    c_main = blues(0.78)

    fig, axis = plt.subplots(figsize=(10, 6))
    for time_h, column in time_cols:
        axis.plot(
            baseline["wavelength_nm"],
            baseline[column],
            label=f"{time_h}h",
            linewidth=1.2,
            color=time_colors[time_h],
        )
    axis.set_title(f"{group_dir.name} | Baseline-Corrected Absorbance vs Wavelength")
    axis.set_xlabel("Wavelength (nm)")
    axis.set_ylabel("Absorbance (a.u.)")
    axis.set_xlim(left=290.0)
    axis.grid(alpha=0.25)
    axis.legend(ncol=4, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / f"abs_spectra_overlay_{file_tag}.png", dpi=dpi)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    time_series = analysis["time_h"]

    axes[0, 0].plot(time_series, analysis["peak_wavelength_nm"], marker="o", color=c_main)
    axes[0, 0].set_title("Peak Wavelength")
    axes[0, 0].set_xlabel("Time (h)")
    axes[0, 0].set_ylabel("nm")
    axes[0, 0].grid(alpha=0.25)

    axes[0, 1].plot(time_series, analysis["peak_absorbance"], marker="o", color=c_main)
    axes[0, 1].set_title("Peak Absorbance")
    axes[0, 1].set_xlabel("Time (h)")
    axes[0, 1].set_ylabel("Abs")
    axes[0, 1].grid(alpha=0.25)

    axes[1, 0].plot(time_series, analysis["spectral_overlap_percent"], marker="o", color=c_main)
    axes[1, 0].set_title("Spectral Overlap")
    axes[1, 0].set_xlabel("Time (h)")
    axes[1, 0].set_ylabel("%")
    axes[1, 0].grid(alpha=0.25)

    axes[1, 1].plot(time_series, analysis["spectral_decay_mag"], marker="o", color=c_main)
    axes[1, 1].set_title("Spectral Decay")
    axes[1, 1].set_xlabel("Time (h)")
    axes[1, 1].set_ylabel("Index")
    axes[1, 1].grid(alpha=0.25)
    t80_values = analysis["t80_h"].dropna()
    t80_text = f"T80: {t80_values.iloc[0]:.2f} hr" if not t80_values.empty else "T80: N/A"
    axes[1, 1].text(
        0.97,
        0.05,
        t80_text,
        transform=axes[1, 1].transAxes,
        va="bottom",
        ha="right",
        fontsize=9,
        color=blues(0.85),
    )

    fig.suptitle(f"{group_dir.name} | Analysis Summary")
    fig.tight_layout()
    fig.savefig(fig_dir / f"analysis_summary_{file_tag}.png", dpi=dpi)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 5))
    x_values = decay["time_h"]
    mag_values = decay["decay_index_mag"]
    positive_values = decay["decay_index_positive"]
    negative_values = decay["decay_index_negative_abs"]

    axis.fill_between(x_values, 0.0, positive_values, color=blues(0.45), alpha=0.45, label="positive")
    axis.fill_between(
        x_values,
        positive_values,
        positive_values + negative_values,
        color="#d95f5f",
        alpha=0.35,
        label="negative",
    )
    axis.plot(x_values, mag_values, marker="o", label="mag", color=c_main, linewidth=1.5)
    axis.set_title(f"{group_dir.name} | Spectral Decay")
    axis.set_xlabel("Time (h)")
    axis.set_ylabel("Index")
    axis.grid(alpha=0.25)
    t80_decay_values = decay["t80_h"].dropna()
    t80_decay_text = (
        f"T80: {t80_decay_values.iloc[0]:.2f} hr" if not t80_decay_values.empty else "T80: N/A"
    )
    axis.text(
        0.93,
        0.05,
        t80_decay_text,
        transform=axis.transAxes,
        va="bottom",
        ha="right",
        fontsize=9,
        color=blues(0.85),
    )
    axis.legend(frameon=False, loc="lower right", bbox_to_anchor=(0.93, 0.13), borderaxespad=0.0, fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / f"spectral_decay_{file_tag}.png", dpi=dpi)
    plt.close(fig)

    if time_cols:
        t0_ref_col = time_cols[0][1]
        for time_h, column in time_cols:
            if time_h == 0:
                t0_ref_col = column
                break

        fig, axis = plt.subplots(figsize=(10, 6))
        for time_h, column in time_cols:
            delta = baseline[column] - baseline[t0_ref_col]
            axis.plot(
                baseline["wavelength_nm"],
                delta,
                label=f"{time_h}h",
                linewidth=1.2,
                color=time_colors[time_h],
            )
        axis.axhline(0.0, color=blues(0.25), linewidth=1.0, linestyle="--")
        axis.set_title(f"{group_dir.name} | Difference-to-t0 Overlay")
        axis.set_xlabel("Wavelength (nm)")
        axis.set_ylabel("Delta Absorbance (A(t)-A(t0))")
        axis.set_xlim(left=290.0)
        axis.grid(alpha=0.25)
        axis.legend(ncol=4, fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(fig_dir / f"deltaA_overlay_{file_tag}.png", dpi=dpi)
        plt.close(fig)


def plot_processed_dir(processed_dir: Path, group: Optional[str] = None, dpi: int = 160) -> int:
    if group:
        group_dir = processed_dir / group
        if not group_dir.exists():
            raise FileNotFoundError(f"Group not found: {group_dir}")
        plot_group(group_dir, dpi=dpi)
        return 1

    count = 0
    for group_dir in sorted(processed_dir.iterdir()):
        if not group_dir.is_dir():
            continue
        plot_group(group_dir, dpi=dpi)
        count += 1
    return count
