"""Page classification: extract features then apply configurable thresholds."""

from typing import Optional

import fitz

from src.models.schemas import PageFeatures, PageType
from src.utils import column_detection, env


def classify_features(page) -> PageFeatures:
    text_blocks = page.get_text("blocks") or []
    images = page.get_images(full=False) or []
    drawings = page.get_drawings() or []

    # PyMuPDF 1.28+ returns paint-type paths ('s' stroke / 'f' fill / 'fs' both).
    # Stroked paths ('s'/'fs') are the visible lines/rects that form table grids.
    line_count = sum(1 for d in drawings if d.get("type") in ("s", "fs"))
    drawings_path_count = len(drawings)
    text_blocks_count = len(text_blocks)
    images_count = len(images)

    # dense-line area ratio vs page area
    line_area = _line_area(drawings, page.rect)
    page_area = max(page.rect.width * page.rect.height, 1.0)
    area_ratio = min(line_area / page_area, 1.0)

    # text-block bbox overlap rate
    overlap_rate = _overlap_rate(text_blocks)

    # char density (chars / text bbox area)
    char_density = _char_density(text_blocks)

    # font flags from spans (hidden-layer feature)
    font_flags = _font_flags(page)

    # orthogonality of lines (table lines tend axis-aligned)
    orthogonality = _orthogonality(drawings)

    # column count via shared detector (single source of truth for columns)
    columns = column_detection.column_detection(text_blocks)

    return PageFeatures(
        line_count=line_count,
        text_blocks_count=text_blocks_count,
        images_count=images_count,
        drawings_path_count=drawings_path_count,
        area_ratio=area_ratio,
        overlap_rate=overlap_rate,
        char_density=char_density,
        font_flags=font_flags,
        orthogonality=orthogonality,
        columns=columns,
    )


def classify_page(page, prev_type: Optional[str] = None, pdf_path: str = "", page_num: int = -1,
                  task_id: str = "", metrics_ctx=None) -> tuple[PageType, PageFeatures]:
    feats = classify_features(page)
    page_type = _classify_with_features(feats, prev_type)
    # 探针兜底：满足以下任一条件时试探性提取确认是否含表格
    # (a) 线条较多但面积比不足（接近表格判定）
    # (b) 文本块远多于线条（稀疏表格布局），但排除纯文本段落过多的页面
    probe_trigger = (
        feats.line_count > env.CLS_LINE_COUNT_TABLE and feats.area_ratio < env.CLS_AREA_RATIO_MIN
    ) or (
        feats.text_blocks_count >= 10 and feats.line_count <= 10
        and feats.text_blocks_count > feats.line_count * 2 and feats.text_blocks_count <= 50
    )
    if page_type != "table" and probe_trigger and pdf_path:
        if _probe_has_tables(page, pdf_path, page_num):
            page_type = "table"
    # VLM 兜底：分类为 mixed 且探针未检出时，用 VLM 判断是否含表格
    if page_type == "mixed" and task_id and _vlm_detect_table(page, task_id, page_num, metrics_ctx):
        page_type = "table"
    return page_type, feats


def _probe_has_tables(page, pdf_path: str, page_num: int) -> bool:
    """用 HybridExtractor 快速探测页面是否含表格（低成本兜底）。
    要求检出表格满足：评分达标 + 多列结构 + 非公式布局。"""
    if not pdf_path or page_num < 0:
        return False
    try:
        from src.parser.table_extractor import HybridExtractor, _table_score
        tables = HybridExtractor().extract(page, pdf_path, page_num)
        if not tables:
            return False
        for t in tables:
            if _table_score(t) < 0.6 or t.n_cols <= 1:
                continue
            if _is_formula_layout(t):
                continue  # 公式布局，跳过
            return True
        return False
    except Exception:
        return False


def _is_formula_layout(t) -> bool:
    """判断检出表格是否为公式布局（含大量 Unicode 数学符号）。
    公式页的行列对齐结构易被误判为表格，需排除。"""
    from src.parser.formula import _UNICODE_MATH
    if not t.rows:
        return False
    total_cells = 0
    formula_cells = 0
    for row in t.rows:
        for cell in row:
            total_cells += 1
            if any(c in _UNICODE_MATH for c in cell):
                formula_cells += 1
    # 超过 15% 单元格含数学符号 → 公式布局
    return formula_cells / total_cells > 0.15 if total_cells else False


def _vlm_detect_table(page, task_id: str, page_num: int, metrics_ctx=None) -> bool:
    """VLM 兜底：对规则分类不确定的 mixed 页，用 VLM 判断是否含表格（需开启 CLS_VLM_FALLBACK=on）。"""
    if env.CLS_VLM_FALLBACK != "on":
        return False
    try:
        from src.vlm import vlm_describe
        from src.utils import pdf_utils
        img_bytes = pdf_utils.page_to_png(page, dpi=100)
        resp = vlm_describe(
            image_bytes=img_bytes,
            prompt="这是PDF的一页。请判断此页面是否包含表格结构（有线或无线的行列对齐数据）。只回答 yes 或 no。",
            model_name="",
            metrics_ctx=metrics_ctx,
            kind="probe",
        )
        return resp.content.strip().lower().startswith("yes") if resp and resp.content else False
    except Exception:
        return False


def _classify_with_features(feats: PageFeatures, prev_type: Optional[str] = None) -> PageType:
    # scan: no text blocks but has images; also hidden-text-layer heuristic
    if feats.text_blocks_count == 0 and feats.images_count > 0:
        return "scan"
    if feats.images_count > 0 and feats.overlap_rate > 0.4 and feats.char_density > 5000 and feats.font_flags:
        return "scan"

    # table: enough lines + text blocks, area filter to reject small logos
    is_table_like = (
        feats.line_count > env.CLS_LINE_COUNT_TABLE
        and feats.text_blocks_count >= env.CLS_TEXT_BLOCKS_MIN
        and feats.area_ratio >= env.CLS_AREA_RATIO_MIN
    )
    if is_table_like:
        return "table"

    # cross-page context: previous page was table + 当前页有线条/面积特征 -> 偏向 table
    if prev_type == "table" and feats.line_count > 5:
        return "table"

    # mixed: images + text; or vector-drawing heavy (no embedded images but many paths)
    if feats.images_count > 0 and feats.text_blocks_count > 0:
        return "mixed"
    if feats.images_count == 0 and feats.drawings_path_count > env.CLS_DRAWINGS_PATH_MIXED:
        return "mixed"

    # text: has text, few lines
    if feats.text_blocks_count > 0 and feats.images_count == 0 and feats.line_count < env.CLS_LINE_COUNT_TEXT:
        return "text"

    # fallback
    return "mixed"


def _line_area(drawings, rect) -> float:
    """Sum area of stroked lines/rects (the visible grid that signals a table).

    PyMuPDF 1.28+ exposes geometry per path in d['items'] as
    ('re', rect) for rectangles and ('l', p0, p1) for line segments.
    """
    area = 0.0
    for d in drawings:
        if d.get("type") not in ("s", "fs"):
            continue
        for item in d.get("items", []):
            if not item:
                continue
            kind = item[0]
            if kind == "re":
                r = item[1]
                area += max(r.width, 0) * max(r.height, 0)
            elif kind == "l" and len(item) >= 3:
                p0, p1 = item[1], item[2]
                dx = abs(float(p1.x) - float(p0.x))
                dy = abs(float(p1.y) - float(p0.y))
                area += (dx + dy) * 2.0
    return area


def _overlap_rate(text_blocks) -> float:
    if len(text_blocks) < 2:
        return 0.0
    rects = [fitz.Rect(b[:4]) for b in text_blocks if len(b) >= 4]
    if len(rects) < 2:
        return 0.0
    overlaps = 0
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if rects[i].intersects(rects[j]):
                inter = rects[i].intersect(rects[j])
                if inter.get_area() > 0:
                    overlaps += 1
    pairs = len(rects) * (len(rects) - 1) / 2
    return overlaps / pairs if pairs else 0.0


def _char_density(text_blocks) -> float:
    total_chars = 0
    area = 0.0
    for b in text_blocks:
        if len(b) >= 5 and isinstance(b[4], str):
            total_chars += len(b[4])
        if len(b) >= 4:
            r = fitz.Rect(b[:4])
            area += r.get_area()
    return total_chars / area if area > 0 else 0.0


def _font_flags(page) -> list[str]:
    flags: list[str] = []
    try:
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type", 0) != 0:
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    f = span.get("flags", 0)
                    if f:
                        flags.append(str(f))
    except Exception:
        return flags
    # deduplicate but keep small
    seen: set[str] = set()
    uniq: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
            if len(uniq) >= 8:
                break
    return uniq


def _orthogonality(drawings) -> float:
    vecs: list[tuple[float, float]] = []
    for d in drawings:
        p = d.get("points") or []
        if len(p) >= 2:
            dx = float(p[1][0]) - float(p[0][0])
            dy = float(p[1][1]) - float(p[0][1])
            if abs(dx) + abs(dy) > 1:
                vecs.append((dx, dy))
    if len(vecs) < 2:
        return 0.0
    axis_aligned = sum(1 for dx, dy in vecs if abs(dx) < 0.5 or abs(dy) < 0.5)
    return axis_aligned / len(vecs)
