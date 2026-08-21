"""Table extraction via pluggable TableExtractor."""

from typing import Optional

from src.models.schemas import Block, MergedCell, PageType, TableData
from src.parser import table_extractor


def extract_tables(
    page,
    page_type: PageType,
    pdf_path: str,
    page_num: int,
    prev_type: Optional[str] = None,
    prev_header: Optional[list[str]] = None,
    task_id: Optional[str] = None,
    metrics_ctx=None,
    model_name: Optional[str] = None,
) -> list[Block]:
    extractor = table_extractor.get_table_extractor()
    try:
        tables = extractor.extract(page, pdf_path, page_num)
    except Exception:
        return []
    tables = [t for t in tables if _has_content(t)]
    blocks: list[Block] = []
    for i, td in enumerate(tables):
        td.cross_page = prev_type == "table"
        if td.cross_page and prev_header and td.rows and _is_header_repeat(td.rows[0], prev_header):
            td.header_repeat = True
            td.rows = td.rows[1:]
            td.n_rows = max(td.n_rows - 1, 0)
        content = tables_to_markdown(td)
        if td.cross_page:
            content = "> （跨页续表）\n" + content
        bbox = td.bbox if td.bbox else [0, 0, page.rect.width, page.rect.height]
        blocks.append(
            Block(
                type="table",
                bbox=bbox,
                page_type=page_type,
                order=i,
                table=td,
                content=content,
            )
        )
    return blocks


def _has_content(t: TableData) -> bool:
    if not t.rows:
        return False
    non_empty = sum(1 for r in t.rows for c in r if c and c.strip())
    return non_empty >= 2


def _is_header_repeat(row: list[str], header: list[str]) -> bool:
    if not row or not header:
        return False
    norm = lambda s: s.strip().replace(" ", "")
    return [norm(c) for c in row] == [norm(c) for c in header]


def tables_to_markdown(table: TableData, title: str = "") -> str:
    if not table.rows:
        return ""
    n_cols = table.n_cols or max((len(r) for r in table.rows), default=0)
    filled = _fill_merged_cells(table.rows, table.merged)
    normalized = [_pad_row(r, n_cols) for r in filled]
    lines: list[str] = []
    if title:
        lines.append(f"**{title}**")
    header = normalized[0] if normalized else ["" for _ in range(n_cols)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * n_cols) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _fill_merged_cells(rows: list[list[str]], merged: list[MergedCell]) -> list[list[str]]:
    if not merged:
        return rows
    filled = [row[:] for row in rows]
    for m in merged:
        if m.rowspan == 1 and m.colspan == 1:
            continue
        value = filled[m.row][m.col] if m.row < len(filled) and m.col < len(filled[m.row]) else ""
        for dr in range(m.rowspan):
            for dc in range(m.colspan):
                r, c = m.row + dr, m.col + dc
                if r < len(filled) and c < len(filled[r]) and (dr != 0 or dc != 0):
                    filled[r][c] = value
    return filled


def _pad_row(row: list[str], n: int) -> list[str]:
    if len(row) >= n:
        return row[:n]
    return row + ["" for _ in range(n - len(row))]
