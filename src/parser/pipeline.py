"""Page dispatch: classify features, then route by page type.

Returns (blocks, features) — features is the single source of truth written
into PageResult.features by the caller.
"""

from typing import Optional

from src.models.schemas import Block, ImageData, PageFeatures, PageRaw
from src.parser import classify, extract_table, extract_text, mixed, scan, mineru_parser, vlm
from src.store import image_cache
from src.task_manager import progress_service
from src.utils import column_detection


def dispatch_page(
    page,
    page_type: str,
    task_id: str,
    page_num: int,
    doc,
    prev_type: Optional[str] = None,
    metrics_ctx=None,
    model_name: Optional[str] = None,
    features: Optional[PageFeatures] = None,
    prev_header: Optional[list[str]] = None,
) -> tuple[list[Block], PageFeatures, PageRaw]:
    if features is None:
        features, raw = classify.classify_features(page)
    else:
        raw = PageRaw()
    blocks = []

    if page_type == "text":
        blocks = _dispatch_text_table(page, page_type, doc.name, page_num)
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "table":
        blocks = _dispatch_text_table(page, page_type, doc.name, page_num)
        # 表格页面也可能有表格外的图片，补充提取
        blocks = _extract_outside_images(blocks, page, task_id, page_num, doc, metrics_ctx, model_name)
    elif page_type == "mixed":
        if mixed._is_chart_table_page(page):
            blocks, _ = mixed.process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name)
        else:
            blocks = _dispatch_mixed_with_images(page, page_type, doc, task_id, page_num, metrics_ctx, model_name)
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "scan":
        blocks = scan.process_scan_page(page, task_id, page_num, metrics_ctx, model_name)
    return blocks, features, raw


def _dispatch_text_table(page, page_type: str, pdf_path: str, page_num: int,
                         task_id: str = "", doc=None, metrics_ctx=None,
                         model_name: Optional[str] = None) -> list[Block]:
    """Route text/table/mixed pages to MinerU if available, else fallback."""
    if mineru_parser.is_mineru_available():
        blocks = mineru_parser.process_with_mineru(pdf_path, page_num, page_type)
        if blocks:
            # 对 MinerU 输出的 image block 调 VLM 描述
            if page_type == "mixed" and task_id and doc:
                blocks = _describe_mineru_images(blocks, page, task_id, page_num, doc, metrics_ctx, model_name)
            return blocks
    # Fallback to original extractors
    if page_type == "text":
        return extract_text.extract_text(page, page_type)
    return extract_table.extract_tables(
        page, page_type, pdf_path, page_num, None, None, None, None, None,
    )


def _dispatch_mixed_with_images(page, page_type: str, doc, task_id: str, page_num: int,
                                 metrics_ctx, model_name: Optional[str]) -> list[Block]:
    """处理普通图文页：MinerU 提取结构 + VLM 描述图片。"""
    # 1. MinerU 提取文字/结构
    blocks: list[Block] = []
    if mineru_parser.is_mineru_available():
        blocks = mineru_parser.process_with_mineru(doc.name, page_num, page_type)
    if not blocks:
        # fallback 到原提取器
        text_blocks = extract_text.extract_text(page, page_type)
        image_blocks = mixed.extract_and_describe_images(page, task_id, page_num, doc, metrics_ctx, model_name)
        return _sort_reading_order(text_blocks + image_blocks)
    # 2. MinerU 提取成功后，补充页面中的图片（MinerU 可能忽略小图）
    page_images = page.get_images(full=True) or []
    if not page_images:
        return blocks
    existing_img_bboxes = [b.bbox for b in blocks if b.type == "image"]
    new_image_blocks: list[Block] = []
    for idx, img in enumerate(page_images):
        bbox = mixed._image_bbox(page, img)
        # 已有 MinerU 处理的图片则跳过
        if any(_bbox_overlap_ratio(bbox, eb) > 0.5 for eb in existing_img_bboxes if eb):
            continue
        try:
            image_bytes = doc.extract_image(img[0])["image"]
        except Exception:
            continue
        image_cache.put(task_id, page_num, idx, image_bytes)
        url = f"/api/v1/tasks/{task_id}/images/{page_num}/{idx}"
        try:
            desc = vlm.vlm_describe(image_bytes, metrics_ctx, model_name)
        except Exception:
            desc = "图片未识别（VLM 调用失败）"
        new_image_blocks.append(
            Block(
                type="image",
                bbox=bbox,
                page_type=page_type,
                order=len(blocks) + len(new_image_blocks),
                image=ImageData(description=desc, image_url=url),
                image_url=url,
                content=desc,
            )
        )
    if new_image_blocks:
        blocks = blocks + new_image_blocks
        blocks = _sort_reading_order(blocks)
    return blocks


def _extract_outside_images(
    blocks: list[Block],
    page,
    task_id: str,
    page_num: int,
    doc,
    metrics_ctx,
    model_name: Optional[str] = None,
) -> list[Block]:
    """提取表格外的图片，追加到 blocks 中。"""
    image_blocks = mixed.extract_and_describe_images(page, task_id, page_num, doc, metrics_ctx, model_name)
    if not image_blocks:
        return blocks
    table_bboxes = [b.bbox for b in blocks if b.type == "table"]
    # 过滤：图片 bbox 在表格内或与表格重叠 >= 50% 则跳过（背景图已在 extract_and_describe_images 中过滤）
    outside_images = [
        b for b in image_blocks
        if not _bbox_inside_any(b.bbox, table_bboxes)
        and max((_bbox_overlap_ratio(b.bbox, tb) for tb in table_bboxes), default=0) < 0.5
    ]
    if outside_images:
        blocks = blocks + outside_images
        blocks = _sort_reading_order(blocks)
    return blocks


def _bbox_area(bbox: list[float]) -> float:
    if len(bbox) < 4:
        return 0.0
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _bbox_inside_any(bbox: list[float], containers: list[list[float]], tolerance: float = 5.0) -> bool:
    """判断 bbox 是否被任一 container bbox 完全包含（允许 tolerance 误差）。"""
    if not bbox or len(bbox) < 4:
        return False
    bx0, by0, bx1, by1 = bbox
    for c in containers:
        if len(c) < 4:
            continue
        cx0, cy0, cx1, cy1 = c
        if (bx0 >= cx0 - tolerance and by0 >= cy0 - tolerance
                and bx1 <= cx1 + tolerance and by1 <= cy1 + tolerance):
            return True
    return False


def _bbox_overlap_ratio(bbox: list[float], container: list[float]) -> float:
    """计算 bbox 与 container 的重叠面积占 bbox 的比例。"""
    if not bbox or len(bbox) < 4 or not container or len(container) < 4:
        return 0.0
    bx0, by0, bx1, by1 = bbox
    cx0, cy0, cx1, cy1 = container
    # 计算交集
    ix0 = max(bx0, cx0)
    iy0 = max(by0, cy0)
    ix1 = min(bx1, cx1)
    iy1 = min(by1, cy1)
    if ix0 >= ix1 or iy0 >= iy1:
        return 0.0
    inter_area = (ix1 - ix0) * (iy1 - iy0)
    bbox_area = (bx1 - bx0) * (by1 - by0)
    return inter_area / bbox_area if bbox_area > 0 else 0.0


def _sort_reading_order(blocks: list[Block]) -> list[Block]:
    """按阅读顺序排序（单列按 y，多列按列分组）。"""
    if len(blocks) <= 1:
        return blocks
    n_cols = column_detection.column_detection(blocks)
    if n_cols <= 1:
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    else:
        xs = [b.bbox[0] for b in blocks if b.bbox]
        if not xs:
            return blocks
        width = max(xs) - min(xs)
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
