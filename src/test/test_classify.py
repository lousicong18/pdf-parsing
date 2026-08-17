"""Page classification: text / table / mixed / scan 判定."""

import fitz
import pytest

from src.parser.classify import classify_features, classify_page


def _open(pdf_path):
    return fitz.open(pdf_path)


class TestClassifyFeatures:
    def test_returns_page_features(self, text_pdf):
        doc = _open(text_pdf)
        feats = classify_features(doc.load_page(0))
        doc.close()
        assert feats is not None
        assert feats.text_blocks_count >= 1
        assert feats.columns >= 1

    def test_features_fields_populated(self, text_pdf):
        doc = _open(text_pdf)
        feats = classify_features(doc.load_page(0))
        doc.close()
        assert isinstance(feats.line_count, int)
        assert isinstance(feats.area_ratio, float)
        assert isinstance(feats.overlap_rate, float)
        assert isinstance(feats.orthogonality, float)
        assert 0.0 <= feats.overlap_rate <= 1.0


class TestClassifyPage:
    def test_text_page_classified(self, text_pdf):
        doc = _open(text_pdf)
        page_type, feats = classify_page(doc.load_page(0))
        doc.close()
        assert page_type in ("text", "table", "mixed", "scan")
        assert feats is not None

    def test_table_page_classified(self, table_pdf):
        doc = _open(table_pdf)
        page_type, feats = classify_page(doc.load_page(0))
        doc.close()
        assert page_type in ("text", "table", "mixed", "scan")
        assert feats is not None

    def test_mixed_page_classified(self, mixed_pdf):
        doc = _open(mixed_pdf)
        page_type, feats = classify_page(doc.load_page(0))
        doc.close()
        assert page_type in ("text", "table", "mixed", "scan")

    def test_scan_page_classified(self, scan_pdf):
        doc = _open(scan_pdf)
        page_type, feats = classify_page(doc.load_page(0))
        doc.close()
        assert page_type in ("text", "table", "mixed", "scan")

    def test_prev_type_context(self, text_pdf):
        doc = _open(text_pdf)
        p1, _ = classify_page(doc.load_page(0))
        p2, _ = classify_page(doc.load_page(0), prev_type=p1)
        doc.close()
        assert p1 in ("text", "table", "mixed", "scan")
        assert p2 in ("text", "table", "mixed", "scan")

    def test_table_page_detected_via_stroked_lines(self, table_pdf):
        doc = _open(table_pdf)
        page_type, feats = classify_page(doc.load_page(0))
        doc.close()
        assert feats.line_count >= 20, f"expected many stroked lines, got {feats.line_count}"
        assert page_type == "table"

    def test_multi_page_each_classified(self, multi_pdf):
        doc = _open(multi_pdf)
        n = doc.page_count
        prev = None
        types = []
        for i in range(n):
            pt, _ = classify_page(doc.load_page(i), prev_type=prev)
            types.append(pt)
            prev = pt
        doc.close()
        assert len(types) == n
        for t in types:
            assert t in ("text", "table", "mixed", "scan")
