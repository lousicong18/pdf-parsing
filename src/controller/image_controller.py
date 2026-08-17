"""GET /api/v1/tasks/{task_id}/images/{page}/{index} — cropped image bytes."""

from fastapi import APIRouter
from fastapi.responses import Response

from src.models.schemas import ErrorResponse
from src.store import image_cache
from src.utils.errors import AppError

router = APIRouter(tags=["images"])


@router.get(
    "/tasks/{task_id}/images/{page}/{index}",
    responses={404: {"model": ErrorResponse}},
)
def get_image(task_id: str, page: int, index: int):
    data = image_cache.get(task_id, page, index)
    if data is None:
        raise AppError(code="IMAGE_NOT_FOUND", detail="图片不存在或已过期", status_code=404)
    return Response(content=data, media_type="image/png")
