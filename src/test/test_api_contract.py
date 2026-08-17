"""API contract: POST /parse, GET /tasks/{id}, GET /export, GET /images, GET /models."""

import io
import time

import fitz
from fastapi.testclient import TestClient

from src.server import app
from src.store import task_store

client = TestClient(app)


def _clear_store():
    task_store._store.clear()


def _make_pdf():
    buf = io.BytesIO()
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "contract test content")
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_post_parse_contract():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("c.pdf", _make_pdf(), "application/pdf")})
    assert resp.status_code == 200
    body = resp.json()
    for k in ("task_id", "filename", "status", "total_pages", "created_at"):
        assert k in body, f"missing {k}"
    assert body["status"] == "pending"


def test_get_task_not_found():
    _clear_store()
    resp = client.get("/api/v1/tasks/nonexistent-id-12345")
    assert resp.status_code == 404
    assert resp.json()["code"] == "TASK_NOT_FOUND"


def test_get_task_returns_full_result():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("g.pdf", _make_pdf(), "application/pdf")})
    task_id = resp.json()["task_id"]
    got = client.get(f"/api/v1/tasks/{task_id}").json()
    assert got["task_id"] == task_id
    assert "pages" in got
    assert "errors" in got


def test_export_invalid_format():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("h.pdf", _make_pdf(), "application/pdf")})
    task_id = resp.json()["task_id"]
    r = client.get(f"/api/v1/tasks/{task_id}/export?format=xml")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_FORMAT"


def test_export_not_found():
    _clear_store()
    r = client.get("/api/v1/tasks/no-such-id/export?format=json")
    assert r.status_code == 404


def test_export_before_ready():
    """Create a task directly in the store at 'pending' (no background parse),
    so the 409 path is exercised deterministically (U3 spec §4.5)."""
    _clear_store()
    from datetime import datetime, timezone
    from src.models.schemas import ParseResult
    from src.utils import unique_id
    task_id = unique_id.gen_task_id()
    result = ParseResult(
        task_id=task_id, filename="pending.pdf", status="pending",
        total_pages=1, created_at=datetime.now(timezone.utc).isoformat(),
    )
    task_store.create(task_id, result)
    r = client.get(f"/api/v1/tasks/{task_id}/export?format=json")
    assert r.status_code == 409
    assert r.json()["code"] == "TASK_NOT_READY"


def test_export_json_and_markdown_after_completion():
    _clear_store()
    resp = client.post("/api/v1/parse", files={"file": ("j.pdf", _make_pdf(), "application/pdf")})
    task_id = resp.json()["task_id"]

    deadline = time.time() + 30
    while time.time() < deadline:
        r = task_store.get(task_id)
        if r and r.status in ("completed", "partial", "failed"):
            break
        time.sleep(0.3)

    r_json = client.get(f"/api/v1/tasks/{task_id}/export?format=json")
    assert r_json.status_code == 200
    assert r_json.headers["content-type"].startswith("application/json")
    assert b"task_id" in r_json.content

    r_md = client.get(f"/api/v1/tasks/{task_id}/export?format=markdown")
    assert r_md.status_code == 200
    assert r_md.headers["content-type"].startswith("text/markdown")


def test_get_models():
    _clear_store()
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    assert "default" in body


def test_get_image_not_found():
    _clear_store()
    r = client.get("/api/v1/tasks/no-such-id/images/0/0")
    assert r.status_code == 404
    assert r.json()["code"] == "IMAGE_NOT_FOUND"
