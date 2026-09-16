import pytest

from curveextractor.core.model import AxisPoint, CoordinateSystem, Curve, Source


@pytest.fixture(autouse=True)
def isolate_gui_settings(request, tmp_path, monkeypatch):
    if "qtbot" not in request.fixturenames:
        return
    from PySide6.QtWidgets import QMessageBox

    from curveextractor.core.settings import Settings, project_root
    from curveextractor.gui import main_window

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    )

    root = tmp_path / "settings_root"
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.default.json").write_bytes(
        (project_root() / "config" / "settings.default.json").read_bytes()
    )
    monkeypatch.setattr(main_window, "Settings", lambda: Settings(root))


@pytest.fixture
def curve_factory():
    def make(points=((0, 0), (1, 1), (2, 2)), name="A"):
        return Curve(
            name,
            Source("doc", 0),
            CoordinateSystem((AxisPoint(0, 0, 0, 0), AxisPoint(1, 0, 1, 0), AxisPoint(0, 1, 0, 1))),
            tuple(points),
        )

    return make
