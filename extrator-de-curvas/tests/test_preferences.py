from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSpinBox

from curveextractor.core.settings import Settings
from curveextractor.gui.main_window import MainWindow
from curveextractor.gui.preferences_dialog import PreferencesDialog


def test_persist_and_apply_preferences(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = PreferencesDialog(window.settings, window.actions)
    qtbot.addWidget(dialog)
    dialog.fields["theme"].setCurrentIndex(dialog.fields["theme"].findData("escuro"))
    dialog.fields["font_color"].setText("#654321")
    dialog.fields["canvas_color"].setText("#123456")
    dialog.fields["raster_dpi"].setValue(300)
    dialog.fields["axis_width"].setValue(3)
    dialog.fields["palette"].setText("#123456, #abcdef")
    dialog.keys["create"].setKeySequence(QKeySequence("Ctrl+Shift+N"))
    dialog.accept()
    loaded = Settings(window.settings.root)
    assert loaded.data["palette"] == ["#123456", "#abcdef"]
    assert loaded.data["font_color"] == "#654321"
    assert loaded.data["raster_dpi"] == 300
    window.apply_preferences()
    assert window.actions["create"].shortcut() == QKeySequence("Ctrl+Shift+N")
    assert window.canvas.backgroundBrush().color().name() == "#123456"
    assert QApplication.palette().color(QPalette.ColorRole.Text).name() == "#654321"
    loaded.path.unlink()
    assert Settings(window.settings.root).data["theme"] == "sistema"


def test_font_color_uses_theme_presets_and_manual_override(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    palette = QApplication.palette()
    window.settings.data["theme"] = "escuro"
    window.apply_preferences()
    assert QApplication.palette().color(QPalette.ColorRole.Text).name() == "#e3edf6"
    window.settings.data["theme"] = "claro"
    window.apply_preferences()
    assert QApplication.palette().color(QPalette.ColorRole.Text).name() == "#202b38"
    window.settings.data["font_color"] = "#123456"
    window.apply_preferences()
    assert QApplication.palette().color(QPalette.ColorRole.Text).name() == "#123456"
    QApplication.setPalette(palette)


def test_numeric_up_arrow_increments(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    dialog = PreferencesDialog(window.settings, window.actions)
    qtbot.addWidget(dialog)
    dialog.show()
    for widget in (window.dpi, dialog.fields["axis_width"]):
        option = QStyleOptionSpinBox()
        option.initFrom(widget)
        option.frame = widget.hasFrame()
        option.buttonSymbols = widget.buttonSymbols()
        option.stepEnabled = widget.stepEnabled()
        up = widget.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            widget,
        )
        before = widget.value()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=up.center())
        assert widget.value() > before
