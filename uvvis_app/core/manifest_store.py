from __future__ import annotations

import json
from pathlib import Path

from .models import RunManifest


def save_manifest(manifest: RunManifest, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as handle:
        json.dump(manifest.to_dict(), handle, indent=2)


def load_manifest(source_path: Path) -> RunManifest:
    with open(source_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return RunManifest.from_dict(payload)
