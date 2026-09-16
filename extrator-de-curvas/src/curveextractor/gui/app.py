"""Desktop bootstrap with a user-readable exception boundary."""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from curveextractor.core.settings import project_root

from .main_window import MainWindow
from .texts import T


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(T.APP)
    log_path = project_root() / "test-output" / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_path, level=logging.ERROR)

    def report(kind, value, traceback):
        logging.error("Unhandled application error", exc_info=(kind, value, traceback))
        QMessageBox.critical(None, T.ERROR, T.GENERIC_ERROR)

    sys.excepthook = report
    window = MainWindow()
    window.show()
    return app.exec()
