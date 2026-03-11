from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from uvvis_app.resources import bundled_path

from .models import (
    CONFIDENCE_NONE,
    FILE_KIND_BLANK,
    FILE_KIND_IGNORE,
    FILE_KIND_SAMPLE,
    DatasetLayout,
    FileEntry,
    RunManifest,
    ScanResult,
)
from .name_parser import is_blank_candidate, parse_measurement_name, score_blank_candidate


SUPPORTED_SUFFIXES = {".dsw", ".csv"}


def detect_dataset_layout(dataset_path: Path) -> DatasetLayout:
    path = dataset_path.resolve()
    if path.name.lower() == "raw":
        dataset_root = path.parent
        raw_dir = path
    elif (path / "raw").is_dir():
        dataset_root = path
        raw_dir = path / "raw"
    else:
        dataset_root = path
        raw_dir = path

    return DatasetLayout(
        dataset_root=dataset_root,
        raw_dir=raw_dir,
        converted_dir=dataset_root / "converted",
        processed_root=dataset_root / "processed",
    )


def default_reference_file(dataset_root: Path) -> Path:
    repo_reference = bundled_path("reference", "am15g_spectrum.csv")
    dataset_reference = dataset_root / "reference" / "am15g_spectrum.csv"
    if dataset_reference.exists():
        return dataset_reference
    return repo_reference


def _find_files(raw_dir: Path) -> List[Path]:
    if not raw_dir.exists():
        return []
    files = [
        path
        for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    return sorted(files, key=lambda item: item.name.lower())


def _entry_from_path(path: Path) -> FileEntry:
    stem = path.stem
    if is_blank_candidate(stem):
        return FileEntry(
            path=path,
            enabled=False,
            kind=FILE_KIND_IGNORE,
            auto_kind=FILE_KIND_BLANK,
            confidence=CONFIDENCE_NONE,
            status="Blank candidate",
            note="Detected by filename keyword.",
        )

    parsed = parse_measurement_name(stem)
    enabled = True
    status = "OK" if parsed.ok else "Needs mapping"
    return FileEntry(
        path=path,
        enabled=enabled,
        kind=FILE_KIND_SAMPLE,
        auto_kind=FILE_KIND_SAMPLE,
        group_key=parsed.group_key,
        time_h=parsed.time_h,
        sample_no=parsed.sample_no,
        confidence=parsed.confidence,
        status=status,
        note=parsed.note,
    )


def _default_blank_candidate(paths: List[Path]) -> Optional[Path]:
    if not paths:
        return None
    ranked = sorted(paths, key=lambda item: (-score_blank_candidate(item.stem), item.name.lower()))
    return ranked[0]


def scan_dataset(
    dataset_path: Path,
    reference_file: Optional[Path] = None,
    previous_manifest: Optional[RunManifest] = None,
) -> ScanResult:
    layout = detect_dataset_layout(dataset_path)
    files = [_entry_from_path(path) for path in _find_files(layout.raw_dir)]
    blank_candidates = [entry.path for entry in files if entry.auto_kind == FILE_KIND_BLANK]

    if previous_manifest:
        previous_by_path = {entry.path.resolve(): entry for entry in previous_manifest.files}
        for entry in files:
            previous = previous_by_path.get(entry.path.resolve())
            if previous is None:
                continue
            entry.enabled = previous.enabled
            entry.kind = previous.kind
            entry.group_key = previous.group_key
            entry.time_h = previous.time_h
            entry.sample_no = previous.sample_no
            entry.note = previous.note
            entry.status = previous.status
            entry.confidence = previous.confidence
            entry.source_parse = previous.source_parse

    return ScanResult(
        layout=layout,
        files=files,
        blank_candidates=blank_candidates,
        reference_file=(reference_file or default_reference_file(layout.dataset_root)).resolve(),
    )


def pick_default_blank_file(scan_result: ScanResult) -> Optional[Path]:
    return _default_blank_candidate(scan_result.blank_candidates)
