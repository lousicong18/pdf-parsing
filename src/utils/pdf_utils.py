import os
from pathlib import Path

import fitz

from src.utils import env

PDF_MAGIC = b"%PDF"


def validate_upload(filename: str, size_bytes: int, content: bytes = b"") -> None:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("INVALID_FILE_TYPE")
    # U1: reject non-PDF formats by magic bytes (extension alone is not enough)
    if content and not content.startswith(PDF_MAGIC):
        raise ValueError("INVALID_FILE_TYPE")
    if size_bytes > env.MAX_FILE_MB * 1024 * 1024:
        raise ValueError("FILE_TOO_LARGE")


def save_temp_pdf(file_bytes: bytes, task_id: str) -> str:
    tmp_dir = Path("/tmp/pdf_parse")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / f"{task_id}.pdf"
    path.write_bytes(file_bytes)
    return str(path)


def get_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()


def remove_temp_pdf(pdf_path: str) -> None:
    if pdf_path and os.path.exists(pdf_path):
        os.remove(pdf_path)


def page_to_png(page, dpi: int = 150) -> bytes:
    """Render a fitz Page to PNG bytes."""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")
