from zipfile import ZipFile

from PySide6.QtWidgets import QMessageBox

from curveextractor.core.dataset import record_extractions
from curveextractor.core.model import Source
from curveextractor.core.raster import load_image
from curveextractor.gui.main_window import MainWindow
from tests.fixtures.synthetic import fixture


def test_four_curves_two_documents_roundtrip(qtbot, curve_factory, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    for angle in [0, 3]:
        _, _, _, png = fixture(angle=angle)
        document = load_image(data=png)
        window.add_document(document)
        for index in range(2):
            curve = curve_factory(name=f"{angle}-{index}")
            curve.source = Source(document.id, 0)
            curve.lock()
            window.project.curves.append(curve)
    window.project.main_curve_id = window.project.curves[0].id
    window.project.next_curve_number = 5
    signature = window.signature()
    path = tmp_path / "session.ecp"
    window.save_project_path(path)
    window.open_project_path(path)
    assert window.signature() == signature
    assert all(c.locked for c in window.project.curves)
    paths = record_extractions(tmp_path / "dataset", window.project, window.project.curves)
    assert len(paths) == 2
    for archive_path in paths:
        with ZipFile(archive_path) as archive:
            assert len([n for n in archive.namelist() if n.endswith(".png")]) == 1
            assert len([n for n in archive.namelist() if n.startswith("extractions/")]) == 2


def test_new_project_discards_or_keeps_current_work(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    _, _, _, png = fixture()
    window.add_document(load_image(data=png))
    old_project = window.project
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel
    )
    window.new_project()
    assert window.project is old_project
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    )
    window.new_project()
    assert window.project is not old_project
    assert window.project.documents == []
    assert window.project.curves == []
    assert window.project_path is None
    assert window.canvas.page is None
    assert window.page_selector.count() == 0
    assert window.signature() == window.saved_signature
