import csv
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QDialog, QFileDialog

from curveextractor.core.export_service import ExportOptions, export
from curveextractor.core.model import Project
from curveextractor.core.settings import Settings
from curveextractor.gui.export_dialog import ExportDialog
from curveextractor.gui.texts import T


def test_destination_picker_selects_without_writing(qtbot, monkeypatch, tmp_path):
    dialog = ExportDialog(Project(), Settings())
    qtbot.addWidget(dialog)
    target = tmp_path / "selecionado.csv"

    def choose(picker):
        assert picker.labelText(QFileDialog.DialogLabel.Accept) == T.BROWSE
        assert picker.testOption(QFileDialog.Option.DontConfirmOverwrite)
        assert picker.testOption(QFileDialog.Option.DontUseNativeDialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QFileDialog, "exec", choose)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda picker: [str(target)])
    dialog.browse()
    assert dialog.path.text() == str(target)
    assert not target.exists()


def test_mk3_full_export_from_curves(curve_factory, tmp_path, qtbot):
    sample = Path(__file__).parent / "fixtures" / "mk3.csv"
    with sample.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))
    curves = []
    for col, name in enumerate(rows[0][1:], 1):
        points = tuple((float(row[0]), float(row[col])) for row in rows[1:] if row[col])
        curve = curve_factory(points, name)
        curve.lock()
        curves.append(curve)
    project = Project(curves=curves, main_curve_id=curves[0].id)
    dialog = ExportDialog(project, Settings(), None)
    qtbot.addWidget(dialog)
    dialog.profile.setCurrentText("SeletorBombasMK3")
    dialog.path.setText(str(tmp_path / "regenerated.csv"))
    for name, combo in dialog.mapping.items():
        combo.setCurrentIndex(combo.findData(next(c.id for c in curves if c.name == name)))
    dialog.accept()
    assert (tmp_path / "regenerated.csv").read_bytes() == sample.read_bytes()
    assert dialog.result_table.incomplete_rows == 1


def test_nonfunctional_raw_preserves_clicks(curve_factory, tmp_path):
    curve = curve_factory(((0, 0), (2, 3), (1, 4)))
    curve.lock()
    paths, table = export(
        [curve], ExportOptions(tmp_path / "raw.csv", None, raw_only=True, format="both")
    )
    assert table is None
    assert len(paths) == 2
    rows = list(csv.reader(paths[0].read_text("utf-8-sig").splitlines()))
    np.testing.assert_allclose(np.array(rows[1:], dtype=float)[:, :2], curve.points_px)


def test_existing_export_requires_confirmation(qtbot, curve_factory, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    curve = curve_factory(((0, 0), (1, 1)))
    curve.lock()
    project = Project(curves=[curve], main_curve_id=curve.id)
    dialog = ExportDialog(project, Settings(), None)
    qtbot.addWidget(dialog)
    path = tmp_path / "curvas.csv"
    path.write_text("existing", encoding="utf-8")
    dialog.path.setText(str(path))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    dialog.accept()
    assert path.read_text(encoding="utf-8") == "existing"
    assert not dialog.result_paths
