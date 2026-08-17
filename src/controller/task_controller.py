"""GET /api/v1/tasks — list task history; GET /api/v1/tasks/{task_id} — get full parse result."""

from fastapi import APIRouter

from src.models.schemas import ErrorResponse, ParseResult, TaskSummary
from src.store import task_store
from src.utils.errors import AppError

router = APIRouter(tags=["tasks"])


@router.get(
    "/tasks",
    response_model=list[TaskSummary],
)
def list_tasks() -> list[TaskSummary]:
    """List task history (summary for history page)."""
    return [task_store.summary(tid) for tid in task_store.list_ids()]


@router.get(
    "/tasks/{task_id}",
    response_model=ParseResult,
    responses={404: {"model": ErrorResponse}},
)
def get_task(task_id: str) -> ParseResult:
    result = task_store.get(task_id)
    if result is None:
        raise AppError(code="TASK_NOT_FOUND", detail="任务不存在或已过期", status_code=404)
    return result
