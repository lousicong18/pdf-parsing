"""Scan page: render full page -> VLM OCR."""

from typing import Optional

from src.models.schemas import Block, PageType
from src.parser import vlm
from src.task_manager import progress_service
from src.utils import env


def process_scan_page(
    page, task_id: str, page_num: int, metrics_ctx, model_name: Optional[str] = None,
) -> list[Block]:
    bbox = [0, 0, page.rect.width, page.rect.height]
    try:
        pix = page.get_pixmap(dpi=env.VLM_OCR_DPI)
        image_bytes = pix.tobytes("png")
        text = vlm.vlm_ocr(image_bytes, metrics_ctx, model_name)
    except Exception as e:
        progress_service.add_error(task_id, page_num, f"VLM OCR failed: {e}")
        text = "扫描件未识别（VLM 调用失败）"
    return [
        Block(
            type="text",  # type: ignore[arg-type]
            bbox=bbox,
            page_type="scan",  # type: ignore[arg-type]
            order=0,
            text=text,
            content=text,
        )
    ]
