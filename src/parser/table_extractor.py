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


class HybridExtractor(TableExtractor):
    """双后端评分选优：pdfplumber + camelot stream 都跑，按质量评分选最优。"""

    def extract(self, page, pdf_path: str, page_num: int) -> list[TableData]:
        pdfplumber_tables = PdfplumberExtractor().extract(page, pdf_path, page_num)
        stream_tables = CamelotStreamExtractor().extract(page, pdf_path, page_num)
        if not pdfplumber_tables:
            return stream_tables
        if not stream_tables:
            return pdfplumber_tables
        # 两者都有结果，选评分更高的
        pp_score = sum(_table_score(t) for t in pdfplumber_tables)
        st_score = sum(_table_score(t) for t in stream_tables)
        return pdfplumber_tables if pp_score >= st_score else stream_tables


def _table_score(t: TableData) -> float:
    """表格质量评分：行数合理、空值少、列对齐好 → 高分。"""
    if not t.rows:
        return 0.0
    # 空值比例（越低越好）
    total = sum(len(r) for r in t.rows)
    empty = sum(1 for r in t.rows for c in r if not c.strip())
    fill_rate = 1.0 - (empty / total if total else 0)
    # 列对齐度（每行列数一致的比例）
    if t.n_cols > 0:
        aligned = sum(1 for r in t.rows if len(r) == t.n_cols)
        align_rate = aligned / len(t.rows)
    else:
        align_rate = 0
    return fill_rate * 0.5 + align_rate * 0.5


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
