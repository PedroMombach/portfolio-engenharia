"""Application shell around the domain and capture controller."""

import json
import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from curveextractor.core.errors import DomainError
from curveextractor.core.model import Project, Source
from curveextractor.core.project_io import curve_record, load_project, save_project
from curveextractor.core.raster import load_image, load_pdf, pdf_count
from curveextractor.core.settings import Settings

from .axis_value_popup import AxisValuePopup
from .canvas_items import marker
from .canvas_view import CanvasView
from .capture_flow import CaptureFlow
from .curve_panel import CurvePanel
from .export_dialog import ExportDialog
from .magnifier import Magnifier
from .pdf_pages_dialog import PdfPagesDialog
from .preferences_dialog import PreferencesDialog
from .shortcuts import apply_shortcuts
from .texts import T, domain_message
from .theme import apply_theme, configure_numeric_input


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle(T.APP)
        self.resize(1280, 820)
        self.project = Project()
        self.project_path = None
        self.saved_signature = self.signature()
        self.settings = settings or Settings()
        self.setAcceptDrops(True)
        self.flow = CaptureFlow()
        self.actions = {}
        self.canvas = CanvasView()
        self.canvas.files_dropped.connect(self.open_dropped_files)
        self.magnifier = Magnifier(self.canvas)
        self.canvas.clicked.connect(lambda x, y: self.run(lambda: self.click(x, y)))
        self.canvas.advance.connect(lambda: self.run(self.advance))
        splitter = QSplitter()
        canvas_body = QWidget()
        canvas_layout = QVBoxLayout(canvas_body)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self.canvas, 1)
        self.thumbnails = QListWidget()
        self.thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnails.setFlow(QListWidget.Flow.LeftToRight)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setMovement(QListWidget.Movement.Static)
        self.thumbnails.setIconSize(QSize(50, 58))
        self.thumbnails.setGridSize(QSize(96, 86))
        self.thumbnails.setMaximumHeight(105)
        self.thumbnails.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.thumbnails.currentRowChanged.connect(self.page_thumbnail_selected)
        self.thumbnails.hide()
        canvas_layout.addWidget(self.thumbnails)
        splitter.addWidget(canvas_body)
        self.side = QWidget()
        self.side.setMinimumWidth(270)
        self.side_layout = QVBoxLayout(self.side)
        self.side_layout.addWidget(QLabel(T.CURVES))
        self.summary = QLabel(T.EMPTY)
        self.summary.setWordWrap(True)
        self.side_layout.addWidget(self.summary)
        creation = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems([T.ASSISTED, T.FREE])
        self.x_scale, self.y_scale = QComboBox(), QComboBox()
        for widget in [self.x_scale, self.y_scale]:
            widget.addItem(T.LINEAR, "lin")
            widget.addItem(T.LOG, "log")
        creation.addRow(T.MODE, self.mode)
        creation.addRow(T.X_SCALE, self.x_scale)
        creation.addRow(T.Y_SCALE, self.y_scale)
        self.side_layout.addLayout(creation)
        self.curve_panel = CurvePanel()
        self.curve_panel.changed.connect(self.metadata_changed)
        self.curve_panel.main_requested.connect(lambda cid: self.run(lambda: self.choose_main(cid)))
        self.curve_panel.delete_requested.connect(
            lambda cid: self.run(lambda: self.delete_curve(cid))
        )
        self.side_layout.addWidget(self.curve_panel, 1)
        self.opacity_sliders = {}
        for label, key in [
            (T.CURVE_OPACITY, "curve_opacity"),
            (T.AXIS_OPACITY, "axis_opacity"),
            (T.IMAGE_OPACITY, "image_opacity"),
        ]:
            self.side_layout.addWidget(QLabel(label))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(round(self.settings.data[key] * 100))
            slider.valueChanged.connect(lambda value, k=key: self.opacity(k, value))
            self.opacity_sliders[key] = slider
            self.side_layout.addWidget(slider)
        splitter.addWidget(self.side)
        splitter.setStretchFactor(0, 1)
        self.setCentralWidget(splitter)
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.page_toolbar = QToolBar()
        self.page_toolbar.setMovable(False)
        self.addToolBarBreak()
        self.addToolBar(self.page_toolbar)
        self.page_selector = QComboBox()
        self.page_selector.setMinimumWidth(300)
        self.page_selector.setIconSize(QSize(32, 44))
        self.page_selector.currentIndexChanged.connect(
            lambda index: self.run(lambda: self.select_page(index))
        )
        self.page_toolbar.addWidget(self.page_selector)
        self.dpi = QSpinBox()
        configure_numeric_input(self.dpi)
        self.dpi.setRange(72, 600)
        self.dpi.setValue(self.settings.data["raster_dpi"])
        self.dpi.setToolTip(T.DPI_NOTE)
        self.dpi.valueChanged.connect(lambda value: self.run(lambda: self.set_dpi(value)))
        self.page_toolbar.addWidget(QLabel(T.DPI))
        self.page_toolbar.addWidget(self.dpi)
        for key, label, shortcut, callback in [
            ("new_project", T.NEW_PROJECT, "", self.new_project),
            ("open", T.OPEN, "Ctrl+O", self.open_dialog),
            ("create", T.CREATE, "Ctrl+N", self.create_curve),
            ("save_curve", T.SAVE_CURVE, "Ctrl+Return", self.advance),
            ("export", T.EXPORT, "Ctrl+E", self.export_dialog),
            ("fit", T.FIT, "Ctrl+0", self.canvas.fit),
            ("actual", T.ACTUAL, "Ctrl+1", self.canvas.resetTransform),
            ("undo", T.UNDO, "Ctrl+Z", self.undo),
            ("redo", T.REDO, "Ctrl+Y", self.redo),
            ("discard", T.DISCARD, "Esc", self.discard),
            ("advance", T.OK, "Return", self.advance),
            ("previous", T.PREVIOUS, "PgUp", lambda: self.move_page(-1)),
            ("next", T.NEXT, "PgDown", lambda: self.move_page(1)),
            ("paste", T.PASTE, "Ctrl+V", self.paste),
            ("duplicate", T.DUPLICATE, "Ctrl+D", self.duplicate_curve),
            ("preferences", T.PREFERENCES, "", self.preferences),
            ("save_project", T.SAVE_PROJECT, "Ctrl+S", self.save_project_dialog),
            ("open_project", T.OPEN_PROJECT, "", self.open_project_dialog),
            ("magnifier", T.MAGNIFIER, "L", self.toggle_magnifier),
            ("zoom_in", T.ZOOM_IN, "Ctrl++", lambda: self.canvas.zoom(1.2)),
            ("zoom_out", T.ZOOM_OUT, "Ctrl+-", lambda: self.canvas.zoom(1 / 1.2)),
        ]:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda checked=False, cb=callback: self.run(cb))
            self.addAction(action)
            self.actions[key] = action
            if key in {"previous", "next"}:
                self.page_toolbar.addAction(action)
            elif key in {
                "new_project",
                "open",
                "create",
                "save_curve",
                "export",
                "fit",
                "preferences",
            }:
                self.toolbar.addAction(action)
        for label, keys in [
            (
                T.FILE_MENU,
                ["new_project", "open", "open_project", "save_project", "export", "preferences"],
            ),
            (
                T.EDIT_MENU,
                ["create", "duplicate", "save_curve", "discard", "undo", "redo", "paste"],
            ),
            (
                T.VIEW_MENU,
                ["fit", "actual", "zoom_in", "zoom_out", "magnifier", "previous", "next"],
            ),
        ]:
            menu = self.menuBar().addMenu(label)
            for key in keys:
                menu.addAction(self.actions[key])
        self.side_layout.insertWidget(2, self.action_button(self.actions["duplicate"]))
        self.apply_preferences()
        if self.settings.data["geometry"]:
            self.restoreGeometry(QByteArray.fromHex(self.settings.data["geometry"].encode("ascii")))
        self.refresh()

    def run(self, callback):
        try:
            return callback()
        except DomainError as error:
            QMessageBox.warning(self, T.ERROR, domain_message(error))
        except OSError as error:
            QMessageBox.warning(self, T.ERROR, T.IO_ERROR.format(detail=str(error)))
        except Exception:
            logging.exception("Application operation failed")
            QMessageBox.critical(self, T.ERROR, T.GENERIC_ERROR)

    def idle_required(self):
        if self.flow.curve:
            raise DomainError("capture_active")

    def open_dialog(self):
        self.idle_required()
        path, _ = QFileDialog.getOpenFileName(self, T.OPEN, "", T.FILTER)
        if path:
            self.open_path(Path(path))

    def open_path(self, path):
        self.idle_required()
        if path.suffix.lower() == ".ecp":
            self.open_project_path(path)
            return
        if path.suffix.lower() == ".pdf":
            count = pdf_count(path)
            pages = [0]
            if count > 1:
                dialog = PdfPagesDialog(path, count, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                pages = dialog.selected()
            document = load_pdf(path, pages, self.settings.data["raster_dpi"])
        else:
            document = load_image(path)
        self.add_document(document)
        self.settings.data["last_directory"] = str(path.parent)

    def add_document(self, document):
        self.project.documents.append(document)
        self.rebuild_pages()
        self.page_selector.setCurrentIndex(self.page_selector.count() - len(document.pages))
        self.select_page(self.page_selector.currentIndex())
        self.refresh()

    def rebuild_pages(self):
        self.page_selector.blockSignals(True)
        self.page_selector.clear()
        self.thumbnails.blockSignals(True)
        self.thumbnails.clear()
        for document in self.project.documents:
            for page in document.pages:
                pixmap = QPixmap()
                pixmap.loadFromData(page.png_bytes)
                icon = QIcon(
                    pixmap.scaled(
                        QSize(64, 80),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                name = Path(document.origin_path).name if document.origin_path else T.PASTE
                self.page_selector.addItem(
                    icon, f"{name} · {T.PAGE.format(number=page.page_index + 1)}", page
                )
                item = QListWidgetItem(icon, T.PAGE.format(number=page.page_index + 1))
                item.setToolTip(name)
                self.thumbnails.addItem(item)
        self.page_selector.blockSignals(False)
        self.thumbnails.blockSignals(False)
        self.thumbnails.setVisible(self.thumbnails.count() > 1)

    def page_thumbnail_selected(self, index):
        if index >= 0:
            self.page_selector.setCurrentIndex(index)

    def select_page(self, index):
        if index < 0:
            return
        if self.flow.curve:
            page = self.canvas.page
            self.page_selector.blockSignals(True)
            for i in range(self.page_selector.count()):
                if self.page_selector.itemData(i) is page:
                    self.page_selector.setCurrentIndex(i)
                    self.thumbnails.blockSignals(True)
                    self.thumbnails.setCurrentRow(i)
                    self.thumbnails.blockSignals(False)
            self.page_selector.blockSignals(False)
            raise DomainError("capture_active")
        page = self.page_selector.itemData(index)
        self.canvas.set_page(page)
        self.thumbnails.blockSignals(True)
        self.thumbnails.setCurrentRow(index)
        self.thumbnails.blockSignals(False)
        self.refresh()

    def move_page(self, delta):
        self.idle_required()
        index = self.page_selector.currentIndex() + delta
        if 0 <= index < self.page_selector.count():
            self.page_selector.setCurrentIndex(index)

    def set_dpi(self, value):
        self.settings.data["raster_dpi"] = value
        self.settings.save()
        self.statusBar().showMessage(T.DPI_NOTE)

    def paste(self):
        self.idle_required()
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.open_path(Path(url.toLocalFile()))
        elif mime.hasImage():
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            clipboard.image().save(buffer, "PNG")
            self.add_document(load_image(data=bytes(buffer.data())))
        elif mime.hasText() and Path(mime.text().strip().strip('"')).is_file():
            self.open_path(Path(mime.text().strip().strip('"')))
        else:
            QMessageBox.information(self, T.APP, T.NO_CLIPBOARD)

    def dragEnterEvent(self, event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.open_dropped_files(paths)
            event.acceptProposedAction()

    def open_dropped_files(self, paths):
        for path in paths:
            self.run(lambda source=Path(path): self.open_path(source))

    def create_curve(self):
        self.idle_required()
        if not self.canvas.page:
            QMessageBox.information(self, T.APP, T.OPEN_FIRST)
            return
        page = self.canvas.page
        curve = self.project.new_curve(
            Source(page.document_id, page.page_index),
            T.CURVE_NAME.format(number=self.project.next_curve_number),
        )
        curve.coordinate_system = replace(
            curve.coordinate_system,
            x_scale=self.x_scale.currentData(),
            y_scale=self.y_scale.currentData(),
        )
        palette = self.settings.data["palette"]
        curve.style = replace(
            curve.style,
            color=palette[(self.project.next_curve_number - 2) % len(palette)],
            marker=self.settings.data["marker"],
            width=self.settings.data["curve_width"],
        )
        self.flow.start(curve, free_mode=self.mode.currentIndex() == 1)
        self.refresh()

    def action_button(self, action):
        from PySide6.QtWidgets import QToolButton

        button = QToolButton()
        button.setDefaultAction(action)
        return button

    def previous_curve(self):
        if not self.canvas.page:
            return None
        page = self.canvas.page
        return next(
            (
                c
                for c in reversed(self.project.curves)
                if c.locked and c.source == Source(page.document_id, page.page_index)
            ),
            None,
        )

    def duplicate_curve(self):
        self.idle_required()
        previous = self.previous_curve()
        if previous:
            self.create_curve()
            self.flow.curve.coordinate_system = previous.coordinate_system.duplicate()
            self.flow.start(self.flow.curve, duplicate=True)
            self.refresh()

    def metadata_changed(self):
        self.canvas.draw_curves(self.project.curves, self.flow.curve, self.settings.data)

    def choose_main(self, curve_id):
        from curveextractor.core.interpolation import ordered_points

        curve = next(c for c in self.project.curves if c.id == curve_id)
        try:
            ordered_points(curve)
        finally:
            self.curve_panel.rebuild(self.project)
        self.project.main_curve_id = curve_id
        self.refresh()

    def delete_curve(self, curve_id):
        if self.flow.curve and self.flow.curve.id == curve_id:
            self.discard()
            return
        if (
            QMessageBox.question(self, T.CONFIRM, T.DELETE_QUESTION)
            == QMessageBox.StandardButton.Yes
        ):
            self.project.curves = [c for c in self.project.curves if c.id != curve_id]
            if self.project.main_curve_id == curve_id:
                self.project.main_curve_id = None
            self.refresh()

    def opacity(self, key, value):
        self.settings.data[key] = value / 100
        self.metadata_changed()

    def preferences(self):
        dialog = PreferencesDialog(self.settings, self.actions, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_preferences()
            self.refresh()

    def signature(self):
        return json.dumps(
            {
                "documents": [
                    (d.id, [p.page_index for p in d.pages]) for d in self.project.documents
                ],
                "curves": [curve_record(c) for c in self.project.curves],
                "main": self.project.main_curve_id,
                "next": self.project.next_curve_number,
            },
            sort_keys=True,
        )

    def confirm_replace(self):
        if self.signature() == self.saved_signature:
            return True
        answer = QMessageBox.question(
            self,
            T.CONFIRM,
            T.UNSAVED,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project_dialog()
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self):
        self.idle_required()
        if not self.confirm_replace():
            return
        self.project = Project()
        self.project_path = None
        self.saved_signature = self.signature()
        self.rebuild_pages()
        self.canvas.set_page(None)
        self.refresh()

    def save_project_dialog(self):
        self.idle_required()
        path = str(self.project_path) if self.project_path else ""
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, T.SAVE_PROJECT, "projeto.ecp", T.PROJECT_FILTER
            )
        if not path:
            return False
        self.save_project_path(Path(path).with_suffix(".ecp"))
        return True

    def save_project_path(self, path):
        self.idle_required()
        save_project(path, self.project)
        self.project_path = path
        self.saved_signature = self.signature()
        self.statusBar().showMessage(T.PROJECT_SAVED)

    def open_project_dialog(self):
        self.idle_required()
        path, _ = QFileDialog.getOpenFileName(self, T.OPEN_PROJECT, "", T.PROJECT_FILTER)
        if path:
            self.open_project_path(Path(path))

    def open_project_path(self, path):
        self.idle_required()
        loaded = load_project(path)
        if not self.confirm_replace():
            return
        self.project, self.project_path = loaded, path
        self.saved_signature = self.signature()
        self.rebuild_pages()
        if self.page_selector.count():
            self.select_page(0)
        else:
            self.canvas.set_page(None)
        self.refresh()

    def apply_preferences(self):
        apply_theme(self.settings.data["theme"], self.settings.data["font_color"])
        apply_shortcuts(self.actions, self.settings.data)
        self.canvas.setBackgroundBrush(QColor(self.settings.data["canvas_color"]))
        self.magnifier.factor = self.settings.data["magnifier_factor"]
        self.update_magnifier()
        self.dpi.blockSignals(True)
        self.dpi.setValue(self.settings.data["raster_dpi"])
        self.dpi.blockSignals(False)
        for key, slider in self.opacity_sliders.items():
            slider.blockSignals(True)
            slider.setValue(round(self.settings.data[key] * 100))
            slider.blockSignals(False)

    def toggle_magnifier(self):
        self.settings.data["magnifier"] = not self.settings.data["magnifier"]
        self.update_magnifier()

    def update_magnifier(self):
        self.magnifier.enabled = self.settings.data["magnifier"] and self.canvas.page is not None
        self.magnifier.setVisible(self.magnifier.enabled and self.magnifier.position is not None)

    def click(self, x, y):
        if not self.flow.curve:
            return
        if self.flow.stage < 4:
            labels = {1: [(T.X_MIN, 0), (T.Y_MIN, 0)], 2: [(T.X_MAX, 100)], 3: [(T.Y_MAX, 100)]}[
                self.flow.stage
            ]
            if self.flow.free_mode:
                labels = [(T.X_VALUE, 1), (T.Y_VALUE, 1)]
            elif self.flow.stage == 1:
                labels = [
                    (T.X_MIN, 1 if self.flow.curve.coordinate_system.x_scale == "log" else 0),
                    (T.Y_MIN, 1 if self.flow.curve.coordinate_system.y_scale == "log" else 0),
                ]
            popup = AxisValuePopup(labels, self)
            popup.move(QCursor.pos())
            if popup.exec() == QDialog.DialogCode.Accepted:
                self.flow.set_axis(x, y, popup.values)
        else:
            self.flow.point(x, y)
        self.refresh()

    def advance(self):
        saved = self.flow.advance()
        if saved and self.project.main_curve_id is None:
            self.project.main_curve_id = saved.id
        self.refresh()

    def undo(self):
        self.flow.undo()
        self.refresh()

    def redo(self):
        self.flow.redo()
        self.refresh()

    def discard(self):
        curve = self.flow.curve
        if (
            curve
            and QMessageBox.question(self, T.CONFIRM, T.DISCARD_QUESTION)
            == QMessageBox.StandardButton.Yes
        ):
            self.project.curves.remove(curve)
            self.flow.discard()
            self.refresh()

    def export_dialog(self):
        self.idle_required()
        if not any(c.locked for c in self.project.curves):
            QMessageBox.information(self, T.APP, T.NO_CURVES)
            return
        dialog = ExportDialog(self.project, self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            message = T.OUTPUT_FILES.format(files="\n".join(str(p) for p in dialog.result_paths))
            if dialog.result_table and dialog.result_table.incomplete_rows:
                message += "\n\n" + T.MISSING.format(
                    rows=dialog.result_table.incomplete_rows,
                    columns=", ".join(dialog.result_table.incomplete_columns),
                )
            QMessageBox.information(self, T.DONE, message)
        self.refresh()

    def refresh(self):
        self.canvas.draw_curves(self.project.curves, self.flow.curve, self.settings.data)
        self.curve_panel.rebuild(self.project)
        self.summary.setText(
            T.PROJECT_COUNTS.format(
                curves=len(self.project.curves), documents=len(self.project.documents)
            )
            if self.project.documents
            else T.SHORT_HELP
        )
        if self.flow.pending:
            point = self.flow.pending
            self.canvas.overlays.append(
                marker(
                    self.canvas.scene(),
                    (point.px, point.py),
                    self.settings.data["axis_color"],
                    "square",
                    10,
                )
            )
        self.update_magnifier()
        stage = self.flow.stage
        self.statusBar().showMessage(
            T.IDLE if stage == 0 else T.CAPTURE if stage == 4 else T.AXIS.format(number=stage)
        )
        self.actions["create"].setEnabled(stage == 0 and self.canvas.page is not None)
        self.actions["new_project"].setEnabled(stage == 0)
        self.actions["save_curve"].setEnabled(stage == 4)
        self.actions["duplicate"].setEnabled(stage == 0 and self.previous_curve() is not None)
        for widget in [self.mode, self.x_scale, self.y_scale]:
            widget.setEnabled(stage == 0)

    def closeEvent(self, event):
        if self.flow.curve:
            self.discard()
            if self.flow.curve:
                event.ignore()
                return
        if not self.confirm_replace():
            event.ignore()
            return
        self.settings.data["geometry"] = bytes(self.saveGeometry().toHex()).decode("ascii")
        try:
            self.settings.save()
        except OSError as error:
            QMessageBox.warning(self, T.ERROR, T.IO_ERROR.format(detail=str(error)))
            event.ignore()
            return
        event.accept()
