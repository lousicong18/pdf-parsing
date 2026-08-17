import json
import threading
from pathlib import Path
from typing import Optional

from src.models.schemas import PageResult, ParseResult, TaskError, TaskMetrics
from src.utils.env import project_root

_store: dict[str, ParseResult] = {}
_lock = threading.Lock()

_DB_PATH = project_root() / ".task_store.json"


def _persist() -> None:
    """Flush in-memory store to disk."""
    try:
        data = {tid: r.model_dump() for tid, r in _store.items()}
        _DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[task_store] persist failed: {e}")


def _load() -> None:
    """Load store from disk on startup."""
    if not _DB_PATH.exists():
        return
    try:
        data = json.loads(_DB_PATH.read_text(encoding="utf-8"))
        for tid, raw in data.items():
            _store[tid] = ParseResult(**raw)
        print(f"[task_store] loaded {len(_store)} tasks from disk")
    except Exception as e:
        print(f"[task_store] load failed: {e}")


_load()


def create(task_id: str, result: ParseResult) -> None:
    with _lock:
        _store[task_id] = result
        _persist()


def list_ids() -> list[str]:
    with _lock:
        return list(_store.keys())


def get(task_id: str) -> Optional[ParseResult]:
    with _lock:
        return _store.get(task_id)


def update_status(task_id: str, status: str) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].status = status  # type: ignore[assignment]
            _persist()


def update_progress(task_id: str, progress: int) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].progress = progress
            _persist()


def append_page(task_id: str, page_result: PageResult) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].pages.append(page_result)
            _persist()


def append_error(task_id: str, task_error: TaskError) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].errors.append(task_error)
            _persist()


def add_cost(task_id: str, cost: float) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].cost_usd += cost
            _persist()


def set_finished(task_id: str, status: str, finished_at: str) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].status = status  # type: ignore[assignment]
            _store[task_id].finished_at = finished_at
            _persist()


def set_metrics(task_id: str, metrics: TaskMetrics) -> None:
    with _lock:
        if task_id in _store:
            _store[task_id].metrics = metrics
            _persist()


def summary(task_id: str):
    """Return a lightweight TaskSummary for history listing."""
    with _lock:
        r = _store.get(task_id)
    if r is None:
        return None
    return {
        "task_id": r.task_id,
        "filename": r.filename,
        "status": r.status,
        "total_pages": r.total_pages,
        "cost_usd": r.cost_usd,
        "created_at": r.created_at,
        "finished_at": r.finished_at,
    }
