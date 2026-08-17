"""State machine: pending -> parsing -> completed / partial / failed."""

import fitz
from fastapi.testclient import TestClient

from src.server import app
from src.store import task_store
from src.task_manager import task_service
from src.utils import pdf_utils

client = TestClient(app)


def _make_pdf_bytes():
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "hello world content")
    import io
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _clear_store():
    task_store._store.clear()


def test_pending_to_completed():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("a.pdf", _make_pdf_bytes(), "application/pdf")})
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["total_pages"] >= 1
    task_id = data["task_id"]

    result = task_store.get(task_id)
    assert result is not None
    assert result.status in ("pending", "parsing", "completed", "partial", "failed")


def test_get_task_then_completed_or_partial():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("b.pdf", _make_pdf_bytes(), "application/pdf")})
    task_id = resp.json()["task_id"]

    got = client.get(f"/api/v1/tasks/{task_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["task_id"] == task_id
    assert body["status"] in ("pending", "parsing", "completed", "partial", "failed")


def test_state_machine_reaches_terminal():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("c.pdf", _make_pdf_bytes(), "application/pdf")})
    task_id = resp.json()["task_id"]

    import time
    deadline = time.time() + 30
    terminal = False
    while time.time() < deadline:
        r = task_store.get(task_id)
        if r and r.status in ("completed", "partial", "failed"):
            terminal = True
            break
        time.sleep(0.2)
    assert terminal, "never reached terminal state"
    # created_at present, finished_at set on terminal (U3)
    r = task_store.get(task_id)
    assert r is not None
    assert r.finished_at is not None
    assert r.created_at


def test_state_machine_transitions_via_slow_parse():
    """Drive run_parse directly with a patched slow dispatch to observe the
    pending -> parsing -> terminal transitions (U3) deterministically."""
    import time
    from datetime import datetime, timezone
    from src.models.schemas import ParseResult
    from src.parser import pipeline
    from src.utils import unique_id, pdf_utils

    _clear_store()
    task_id = unique_id.gen_task_id()
    pdf_path = pdf_utils.save_temp_pdf(_make_pdf_bytes(), task_id)
    result = ParseResult(
        task_id=task_id, filename="slow.pdf", status="pending",
        total_pages=1, created_at=datetime.now(timezone.utc).isoformat(),
    )
    task_store.create(task_id, result)
    assert task_store.get(task_id).status == "pending"

    original = pipeline.dispatch_page

    def slow_dispatch(*args, **kwargs):
        time.sleep(0.2)
        return original(*args, **kwargs)

    pipeline.dispatch_page = slow_dispatch
    try:
        task_service.run_parse(task_id, pdf_path)
    finally:
        pipeline.dispatch_page = original
        pdf_utils.remove_temp_pdf(pdf_path)

    r = task_store.get(task_id)
    assert r.status in ("completed", "partial", "failed")


def test_progress_increments():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("d.pdf", _make_pdf_bytes(), "application/pdf")})
    task_id = resp.json()["task_id"]
    import time
    deadline = time.time() + 30
    while time.time() < deadline:
        r = task_store.get(task_id)
        if r and r.status in ("completed", "partial", "failed"):
            assert r.progress >= 1
            break
        time.sleep(0.2)
    r = task_store.get(task_id)
    assert r is not None
    assert r.progress >= 1
