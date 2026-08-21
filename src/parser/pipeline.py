"""Page dispatch: classify features, then route by page type.

Returns (blocks, features) — features is the single source of truth written
into PageResult.features by the caller.
"""

from typing import Optional

from src.models.schemas import Block, PageFeatures, PageRaw
from src.parser import classify, extract_table, extract_text, mixed, scan
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
        blocks = extract_text.extract_text(page, page_type)  # type: ignore[arg-type]
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "table":
        blocks = extract_table.extract_tables(
            page, page_type, doc.name, page_num, prev_type, prev_header, task_id, metrics_ctx, model_name,  # type: ignore[arg-type]
        )
        # 表格页面也可能有表格外的图片，补充提取
        blocks = _extract_outside_images(blocks, page, task_id, page_num, doc, metrics_ctx, model_name)
    elif page_type == "mixed":
        blocks = mixed.process_mixed_page(page, task_id, page_num, doc, metrics_ctx, model_name)
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "scan":
        blocks = scan.process_scan_page(page, task_id, page_num, metrics_ctx, model_name)
    return blocks, features, raw


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
