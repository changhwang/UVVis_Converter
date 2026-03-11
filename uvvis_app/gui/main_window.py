from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSignalBlocker, QThread, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from uvvis_app.resources import bundled_path
from uvvis_app.core.manifest_store import save_manifest
from uvvis_app.core.models import (
    FILE_KIND_BLANK,
    FILE_KIND_IGNORE,
    FILE_KIND_SAMPLE,
    RunManifest,
    RunOptions,
    ScanResult,
)
from uvvis_app.core.scanner import pick_default_blank_file, scan_dataset
from uvvis_app.core.validator import validate_manifest
from uvvis_app.gui.workers import RunWorker


TABLE_COLUMNS = [
    "Role",
    "Filename",
    "Detected",
    "Group Key",
    "Time (h)",
    "Sample",
    "Confidence",
    "Status",
    "Note",
    "Source",
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UV-Vis Converter")
        self.resize(1380, 900)

        self.scan_result: Optional[ScanResult] = None
        self.current_blank_file: Optional[Path] = None
        self.external_blank_file: Optional[Path] = None
        self.blank_is_external = False
        self.last_output_dir: Optional[Path] = None
        self.last_manifest_path: Optional[Path] = None
        self._visible_entries: List = []
        self._table_loading = False
        self._log_lines: List[str] = []
        self._thread: Optional[QThread] = None
        self._worker: Optional[RunWorker] = None

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        root_layout.addWidget(self._build_top_panel())
        self.tabs = QTabWidget()
        root_layout.addWidget(self.tabs, 1)

        self.files_tab = QWidget()
        self.validation_tab = QWidget()
        self.run_tab = QWidget()
        self.results_tab = QWidget()
        self.tabs.addTab(self.files_tab, "Files")
        self.tabs.addTab(self.validation_tab, "Validation")
        self.tabs.addTab(self.run_tab, "Run")
        self.tabs.addTab(self.results_tab, "Results")

        self._build_files_tab()
        self._build_validation_tab()
        self._build_run_tab()
        self._build_results_tab()
        self._refresh_summary()

    def _build_top_panel(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout(panel)

        self.dataset_edit = QLineEdit("")
        self.browse_dataset_button = QPushButton("Browse...")
        self.scan_button = QPushButton("Scan")
        self.rescan_button = QPushButton("Rescan")
        self.summary_label = QLabel("Select a dataset folder and scan.")

        self.run_label_edit = QLineEdit(self._default_run_label())
        self.reference_edit = QLineEdit(str(bundled_path("reference", "am15g_spectrum.csv")))
        self.browse_reference_button = QPushButton("Override...")

        self.blank_combo = QComboBox()
        self.blank_combo.setMinimumWidth(360)
        self.browse_blank_button = QPushButton("Browse...")
        self.blank_source_label = QLabel("Blank source: not selected")

        self.browse_dataset_button.clicked.connect(self._browse_dataset)
        self.scan_button.clicked.connect(self._scan_requested)
        self.rescan_button.clicked.connect(self._scan_requested)
        self.browse_blank_button.clicked.connect(self._browse_blank)
        self.browse_reference_button.clicked.connect(self._browse_reference)
        self.blank_combo.currentIndexChanged.connect(self._on_blank_selection_changed)

        layout.addWidget(QLabel("Dataset Folder"), 0, 0)
        layout.addWidget(self.dataset_edit, 0, 1)
        layout.addWidget(self.browse_dataset_button, 0, 2)
        layout.addWidget(self.scan_button, 0, 3)
        layout.addWidget(self.rescan_button, 0, 4)

        layout.addWidget(QLabel("Run Label"), 1, 0)
        layout.addWidget(self.run_label_edit, 1, 1)
        layout.addWidget(QLabel("Reference AM1.5"), 1, 2)
        layout.addWidget(self.reference_edit, 1, 3)
        layout.addWidget(self.browse_reference_button, 1, 4)

        layout.addWidget(QLabel("Selected Blank"), 2, 0)
        layout.addWidget(self.blank_combo, 2, 1)
        layout.addWidget(self.browse_blank_button, 2, 2)
        layout.addWidget(self.summary_label, 2, 3, 1, 2)
        layout.addWidget(self.blank_source_label, 3, 1, 1, 4)
        return panel

    def _build_files_tab(self) -> None:
        layout = QVBoxLayout(self.files_tab)

        filter_row = QHBoxLayout()
        self.only_selected_checkbox = QCheckBox("Only selected")
        self.only_issues_checkbox = QCheckBox("Only issues")
        self.only_selected_checkbox.toggled.connect(self._populate_file_table)
        self.only_issues_checkbox.toggled.connect(self._populate_file_table)
        self.exclude_invalid_button = QPushButton("Exclude Invalid Files")
        self.exclude_invalid_button.clicked.connect(self._exclude_invalid_files)
        filter_row.addWidget(self.only_selected_checkbox)
        filter_row.addWidget(self.only_issues_checkbox)
        filter_row.addWidget(self.exclude_invalid_button)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.files_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.files_table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.files_table.horizontalHeader().setStretchLastSection(True)
        self.files_table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.files_table, 1)

    def _build_validation_tab(self) -> None:
        layout = QVBoxLayout(self.validation_tab)
        self.validation_text = QPlainTextEdit()
        self.validation_text.setReadOnly(True)
        layout.addWidget(self.validation_text)

    def _build_run_tab(self) -> None:
        layout = QVBoxLayout(self.run_tab)

        options_box = QGroupBox("Run Options")
        options_layout = QGridLayout(options_box)

        self.generate_figures_checkbox = QCheckBox("Generate figures")
        self.generate_figures_checkbox.setChecked(True)
        self.generate_figures_checkbox.toggled.connect(self._refresh_summary)

        self.assume_zero_blank_checkbox = QCheckBox("Assume zero blank if none selected")
        self.assume_zero_blank_checkbox.setChecked(False)
        self.assume_zero_blank_checkbox.toggled.connect(self._refresh_summary)

        self.min_wavelength_spin = QDoubleSpinBox()
        self.min_wavelength_spin.setRange(0.0, 2000.0)
        self.min_wavelength_spin.setValue(290.0)
        self.min_wavelength_spin.valueChanged.connect(self._refresh_summary)

        self.peak_min_spin = QDoubleSpinBox()
        self.peak_min_spin.setRange(0.0, 2000.0)
        self.peak_min_spin.setValue(290.0)
        self.peak_min_spin.valueChanged.connect(self._refresh_summary)

        self.peak_max_spin = QDoubleSpinBox()
        self.peak_max_spin.setRange(0.0, 2000.0)
        self.peak_max_spin.setValue(800.0)
        self.peak_max_spin.valueChanged.connect(self._refresh_summary)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(160)
        self.dpi_spin.valueChanged.connect(self._refresh_summary)

        options_layout.addWidget(self.generate_figures_checkbox, 0, 0)
        options_layout.addWidget(QLabel("Min wavelength (nm)"), 0, 1)
        options_layout.addWidget(self.min_wavelength_spin, 0, 2)
        options_layout.addWidget(QLabel("DPI"), 0, 3)
        options_layout.addWidget(self.dpi_spin, 0, 4)
        options_layout.addWidget(self.assume_zero_blank_checkbox, 1, 0, 1, 2)
        options_layout.addWidget(QLabel("Peak min (nm)"), 1, 2)
        options_layout.addWidget(self.peak_min_spin, 1, 3)
        options_layout.addWidget(QLabel("Peak max (nm)"), 1, 4)
        options_layout.addWidget(self.peak_max_spin, 1, 5)

        layout.addWidget(options_box)

        button_row = QHBoxLayout()
        self.run_full_button = QPushButton("Run")
        self.run_convert_button = QPushButton("Convert Only")
        self.run_reprocess_button = QPushButton("Process Only")
        self.run_figures_button = QPushButton("Figures Only")
        self.run_full_button.clicked.connect(lambda: self._start_run(mode="run"))
        self.run_convert_button.clicked.connect(self._start_convert_only)
        self.run_reprocess_button.clicked.connect(lambda: self._start_run(mode="process"))
        self.run_figures_button.clicked.connect(self._start_figures_only)
        button_row.addWidget(self.run_full_button)
        button_row.addWidget(self.run_convert_button)
        button_row.addWidget(self.run_reprocess_button)
        button_row.addWidget(self.run_figures_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.run_log = QPlainTextEdit()
        self.run_log.setReadOnly(True)
        layout.addWidget(self.run_log, 1)

    def _build_results_tab(self) -> None:
        layout = QVBoxLayout(self.results_tab)

        self.results_label = QLabel("No run completed yet.")
        self.open_output_button = QPushButton("Open Output Folder")
        self.open_manifest_button = QPushButton("Open Manifest Folder")
        self.open_output_button.clicked.connect(self._open_last_output)
        self.open_manifest_button.clicked.connect(self._open_manifest_dir)

        row = QHBoxLayout()
        row.addWidget(self.open_output_button)
        row.addWidget(self.open_manifest_button)
        row.addStretch(1)

        layout.addWidget(self.results_label)
        layout.addLayout(row)
        layout.addStretch(1)

    def _default_run_label(self) -> str:
        return datetime.now().strftime("%Y-%m-%d_%H%M")

    def _default_role_for_entry(self, entry) -> str:
        if entry.auto_kind == FILE_KIND_BLANK:
            return FILE_KIND_IGNORE
        return FILE_KIND_SAMPLE

    def _set_entry_role(self, entry, role: str) -> None:
        entry.kind = role
        entry.enabled = role == FILE_KIND_SAMPLE

    def _find_entry_by_path(self, path: Optional[Path]):
        if not self.scan_result or path is None:
            return None
        resolved = path.resolve()
        for entry in self.scan_result.files:
            if entry.path.resolve() == resolved:
                return entry
        return None

    def _sync_blank_roles(self) -> None:
        if not self.scan_result:
            return

        selected_blank = self.current_blank_file.resolve() if self.current_blank_file else None
        for entry in self.scan_result.files:
            is_selected_internal_blank = bool(
                selected_blank
                and not self.blank_is_external
                and entry.path.resolve() == selected_blank
            )
            if is_selected_internal_blank:
                self._set_entry_role(entry, FILE_KIND_BLANK)
            elif entry.kind == FILE_KIND_BLANK:
                self._set_entry_role(entry, self._default_role_for_entry(entry))
            entry.status = self._entry_status(entry)

    def _set_internal_blank(self, path: Optional[Path]) -> None:
        self.blank_is_external = False
        self.current_blank_file = path.resolve() if path else None
        self._sync_blank_roles()
        self._populate_blank_combo()
        self._populate_file_table()
        self._refresh_summary()

    def _set_external_blank(self, path: Optional[Path]) -> None:
        self.external_blank_file = path.resolve() if path else None
        self.current_blank_file = self.external_blank_file
        self.blank_is_external = self.external_blank_file is not None
        self._sync_blank_roles()
        self._populate_blank_combo()
        self._populate_file_table()
        self._refresh_summary()

    def _browse_dataset(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Dataset Folder", self.dataset_edit.text())
        if folder:
            self.dataset_edit.setText(folder)

    def _browse_blank(self) -> None:
        start_dir = self.dataset_edit.text() or "."
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Blank File",
            start_dir,
            "Spectrum Files (*.DSW *.dsw *.csv);;All Files (*.*)",
        )
        if not file_path:
            return

        self._set_external_blank(Path(file_path))

    def _browse_reference(self) -> None:
        start_dir = str(Path(self.reference_edit.text()).parent)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select AM1.5 Reference File",
            start_dir,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if file_path:
            self.reference_edit.setText(file_path)
            self._refresh_summary()

    def _scan_requested(self) -> None:
        dataset_path = Path(self.dataset_edit.text().strip())
        if not dataset_path.exists():
            QMessageBox.warning(self, "Dataset Missing", f"Dataset folder does not exist:\n{dataset_path}")
            return

        previous_manifest = self._build_manifest() if self.scan_result else None
        scan_result = scan_dataset(
            dataset_path=dataset_path,
            reference_file=Path(self.reference_edit.text().strip()),
            previous_manifest=previous_manifest,
        )
        self.scan_result = scan_result
        self.reference_edit.setText(str(scan_result.reference_file))

        previous_blank = previous_manifest.effective_blank_file if previous_manifest else None
        if previous_blank and Path(previous_blank).exists():
            previous_blank = Path(previous_blank).resolve()
            candidate_paths = {path.resolve() for path in scan_result.blank_candidates}
            if previous_blank in candidate_paths:
                self.current_blank_file = previous_blank
                self.blank_is_external = False
            else:
                self.external_blank_file = previous_blank
                self.current_blank_file = previous_blank
                self.blank_is_external = True
        else:
            self.current_blank_file = pick_default_blank_file(scan_result)
            self.external_blank_file = None
            self.blank_is_external = False

        if not self.run_label_edit.text().strip():
            self.run_label_edit.setText(self._default_run_label())

        self._sync_blank_roles()
        self._populate_blank_combo()
        self._populate_file_table()
        self._refresh_summary()

    def _blank_combo_items(self):
        items = []
        if self.external_blank_file and self.external_blank_file.exists():
            items.append((f"[External] {self.external_blank_file.name}", self.external_blank_file, True))
        if self.scan_result:
            candidate_paths = {path.resolve() for path in self.scan_result.blank_candidates}
            if (
                self.current_blank_file
                and not self.blank_is_external
                and self.current_blank_file.resolve() not in candidate_paths
            ):
                items.append((f"[Selected] {self.current_blank_file.name}", self.current_blank_file, False))
            for path in self.scan_result.blank_candidates:
                items.append((path.name, path, False))
        return items

    def _populate_blank_combo(self) -> None:
        blocker = QSignalBlocker(self.blank_combo)
        self.blank_combo.clear()
        self.blank_combo.addItem("<No blank selected>", None)
        items = self._blank_combo_items()
        current_index = 0
        for index, (label, path, is_external) in enumerate(items, start=1):
            self.blank_combo.addItem(label, (str(path), is_external))
            if self.current_blank_file and path.resolve() == self.current_blank_file.resolve():
                current_index = index
        self.blank_combo.setCurrentIndex(current_index)
        del blocker

    def _on_blank_selection_changed(self) -> None:
        data = self.blank_combo.currentData()
        if not data:
            self.current_blank_file = None
            self.blank_is_external = False
            self._populate_file_table()
            self._refresh_summary()
            return

        path_str, is_external = data
        path = Path(path_str)
        if is_external:
            self._set_external_blank(path)
            return
        self._set_internal_blank(path)

    def _entry_status(self, entry) -> str:
        if entry.kind == FILE_KIND_BLANK:
            return "Selected blank"
        if entry.kind == FILE_KIND_IGNORE:
            if self.scan_result and entry.path in self.scan_result.blank_candidates:
                return "Blank candidate"
            return "Excluded"
        if entry.enabled:
            if entry.group_key and entry.time_h is not None:
                return "OK"
            return "Needs mapping"
        return "Excluded"

    def _entry_detected(self, entry) -> str:
        if self.scan_result and entry.path in self.scan_result.blank_candidates:
            return "blank candidate"
        return entry.path.suffix.lower().lstrip(".") or "file"

    def _entry_has_issue(self, entry) -> bool:
        if entry.kind in {FILE_KIND_BLANK, FILE_KIND_IGNORE}:
            return False
        if not entry.group_key or entry.time_h is None:
            return True
        if entry.confidence in {"low", "none"}:
            return True
        return False

    def _visible_file_entries(self) -> List:
        if not self.scan_result:
            return []
        entries = list(self.scan_result.files)
        if self.only_selected_checkbox.isChecked():
            entries = [
                entry
                for entry in entries
                if entry.kind in {FILE_KIND_SAMPLE, FILE_KIND_BLANK}
            ]
        if self.only_issues_checkbox.isChecked():
            entries = [entry for entry in entries if self._entry_has_issue(entry)]
        return entries

    def _populate_file_table(self) -> None:
        self._table_loading = True
        self._visible_entries = self._visible_file_entries()
        self.files_table.setRowCount(len(self._visible_entries))

        for row, entry in enumerate(self._visible_entries):
            self.files_table.setCellWidget(row, 0, self._make_role_combo(entry))
            self.files_table.setItem(row, 1, self._read_only_item(entry.filename))
            self.files_table.setItem(row, 2, self._read_only_item(self._entry_detected(entry)))
            editable = entry.kind != FILE_KIND_BLANK
            self.files_table.setItem(row, 3, self._editable_item(entry.group_key, enabled=editable))
            self.files_table.setItem(
                row,
                4,
                self._editable_item("" if entry.time_h is None else str(entry.time_h), enabled=editable),
            )
            self.files_table.setItem(row, 5, self._editable_item(entry.sample_no, enabled=editable))
            self.files_table.setItem(row, 6, self._read_only_item(entry.confidence))
            self.files_table.setItem(row, 7, self._read_only_item(self._entry_status(entry)))
            self.files_table.setItem(row, 8, self._editable_item(entry.note, enabled=True))
            self.files_table.setItem(row, 9, self._read_only_item(self._entry_source(entry)))

        self.files_table.resizeColumnsToContents()
        self._table_loading = False

    def _make_role_combo(self, entry) -> QComboBox:
        combo = QComboBox()
        combo.addItem("sample", FILE_KIND_SAMPLE)
        combo.addItem("blank", FILE_KIND_BLANK)
        combo.addItem("exclude", FILE_KIND_IGNORE)
        role_index = {
            FILE_KIND_SAMPLE: 0,
            FILE_KIND_BLANK: 1,
            FILE_KIND_IGNORE: 2,
        }.get(entry.kind, 0)
        combo.setCurrentIndex(role_index)
        combo.currentIndexChanged.connect(
            lambda _index, entry_ref=entry, combo_ref=combo: self._on_role_changed(entry_ref, combo_ref.currentData())
        )
        return combo

    def _entry_source(self, entry) -> str:
        if not self.scan_result:
            return str(entry.path)
        dataset_root = self.scan_result.layout.dataset_root.resolve()
        try:
            return str(entry.path.resolve().relative_to(dataset_root))
        except ValueError:
            return f"[External] {entry.path}"

    def _read_only_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        return item

    def _editable_item(self, text: str, enabled: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        flags = Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled
        if not enabled:
            flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        item.setFlags(flags)
        return item

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._table_loading:
            return
        row = item.row()
        col = item.column()
        if row >= len(self._visible_entries):
            return

        entry = self._visible_entries[row]
        if col == 3:
            entry.group_key = item.text().strip()
            self._mark_manual(entry)
        elif col == 4:
            text = item.text().strip()
            entry.time_h = int(text) if text else None
            self._mark_manual(entry)
        elif col == 5:
            new_sample = item.text().strip()
            self._apply_sample_change(entry, new_sample)
            entry.sample_no = new_sample
            self._mark_manual(entry)
        elif col == 8:
            entry.note = item.text().strip()

        entry.status = self._entry_status(entry)
        self._refresh_summary()

    def _apply_sample_change(self, entry, new_sample: str) -> None:
        old_sample = entry.sample_no
        if not new_sample or not old_sample or not entry.group_key:
            return
        suffix = f"-{old_sample}"
        if entry.group_key.endswith(suffix):
            entry.group_key = f"{entry.group_key[:-len(suffix)]}-{new_sample}"

    def _mark_manual(self, entry) -> None:
        entry.source_parse = "manual"
        entry.confidence = "manual"

    def _is_current_internal_blank(self, entry) -> bool:
        return bool(
            self.current_blank_file
            and not self.blank_is_external
            and entry.path.resolve() == self.current_blank_file.resolve()
        )

    def _on_role_changed(self, entry, role: str) -> None:
        if role == FILE_KIND_BLANK:
            self._set_entry_role(entry, FILE_KIND_BLANK)
            self.current_blank_file = entry.path.resolve()
            self.blank_is_external = False
            self._sync_blank_roles()
            self._populate_blank_combo()
            self._populate_file_table()
            self._refresh_summary()
            return

        if self._is_current_internal_blank(entry):
            self.current_blank_file = None
        self._set_entry_role(entry, role)
        self._sync_blank_roles()
        self._populate_blank_combo()
        self._populate_file_table()
        self._refresh_summary()

    def _exclude_invalid_files(self) -> None:
        if not self.scan_result:
            return
        for entry in self.scan_result.files:
            if self._entry_has_issue(entry):
                self._set_entry_role(entry, FILE_KIND_IGNORE)
        self._sync_blank_roles()
        self._populate_file_table()
        self._refresh_summary()

    def _build_options(self, skip_convert: bool = False) -> RunOptions:
        return RunOptions(
            min_wavelength_nm=self.min_wavelength_spin.value(),
            peak_min_nm=self.peak_min_spin.value(),
            peak_max_nm=self.peak_max_spin.value(),
            skip_convert=skip_convert,
            generate_figures=self.generate_figures_checkbox.isChecked(),
            dpi=self.dpi_spin.value(),
            assume_zero_blank=self.assume_zero_blank_checkbox.isChecked(),
        )

    def _build_manifest(self, skip_convert: bool = False) -> Optional[RunManifest]:
        if not self.scan_result:
            return None

        files = []
        for entry in self.scan_result.files:
            cloned = replace(entry)
            if self._is_current_internal_blank(entry):
                cloned.kind = FILE_KIND_BLANK
                cloned.enabled = False
                cloned.status = "Selected blank"
            else:
                cloned.kind = entry.kind
                cloned.enabled = entry.kind == FILE_KIND_SAMPLE
                cloned.status = self._entry_status(entry)
            files.append(cloned)

        blank_file = self.current_blank_file if self.current_blank_file and not self.blank_is_external else None
        external_blank = self.current_blank_file if self.current_blank_file and self.blank_is_external else None

        return RunManifest(
            layout=self.scan_result.layout,
            reference_file=Path(self.reference_edit.text().strip()).resolve(),
            blank_file=blank_file,
            external_blank_file=external_blank,
            run_label=self.run_label_edit.text().strip(),
            options=self._build_options(skip_convert=skip_convert),
            files=files,
        )

    def _refresh_summary(self) -> None:
        manifest = self._build_manifest(skip_convert=False)
        issues = validate_manifest(manifest, mode="run") if manifest else []
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = sum(1 for issue in issues if issue.severity == "warning")
        selected = len(manifest.selected_samples()) if manifest else 0

        if self.scan_result:
            summary = (
                f"raw {self.scan_result.raw_count} | selected {selected} | "
                f"blank candidates {len(self.scan_result.blank_candidates)} | "
                f"validation errors {errors} | warnings {warnings}"
            )
        else:
            summary = "Select a dataset folder and scan."
        self.summary_label.setText(summary)
        self._update_blank_source_label()

        self._update_validation_view(issues)
        self.run_full_button.setEnabled(bool(manifest) and errors == 0 and self._thread is None)
        convert_enabled = bool(manifest and self._thread is None)
        self.run_convert_button.setEnabled(convert_enabled)
        self.run_reprocess_button.setEnabled(bool(manifest) and errors == 0 and self._thread is None)
        figures_enabled = bool(manifest and manifest.processed_dir.exists() and self._thread is None)
        self.run_figures_button.setEnabled(figures_enabled)

    def _update_validation_view(self, issues) -> None:
        if not issues:
            self.validation_text.setPlainText("No validation issues.")
            return

        order = {"error": 0, "warning": 1, "info": 2}
        lines = []
        for issue in sorted(issues, key=lambda item: order.get(item.severity, 99)):
            lines.append(f"[{issue.severity.upper()}] {issue.message}")
        self.validation_text.setPlainText("\n".join(lines))

    def _update_blank_source_label(self) -> None:
        if not self.current_blank_file:
            self.blank_source_label.setText("Blank source: not selected")
            return
        if self.blank_is_external:
            self.blank_source_label.setText(f"Blank source: [External] {self.current_blank_file}")
            return
        if self.scan_result:
            try:
                relative = self.current_blank_file.resolve().relative_to(
                    self.scan_result.layout.dataset_root.resolve()
                )
                self.blank_source_label.setText(f"Blank source: {relative}")
                return
            except ValueError:
                pass
        self.blank_source_label.setText(f"Blank source: {self.current_blank_file}")

    def _start_run(self, mode: str) -> None:
        skip_convert = mode == "process"
        manifest = self._build_manifest(skip_convert=skip_convert)
        if manifest is None:
            QMessageBox.warning(self, "No Dataset", "Scan a dataset before running.")
            return

        issues = validate_manifest(manifest, mode=mode)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            self.tabs.setCurrentWidget(self.validation_tab)
            message = "\n".join(issue.message for issue in errors[:5])
            QMessageBox.warning(self, "Validation Errors", message)
            self._refresh_summary()
            return

        self._start_worker(manifest, mode="process")

    def _start_convert_only(self) -> None:
        manifest = self._build_manifest(skip_convert=False)
        if manifest is None:
            QMessageBox.warning(self, "No Dataset", "Scan a dataset before running.")
            return

        issues = validate_manifest(manifest, mode="convert")
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            self.tabs.setCurrentWidget(self.validation_tab)
            message = "\n".join(issue.message for issue in errors[:5])
            QMessageBox.warning(self, "Validation Errors", message)
            self._update_validation_view(issues)
            self._refresh_summary()
            return

        self._start_worker(manifest, mode="convert")

    def _start_figures_only(self) -> None:
        manifest = self._build_manifest(skip_convert=True)
        if manifest is None:
            QMessageBox.warning(self, "No Dataset", "Scan a dataset before running.")
            return
        issues = validate_manifest(manifest, mode="figures")
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            self.tabs.setCurrentWidget(self.validation_tab)
            self._update_validation_view(issues)
            QMessageBox.warning(self, "Validation Errors", errors[0].message)
            return
        self._start_worker(manifest, mode="figures")

    def _start_worker(self, manifest: RunManifest, mode: str) -> None:
        self.run_log.clear()
        self._log_lines = []
        self.progress_bar.setValue(0)
        self.tabs.setCurrentWidget(self.run_tab)

        self._thread = QThread(self)
        self._worker = RunWorker(manifest, mode=mode)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.failed.connect(self._cleanup_worker)
        self._thread.start()
        self._refresh_summary()

    def _append_log(self, message: str) -> None:
        self._log_lines.append(message)
        self.run_log.appendPlainText(message)

    def _on_worker_progress(self, message: str, value: int) -> None:
        self.progress_bar.setValue(value)
        if message:
            self._append_log(message)

    def _on_worker_finished(self, output_dir: str) -> None:
        output_path = Path(output_dir)
        self.last_output_dir = output_path
        self.last_manifest_path = output_path / "_manifest.json"
        self.results_label.setText(f"Last output: {output_path}")
        self.progress_bar.setValue(100)
        self._write_run_log(output_path)
        self.tabs.setCurrentWidget(self.results_tab)
        QMessageBox.information(self, "Run Complete", f"Outputs written to:\n{output_path}")
        self._refresh_summary()

    def _on_worker_failed(self, trace: str) -> None:
        self._append_log(trace)
        QMessageBox.critical(self, "Run Failed", trace)
        self._refresh_summary()

    def _cleanup_worker(self, *_args) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._refresh_summary()

    def _write_run_log(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "_run.log"
        log_path.write_text("\n".join(self._log_lines), encoding="utf-8")
        manifest = self._build_manifest(skip_convert=False)
        if manifest:
            save_manifest(manifest, output_dir / "_last_session_manifest.json")

    def _open_last_output(self) -> None:
        if not self.last_output_dir:
            QMessageBox.information(self, "No Output", "No output directory is available yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output_dir)))

    def _open_manifest_dir(self) -> None:
        if not self.last_manifest_path:
            QMessageBox.information(self, "No Manifest", "No manifest directory is available yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_manifest_path.parent)))


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
