"""Page dispatch: classify features, then route by page type.

Returns (blocks, features) — features is the single source of truth written
into PageResult.features by the caller.
"""

from typing import Optional

from src.models.schemas import Block, PageFeatures
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
) -> tuple[list[Block], PageFeatures]:
    if features is None:
        features = classify.classify_features(page)
    blocks = []
    if page_type == "text":
        blocks = extract_text.extract_text(page, page_type)  # type: ignore[arg-type]
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "table":
        blocks = extract_table.extract_tables(
            page, page_type, doc.name, page_num, prev_type, prev_header,  # type: ignore[arg-type]
        )
    elif page_type == "mixed":
        blocks = mixed.process_mixed_page(page, task_id, page_num, doc, metrics_ctx, model_name)
        features.columns = column_detection.column_detection(blocks)
    elif page_type == "scan":
        blocks = scan.process_scan_page(page, task_id, page_num, metrics_ctx, model_name)
    return blocks, features
