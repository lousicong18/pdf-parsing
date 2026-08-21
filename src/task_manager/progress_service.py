from datetime import datetime, timezone
from typing import Optional

from src.models.schemas import Block, PageFeatures, PageRaw, PageResult, TaskError, TaskMetrics
from src.store import task_store


def mark_parsing(task_id: str) -> None:
    task_store.update_status(task_id, "parsing")


def update_page_done(
    task_id: str,
    page: int,
    page_type: str,
    blocks: list[Block],
    features: Optional[PageFeatures] = None,
    classification_log: Optional[list[str]] = None,
    raw: Optional[PageRaw] = None,
) -> None:
    page_result = PageResult(
        page=page,
        type=page_type,  # type: ignore[arg-type]
        blocks=blocks,
        features=features,
        classification_log=classification_log or [],
        raw=raw,
    )
    task_store.append_page(task_id, page_result)
    task_store.update_progress(task_id, page)


def add_error(task_id: str, page: Optional[int], msg: str) -> None:
    task_store.append_error(task_id, TaskError(page=page, message=msg))


def add_cost(task_id: str, cost: float) -> None:
    task_store.add_cost(task_id, cost)


def set_metrics(task_id: str, metrics: TaskMetrics) -> None:
    task_store.set_metrics(task_id, metrics)


def finish(task_id: str, status: str) -> None:
    finished_at = datetime.now(timezone.utc).isoformat()
    task_store.set_finished(task_id, status, finished_at)
