"""Tests for parse_pdf basic parsing and chunking."""

import shutil
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_task():
    """Mock task_service to return a simple completed result."""
    from src.models.schemas import ParseResult, PageResult, Block, TaskMetrics

    block = Block(
        type="text",
        bbox=[0, 0, 100, 100],
        page_type="text",
        order=0,
        content="This is a test paragraph with enough words to form a meaningful block for testing.",
    )
    page = PageResult(page=0, type="text", blocks=[block])
    result = ParseResult(
        task_id="test123",
        filename="test.pdf",
        status="completed",
        total_pages=1,
        pages=[page],
        metrics=TaskMetrics(vlm_calls=[], total_cost=0.0, total_latency_ms=100),
    )
    return result


def test_parse_pdf_basic(mock_task, text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse") as mock_run, \
         patch("src.mcp_tools.task_store") as mock_store:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="test123", filename="test.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/test.pdf")
        mock_store.get.return_value = mock_task

        result = parse_pdf(text_pdf)

    assert result["task_id"] == "test123"
    assert result["filename"] == "test.pdf"
    assert result["status"] == "completed"
    assert result["total_pages"] == 1
    assert len(result["chunks"]) >= 1
    assert "content" in result["chunks"][0]
    assert "chunk_id" in result["chunks"][0]
    assert "metrics" in result
    assert result["metrics"]["total_latency_ms"] == 100


def test_parse_pdf_chunking(mock_task, text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="test123", filename="test.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/test.pdf")
        mock_store.get.return_value = mock_task

        result = parse_pdf(text_pdf, chunk_tokens=100, overlap_tokens=10)

    assert result["task_id"] == "test123"
    assert len(result["chunks"]) >= 1


def test_parse_pdf_empty_vlm_model_defaults(text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse") as mock_run, \
         patch("src.mcp_tools.task_store") as mock_store:
        from src.models.schemas import CreateTaskResponse, ParseResult, TaskMetrics
        mock_create.return_value = (CreateTaskResponse(
            task_id="t", filename="f.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/f.pdf")
        mock_store.get.return_value = ParseResult(
            task_id="t", filename="f.pdf", status="completed",
            total_pages=1, metrics=TaskMetrics(),
        )

        result = parse_pdf(text_pdf, vlm_model="")

    assert "error" not in result


def _parse_with_mocks(pdf_path, mock_task):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="test123", filename="sample.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/test.pdf")
        mock_store.get.return_value = mock_task

        return parse_pdf(pdf_path)


def test_parse_pdf_writes_md_file(mock_task, text_pdf, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    shutil.copy(text_pdf, pdf_path)

    result = _parse_with_mocks(str(pdf_path), mock_task)

    md_path = tmp_path / "sample.md"
    assert result["md_path"] == str(md_path)
    expected = "\n\n".join(c["content"] for c in result["chunks"])
    assert md_path.read_text(encoding="utf-8") == expected


def test_parse_pdf_md_write_failure_degrades(mock_task, text_pdf, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    shutil.copy(text_pdf, pdf_path)
    (tmp_path / "sample.md").mkdir()  # 目录占位，使同名 .md 写入失败

    result = _parse_with_mocks(str(pdf_path), mock_task)

    assert result["md_path"] is None
    assert result["md_error"]
    assert len(result["chunks"]) >= 1
    assert "error" not in result
