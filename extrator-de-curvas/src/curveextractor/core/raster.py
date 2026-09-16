"""Image loading and PDF rasterization without a GUI dependency."""

import hashlib
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from .errors import DomainError
from .model import Document, PageImage


def make_page(document_id: str, index: int, image: Image.Image, dpi: int) -> PageImage:
    stream = BytesIO()
    image.convert("RGB").save(stream, format="PNG")
    return PageImage(document_id, index, image.width, image.height, dpi, stream.getvalue())


def load_image(path: Path | None = None, data: bytes | None = None) -> Document:
    content = path.read_bytes() if path else data
    if not content:
        raise DomainError("image_invalid")
    document = Document(
        str(path) if path else None,
        hashlib.sha256(content).hexdigest(),
        "image" if path else "clipboard",
    )
    with Image.open(BytesIO(content)) as image:
        page = make_page(document.id, 0, ImageOps.exif_transpose(image), 200)
    document.pages.append(page)
    return document


def pdf_count(path: Path) -> int:
    with pdfium.PdfDocument(path) as pdf:
        return len(pdf)


def pdf_preview(path: Path, index: int) -> bytes:
    with pdfium.PdfDocument(path) as pdf:
        page = pdf[index]
        try:
            bitmap = page.render(scale=0.25)
            try:
                return make_page("preview", index, bitmap.to_pil(), 18).png_bytes
            finally:
                bitmap.close()
        finally:
            page.close()


def load_pdf(path: Path, pages: list[int], dpi: int = 200) -> Document:
    if not 72 <= dpi <= 600:
        raise DomainError("dpi")
    document = Document(str(path), hashlib.sha256(path.read_bytes()).hexdigest(), "pdf")
    with pdfium.PdfDocument(path) as pdf:
        document.page_count = len(pdf)
        for index in dict.fromkeys(pages):
            page = pdf[index]
            try:
                bitmap = page.render(scale=dpi / 72)
                try:
                    document.pages.append(make_page(document.id, index, bitmap.to_pil(), dpi))
                finally:
                    bitmap.close()
            finally:
                page.close()
    return document
