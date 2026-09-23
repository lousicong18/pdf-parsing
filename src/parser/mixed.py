"""Mixed (text + image) page processing."""

import logging
from typing import Optional

from src.models.schemas import Block, ImageData, PageType
from src.parser import vlm
from src.store import image_cache
from src.task_manager import progress_service
from src.utils import pdf_utils

logger = logging.getLogger("pdf_parser")


def extract_and_describe_images(
    page, task_id: str, page_num: int, doc, metrics_ctx, model_name: Optional[str] = None,
) -> list[Block]:
    blocks: list[Block] = []
    images = page.get_images(full=True) or []
    page_area = page.rect.width * page.rect.height
    for index, img in enumerate(images):
        xref = img[0]
        try:
            image_bytes = doc.extract_image(xref)["image"]
        except Exception:
            progress_service.add_error(task_id, page_num, f"extract image {index} failed")
            continue
        bbox = _image_bbox(page, img)
        if page_area > 0 and bbox:
            img_area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
            if img_area >= 0.8 * page_area:
                continue
        image_cache.put(task_id, page_num, index, image_bytes)
        url = f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"
        try:
            desc = vlm.vlm_describe(image_bytes, metrics_ctx, model_name)
        except Exception as e:
            progress_service.add_error(task_id, page_num, f"VLM describe failed: {e}")
            desc = "图片未识别（VLM 调用失败）"
        blocks.append(
            Block(
                type="image",
                bbox=bbox,
                page_type="mixed",
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


def _is_chart_table_page(page) -> bool:
    """Detect chart page by counting non-background fills."""
    drawings = page.get_drawings() or []
    filled = 0
    colors = set()
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        if fill[0] > 0.85 and fill[1] > 0.85 and fill[2] > 0.85:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        if w < 2 or h < 2:
            continue
        filled += 1
        colors.add((round(fill[0], 1), round(fill[1], 1), round(fill[2], 1)))
    return filled > 10 or len(colors) >= 3


_CHART_DATA_PROMPT = (
    "分析这个PDF页面,提取所有文字和图表数据。\n\n"
    "严格要求:\n"
    "1. 普通文字正常输出\n"
    "2. 每个图表(柱状图/折线图)下方必须输出一个 markdown 表格,列出逐年数值\n"
    "3. 表格格式: | 年份 | 数据1 | 数据2 | ... |\n"
    "4. 无法精确读取的数值用 ~xx 标记\n"
    "5. 不要输出没有表格的纯文字描述\n\n"
    "输出必须包含表格,这是强制要求。用中文输出。"
)

_TABLE_FOLLOWUP_PROMPT = (
    "请将上述图表描述转换为 markdown 表格格式。\n"
    "每个图表一个表格,表头为年份和各数据系列,数据根据纵轴刻度估算。\n"
    "格式: | 年份 | 数据1 | 数据2 | ... |\n"
    "无法精确读取的数值用 ~xx 标记。"
)


def _has_table(text: str) -> bool:
    """Check if text contains a markdown table."""
    return "|" in text and "---" in text


def _vlm_ocr_full_text(page, metrics_ctx, model_name) -> str:
    """OCR the full page. Retry + follow-up to ensure table output."""
    img_bytes = pdf_utils.page_to_png(page, dpi=200)
    best = ""
    for attempt in range(3):
        try:
            text = vlm.vlm_ocr(img_bytes, metrics_ctx, model_name, prompt=_CHART_DATA_PROMPT)
        except Exception as e:
            logger.error("OCR failed: %s", e)
            continue
        if text and _has_table(text):
            return text
        if len(text) > len(best):
            best = text
    # Fallback: follow-up to convert description into tables
    if best:
        try:
            followup = vlm.vlm_ocr(
                img_bytes, metrics_ctx, model_name,
                prompt=f"已识别内容:\n{best}\n\n{_TABLE_FOLLOWUP_PROMPT}",
            )
            if followup and _has_table(followup):
                return best + "\n\n" + followup
        except Exception as e:
            logger.error("Follow-up failed: %s", e)
    return best


def process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name):
    """Process chart-embedded table page: OCR outputs full markdown content."""
    ocr_text = _vlm_ocr_full_text(page, metrics_ctx, model_name)
    if ocr_text and len(ocr_text) > 20:
        bbox = [0, 0, page.rect.width, page.rect.height]
        block = Block(type="table", bbox=bbox, page_type="mixed", order=0,
                      table=None, content=ocr_text)
        return [block], "chart_table_ocr"
    logger.warning("Chart table extraction failed for page %s", page_num)
    progress_service.add_error(task_id, page_num, "chart table extraction failed")
    return [], "chart_table_failed"
