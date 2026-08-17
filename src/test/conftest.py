"""Shared fixtures: programmatically generated PDFs for each page type."""

import os
from pathlib import Path

import fitz
import pytest

TMP = Path("/tmp/pdf_parse_tests")
TMP.mkdir(parents=True, exist_ok=True)


def _make_text_page(doc):
    p = doc.new_page(width=612, height=792)
    text = "\n".join(f"This is line {i} of a pure text page with enough words to form a block." for i in range(15))
    p.insert_text((72, 72), text)


def _make_table_page(doc):
    p = doc.new_page(width=612, height=792)
    rows, cols = 8, 5
    x0, y0 = 72, 120
    cell_w, cell_h = 90, 36
    header = [f"Col{i}" for i in range(cols)]
    for c, h in enumerate(header):
        p.insert_text((x0 + c * cell_w + 5, y0 - 15), h)
    for r in range(rows):
        for c in range(cols):
            cx = x0 + c * cell_w
            cy = y0 + r * cell_h
            p.draw_rect(fitz.Rect(cx, cy, cx + cell_w, cy + cell_h))
            p.insert_text((cx + 5, cy + 20), f"R{r}C{c}")


def _make_mixed_page(doc):
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 72), "Section header\n\nThis page has both text and an image below.\nParagraph two with detail.")
    rect = fitz.Rect(150, 300, 450, 500)
    p.draw_rect(rect, color=(0.2, 0.5, 0.8), fill=(0.7, 0.85, 1.0))
    p.draw_line((150, 300), (450, 500), color=(0.1, 0.3, 0.6))
    p.draw_line((450, 300), (150, 500), color=(0.1, 0.3, 0.6))
    p.insert_text((rect.x0 + 20, rect.y0 + 60), "FIGURE")


def _make_scan_page(doc):
    """Build a scan-like page: a page that has only a full-page raster image
    and no extractable text (simulates a scanned page)."""
    scratch = fitz.open()
    sp = scratch.new_page(width=612, height=792)
    for i in range(30):
        sp.insert_text((72, 60 + i * 22), f"Scan line {i} content that simulates a rendered page image.")
    pix = sp.get_pixmap(dpi=100)
    scratch.close()
    p = doc.new_page(width=612, height=792)
    p.insert_image(fitz.Rect(0, 0, 612, 792), pixmap=pix)


@pytest.fixture
def text_pdf():
    path = TMP / "text.pdf"
    doc = fitz.open()
    _make_text_page(doc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def table_pdf():
    path = TMP / "table.pdf"
    doc = fitz.open()
    _make_table_page(doc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def mixed_pdf():
    path = TMP / "mixed.pdf"
    doc = fitz.open()
    _make_mixed_page(doc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def scan_pdf():
    path = TMP / "scan.pdf"
    doc = fitz.open()
    _make_scan_page(doc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def multi_pdf():
    path = TMP / "multi.pdf"
    doc = fitz.open()
    _make_text_page(doc)
    _make_table_page(doc)
    _make_mixed_page(doc)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def corrupt_pdf():
    path = TMP / "corrupt.pdf"
    path.write_bytes(b"NOT a PDF file at all %PDF-broken")
    return str(path)
