"""Mixed (text + image) page processing."""

from typing import Optional

from src.models.schemas import Block, ImageData, PageType
from src.parser import extract_text, vlm
from src.store import image_cache
from src.task_manager import progress_service
from src.utils import column_detection


def extract_and_describe_images(
    page, task_id: str, page_num: int, doc, metrics_ctx, model_name: Optional[str] = None,
) -> list[Block]:
    blocks: list[Block] = []
    images = page.get_images(full=True) or []
    for index, img in enumerate(images):
        xref = img[0]
        try:
            image_bytes = doc.extract_image(xref)["image"]
        except Exception:
            progress_service.add_error(task_id, page_num, f"extract image {index} failed")
            continue
        bbox = _image_bbox(page, img)
        image_cache.put(task_id, page_num, index, image_bytes)
        url = f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"
        try:
            desc = vlm.vlm_describe(image_bytes, metrics_ctx, model_name)
        except Exception as e:
            progress_service.add_error(task_id, page_num, f"VLM describe failed: {e}")
            desc = "图片未识别（VLM 调用失败）"
        blocks.append(
            Block(
                type="image",  # type: ignore[arg-type]
                bbox=bbox,
                page_type="mixed",  # type: ignore[arg-type]
                order=index,
                image=ImageData(description=desc, image_url=url),
                content=desc,
                image_url=url,
            )
        )
    return blocks


def _image_bbox(page, img) -> list[float]:
    try:
        rects = page.get_image_rects(img[0])
        if rects:
            r = rects[0]
            return [r.x0, r.y0, r.x1, r.y1]
    except Exception:
        pass
    try:
        bb = page.get_image_bbox(img)
        return [bb.x0, bb.y0, bb.x1, bb.y1]
    except Exception:
        return [0, 0, 0, 0]


def process_mixed_page(
    page, task_id: str, page_num: int, doc, metrics_ctx, model_name: Optional[str] = None,
) -> list[Block]:
    text_blocks = extract_text.extract_text(page, "mixed")  # type: ignore[arg-type]
    image_blocks = extract_and_describe_images(page, task_id, page_num, doc, metrics_ctx, model_name)
    merged = text_blocks + image_blocks
    return _sort_reading_order(merged)


def _sort_reading_order(blocks: list[Block]) -> list[Block]:
    if len(blocks) <= 1:
        return blocks
    n_cols = column_detection.column_detection(blocks)
    if n_cols <= 1:
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    else:
        xs = [b.bbox[0] for b in blocks]
        width = max(xs) - min(xs) if xs else 0
        tol = max(width * 0.1, 20.0)
        columns: dict[int, list[Block]] = {}
        for b in blocks:
            col = int((b.bbox[0] - min(xs)) / max(tol, 1))
            columns.setdefault(col, []).append(b)
        ordered: list[Block] = []
        for col in sorted(columns.keys()):
            group = columns[col]
            group.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            ordered.extend(group)
        blocks = ordered
    for i, b in enumerate(blocks):
        b.order = i
    return blocks
