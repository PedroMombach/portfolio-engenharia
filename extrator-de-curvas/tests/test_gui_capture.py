from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from curveextractor.core.aggregation import aggregate
from curveextractor.core.export_csv import write_csv
from curveextractor.core.model import Source
from curveextractor.core.raster import load_image
from curveextractor.gui.main_window import MainWindow
from tests.fixtures.synthetic import fixture


def test_image_capture_to_csv(qtbot, tmp_path):
    system, pixels, _, png = fixture()
    document = load_image(data=png)
    window = MainWindow()
    qtbot.addWidget(window)
    window.project.documents.append(document)
    window.canvas.set_page(document.pages[0])
    window.create_curve()
    for point in system.points:
        window.flow.set_axis(
            point.px,
            point.py,
            (point.vx, point.vy)
            if window.flow.stage == 1
            else (point.vx,)
            if window.flow.stage == 2
            else (point.vy,),
        )
        window.advance()
    for x, y in pixels:
        window.click(x, y)
    window.undo()
    assert len(window.flow.curve.points_px) == 19
    window.redo()
    window.advance()
    curve = window.project.curves[0]
    assert curve.locked and len(curve.points_px) == 20
    assert curve.source == Source(document.id, 0)
    table = aggregate([curve], curve.id)
    write_csv(tmp_path / "captured.csv", table)
    assert len((tmp_path / "captured.csv").read_text("utf-8-sig").splitlines()) == 21
    old_points = curve.points_px
    window.canvas.zoom(3)
    assert curve.points_px == old_points
    assert all(item.pen().isCosmetic() for item in window.canvas.overlays)


def test_canvas_mouse_captures_original_pixels(qtbot, curve_factory):
    window = MainWindow()
    qtbot.addWidget(window)
    _, _, _, png = fixture()
    document = load_image(data=png)
    window.project.documents.append(document)
    window.canvas.set_page(document.pages[0])
    curve = curve_factory()
    curve.source = Source(document.id, 0)
    window.project.curves.append(curve)
    window.flow.start(curve, duplicate=True)
    window.show()
    qtbot.waitExposed(window)
    position = window.canvas.viewport().rect().center()
    expected = window.canvas.mapToScene(position)
    qtbot.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert curve.points_px[-1] == (expected.x(), expected.y())
    window.flow.discard()


def test_image_drop_on_canvas_opens_document(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    _, _, _, png = fixture()
    path = tmp_path / "grafico.png"
    path.write_bytes(png)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    position = window.canvas.viewport().rect().center()
    enter = QDragEnterEvent(
        QPoint(position),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window.canvas.viewport(), enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(position),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window.canvas.viewport(), drop)
    assert drop.isAccepted()
    assert len(window.project.documents) == 1
    assert window.canvas.page is window.project.documents[0].pages[0]
