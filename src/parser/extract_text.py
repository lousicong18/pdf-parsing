"""Text extraction from get_text('dict') blocks, multi-column reading order."""

from typing import Optional

from src.models.schemas import Block, BlockType, PageType
from src.parser import formula
from src.utils import column_detection


def extract_text(page, page_type: PageType) -> list[Block]:
    try:
        data = page.get_text("dict")
    except Exception:
        return []
    raw_blocks = data.get("blocks", []) or []
    recognizer = formula.get_formula_recognizer()
    annotations = recognizer.recognize(page)
    ann_bboxes = [a.get("bbox") for a in annotations if a.get("bbox")]

    pieces: list[Block] = []
    order = 0
    for b in raw_blocks:
        if b.get("type", 0) != 0:
            continue
        text = _block_text(b).strip()
        if not text:
            continue
        bbox = b.get("bbox")
        snippet = _annotate(text, bbox, ann_bboxes, annotations)
        pieces.append(
            Block(
                type="text",  # type: ignore[arg-type]
                bbox=bbox or [0, 0, 0, 0],
                page_type=page_type,
                order=order,
                text=snippet,
                content=snippet,
            )
        )
        order += 1

    return _sort_reading_order(pieces)


def _annotate(text: str, bbox, ann_bboxes: list, annotations: list[dict]) -> str:
    """Attach a [formula: kind] tag when bbox overlaps a formula annotation."""
    if not bbox or not ann_bboxes:
        return text
    import fitz
    r = fitz.Rect(bbox)
    for ab, ann in zip(ann_bboxes, annotations):
        if ab and r.intersects(fitz.Rect(ab)):
            kind = ann.get("kind", "")
            return f"{text}\n[formula:{kind}]"
    return text


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


def _block_text(block: dict) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        if line_text:
            parts.append(line_text)
    return "\n".join(parts)
