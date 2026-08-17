"""GET /api/v1/tasks/{task_id}/export?format=json|markdown — export."""

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, Response

from src.models.schemas import ErrorResponse, ParseResult
from src.store import task_store
from src.utils.errors import AppError

router = APIRouter(tags=["export"])

_TERMINAL = {"completed", "partial", "failed"}


@router.get(
    "/tasks/{task_id}/export",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def export(task_id: str, fmt: str = Query(default="json", alias="format")):
    if fmt not in ("json", "markdown"):
        raise AppError(code="INVALID_FORMAT", detail="不支持的导出格式，仅支持 json / markdown", status_code=400)
    result = task_store.get(task_id)
    if result is None:
        raise AppError(code="TASK_NOT_FOUND", detail="任务不存在或已过期", status_code=404)
    if result.status not in _TERMINAL:
        raise AppError(code="TASK_NOT_READY", detail="任务尚未完成，请稍后再试", status_code=409)
    if fmt == "json":
        return Response(
            content=result.model_dump_json(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{task_id}.json"'},
        )
    md = _build_markdown(result)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{task_id}.md"'},
    )


def _build_markdown(result: ParseResult) -> str:
    lines: list[str] = [f"# {result.filename}\n"]
    for page in result.pages:
        lines.append(f"\n## 第 {page.page} 页 · 类型：{page.type}\n")
        for block in page.blocks:
            lines.append(block.content or "")
            lines.append("")
    return "\n".join(lines)
