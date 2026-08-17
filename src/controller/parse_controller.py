"""POST /api/v1/parse — upload PDF, create task, launch background parse."""

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from src.models.schemas import CreateTaskResponse, ErrorResponse
from src.task_manager import task_service
from src.utils import env
from src.utils.errors import AppError

router = APIRouter(tags=["parse"])


@router.post(
    "/parse",
    response_model=CreateTaskResponse,
    responses={400: {"model": ErrorResponse}},
)
def parse(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    vlm_model: str = Form(default=""),
) -> CreateTaskResponse:
    content = file.file.read()
    model = vlm_model if vlm_model else None
    try:
        response, pdf_path = task_service.create_task(content, file.filename or "upload.pdf", model)
    except ValueError as e:
        raise _to_app_error(e)
    background_tasks.add_task(task_service.run_parse, response.task_id, pdf_path, model)
    return response


def _to_app_error(e: ValueError) -> AppError:
    msg = str(e)
    if msg == "INVALID_FILE_TYPE":
        return AppError(code="INVALID_FILE_TYPE", detail="仅支持 PDF 文件", status_code=400)
    if msg == "FILE_TOO_LARGE":
        return AppError(code="FILE_TOO_LARGE", detail=f"文件大小超过限制（最大 {env.MAX_FILE_MB}MB）", status_code=400)
    if isinstance(msg, str) and msg.startswith("PARSE_FAILED"):
        return AppError(code="PARSE_FAILED", detail="文件损坏或无法解析", status_code=400)
    return AppError(code="BAD_REQUEST", detail=msg, status_code=400)
