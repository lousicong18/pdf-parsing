import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from src.utils import env
from src.utils.env import project_root


class ModelConfig(BaseModel):
    name: str
    base_url: str
    api_key: str
    model: str
    thinking: Optional[dict] = None


def load_registry(path: Optional[str] = None) -> dict[str, ModelConfig]:
    """Load models.json; fall back to .env single model when missing."""
    reg_path = Path(path) if path else project_root() / env.VLM_MODELS_FILE
    if reg_path.is_file():
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        return {
            name: ModelConfig(**cfg) for name, cfg in data.items()
        }
    # fallback: single model from .env
    return {
        env.VLM_DEFAULT_MODEL: ModelConfig(
            name=env.VLM_DEFAULT_MODEL,
            base_url=env.VLM_BASE_URL,
            api_key=env.VLM_API_KEY,
            model=env.VLM_MODEL,
        )
    }


def get_model(name: Optional[str] = None) -> ModelConfig:
    registry = load_registry()
    key = name or env.VLM_DEFAULT_MODEL
    if key in registry:
        return registry[key]
    if registry:
        return next(iter(registry.values()))
    raise ValueError("no VLM model configured")


def list_models() -> list[str]:
    return list(load_registry().keys())
