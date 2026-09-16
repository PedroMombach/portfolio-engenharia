from PIL import Image

from curveextractor.core.raster import load_pdf, pdf_count
from curveextractor.gui.main_window import MainWindow
from curveextractor.gui.pdf_pages_dialog import PdfPagesDialog


def test_multipage_pdf_selection_and_fixed_dpi(qtbot, tmp_path):
    path = tmp_path / "catalog.pdf"
    pages = [Image.new("RGB", (72, 72), (index * 7, 100, 150)) for index in range(30)]
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=72)
    assert pdf_count(path) == 30
    dialog = PdfPagesDialog(path, 30)
    qtbot.addWidget(dialog)
    dialog.timer.stop()
    for index in [1, 10, 29]:
        dialog.pages.item(index).setSelected(True)
    assert dialog.selected() == [1, 10, 29]
    document = load_pdf(path, dialog.selected(), 200)
    assert len(document.pages) == 3
    assert all(p.width_px == 200 and p.raster_dpi == 200 for p in document.pages)
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_document(document)
    window.page_selector.setCurrentIndex(2)
    assert window.canvas.page.page_index == 29
    for index in range(3):
        window.page_selector.setCurrentIndex(index)
        window.create_curve()
        window.flow.free_mode = True
        for x, y in [(0, 0), (100, 0), (0, 100)]:
            window.flow.set_axis(x, y, (x, y))
            window.advance()
        window.click(10, 10)
        window.click(20, 20)
        window.advance()
    assert len(window.project.curves) == 3
