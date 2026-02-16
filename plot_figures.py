import argparse
from pathlib import Path
import re
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt



def parse_time_col(col: str):
    m = re.fullmatch(r"t(\d+)h", col)
    if not m:
        return None
    return int(m.group(1))


def find_latest_csv(group_dir: Path, prefix: str) -> Optional[Path]:
    candidates = sorted(group_dir.glob(f"{prefix}_*.csv"))
    if candidates:
        return candidates[-1]
    return None


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
    for c in baseline.columns:
        t = parse_time_col(c)
        if t is not None:
            time_cols.append((t, c))
    time_cols.sort(key=lambda x: x[0])
    max_time = max((t for t, _ in time_cols), default=0)
    file_tag = f"{group_dir.name}_{max_time}h"
    blues = plt.get_cmap("Blues")
    n = max(1, len(time_cols))
    time_colors = {
        t: blues(0.35 + 0.55 * (i / max(1, n - 1)))
        for i, (t, _) in enumerate(time_cols)
    }
    c_main = blues(0.78)
    c_alt = blues(0.55)

    # 1) Baseline-corrected absorbance overlay
    fig, ax = plt.subplots(figsize=(10, 6))
    for t, c in time_cols:
        ax.plot(
            baseline["wavelength_nm"],
            baseline[c],
            label=f"{t}h",
            linewidth=1.2,
            color=time_colors[t],
        )
    ax.set_title(f"{group_dir.name} | Baseline-Corrected Absorbance vs Wavelength")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Absorbance (a.u.)")
    ax.set_xlim(left=290.0)
    ax.grid(alpha=0.25)
    ax.legend(ncol=4, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / f"abs_spectra_overlay_{file_tag}.png", dpi=dpi)
    plt.close(fig)

    # 2) Analysis summary panel (2x2)
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    t = analysis["time_h"]

    axes[0, 0].plot(t, analysis["peak_wavelength_nm"], marker="o", color=c_main)
    axes[0, 0].set_title("Peak Wavelength")
    axes[0, 0].set_xlabel("Time (h)")
    axes[0, 0].set_ylabel("nm")
    axes[0, 0].grid(alpha=0.25)

    axes[0, 1].plot(t, analysis["peak_absorbance"], marker="o", color=c_main)
    axes[0, 1].set_title("Peak Absorbance")
    axes[0, 1].set_xlabel("Time (h)")
    axes[0, 1].set_ylabel("Abs")
    axes[0, 1].grid(alpha=0.25)

    overlap_pct = analysis["spectral_overlap_percent"]
    axes[1, 0].plot(t, overlap_pct, marker="o", color=c_main)
    axes[1, 0].set_title("Spectral Overlap")
    axes[1, 0].set_xlabel("Time (h)")
    axes[1, 0].set_ylabel("%")
    axes[1, 0].grid(alpha=0.25)

    decay_mag_summary = analysis["spectral_decay_mag"]
    axes[1, 1].plot(t, decay_mag_summary, marker="o", color=c_main)
    axes[1, 1].set_title("Spectral Decay")
    axes[1, 1].set_xlabel("Time (h)")
    axes[1, 1].set_ylabel("Index")
    axes[1, 1].grid(alpha=0.25)
    t80_vals = analysis["t80_h"].dropna()
    t80_txt = f"T80: {t80_vals.iloc[0]:.2f} hr" if not t80_vals.empty else "T80: N/A"
    axes[1, 1].text(
        0.97,
        0.05,
        t80_txt,
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

    # 3) Spectral decay detail (mag with positive/negative components)
    fig, ax = plt.subplots(figsize=(8, 5))
    x = decay["time_h"]
    mag = decay["decay_index_mag"]
    pos = decay["decay_index_positive"]
    neg = decay["decay_index_negative_abs"]

    ax.fill_between(x, 0.0, pos, color=blues(0.45), alpha=0.45, label="positive")
    ax.fill_between(x, pos, pos + neg, color="#d95f5f", alpha=0.35, label="negative")
    ax.plot(x, mag, marker="o", label="mag", color=c_main, linewidth=1.5)
    ax.set_title(f"{group_dir.name} | Spectral Decay")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Index")
    ax.grid(alpha=0.25)
    t80_vals_decay = decay["t80_h"].dropna()
    t80_txt_decay = f"T80: {t80_vals_decay.iloc[0]:.2f} hr" if not t80_vals_decay.empty else "T80: N/A"
    ax.text(
        0.93,
        0.05,
        t80_txt_decay,
        transform=ax.transAxes,
        va="bottom",
        ha="right",
        fontsize=9,
        color=blues(0.85),
    )
    ax.legend(
        frameon=False,
        loc="lower right",
        bbox_to_anchor=(0.93, 0.13),
        borderaxespad=0.0,
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(fig_dir / f"spectral_decay_{file_tag}.png", dpi=dpi)
    plt.close(fig)

    # 4) Signed delta overlay: delta A = A(t) - A(t0)
    if time_cols:
        first_time, first_col = time_cols[0]
        t0_ref_col = first_col
        for tt, cc in time_cols:
            if tt == 0:
                t0_ref_col = cc
                break

        fig, ax = plt.subplots(figsize=(10, 6))
        for tt, cc in time_cols:
            delta = baseline[cc] - baseline[t0_ref_col]
            ax.plot(
                baseline["wavelength_nm"],
                delta,
                label=f"{tt}h",
                linewidth=1.2,
                color=time_colors[tt],
            )
        ax.axhline(0.0, color=blues(0.25), linewidth=1.0, linestyle="--")
        ax.set_title(f"{group_dir.name} | Difference-to-t0 Overlay")
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Delta Absorbance (A(t)-A(t0))")
        ax.set_xlim(left=290.0)
        ax.grid(alpha=0.25)
        ax.legend(ncol=4, fontsize=8, frameon=False)
        fig.tight_layout()
        fig.savefig(fig_dir / f"deltaA_overlay_{file_tag}.png", dpi=dpi)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate figures from processed UV-Vis outputs.")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--group", default=None, help="Optional group name, e.g., TT-127-1")
    parser.add_argument("--dpi", type=int, default=160)
    args = parser.parse_args()

    try:
        import matplotlib  # noqa: F401
    except Exception as e:
        raise SystemExit(
            "matplotlib is required. Install it in venv first, then rerun.\n"
            f"Import error: {e}"
        )

    processed_dir = Path(args.processed_dir)
    if not processed_dir.exists():
        raise SystemExit(f"Processed directory not found: {processed_dir}")

    if args.group:
        group_dir = processed_dir / args.group
        if not group_dir.exists():
            raise SystemExit(f"Group not found: {group_dir}")
        plot_group(group_dir, dpi=args.dpi)
        print(f"Generated figures for {group_dir.name}")
        return

    count = 0
    for group_dir in sorted(processed_dir.iterdir()):
        if not group_dir.is_dir():
            continue
        plot_group(group_dir, dpi=args.dpi)
        count += 1
    print(f"Generated figures for {count} groups.")


if __name__ == "__main__":
    main()
