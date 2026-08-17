"""Table extraction via pluggable TableExtractor, with cross-page annotation."""

from typing import Optional

from src.models.schemas import Block, PageType, TableData
from src.parser import table_extractor


def extract_tables(
    page,
    page_type: PageType,
    pdf_path: str,
    page_num: int,
    prev_type: Optional[str] = None,
    prev_header: Optional[list[str]] = None,
) -> list[Block]:
    extractor = table_extractor.get_table_extractor()
    try:
        tables = extractor.extract(page, pdf_path, page_num)
    except Exception:
        return []
    blocks: list[Block] = []
    for i, td in enumerate(tables):
        td.cross_page = prev_type == "table"
        # 检测续表行是否与上一页表头重复
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
                type="table",  # type: ignore[arg-type]
                bbox=bbox,
                page_type=page_type,
                order=i,
                table=td,
                content=content,
            )
        )
    return blocks


def _is_header_repeat(row: list[str], header: list[str]) -> bool:
    """判断续表首行是否与上一页表头相同（允许少量空白差异）。"""
    if not row or not header:
        return False
    norm = lambda s: s.strip().replace(" ", "")
    return [norm(c) for c in row] == [norm(c) for c in header]


def tables_to_markdown(table: TableData) -> str:
    if not table.rows:
        return ""
    n_cols = table.n_cols or max((len(r) for r in table.rows), default=0)
    normalized = [_pad_row(r, n_cols) for r in table.rows]
    lines: list[str] = []
    header = normalized[0] if normalized else ["" for _ in range(n_cols)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * n_cols) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _pad_row(row: list[str], n: int) -> list[str]:
    if len(row) >= n:
        return row[:n]
    return row + ["" for _ in range(n - len(row))]
