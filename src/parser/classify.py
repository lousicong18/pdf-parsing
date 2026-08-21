"""Page classification: extract features then apply configurable thresholds."""

from typing import Optional

import fitz

from src.models.schemas import PageFeatures, PageRaw, PageType
from src.utils import column_detection, env

_DRAWINGS_LIMIT = 200  # 前端展示时 drawings 最大数量（避免 payload 过大）


def classify_features(page) -> tuple[PageFeatures, PageRaw]:
    text_blocks = page.get_text("blocks") or []
    images = page.get_images(full=True) or []
    drawings = page.get_drawings() or []
    links = page.get_links() or []

    # PyMuPDF 1.28+ returns paint-type paths ('s' stroke / 'f' fill / 'fs' both).
    # Stroked paths ('s'/'fs') are the visible lines/rects that form table grids.
    line_count = sum(1 for d in drawings if d.get("type") in ("s", "fs"))
    filled_path_count = sum(
        1 for d in drawings
        if d.get("type") in ("f", "fs") and d.get("fill") and len(d.get("fill", [])) >= 3
    )
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

    feats = PageFeatures(
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
        filled_path_count=filled_path_count,
    )
    raw = _build_raw(page, text_blocks, images, drawings, links)
    return feats, raw


def _build_raw(page, text_blocks, images, drawings, links) -> PageRaw:
    """构建前端可展示的 PyMuPDF 原始数据（drawings 截断到 _DRAWINGS_LIMIT）。"""
    # text_blocks: tuple → list，文本截断到 200 字符
    tb_raw = []
    for b in text_blocks:
        item = list(b)
        if len(item) >= 5 and isinstance(item[4], str):
            item[4] = item[4][:200]
        tb_raw.append(item)
    # images: 只保留元数据（不含二进制）
    img_raw = [list(img[:8]) for img in images]
    # drawings: 截断数量，保留关键字段
    draw_raw = []
    for d in drawings[:_DRAWINGS_LIMIT]:
        draw_raw.append({
            "type": d.get("type"),
            "rect": list(d.get("rect", [])),
            "color": d.get("color"),
            "fill": d.get("fill"),
            "width": d.get("width"),
            "items": _summarize_draw_items(d.get("items", [])),
        })
    # links: [kind, from, page, to, ...]
    link_raw = [list(l[:6]) for l in links]
    return PageRaw(
        text_blocks=tb_raw,
        images=img_raw,
        drawings=draw_raw,
        links=link_raw,
        page_size=[page.rect.width, page.rect.height],
    )


def _summarize_draw_items(items) -> list[list]:
    """drawing items 摘要：('re',rect) / ('l',p0,p1) / ('c',...) → 保留类型+坐标。"""
    summary = []
    for item in items:
        if not item:
            continue
        kind = item[0]
        if kind == "re":
            summary.append(["re", list(item[1])] if len(item) >= 2 else ["re"])
        elif kind == "l":
            summary.append(["l", list(item[1]), list(item[2])] if len(item) >= 3 else ["l"])
        else:
            summary.append([kind])
    return summary


def classify_page(page, prev_type: Optional[str] = None, pdf_path: str = "", page_num: int = -1,
                  task_id: str = "", metrics_ctx=None) -> tuple[PageType, PageFeatures, list[str], PageRaw]:
    log: list[str] = []
    feats, raw = classify_features(page)
    log.append(f"特征: 线条={feats.line_count}, 文本块={feats.text_blocks_count}, 图片={feats.images_count}, "
               f"面积比={feats.area_ratio:.3f}, 栏数={feats.columns}, 路径数={feats.drawings_path_count}")
    page_type = _classify_with_features(feats, prev_type, log)
    # 探针兜底：满足以下任一条件时试探性提取确认是否含表格
    probe_trigger = (
        feats.line_count > env.CLS_LINE_COUNT_TABLE and feats.area_ratio < env.CLS_AREA_RATIO_MIN
    ) or (
        feats.text_blocks_count >= 10 and 5 <= feats.line_count <= 10
        and feats.text_blocks_count > feats.line_count * 2 and feats.text_blocks_count <= 50
    )
    if page_type != "table" and probe_trigger and pdf_path:
        log.append(f"探针兜底触发: 尝试提取表格验证")
        if _probe_has_tables(page, pdf_path, page_num):
            page_type = "table"
            log.append(f"探针检出表格 → 修正为 table")
    # VLM 兜底：分类为 mixed 且探针未检出时，用 VLM 判断是否含表格
    if page_type == "mixed" and task_id and env.CLS_VLM_FALLBACK == "on":
        log.append(f"VLM 兜底触发: 判断 mixed 页是否含表格")
        if _vlm_detect_table(page, task_id, page_num, metrics_ctx):
            page_type = "table"
            log.append(f"VLM 检出表格 → 修正为 table")
    log.append(f"最终判定: {page_type}")
    return page_type, feats, log, raw


def _probe_has_tables(page, pdf_path: str, page_num: int) -> bool:
    """用 HybridExtractor 快速探测页面是否含表格（低成本兜底）。
    要求检出表格满足：评分达标 + 多列结构 + 非公式布局 + 多列有内容。"""
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
                continue
            if not _multi_col_has_content(t):
                continue  # 只有单列有内容（空列+文字假表格）
            return True
        return False
    except Exception:
        return False


def _multi_col_has_content(t: "TableData") -> bool:
    """至少 2 列包含多个有意义单元格（排除"项目符号列+文字"的假表格）。"""
    if not t.rows or t.n_cols < 2:
        return False
    meaningful_len = 5  # 排除项目符号、短标签
    cols_with_content = 0
    for c in range(t.n_cols):
        count = sum(1 for row in t.rows if c < len(row) and len(row[c].strip()) > meaningful_len)
        if count >= 2:  # 该列至少 2 行有实质内容
            cols_with_content += 1
    return cols_with_content >= 2


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


def _classify_with_features(feats: PageFeatures, prev_type: Optional[str] = None,
                            log: Optional[list[str]] = None) -> PageType:
    def info(msg: str) -> None:
        if log is not None:
            log.append(msg)

    # scan: no text blocks but has images; also hidden-text-layer heuristic
    if feats.text_blocks_count == 0 and feats.images_count > 0:
        info(f"scan: 无文本块({feats.text_blocks_count}=0) 且有图片({feats.images_count}>0)")
        return "scan"
    if feats.images_count > 0 and feats.overlap_rate > 0.4 and feats.char_density > 5000 and feats.font_flags:
        info(f"scan: 隐形文本层启发式 (重叠率={feats.overlap_rate:.2f}>0.4, 字符密度={feats.char_density:.0f}>5000, 有字体标记)")
        return "scan"

    # table: enough lines + text blocks, area filter to reject small logos
    is_table_like = (
        feats.line_count > env.CLS_LINE_COUNT_TABLE
        and feats.text_blocks_count >= env.CLS_TEXT_BLOCKS_MIN
        and feats.area_ratio >= env.CLS_AREA_RATIO_MIN
    )

    # chart-embedded table: fills dominate grid lines (dots/bars/areas)
    if feats.filled_path_count > 30 and feats.filled_path_count > feats.line_count:
        info(f"chart_table: chart-embedded table (fills={feats.filled_path_count}>30, "
             f"fills>lines {feats.filled_path_count}>{feats.line_count})")
        return "mixed"

    # 无线表格兜底：线条多 + 文本块多 + 多列结构，但面积比不足
    is_borderless_table = (
        feats.line_count > env.CLS_LINE_COUNT_TABLE
        and feats.text_blocks_count >= 10
        and feats.area_ratio < env.CLS_AREA_RATIO_MIN
        and feats.columns >= 2
    )

    if is_table_like:
        info(f"table: 有线表格 (线条{feats.line_count}>{env.CLS_LINE_COUNT_TABLE}, "
             f"文本块{feats.text_blocks_count}>={env.CLS_TEXT_BLOCKS_MIN}, "
             f"面积比{feats.area_ratio:.3f}>={env.CLS_AREA_RATIO_MIN})")
        return "table"
    if is_borderless_table:
        info(f"table: 无线表格 (线条{feats.line_count}>{env.CLS_LINE_COUNT_TABLE}, "
             f"文本块{feats.text_blocks_count}>=10, 面积比{feats.area_ratio:.3f}<{env.CLS_AREA_RATIO_MIN}, "
             f"栏数{feats.columns}>=2)")
        return "table"

    # cross-page context
    if prev_type == "table" and feats.line_count > 5:
        info(f"table: 跨页上下文 (上页为 table, 本页线条{feats.line_count}>5)")
        return "table"

    # mixed
    if feats.images_count > 0 and feats.text_blocks_count > 0:
        info(f"mixed: 图文混排 (图片{feats.images_count}>0, 文本块{feats.text_blocks_count}>0)")
        return "mixed"
    if feats.images_count == 0 and feats.drawings_path_count > env.CLS_DRAWINGS_PATH_MIXED:
        info(f"mixed: 矢量图密集 (无嵌入图片, 路径数{feats.drawings_path_count}>{env.CLS_DRAWINGS_PATH_MIXED})")
        return "mixed"

    # text
    if feats.text_blocks_count > 0 and feats.images_count == 0 and feats.line_count < env.CLS_LINE_COUNT_TEXT:
        info(f"text: 纯文本 (文本块{feats.text_blocks_count}>0, 无图片, 线条{feats.line_count}<{env.CLS_LINE_COUNT_TEXT})")
        return "text"

    info(f"mixed: 兜底默认")
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
