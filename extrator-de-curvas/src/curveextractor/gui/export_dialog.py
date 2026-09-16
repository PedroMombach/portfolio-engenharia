"""One dialog for selection, interpolation, profiles and raw exports."""

from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from curveextractor.core.dataset import record_extractions
from curveextractor.core.errors import DomainError
from curveextractor.core.export_service import ExportOptions, export, planned_paths
from curveextractor.core.transform import Transform

from .texts import T, domain_message
from .theme import configure_numeric_input


class ExportDialog(QDialog):
    def __init__(self, project, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T.EXPORT)
        self.resize(820, 720)
        self.project, self.settings = project, settings
        self.curves = [c for c in project.curves if c.locked]
        self.result_paths, self.result_table = [], None
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(self.curves), 4)
        self.table.setHorizontalHeaderLabels([T.INCLUDE, T.MAIN, T.NAME, T.DOMAIN])
        self.main_group = QButtonGroup(self)
        self.included = []
        for row, curve in enumerate(self.curves):
            included = QCheckBox()
            included.setChecked(True)
            self.included.append(included)
            self.table.setCellWidget(row, 0, included)
            main = QRadioButton()
            main.setChecked(curve.id == project.main_curve_id)
            self.main_group.addButton(main, row)
            self.table.setCellWidget(row, 1, main)
            self.table.setItem(row, 2, QTableWidgetItem(curve.name))
            points = Transform(curve.coordinate_system).to_real(curve.points_px)
            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    f"{np.min(points[:, 0]):g} / {np.max(points[:, 0]):g} / {len(points)}"
                ),
            )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        from PySide6.QtWidgets import QScrollArea, QTabWidget, QWidget

        tabs = QTabWidget()
        layout.addWidget(tabs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        scroll.setWidget(body)
        tabs.addTab(scroll, T.EXPORT_SETTINGS)
        provenance_body = QWidget()
        provenance_form = QFormLayout(provenance_body)
        tabs.addTab(provenance_body, T.PROVENANCE)
        self.base = QComboBox()
        self.base.addItems([T.MAIN_X, T.UNIFORM_X])
        self.count = QSpinBox()
        configure_numeric_input(self.count)
        self.count.setRange(2, 100000)
        self.count.setValue(100)
        self.method = QComboBox()
        self.method.addItem(T.LINEAR, "linear")
        self.method.addItem("PCHIP", "pchip")
        self.profile = QComboBox()
        self.profile.addItems(["Padrão", "SeletorBombasMK3"])
        self.profile.setCurrentText(settings.data["profile"])
        self.format = QComboBox()
        for label, value in [("CSV", "CSV"), ("XLSX", "XLSX"), (T.BOTH, "both")]:
            self.format.addItem(label, value)
        self.x_label = QLineEdit("X")
        for label, widget in [
            (T.BASE, self.base),
            (T.COUNT, self.count),
            (T.METHOD, self.method),
            (T.PROFILE, self.profile),
            (T.FORMAT, self.format),
            (T.X_LABEL, self.x_label),
        ]:
            form.addRow(label, widget)
        self.mapping = {}
        for header in ("H", "Eta1", "NPSH"):
            combo = QComboBox()
            combo.addItem(T.NONE, None)
            for curve in self.curves:
                combo.addItem(curve.name, curve.id)
            self.mapping[header] = combo
            form.addRow(header, combo)
        self.decimal, self.delimiter = QComboBox(), QComboBox()
        self.decimal.addItems([".", ","])
        self.delimiter.addItems([",", ";", "\t"])
        self.decimal.setCurrentText(settings.data["decimal"])
        self.delimiter.setCurrentText(settings.data["delimiter"])
        form.addRow(T.DECIMAL, self.decimal)
        form.addRow(T.DELIMITER, self.delimiter)
        self.bom, self.raw, self.raw_only = (
            QCheckBox(T.BOM),
            QCheckBox(T.RAW),
            QCheckBox(T.RAW_ONLY),
        )
        self.bom.setChecked(settings.data["bom"])
        self.raw.setChecked(settings.data["include_raw"])
        self.tracking = QCheckBox(T.TRACKING)
        self.tracking.setChecked(settings.data["tracking"])
        self.tracking.toggled.connect(self.tracking_changed)
        provenance_form.addRow(self.tracking)
        self.provenance = {}
        for key, label in [
            ("fabricante", T.MANUFACTURER),
            ("modelo", T.MODEL),
            ("observacao", T.NOTES),
        ]:
            widget = QLineEdit()
            self.provenance[key] = widget
            provenance_form.addRow(label, widget)
        self.restricted = QCheckBox(T.RESTRICTED)
        self.restricted.setChecked(True)
        provenance_form.addRow(self.restricted)
        self.dataset_root = QLineEdit(settings.data["dataset_root"])
        provenance_form.addRow(T.DATASET_ROOT, self.dataset_root)
        for checkbox in [self.bom, self.raw, self.raw_only]:
            form.addRow(checkbox)
        self.path = QLineEdit(
            str(Path(settings.data["last_directory"] or settings.root) / "curvas.csv")
        )
        destination = QHBoxLayout()
        destination.addWidget(self.path)
        browse = QPushButton(T.BROWSE)
        browse.clicked.connect(self.browse)
        destination.addWidget(browse)
        form.addRow(T.DESTINATION, destination)
        self.buttons = QDialogButtonBox()
        self.confirm = self.buttons.addButton(T.EXPORT, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(T.CANCEL, QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.profile.currentIndexChanged.connect(self.controls)
        self.decimal.currentIndexChanged.connect(self.controls)
        self.delimiter.currentIndexChanged.connect(self.controls)
        self.base.currentIndexChanged.connect(self.controls)
        self.raw_only.toggled.connect(self.controls)
        self.controls()

    def controls(self):
        custom = self.profile.currentText() == "Padrão"
        self.count.setEnabled(self.base.currentIndex() == 1 and not self.raw_only.isChecked())
        for widget in [self.decimal, self.delimiter, self.bom, self.x_label]:
            widget.setEnabled(custom)
        for combo in self.mapping.values():
            combo.setEnabled(not custom and not self.raw_only.isChecked())
        self.confirm.setEnabled(
            not custom or self.decimal.currentText() != self.delimiter.currentText()
        )

    def tracking_changed(self, checked):
        previous = self.settings.data["tracking"]
        self.settings.data["tracking"] = checked
        try:
            self.settings.save()
        except OSError as error:
            self.settings.data["tracking"] = previous
            self.tracking.blockSignals(True)
            self.tracking.setChecked(previous)
            self.tracking.blockSignals(False)
            QMessageBox.warning(self, T.ERROR, T.IO_ERROR.format(detail=str(error)))

    def browse(self):
        dialog = QFileDialog(self, T.CHOOSE_DESTINATION, self.path.text())
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, T.BROWSE)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.path.setText(dialog.selectedFiles()[0])

    def selected_curves(self):
        return [c for c, checkbox in zip(self.curves, self.included) if checkbox.isChecked()]

    def options(self):
        index = self.main_group.checkedId()
        return ExportOptions(
            Path(self.path.text()),
            self.curves[index].id if index >= 0 else None,
            self.method.currentData(),
            self.count.value() if self.base.currentIndex() else None,
            self.profile.currentText(),
            self.format.currentData(),
            self.delimiter.currentText(),
            self.decimal.currentText(),
            self.bom.isChecked(),
            self.raw.isChecked(),
            self.raw_only.isChecked(),
            self.x_label.text(),
            {k: w.currentData() for k, w in self.mapping.items()},
        )

    def accept(self):
        try:
            curves, options = self.selected_curves(), self.options()
            existing = [p for p in planned_paths(curves, options) if p.exists()]
            if (
                existing
                and QMessageBox.question(
                    self,
                    T.CONFIRM,
                    T.OVERWRITE.format(files="\n".join(str(p) for p in existing)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.result_paths, self.result_table = export(curves, options)
            self.project.main_curve_id = options.main_id
        except DomainError as error:
            QMessageBox.warning(self, T.ERROR, domain_message(error))
            return
        except OSError as error:
            QMessageBox.warning(self, T.ERROR, T.IO_ERROR.format(detail=str(error)))
            return
        if self.tracking.isChecked():
            try:
                root = Path(self.dataset_root.text())
                if not root.is_absolute():
                    root = self.settings.root / root
                record_extractions(
                    root,
                    self.project,
                    curves,
                    {k: w.text() or None for k, w in self.provenance.items()}
                    | {"uso_restrito": self.restricted.isChecked()},
                )
                self.settings.data["dataset_root"] = self.dataset_root.text()
                self.settings.save()
            except (OSError, DomainError) as error:
                detail = domain_message(error) if isinstance(error, DomainError) else str(error)
                QMessageBox.warning(self, T.ERROR, T.TRACKING_FAILED.format(detail=detail))
        super().accept()
