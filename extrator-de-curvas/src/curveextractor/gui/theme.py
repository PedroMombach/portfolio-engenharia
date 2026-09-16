"""Native widgets with restrained light and dark palettes."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QStyleFactory


def configure_numeric_input(widget):
    """Keep arrow buttons explicit on all numeric inputs."""
    widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)


def apply_theme(theme, font_color="auto"):
    app = QApplication.instance()
    if app.style().objectName().lower() != "fusion":
        app.setStyle(QStyleFactory.create("Fusion"))
    dark = theme == "escuro" or (
        theme == "sistema" and app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    )
    palette = app.style().standardPalette()
    if dark:
        for role, color in [
            (QPalette.ColorRole.Window, "#19232e"),
            (QPalette.ColorRole.Base, "#111a24"),
            (QPalette.ColorRole.AlternateBase, "#202e3d"),
            (QPalette.ColorRole.Button, "#253647"),
            (QPalette.ColorRole.Highlight, "#087fba"),
            (QPalette.ColorRole.HighlightedText, "#ffffff"),
        ]:
            palette.setColor(role, QColor(color))
    else:
        for role, color in [
            (QPalette.ColorRole.Window, "#f4f7fb"),
            (QPalette.ColorRole.Base, "#ffffff"),
            (QPalette.ColorRole.AlternateBase, "#edf2f7"),
            (QPalette.ColorRole.Button, "#f4f7fb"),
            (QPalette.ColorRole.Highlight, "#087fba"),
            (QPalette.ColorRole.HighlightedText, "#ffffff"),
        ]:
            palette.setColor(role, QColor(color))
    text_color = "#e3edf6" if dark else "#202b38"
    if font_color != "auto":
        text_color = font_color
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.ToolTipText,
    ):
        palette.setColor(role, QColor(text_color))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 10))
    border = "#384b5d" if dark else "#ccd7df"
    app.setStyleSheet(f"""
        QToolBar {{ spacing: 7px; padding: 7px; border-bottom: 1px solid {border}; }}
        QToolButton {{ padding: 6px 9px; border-radius: 4px; }}
        QToolButton:hover, QPushButton:hover {{ background: #087fba; color: white; }}
        QPushButton {{ padding: 6px 10px; }}
        QLineEdit, QComboBox {{ padding: 4px; }}
        QTreeWidget, QTableWidget {{ border: 1px solid {border}; border-radius: 4px; }}
        QHeaderView::section {{ padding: 7px; }}
        QStatusBar {{ padding: 7px; border-top: 1px solid {border}; }}
        QSplitter::handle {{ background: {border}; width: 1px; }}
    """)
