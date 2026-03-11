import argparse
from pathlib import Path

from uvvis_app.core.models import FILE_KIND_BLANK, RunOptions
from uvvis_app.core.pipeline import run_manifest
from uvvis_app.core.scanner import pick_default_blank_file, scan_dataset
from uvvis_app.core.validator import validate_manifest


DEFAULT_DATASET_DIR = Path("data/Tiara_021126_127")
DEFAULT_REFERENCE = Path("reference") / "am15g_spectrum.csv"


def _apply_blank_choice(scan_result, blank_file: Path | None) -> Path | None:
    chosen = blank_file or pick_default_blank_file(scan_result)
    if chosen is None:
        return None

    resolved = chosen.resolve()
    for entry in scan_result.files:
        if entry.path.resolve() == resolved:
            entry.kind = FILE_KIND_BLANK
            entry.enabled = False
            entry.status = "Selected blank"
    return resolved


def _print_issues(issues) -> None:
    if not issues:
        return
    for issue in issues:
        print(f"[{issue.severity}] {issue.message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="UV-Vis DSW to grouped analysis pipeline")
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--converted-dir", default=None)
    parser.add_argument("--processed-dir", default=None)
    parser.add_argument("--am15-path", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--blank-file", default=None)
    parser.add_argument("--run-label", default="")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--min-wavelength-nm", type=float, default=290.0)
    parser.add_argument("--peak-min-nm", type=float, default=290.0)
    parser.add_argument("--peak-max-nm", type=float, default=800.0)
    parser.add_argument("--dpi", type=int, default=160)
    args = parser.parse_args()

    scan_result = scan_dataset(
        dataset_path=Path(args.dataset_dir),
        reference_file=Path(args.am15_path),
    )

    if args.raw_dir:
        scan_result.layout.raw_dir = Path(args.raw_dir).resolve()
    if args.converted_dir:
        scan_result.layout.converted_dir = Path(args.converted_dir).resolve()
    if args.processed_dir:
        scan_result.layout.processed_root = Path(args.processed_dir).resolve()

    blank_file = _apply_blank_choice(
        scan_result=scan_result,
        blank_file=Path(args.blank_file).resolve() if args.blank_file else None,
    )

    manifest = scan_result.build_manifest(
        blank_file=blank_file,
        external_blank_file=None,
        run_label=args.run_label,
        options=RunOptions(
            min_wavelength_nm=args.min_wavelength_nm,
            peak_min_nm=args.peak_min_nm,
            peak_max_nm=args.peak_max_nm,
            skip_convert=args.skip_convert,
            generate_figures=not args.no_figures,
            dpi=args.dpi,
        ),
    )

    issues = validate_manifest(manifest)
    _print_issues(issues)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise SystemExit("Validation failed. Resolve the errors above and rerun.")

    processed_dir = run_manifest(manifest, logger=print)
    print(f"Outputs written to {processed_dir}")


if __name__ == "__main__":
    main()
