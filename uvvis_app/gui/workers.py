from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from uvvis_app.core.pipeline import convert_manifest_inputs, run_manifest


class RunWorker(QObject):
    progress = Signal(str, int)
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, manifest, mode: str) -> None:
        super().__init__()
        self.manifest = manifest
        self.mode = mode

    @Slot()
    def run(self) -> None:
        try:
            if self.mode == "convert":
                self.log.emit(f"Converting spectra into {self.manifest.layout.converted_dir}")
                output_dir = convert_manifest_inputs(
                    manifest=self.manifest,
                    logger=self.log.emit,
                    progress=self.progress.emit,
                )
                self.finished.emit(str(output_dir))
                return

            if self.mode == "figures":
                from uvvis_app.core.plotting import plot_processed_dir

                self.log.emit(f"Generating figures in {self.manifest.processed_dir}")
                plot_processed_dir(
                    processed_dir=self.manifest.processed_dir,
                    dpi=self.manifest.options.dpi,
                )
                self.progress.emit("Figure generation complete", 100)
                self.finished.emit(str(self.manifest.processed_dir))
                return

            output_dir = run_manifest(
                manifest=self.manifest,
                logger=self.log.emit,
                progress=self.progress.emit,
            )
            self.finished.emit(str(output_dir))
        except Exception:
            self.failed.emit(traceback.format_exc())
