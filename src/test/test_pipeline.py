"""Pipeline dispatch: returns (blocks, features), every block carries bbox + page_type."""

import fitz
import pytest

from src.parser.pipeline import dispatch_page
from src.utils import metrics


def _blocks_have_bbox_and_page_type(blocks):
    for b in blocks:
        assert isinstance(b.bbox, list), "block.bbox must be list"
        assert len(b.bbox) == 4, f"block.bbox must be [x0,y0,x1,y1], got {b.bbox}"
        assert b.page_type in ("text", "table", "mixed", "scan"), f"bad page_type {b.page_type}"


class TestDispatchPage:
    def test_returns_tuple(self, text_pdf):
        doc = fitz.open(text_pdf)
        page = doc.load_page(0)
        result = dispatch_page(page, "text", "t1", 0, doc)
        doc.close()
        assert isinstance(result, tuple)
        assert len(result) == 3
        blocks, features, raw = result
        assert isinstance(blocks, list)
        assert features is not None

    def test_text_branch(self, text_pdf):
        doc = fitz.open(text_pdf)
        page = doc.load_page(0)
        blocks, features, raw = dispatch_page(page, "text", "t1", 0, doc)
        doc.close()
        _blocks_have_bbox_and_page_type(blocks)
        for b in blocks:
            assert b.page_type == "text"

    def test_table_branch(self, table_pdf):
        doc = fitz.open(table_pdf)
        page = doc.load_page(0)
        blocks, features, raw = dispatch_page(page, "table", "t1", 0, doc)
        doc.close()
        _blocks_have_bbox_and_page_type(blocks)

    def test_mixed_branch(self, mixed_pdf):
        doc = fitz.open(mixed_pdf)
        page = doc.load_page(0)
        ctx = metrics.new_task_metrics()
        blocks, features, raw = dispatch_page(page, "mixed", "t1", 0, doc, metrics_ctx=ctx)
        doc.close()
        _blocks_have_bbox_and_page_type(blocks)
        for b in blocks:
            assert b.page_type == "mixed"

    def test_scan_branch(self, scan_pdf):
        doc = fitz.open(scan_pdf)
        page = doc.load_page(0)
        ctx = metrics.new_task_metrics()
        blocks, features, raw = dispatch_page(page, "scan", "t1", 0, doc, metrics_ctx=ctx)
        doc.close()
        _blocks_have_bbox_and_page_type(blocks)
        for b in blocks:
            assert b.page_type == "scan"

    def test_features_columns_populated(self, text_pdf):
        doc = fitz.open(text_pdf)
        page = doc.load_page(0)
        blocks, features, raw = dispatch_page(page, "text", "t1", 0, doc)
        doc.close()
        assert features.columns >= 1
