"""Error fallback: X1 corrupt file, X2 VLM failure, X3 empty response."""

import io
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from src.server import app
from src.store import task_store

client = TestClient(app)


def _clear_store():
    task_store._store.clear()


def test_x1_corrupt_file_rejects():
    """Non-PDF content (wrong magic bytes) must be rejected even with .pdf extension (U1)."""
    _clear_store()
    resp = client.post("/api/v1/parse",
                       files={"file": ("bad.pdf", b"not a pdf at all", "application/pdf")})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_x1_fitz_open_failure_marks_failed():
    _clear_store()
    pdf_bytes = io.BytesIO()
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "content")
    doc.save(pdf_bytes)
    doc.close()
    data = pdf_bytes.getvalue()

    _clear_store()
    # get_page_count (inside create_task) fails on corrupt file -> 400 PARSE_FAILED (X1)
    with patch("src.task_manager.task_service.fitz.open", side_effect=RuntimeError("corrupt")):
        resp = client.post("/api/v1/parse", files={"file": ("e.pdf", data, "application/pdf")})
    assert resp.status_code == 400
    assert resp.json()["code"] == "PARSE_FAILED"


def test_x1_non_pdf_extension_rejected():
    _clear_store()
    resp = client.post("/api/v1/parse",
                       files={"file": ("doc.txt", b"%PDF-1.4 fake but wrong ext", "text/plain")})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_x2_vlm_failure_scan_marks_partial(scan_pdf):
    """X2: when VLM OCR fails on a scan page, the page must be marked
    '扫描件未识别（VLM 调用失败）' and an error recorded (status -> partial)."""
    _clear_store()
    from datetime import datetime, timezone
    from unittest.mock import patch
    from src.models.schemas import ParseResult
    from src.parser import scan

    # create the task so progress_service.add_error can record into it
    task_store.create("task-x2", ParseResult(
        task_id="task-x2", filename="s.pdf", status="parsing",
        total_pages=1, created_at=datetime.now(timezone.utc).isoformat(),
    ))

    doc = fitz.open(scan_pdf)
    page = doc.load_page(0)
    with patch("src.parser.vlm._call_vlm", side_effect=RuntimeError("vlm timeout")):
        blocks = scan.process_scan_page(page, "task-x2", 0, None)
    doc.close()

    assert len(blocks) == 1
    assert "VLM 调用失败" in blocks[0].content
    r = task_store.get("task-x2")
    assert any("VLM" in e.message for e in r.errors)


def test_file_too_large_rejected():
    """File exceeding MAX_FILE_MB must be rejected (U2). Build a real >limit
    payload so the size check triggers on actual bytes read."""
    _clear_store()
    from src.utils import env as _env
    old = _env.MAX_FILE_MB
    _env.MAX_FILE_MB = 0  # any non-empty file now exceeds the limit
    try:
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024)
        resp = client.post("/api/v1/parse",
                           files={"file": ("big.pdf", big, "application/pdf")})
    finally:
        _env.MAX_FILE_MB = old
    assert resp.status_code == 400
    assert resp.json()["code"] == "FILE_TOO_LARGE"
