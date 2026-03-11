import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate figures from processed UV-Vis outputs.")
    parser.add_argument("--processed-dir", default="data/Tiara_021126_127/processed")
    parser.add_argument("--group", default=None, help="Optional group name, e.g., TT-127-1")
    parser.add_argument("--dpi", type=int, default=160)
    args = parser.parse_args()

    processed_dir = Path(args.processed_dir)
    if not processed_dir.exists():
        raise SystemExit(f"Processed directory not found: {processed_dir}")

    try:
        from uvvis_app.core.plotting import plot_processed_dir
    except ImportError as exc:
        raise SystemExit(
            "matplotlib and pandas are required. Install requirements first, then rerun.\n"
            f"Import error: {exc}"
        )

    count = plot_processed_dir(processed_dir=processed_dir, group=args.group, dpi=args.dpi)
    if args.group:
        print(f"Generated figures for {args.group}")
        return
    print(f"Generated figures for {count} groups.")


if __name__ == "__main__":
    main()
