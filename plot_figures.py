import argparse
from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt



def parse_time_col(col: str):
    m = re.fullmatch(r"t(\d+)h", col)
    if not m:
        return None
    return int(m.group(1))


def plot_group(group_dir: Path, dpi: int = 160) -> None:

    baseline_path = group_dir / "baseline_corrected.csv"
    analysis_path = group_dir / "analysis.csv"
    decay_path = group_dir / "spectral_decay.csv"

    if not baseline_path.exists() or not analysis_path.exists() or not decay_path.exists():
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
    blues = plt.get_cmap("Blues")
    n = max(1, len(time_cols))
    time_colors = {
        t: blues(0.35 + 0.55 * (i / max(1, n - 1)))
        for i, (t, _) in enumerate(time_cols)
    }
    c_main = blues(0.78)
    c_alt = blues(0.55)

    # 1) True absorbance overlay (blank-corrected)
    fig, ax = plt.subplots(figsize=(10, 6))
    for t, c in time_cols:
        ax.plot(
            baseline["wavelength_nm"],
            baseline[c],
            label=f"t{t}h",
            linewidth=1.2,
            color=time_colors[t],
        )
    ax.set_title(f"{group_dir.name} | True Absorbance vs Wavelength (blank-corrected)")
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Absorbance (a.u.)")
    ax.set_xlim(left=290.0)
    ax.grid(alpha=0.25)
    ax.legend(ncol=4, fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "true_absorbance_overlay.png", dpi=dpi)
    fig.savefig(fig_dir / "abs_spectra_decay.png", dpi=dpi)
    plt.close(fig)

    # 2) Analysis summary (2x2)
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

    axes[1, 0].plot(t, analysis["total_absorbed_percent"], marker="o", label="Total absorbed %", color=c_main)
    axes[1, 0].plot(t, analysis["delta_vs_t0_percent"], marker="o", label="Delta vs t0 %", color=c_alt)
    axes[1, 0].set_title("Fresh Metrics")
    axes[1, 0].set_xlabel("Time (h)")
    axes[1, 0].set_ylabel("%")
    axes[1, 0].grid(alpha=0.25)
    axes[1, 0].legend(frameon=False, fontsize=8)

    axes[1, 1].plot(t, analysis["spectral_decay_mag"], marker="o", label="Decay mag", color=c_main)
    axes[1, 1].plot(t, analysis["spectral_decay_signed"], marker="o", label="Decay signed", color=c_alt)
    axes[1, 1].set_title("Spectral Decay Metrics")
    axes[1, 1].set_xlabel("Time (h)")
    axes[1, 1].set_ylabel("Index")
    axes[1, 1].grid(alpha=0.25)
    axes[1, 1].legend(frameon=False, fontsize=8)

    fig.suptitle(f"{group_dir.name} | Analysis Summary")
    fig.tight_layout()
    fig.savefig(fig_dir / "analysis_summary.png", dpi=dpi)
    plt.close(fig)

    # 3) Spectral decay index only
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(decay["time_h"], decay["decay_index_mag"], marker="o", label="decay_index_mag", color=c_main)
    ax.plot(decay["time_h"], decay["decay_index_signed"], marker="o", label="decay_index_signed", color=c_alt)
    ax.set_title(f"{group_dir.name} | Spectral Decay")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Index")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "spectral_decay.png", dpi=dpi)
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
