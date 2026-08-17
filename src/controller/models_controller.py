"""GET /api/v1/models — list available VLM models."""

from fastapi import APIRouter

from src.utils import env, vlm_models

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> dict:
    return {"models": vlm_models.list_models(), "default": env.VLM_DEFAULT_MODEL}
