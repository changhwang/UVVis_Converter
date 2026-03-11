from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


FILE_KIND_SAMPLE = "sample"
FILE_KIND_BLANK = "blank"
FILE_KIND_IGNORE = "ignore"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_NONE = "none"

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass
class RunOptions:
    min_wavelength_nm: float = 290.0
    peak_min_nm: float = 290.0
    peak_max_nm: float = 800.0
    decay_threshold: float = 0.01
    skip_convert: bool = False
    generate_figures: bool = True
    dpi: int = 160
    assume_zero_blank: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "RunOptions":
        if not payload:
            return cls()
        return cls(**payload)


@dataclass
class DatasetLayout:
    dataset_root: Path
    raw_dir: Path
    converted_dir: Path
    processed_root: Path

    def to_dict(self) -> Dict[str, str]:
        return {
            "dataset_root": str(self.dataset_root),
            "raw_dir": str(self.raw_dir),
            "converted_dir": str(self.converted_dir),
            "processed_root": str(self.processed_root),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, str]) -> "DatasetLayout":
        return cls(
            dataset_root=Path(payload["dataset_root"]),
            raw_dir=Path(payload["raw_dir"]),
            converted_dir=Path(payload["converted_dir"]),
            processed_root=Path(payload["processed_root"]),
        )


@dataclass
class FileEntry:
    path: Path
    enabled: bool = True
    kind: str = FILE_KIND_SAMPLE
    auto_kind: str = FILE_KIND_SAMPLE
    group_key: str = ""
    time_h: Optional[int] = None
    sample_no: str = ""
    confidence: str = CONFIDENCE_NONE
    status: str = ""
    note: str = ""
    source_parse: str = "auto"

    @property
    def filename(self) -> str:
        return self.path.name

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FileEntry":
        return cls(
            path=Path(payload["path"]),
            enabled=payload.get("enabled", True),
            kind=payload.get("kind", FILE_KIND_SAMPLE),
            auto_kind=payload.get("auto_kind", payload.get("kind", FILE_KIND_SAMPLE)),
            group_key=payload.get("group_key", ""),
            time_h=payload.get("time_h"),
            sample_no=payload.get("sample_no", ""),
            confidence=payload.get("confidence", CONFIDENCE_NONE),
            status=payload.get("status", ""),
            note=payload.get("note", ""),
            source_parse=payload.get("source_parse", "auto"),
        )


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str
    file_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "file_path": str(self.file_path) if self.file_path else None,
        }


@dataclass
class RunManifest:
    layout: DatasetLayout
    reference_file: Path
    blank_file: Optional[Path] = None
    external_blank_file: Optional[Path] = None
    run_label: str = ""
    options: RunOptions = field(default_factory=RunOptions)
    files: List[FileEntry] = field(default_factory=list)

    @property
    def processed_dir(self) -> Path:
        if self.run_label:
            return self.layout.processed_root / self.run_label
        return self.layout.processed_root

    @property
    def effective_blank_file(self) -> Optional[Path]:
        return self.external_blank_file or self.blank_file

    def selected_samples(self) -> List[FileEntry]:
        return [
            entry
            for entry in self.files
            if entry.kind == FILE_KIND_SAMPLE and entry.enabled
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout": self.layout.to_dict(),
            "reference_file": str(self.reference_file),
            "blank_file": str(self.blank_file) if self.blank_file else None,
            "external_blank_file": (
                str(self.external_blank_file) if self.external_blank_file else None
            ),
            "run_label": self.run_label,
            "options": self.options.to_dict(),
            "files": [entry.to_dict() for entry in self.files],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RunManifest":
        return cls(
            layout=DatasetLayout.from_dict(payload["layout"]),
            reference_file=Path(payload["reference_file"]),
            blank_file=Path(payload["blank_file"]) if payload.get("blank_file") else None,
            external_blank_file=(
                Path(payload["external_blank_file"])
                if payload.get("external_blank_file")
                else None
            ),
            run_label=payload.get("run_label", ""),
            options=RunOptions.from_dict(payload.get("options")),
            files=[FileEntry.from_dict(item) for item in payload.get("files", [])],
        )


@dataclass
class ScanResult:
    layout: DatasetLayout
    files: List[FileEntry]
    blank_candidates: List[Path]
    reference_file: Path

    @property
    def raw_count(self) -> int:
        return len(self.files)

    @property
    def selected_count(self) -> int:
        return sum(
            1
            for entry in self.files
            if entry.kind == FILE_KIND_SAMPLE and entry.enabled
        )

    def build_manifest(
        self,
        blank_file: Optional[Path],
        external_blank_file: Optional[Path],
        run_label: str,
        options: Optional[RunOptions] = None,
    ) -> RunManifest:
        return RunManifest(
            layout=self.layout,
            reference_file=self.reference_file,
            blank_file=blank_file,
            external_blank_file=external_blank_file,
            run_label=run_label,
            options=options or RunOptions(),
            files=self.files,
        )
