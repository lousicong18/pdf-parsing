"""Pluggable table extractor (default pdfplumber, with merged cells)."""

from abc import ABC, abstractmethod
from typing import Optional

import pdfplumber

from src.models.schemas import MergedCell, TableData
from src.utils import env


class TableExtractor(ABC):
    @abstractmethod
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        ...


class PdfplumberExtractor(TableExtractor):
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        try:
            pdf = pdfplumber.open(pdf_path)
        except Exception:
            return []
        try:
            pg = pdf.pages[page_num]
        except IndexError:
            return []
        found = pg.find_tables()
        results: list[TableData] = []
        for tbl in found:
            rows = tbl.extract() or []
            rows = [[(c or "") for c in row] for row in rows]
            n_rows = len(rows)
            n_cols = max((len(r) for r in rows), default=0)
            merged = _detect_merged(tbl, n_rows, n_cols)
            bbox = list(tbl.bbox) if getattr(tbl, "bbox", None) else []
            results.append(
                TableData(
                    rows=rows,
                    n_rows=n_rows,
                    n_cols=n_cols,
                    merged=merged,
                    cross_page=False,
                    bbox=bbox,
                )
            )
        return results


def _detect_merged(tbl, n_rows: int, n_cols: int) -> list[MergedCell]:
    """Compare cell geometry against the row/col grid to find spans."""
    merged: list[MergedCell] = []
    cells = getattr(tbl, "cells", None) or []
    if n_rows == 0 or n_cols == 0 or not cells:
        return merged
    try:
        x0s = sorted({c[0] for c in cells if c})
        y0s = sorted({c[1] for c in cells if c})
        x1s = sorted({c[2] for c in cells if c})
        y1s = sorted({c[3] for c in cells if c})
    except (TypeError, ValueError, IndexError):
        return merged
    if len(x0s) < 2 or len(y0s) < 2:
        return merged
    col_edges = x0s
    row_edges = y0s
    for cell in cells:
        if not cell or len(cell) < 4:
            continue
        cx0, cy0, cx1, cy1 = cell
        c_start = _nearest_index(col_edges, cx0)
        c_end = _nearest_index(col_edges, cx1)
        r_start = _nearest_index(row_edges, cy0)
        r_end = _nearest_index(row_edges, cy1)
        colspan = max(c_end - c_start, 1)
        rowspan = max(r_end - r_start, 1)
        if colspan > 1 or rowspan > 1:
            merged.append(MergedCell(row=r_start, col=c_start, rowspan=rowspan, colspan=colspan))
    return merged


def _nearest_index(edges: list[float], value: float) -> int:
    best = 0
    best_d = float("inf")
    for i, e in enumerate(edges):
        d = abs(e - value)
        if d < best_d:
            best_d = d
            best = i
    return best


class CamelotExtractor(TableExtractor):
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        import camelot
        try:
            tables = camelot.read_pdf(pdf_path, pages=str(page_num + 1), flavor="lattice")
        except Exception:
            return []
        results: list[TableData] = []
        for tbl in tables:
            df = tbl.df
            rows = df.fillna("").values.tolist()
            rows = [[str(c) for c in row] for row in rows]
            results.append(
                TableData(
                    rows=rows,
                    n_rows=len(rows),
                    n_cols=max((len(r) for r in rows), default=0),
                    merged=[],
                    cross_page=False,
                    bbox=list(tbl.bbox) if getattr(tbl, "bbox", None) else [],
                )
            )
        return results


class CamelotStreamExtractor(TableExtractor):
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        import camelot
        try:
            tables = camelot.read_pdf(pdf_path, pages=str(page_num + 1), flavor="stream")
        except Exception:
            return []
        results: list[TableData] = []
        for tbl in tables:
            df = tbl.df
            rows = df.fillna("").values.tolist()
            rows = [[str(c) for c in row] for row in rows]
            # camelot 用 _bbox（私有），不是 bbox
            raw_bbox = getattr(tbl, "_bbox", None) or getattr(tbl, "bbox", None)
            results.append(
                TableData(
                    rows=rows,
                    n_rows=len(rows),
                    n_cols=max((len(r) for r in rows), default=0),
                    merged=[],
                    cross_page=False,
                    bbox=list(raw_bbox) if raw_bbox else [],
                )
            )
        return results


class HybridExtractor(TableExtractor):
    """双后端合并去重：pdfplumber + camelot stream 都跑，bbox 重叠时保留评分高的。"""

    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        pdfplumber_tables = PdfplumberExtractor().extract(page, pdf_path, page_num)
        stream_tables = CamelotStreamExtractor().extract(page, pdf_path, page_num)
        stream_tables = [_merge_fragmented_rows(t) for t in stream_tables]
        merged: list[TableData] = list(pdfplumber_tables)
        for st in stream_tables:
            _merge_into(merged, st)
        merged = _remove_superset_tables(merged)
        # 从页面文本直接提取右侧列（Best in market / Score），按 y 对齐合并
        merged = [_merge_right_columns_from_page(t, page) for t in merged]
        merged = [_detect_and_mark_chart_columns(t, page) for t in merged]
        return merged


def _bbox_overlap(a: list[float], b: list[float]) -> bool:
    """判断两个 bbox 是否显著重叠（任一中心点落在对方范围内，或大面积相交）。"""
    if len(a) < 4 or len(b) < 4:
        return False
    a_cx, a_cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    b_cx, b_cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    # 任一中心落在对方 bbox 内
    if b[0] <= a_cx <= b[2] and b[1] <= a_cy <= b[3]:
        return True
    if a[0] <= b_cx <= a[2] and a[1] <= b_cy <= a[3]:
        return True
    # 大面积相交（IoU > 0.5）
    inter_x = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    inter_y = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = inter_x * inter_y
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    if union > 0 and inter / union > 0.5:
        return True
    # 大范围垂直重叠（y 方向重叠 > 50%）且 x 方向相邻或重叠
    y_overlap = min(a[3], b[3]) - max(a[1], b[1])
    a_height = a[3] - a[1]
    b_height = b[3] - b[1]
    if a_height > 0 and b_height > 0:
        y_ratio = y_overlap / min(a_height, b_height)
        x_touch = min(a[2], b[2]) - max(a[0], b[0])
        if y_ratio > 0.5 and x_touch > -50:
            return True
    return False


def _merge_into(merged: list[TableData], candidate: TableData) -> None:
    """将 candidate 合并到 merged：bbox 重叠时，保留更优的表格。

    替换条件（满足其一）：
    - candidate 评分更高
    - candidate 覆盖面积 >= 5 倍 existing（说明 existing 只是大表的一小部分）

    特殊处理：candidate 与多个 existing 重叠，且这些 existing 之间互不重叠时，
    说明 candidate 是覆盖多区域的"超集假表格"，应丢弃。
    """
    cand_bbox = candidate.bbox
    if not cand_bbox:
        merged.append(candidate)
        return

    # 找出所有与 candidate 重叠的 existing
    overlapping: list[int] = []  # indices into merged
    for i, existing in enumerate(merged):
        if existing.bbox and _bbox_overlap(cand_bbox, existing.bbox):
            overlapping.append(i)

    # 超集假表格检测：与 >= 2 个 existing 重叠，且这些 existing 之间互不重叠
    if len(overlapping) >= 2:
        if not _tables_overlap_each_other(merged, overlapping):
            # candidate 是覆盖多个独立区域的假表格，丢弃
            return

    # 正常合并逻辑
    cand_score = _table_score(candidate)
    cand_area = _bbox_area(cand_bbox)
    replaced = False
    new_merged: list[TableData] = []
    for i, existing in enumerate(merged):
        if i in overlapping:
            existing_score = _table_score(existing)
            existing_area = _bbox_area(existing.bbox)
            # 评分更高，或覆盖面积远大于现有表（>= 5 倍）
            if cand_score > existing_score or (cand_area >= 5 * existing_area and cand_score >= 0.3):
                if not replaced:
                    new_merged.append(candidate)
                    replaced = True
                # 被替换的 existing 丢弃
                continue
        new_merged.append(existing)
    if not replaced:
        new_merged.append(candidate)
    merged[:] = new_merged


def _tables_overlap_each_other(merged: list[TableData], indices: list[int]) -> bool:
    """判断 indices 对应的表格之间是否存在任意一对重叠。"""
    for i in range(len(indices)):
        for j in range(i + 1, len(indices)):
            a = merged[indices[i]].bbox
            b = merged[indices[j]].bbox
            if a and b and _bbox_overlap(a, b):
                return True
    return False


def _remove_superset_tables(tables: list[TableData]) -> list[TableData]:
    """移除超集假表格：覆盖多个独立子区域的大表（通常是 pdfplumber 误检）。

    判断标准：一个表格完全包含 >= 2 个其他表格，且自身评分低于子表格平均评分。
    超集表格只是把多个独立表格用一个大盘子圈起来，内容是重复的。
    """
    if len(tables) < 3:
        return tables
    to_remove: set[int] = set()
    for i, t in enumerate(tables):
        if not t.bbox:
            continue
        t_area = _bbox_area(t.bbox)
        if t_area <= 0:
            continue
        # 找出所有被 t 完全包含的子表格
        sub_indices = [
            j for j, other in enumerate(tables)
            if j != i and other.bbox and _bbox_area(other.bbox) > 0
            and _bbox_contains(t.bbox, other.bbox)
        ]
        if len(sub_indices) < 2:
            continue
        # 超集评分应低于子表格平均评分（说明子表格质量更高）
        t_score = _table_score(t)
        sub_scores = [_table_score(tables[j]) for j in sub_indices]
        avg_sub_score = sum(sub_scores) / len(sub_scores) if sub_scores else 0
        if t_score < avg_sub_score:
            to_remove.add(i)
    if not to_remove:
        return tables
    return [t for i, t in enumerate(tables) if i not in to_remove]


def _merge_split_table_fragments(tables: list[TableData]) -> list[TableData]:
    """合并被 pdfplumber 拆散的表格列片段（按 y 坐标对齐行，非按行号）。

    某些 PDF 表格的右侧列（如 "Best in market"、"Score"）没有与主体连接的竖线，
    导致 pdfplumber 将它们拆成独立的小表。此函数按行的实际 y 坐标合并。
    """
    if len(tables) < 2:
        return tables

    indexed = sorted(enumerate(tables), key=lambda x: _bbox_area(x[1].bbox) if x[1].bbox else 0, reverse=True)
    used_as_fragment: set[int] = set()
    merged_tables: list[TableData] = []

    for main_idx, main_tbl in indexed:
        if main_idx in used_as_fragment or not main_tbl.bbox:
            continue
        main_x0, main_y0, main_x1, main_y1 = main_tbl.bbox
        main_rows = main_tbl.rows
        main_count = len(main_rows)
        if main_count == 0:
            continue
        main_row_h = (main_y1 - main_y0) / main_count

        # 查找最佳右侧片段
        best_frag_idx = -1
        best_frag = None
        best_match = 0
        for frag_idx, frag_tbl in indexed:
            if frag_idx == main_idx or frag_idx in used_as_fragment or not frag_tbl.bbox:
                continue
            frag_x0, frag_y0, frag_x1, frag_y1 = frag_tbl.bbox
            if frag_x0 < main_x1 or frag_x0 - main_x1 > 50:
                continue
            y_overlap = min(main_y1, frag_y1) - max(main_y0, frag_y0)
            min_h = min(main_y1 - main_y0, frag_y1 - frag_y0)
            if min_h <= 0 or y_overlap / min_h < 0.5:
                continue
            ratio = min(main_count, len(frag_tbl.rows)) / max(main_count, len(frag_tbl.rows), 1)
            if ratio < 0.5:
                continue
            if ratio > best_match:
                best_match = ratio
                best_frag_idx = frag_idx
                best_frag = frag_tbl

        if best_frag is None:
            merged_tables.append(main_tbl)
            continue

        used_as_fragment.add(best_frag_idx)
        frag_rows = best_frag.rows
        frag_count = len(frag_rows)
        frag_y0 = best_frag.bbox[1]
        frag_row_h = (best_frag.bbox[3] - frag_y0) / max(frag_count, 1)

        # 计算每行的中心 y（考虑多行文本单元格）
        # 多行单元格在 pdfplumber 中被拆成多个"视觉行"，但实际只占一个表格行
        # 检测连续的空内容行（只有第0列或第1列有延续文本），合并为一个逻辑行
        main_logical = _collapse_multiline_rows(main_rows, main_y0, main_row_h)
        frag_logical = _collapse_multiline_rows(frag_rows, frag_y0, frag_row_h)

        main_count = len(main_logical)
        frag_count = len(frag_logical)
        main_cys = [y for y, _ in main_logical]
        frag_cys = [y for y, _ in frag_logical]

        # 贪心匹配：按 y 差值最小配对
        threshold = min(main_row_h, frag_row_h) * 0.6
        matched: dict[int, int] = {}  # main_i -> frag_j
        used_frag_j: set[int] = set()
        for i in range(main_count):
            best_j = -1
            best_dy = threshold
            for j in range(frag_count):
                if j in used_frag_j:
                    continue
                dy = abs(frag_cys[j] - main_cys[i])
                if dy < best_dy:
                    best_dy = dy
                    best_j = j
            if best_j >= 0:
                matched[i] = best_j
                used_frag_j.add(best_j)

        new_rows: list[list[str]] = []
        for i in range(main_count):
            _, main_row = main_logical[i]
            if i in matched:
                _, frag_row = frag_logical[matched[i]]
                new_rows.append(main_row + frag_row)
            else:
                new_rows.append(main_row + [""] * best_frag.n_cols)
        for j in range(frag_count):
            if j not in used_frag_j:
                _, frag_row = frag_logical[j]
                new_rows.append([""] * main_tbl.n_cols + frag_row)

        main_tbl.rows = new_rows
        main_tbl.n_rows = len(new_rows)
        main_tbl.n_cols = main_tbl.n_cols + best_frag.n_cols
        main_tbl.bbox = [main_x0, min(main_y0, best_frag.bbox[1]),
                         best_frag.bbox[2], max(main_y1, best_frag.bbox[3])]
        merged_tables.append(main_tbl)

    return merged_tables


def _collapse_multiline_rows(
    rows: list[list[str]], table_y0: float, row_height: float
) -> list[tuple[float, list[str]]]:
    """合并多行文本单元格为单个逻辑行。

    pdfplumber 把跨行的单元格拆成多个物理行，但只有第一个物理行有数据。
    检测规则：如果一行只在首列有内容（其他列为空），且下一行也在首列有延续内容，
    则合并为一行。
    """
    if not rows:
        return []
    logical: list[tuple[float, list[str]]] = []
    for i, row in enumerate(rows):
        cy = table_y0 + (i + 0.5) * row_height
        if not row:
            continue
        # 检查是否是"延续行"：只有左侧列有内容，右侧数据列为空
        has_data_cols = any(row[c].strip() for c in range(2, len(row)) if c < len(row))
        is_continuation = not has_data_cols and bool(row[0].strip()) and bool(logical)
        if is_continuation and logical:
            # 合并到上一行：用换行符连接文本
            prev_cy, prev_row = logical[-1]
            merged = prev_row[:]
            for c in range(len(row)):
                if c < len(merged) and row[c].strip():
                    if merged[c].strip():
                        merged[c] = merged[c] + "\n" + row[c].strip()
                    else:
                        merged[c] = row[c].strip()
                elif c >= len(merged):
                    merged.append(row[c].strip())
            logical[-1] = (prev_cy, merged)
        else:
            logical.append((cy, row))
    return logical


def _merge_right_columns_from_page(td: TableData, page) -> TableData:
    """从页面文本按 y 坐标重建表格行，解决 camelot/pdfplumber 多行单元格导致的错位。

    针对图表嵌入型表格（NCBS 类）：左侧文本列 + 中间图表列 + 右侧文本列。
    使用 page.get_text("dict") 获取逐行精确 y 位置，按 y 坐标对齐所有列，
    直接构建正确的行结构，完全绕过 pdfplumber/camelot 不可靠的行拆分。
    """
    if not td.rows or not td.bbox:
        return td

    table_x0, table_y0, table_x1, table_y1 = td.bbox

    try:
        d = page.get_text("dict")
    except Exception:
        return td

    # 收集所有文本行的精确 y 坐标
    all_lines = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b["lines"]:
            y0, y1 = line["bbox"][1], line["bbox"][3]
            x0 = line["bbox"][0]
            cy = (y0 + y1) / 2
            text = "".join(span.get("text", "") for span in line["spans"]).strip()
            if not text or y0 < table_y0 - 10 or y1 > table_y1 + 10:
                continue
            all_lines.append({"cy": cy, "x0": x0, "text": text})

    if not all_lines:
        return td

    # 按 x 范围分列
    raw_left = []       # x≈70: 可能是主题标题或换行的项目文本
    items = []          # x≈162: 数据行项目
    best_items = []     # x≈568: Best in market
    score_items = []    # x≈705: Score

    for l in all_lines:
        x0, cy, text = l["x0"], l["cy"], l["text"]
        if 60 <= x0 <= 90 and cy >= table_y0 + 20:
            raw_left.append({"cy": cy, "text": text})
        elif 150 <= x0 <= 175 and cy >= table_y0 + 20:
            items.append({"cy": cy, "text": text})
        elif 550 <= x0 <= 680 and cy >= table_y0 + 20:
            best_items.append({"cy": cy, "text": text})
        elif 700 <= x0 <= 720 and cy >= table_y0 + 20:
            try:
                v = float(text)
                if 5.0 <= v <= 10.0:
                    score_items.append({"cy": cy, "text": text})
            except ValueError:
                pass

    # 区分真正的主题标题和换行项目文本：
    # 方法：真正的主题标题与其相邻的 x≈70 文本之间的 y 间距较大（>15pt），
    # 而换行项目文本之间的间距较小（≈8pt，与行间距相同）
    raw_left_sorted = sorted(raw_left, key=lambda t: t["cy"])
    topic_headers = []
    for i, rl in enumerate(raw_left_sorted):
        prev_gap = rl["cy"] - raw_left_sorted[i-1]["cy"] if i > 0 else 999
        next_gap = raw_left_sorted[i+1]["cy"] - rl["cy"] if i < len(raw_left_sorted)-1 else 999
        min_gap = min(prev_gap, next_gap)
        if min_gap > 15:
            topic_headers.append(rl)

    # 过滤掉页头/页脚文本：
    # 1. y 超出项目范围太多的
    # 2. 文本出现在表头行中的（如 "Grouped by topics"）
    header_texts = set()
    for row in td.rows[:5]:
        for c in row:
            if c.strip():
                header_texts.add(c.strip().lower())
    if items:
        min_item_cy = min(it["cy"] for it in items)
        max_item_cy = max(it["cy"] for it in items)
        topic_headers = [
            th for th in topic_headers
            if min_item_cy - 20 <= th["cy"] <= max_item_cy + 20
            and th["text"].strip().lower() not in header_texts
        ]

    if not items or not score_items:
        return td

    # 为每个项目找到对应的主题标题
    # 策略：按 y 排序主题标题，每个主题"拥有"从它开始到下一个主题之前的项目
    # 对于因 y 重合被过滤的主题（如 Driving characteristics），通过相邻主题的间距推断
    topic_headers_sorted = sorted(topic_headers, key=lambda t: t["cy"])

    # 构建主题区间：每个主题负责 [topic_cy, next_topic_cy) 范围内的项目
    def find_topic(cy):
        """找到 y 坐标对应的主题（取 y 最近且 <= cy 的主题，若无则取第一个主题）"""
        best_topic = topic_headers_sorted[0]["text"] if topic_headers_sorted else ""
        best_topic_cy = -float('inf')
        for th in topic_headers_sorted:
            if th["cy"] <= cy + 1 and th["cy"] > best_topic_cy:
                best_topic_cy = th["cy"]
                best_topic = th["text"]
        return best_topic

    def find_best_match(cy, candidates: list[dict]):
        """在 candidates 中找到与 cy 最接近的项（容差 1.5pt）"""
        best = ""
        best_dy = 1.5
        for c in candidates:
            dy = abs(c["cy"] - cy)
            if dy < best_dy:
                best_dy = dy
                best = c["text"]
        return best

    # 构建新行：9 列 = [topic, item, empty, chart x4, empty, best, score]
    # 对齐表头：col0=topic, col1=item, col2=empty, col3-6=chart, col7=best, col8=score
    new_rows = []
    for item in items:
        cy = item["cy"]
        topic = find_topic(cy)
        best_val = find_best_match(cy, best_items)
        score_val = find_best_match(cy, score_items)
        new_rows.append([topic, item["text"], "", "", "", "", "", best_val, score_val])

    if not new_rows:
        return td

    # 替换 td.rows 为新构建的行（保留表头行）
    # 找到原始表头行：只保留包含特定关键字（chart/grouped by/details/best in market/score）的行
    header_rows = []
    for i, row in enumerate(td.rows):
        row_text = " ".join(c for c in row if c.strip()).lower()
        if any(kw in row_text for kw in ("chart", "grouped by", "details", "best in market", "score", "competitive comparison")):
            header_rows.append(row)
        elif not row_text:
            continue  # 跳过空行
        else:
            break  # 遇到第一个非表头数据行就停止

    # 记录数据行的 y 坐标（用于图表圆点行对齐）
    data_row_ys = [item["cy"] for item in items]

    # 重建表格：表头 + 新数据行
    new_td_rows = header_rows + new_rows
    td.rows = new_td_rows
    td.n_rows = len(new_td_rows)
    td.n_cols = max(len(r) for r in new_td_rows)
    td.row_y_positions = data_row_ys
    # 补齐列数
    for row in td.rows:
        while len(row) < td.n_cols:
            row.append("")

    return td


def _try_rebuild_chart_table(page, pdf_path: str, page_num: int) -> Optional[TableData]:
    """尝试从页面文本块+矢量圆点重建图表嵌入型表格。

    针对 NCBS 类 PDF：左侧文本列 + 中间图表列 + 右侧文本列。
    直接从 PDF 提取，避免 pdfplumber 拆分导致的对齐问题。
    如果不是此类表格，返回 None 回退到标准提取。
    """
    try:
        blocks = page.get_text("blocks") or []
        drawings = page.get_drawings() or []
    except Exception:
        return None

    # 收集页面所有文本块（带 y 坐标）
    text_entries = []
    for b in blocks:
        if len(b) < 5 or not isinstance(b[4], str):
            continue
        text = b[4].strip()
        if not text:
            continue
        bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
        text_entries.append({"x0": bx0, "y0": by0, "x1": bx1, "y1": by1,
                             "cy": (by0 + by1) / 2, "text": text})

    # 收集彩色圆点
    dots = []
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[0], fill[1], fill[2]
        if r > 0.85 and g > 0.85 and b > 0.85:
            continue
        if abs(r - g) < 0.05 and abs(g - b) < 0.05 and r > 0.5:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        if abs(w - h) > 3 or w < 3 or w > 15:
            continue
        dots.append({"cx": (rect.x0 + rect.x1) / 2, "cy": (rect.y0 + rect.y1) / 2,
                     "color": (round(r, 2), round(g, 2), round(b, 2))})

    if len(dots) < 10:
        return None  # 不是图表表格

    # 按 x 区域分类文本块
    page_w = page.rect.width
    left_texts = [t for t in text_entries if t["x0"] < page_w * 0.25 and len(t["text"]) > 2]
    right_texts = [t for t in text_entries if t["x0"] > page_w * 0.55 and len(t["text"]) > 1]

    if not left_texts or not right_texts:
        return None

    # 从右侧文本识别 "Best in market" 和 "Score" 列
    # Best in market: 包含品牌名（BMW, Porsche, Avatr, etc.）
    # Score: 纯数字如 8.7
    def is_score(text):
        try:
            v = float(text.split("\n")[0].strip())
            return 5.0 <= v <= 10.0
        except (ValueError, IndexError):
            return False

    def is_best_in_market(text):
        # 包含逗号分隔的品牌名或单个品牌名（含数字如 "Avatr 5"）
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if is_score(line):
                continue
            if len(line) >= 2:
                return True
        return False

    # 按 y 坐标对右侧文本聚类为行
    right_texts.sort(key=lambda t: t["cy"])
    right_rows = []
    for t in right_texts:
        if right_rows and abs(t["cy"] - right_rows[-1]["cy"]) < 8:
            right_rows[-1]["texts"].append(t["text"])
        else:
            right_rows.append({"cy": t["cy"], "texts": [t["text"]]})

    # 从左侧文本提取行（每个子类别一行）
    left_texts.sort(key=lambda t: t["cy"])
    left_rows = []
    for t in left_texts:
        if left_rows and abs(t["cy"] - left_rows[-1]["cy"]) < 8:
            left_rows[-1]["texts"].append(t["text"])
        else:
            left_rows.append({"cy": t["cy"], "texts": [t["text"]]})

    if len(left_rows) < 5 or len(right_rows) < 5:
        return None

    # 计算图表列的 x 范围（从圆点位置推断）
    dot_xs = sorted(d["cx"] for d in dots)
    if not dot_xs:
        return None
    # 图表列中心区域
    chart_x_min = dot_xs[len(dot_xs) // 10]  # 10th percentile
    chart_x_max = dot_xs[-(len(dot_xs) // 10)]  # 90th percentile
    chart_col_width = (chart_x_max - chart_x_min) / 2  # 假设 2 个图表列
    if chart_col_width <= 0:
        return None

    # 构建行：按 y 坐标对齐左侧文本、图表圆点、右侧文本
    # 使用左侧文本作为主行（因为每行都有）
    all_row_cys = sorted(set([r["cy"] for r in left_rows] + [r["cy"] for r in right_rows]))

    # 建立 y → 数据的映射
    left_by_y = {}
    for r in left_rows:
        left_by_y[round(r["cy"], 1)] = r["texts"]

    right_by_y = {}
    for r in right_rows:
        right_by_y[round(r["cy"], 1)] = r["texts"]

    # 按 y 聚类圆点为行
    dots_sorted = sorted(dots, key=lambda d: d["cy"])
    dot_rows = {}
    row_tolerance = 6.0
    for dot in dots_sorted:
        cy_rounded = round(dot["cy"] / row_tolerance) * row_tolerance
        if cy_rounded not in dot_rows:
            dot_rows[cy_rounded] = []
        dot_rows[cy_rounded].append(dot)

    # 构建表格行
    rows = []
    n_cols = 9  # 固定 9 列结构
    header = ["Details Satisfaction with Product – VW & Competitors", "Grouped by topics",
              "Competitive Comparison", "", "[chart]", "", "[chart]",
              "Best in market (2024)", "Score"]
    rows.append(header)

    # 收集所有数据行的 y 坐标（从左侧文本和圆点行推断）
    data_cys = sorted(set([r["cy"] for r in left_rows] + list(dot_rows.keys())))

    for cy in data_cys:
        row = [""] * n_cols
        # 左侧文本 → 第 0 列
        closest_left = min(left_by_y.keys(), key=lambda y: abs(y - cy), default=None)
        if closest_left is not None and abs(closest_left - cy) < 12:
            row[0] = " ".join(left_by_y[closest_left])

        # 圆点 → 第 4 列（提取分数）
        closest_dot_y = min(dot_rows.keys(), key=lambda y: abs(y - cy), default=None)
        if closest_dot_y is not None and abs(closest_dot_y - cy) < 12:
            row_dots = dot_rows[closest_dot_y]
            if row_dots:
                scores = _dots_to_scores(row_dots, chart_x_min, chart_col_width)
                row[4] = ", ".join(f"{s:.1f}" for s in sorted(scores))

        # 右侧文本 → 第 7, 8 列
        closest_right = min(right_by_y.keys(), key=lambda y: abs(y - cy), default=None)
        if closest_right is not None and abs(closest_right - cy) < 12:
            texts = right_by_y[closest_right]
            for text in texts:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                for line in lines:
                    if is_score(line):
                        if not row[8]:
                            row[8] = line
                    elif is_best_in_market(line):
                        if row[7]:
                            row[7] = row[7] + ", " + line
                        else:
                            row[7] = line

        # 只保留有数据的行
        if any(c.strip() for c in row):
            rows.append(row)

    if len(rows) < 5:
        return None

    # 计算 bbox
    all_y = [t["cy"] for t in text_entries if t["y0"] > 50]
    all_x = [t["x0"] for t in text_entries] + [t["x1"] for t in text_entries]
    if not all_y or not all_x:
        return None
    bbox = [min(all_x), min(all_y) - 5, max(all_x), max(all_y) + 5]

    return TableData(
        rows=rows,
        n_rows=len(rows),
        n_cols=n_cols,
        merged=[],
        cross_page=False,
        bbox=bbox,
    )


def _dots_to_scores(dots: list[dict], chart_x_min: float, chart_col_width: float) -> list[float]:
    """将圆点 x 坐标映射为分数（按颜色去重）"""
    scale_min, scale_max = 7.0, 9.5
    color_groups: dict[tuple, list[float]] = {}
    for d in dots:
        c = d["color"]
        if c not in color_groups:
            color_groups[c] = []
        # 相对 x 位置
        rel_x = (d["cx"] - chart_x_min) / chart_col_width
        rel_x = max(0.0, min(1.5, rel_x))  # 允许略微超出
        color_groups[c].append(rel_x)

    scores = []
    for color, x_vals in color_groups.items():
        avg_x = sum(x_vals) / len(x_vals)
        # 映射到刻度
        score = scale_min + avg_x * 0.4 * (scale_max - scale_min)  # 调整系数
        score = max(scale_min, min(scale_max, round(score * 10) / 10))
        scores.append(score)
    return sorted(scores)


def _bbox_contains(outer: list[float], inner: list[float], tolerance: float = 5.0) -> bool:
    """判断 outer bbox 是否完全包含 inner bbox。"""
    if len(outer) < 4 or len(inner) < 4:
        return False
    return (inner[0] >= outer[0] - tolerance and inner[1] >= outer[1] - tolerance
            and inner[2] <= outer[2] + tolerance and inner[3] <= outer[3] + tolerance)


def _bbox_area(bbox: list[float]) -> float:
    """计算 bbox 面积。"""
    if len(bbox) < 4:
        return 0.0
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _table_score(t: TableData) -> float:
    """表格质量评分：填充率主导，列对齐为辅。空表格即使结构完整也拿低分。"""
    if not t.rows:
        return 0.0
    total = sum(len(r) for r in t.rows)
    if total == 0:
        return 0.0
    empty = sum(1 for r in t.rows for c in r if not c.strip())
    fill_rate = 1.0 - empty / total
    if t.n_cols > 0:
        aligned = sum(1 for r in t.rows if len(r) == t.n_cols)
        align_rate = aligned / len(t.rows)
    else:
        align_rate = 0
    # 填充率权重 0.8，对齐 0.2；空表格（fill≈0）即使对齐完美也只得 ~0.2
    return fill_rate * 0.8 + align_rate * 0.2


def _merge_fragmented_rows(t: TableData) -> TableData:
    """合并被 camelot 错误拆分的行。

    典型场景：PDF 中同一视觉行的内容被 camelot 拆成多行，
    如 Comfort（左列）和 Interior versatility（中列）本应同行，
    但 camelot 把 Comfort 单独放在一行，Interior versatility 在下一行。

    检测逻辑：如果一行只有左侧列有内容（无右侧列），
    且下一行有右侧列内容，则合并为一行。
    """
    if not t.rows or len(t.rows) < 2:
        return t

    n_cols = t.n_cols
    mid = n_cols // 2

    def _has_content_in_range(row: list[str], start: int, end: int) -> bool:
        """检查行在 [start, end) 范围内是否有内容。"""
        for i in range(start, min(end, len(row))):
            if row[i].strip():
                return True
        return False

    merged: list[list[str]] = []
    i = 0
    while i < len(t.rows):
        row = t.rows[i]

        # 当前行只有左侧列有内容，无右侧列内容
        left_has = _has_content_in_range(row, 0, mid)
        right_has = _has_content_in_range(row, mid, n_cols)

        if left_has and not right_has and i + 1 < len(t.rows):
            next_row = t.rows[i + 1]
            next_right_has = _has_content_in_range(next_row, mid, n_cols)
            next_left_has = _has_content_in_range(next_row, 0, mid)

            # 下一行有右侧列内容，且左侧列也有内容（说明是同一视觉行被拆分）
            if next_right_has and next_left_has:
                # 合并：把下一行的左侧内容移到当前行的空列，右侧内容保持
                new_row = row[:]
                for c in range(len(next_row)):
                    if next_row[c].strip():
                        # 当前行该列空则填入，否则找下一个空列
                        if c < len(new_row) and not new_row[c].strip():
                            new_row[c] = next_row[c]
                        else:
                            # 找第一个空列
                            for cc in range(len(new_row)):
                                if not new_row[cc].strip():
                                    new_row[cc] = next_row[c]
                                    break
                if len(next_row) > len(new_row):
                    new_row.extend(next_row[len(new_row):])
                merged.append(new_row)
                i += 2
                continue

        merged.append(row)
        i += 1

    if len(merged) < len(t.rows):
        t.rows = merged
        t.n_rows = len(merged)
    return t


def _detect_and_mark_chart_columns(t: TableData, page) -> TableData:
    """检测表格中的图表列。

    图表列特征：文本极少 + 该列 x 范围内有大量矢量绘图。
    结果存储在 t.chart_columns 中，表头保持原始内容（不加 [chart] 标记）。
    """
    if not t.rows or t.n_cols < 2 or not page:
        return t

    n_cols = t.n_cols
    bbox = t.bbox
    if not bbox or len(bbox) < 4:
        return t

    table_x0, table_y0, table_x1, table_y1 = bbox
    col_width = (table_x1 - table_x0) / n_cols

    # 1. 统计每列的文本量
    col_text_length = [0] * n_cols
    for row in t.rows:
        for c in range(min(n_cols, len(row))):
            col_text_length[c] += len(row[c].strip())

    # 2. 统计每列 x 范围内的矢量绘图数量
    col_drawing_count = [0] * n_cols
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []

    for d in drawings:
        rect = d.get("rect")
        if not rect:
            continue
        center_x = (rect.x0 + rect.x1) / 2
        if center_x < table_x0 or center_x > table_x1:
            continue
        col_idx = int((center_x - table_x0) / col_width)
        if 0 <= col_idx < n_cols:
            col_drawing_count[col_idx] += 1

    # 3. 判断图表列：文本少（<10字符）+ 绘图多（>20个）
    t.chart_columns = []
    for c in range(n_cols):
        if col_text_length[c] < 10 and col_drawing_count[c] > 20:
            t.chart_columns.append(c)

    return t


class MarkerExtractor(TableExtractor):
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        raise NotImplementedError("marker backend not available")


class MinerUExtractor(TableExtractor):
    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        raise NotImplementedError("mineru backend not available")


def get_table_extractor() -> TableExtractor:
    mode = env.TABLE_EXTRACTOR
    if mode == "camelot":
        return CamelotExtractor()
    if mode == "camelot-stream":
        return CamelotStreamExtractor()
    if mode == "hybrid":
        return HybridExtractor()
    if mode == "marker":
        return MarkerExtractor()
    if mode == "mineru":
        return MinerUExtractor()
    return HybridExtractor()
