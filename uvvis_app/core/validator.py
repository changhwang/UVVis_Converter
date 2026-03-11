from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List

from .models import (
    FILE_KIND_IGNORE,
    FILE_KIND_SAMPLE,
    RunManifest,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ValidationIssue,
)


def _expected_converted_path(manifest: RunManifest, source_path: Path) -> Path:
    return manifest.layout.converted_dir / f"{source_path.stem}.csv"


def validate_manifest(manifest: RunManifest, mode: str = "run") -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    if mode == "convert":
        convertible = [
            entry for entry in manifest.files if entry.kind != FILE_KIND_IGNORE
        ]
        if not convertible and not manifest.effective_blank_file:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="no_inputs",
                    message="Select at least one file or blank to convert.",
                )
            )
        return issues

    if mode == "figures":
        if not manifest.processed_dir.exists():
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="processed_missing",
                    message=f"Processed directory does not exist: {manifest.processed_dir}",
                    file_path=manifest.processed_dir,
                )
            )
        return issues

    blank_file = manifest.effective_blank_file
    if not blank_file:
        if manifest.options.assume_zero_blank:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_WARNING,
                    code="blank_assumed_zero",
                    message=(
                        "No blank file selected. Proceeding with assumed zero absorbance "
                        "for all wavelengths."
                    ),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="blank_missing",
                    message="Select exactly one blank file before running.",
                )
            )
    elif not Path(blank_file).exists():
        issues.append(
            ValidationIssue(
                severity=SEVERITY_ERROR,
                code="blank_not_found",
                message=f"Blank file does not exist: {blank_file}",
                file_path=Path(blank_file),
            )
        )

    if not manifest.reference_file.exists():
        issues.append(
            ValidationIssue(
                severity=SEVERITY_ERROR,
                code="reference_missing",
                message=f"AM1.5 reference file does not exist: {manifest.reference_file}",
                file_path=manifest.reference_file,
            )
        )

    selected_samples = manifest.selected_samples()
    if not selected_samples:
        issues.append(
            ValidationIssue(
                severity=SEVERITY_ERROR,
                code="no_samples",
                message="Select at least one sample file to process.",
            )
        )

    seen_keys = Counter()
    for entry in selected_samples:
        if not entry.path.exists():
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="missing_file",
                    message=f"Selected file does not exist: {entry.path}",
                    file_path=entry.path,
                )
            )
        if entry.kind != FILE_KIND_SAMPLE:
            continue
        if not entry.group_key:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="group_missing",
                    message=f"Group is missing for {entry.filename}",
                    file_path=entry.path,
                )
            )
        if entry.time_h is None:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="time_missing",
                    message=f"Time (h) is missing for {entry.filename}",
                    file_path=entry.path,
                )
            )
        if entry.group_key and entry.time_h is not None:
            seen_keys[(entry.group_key, entry.time_h)] += 1
        if entry.confidence in {"low", "none"}:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_WARNING,
                    code="low_confidence",
                    message=f"Auto parse confidence is {entry.confidence} for {entry.filename}.",
                    file_path=entry.path,
                )
            )
        if mode == "process" or (mode == "run" and manifest.options.skip_convert):
            if entry.path.suffix.lower() == ".dsw":
                expected_csv = _expected_converted_path(manifest, entry.path)
                if not expected_csv.exists():
                    issues.append(
                        ValidationIssue(
                            severity=SEVERITY_ERROR,
                            code="converted_missing",
                            message=(
                                "Process Only requires an existing converted CSV for "
                                f"{entry.filename}: expected {expected_csv.name}"
                            ),
                            file_path=expected_csv,
                        )
                    )

    if blank_file and (mode == "process" or (mode == "run" and manifest.options.skip_convert)):
        blank_path = Path(blank_file)
        if blank_path.suffix.lower() == ".dsw":
            expected_blank_csv = _expected_converted_path(manifest, blank_path)
            if not expected_blank_csv.exists():
                issues.append(
                    ValidationIssue(
                        severity=SEVERITY_ERROR,
                        code="blank_converted_missing",
                        message=(
                            "Process Only requires an existing converted CSV for the blank "
                            f"file: expected {expected_blank_csv.name}"
                        ),
                        file_path=expected_blank_csv,
                    )
                )

    for (group_key, time_h), count in seen_keys.items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="duplicate_group_time",
                    message=f"{group_key} has {count} files mapped to {time_h}h.",
                )
            )

    group_times = {}
    for entry in selected_samples:
        group_times.setdefault(entry.group_key, []).append(entry.time_h)
    for group_key, times in group_times.items():
        valid_times = [time for time in times if time is not None]
        if valid_times and 0 not in valid_times:
            issues.append(
                ValidationIssue(
                    severity=SEVERITY_WARNING,
                    code="missing_t0",
                    message=f"{group_key} does not include a 0h reference point.",
                )
            )

    ignored_count = sum(
        1 for entry in manifest.files if entry.kind != FILE_KIND_SAMPLE or not entry.enabled
    )
    if ignored_count:
        issues.append(
            ValidationIssue(
                severity=SEVERITY_INFO,
                code="ignored_files",
                message=f"{ignored_count} files are excluded from the current run.",
            )
        )

    if manifest.external_blank_file:
        issues.append(
            ValidationIssue(
                severity=SEVERITY_INFO,
                code="external_blank",
                message=f"Using external blank file: {manifest.external_blank_file}",
                file_path=manifest.external_blank_file,
            )
        )

    return issues
