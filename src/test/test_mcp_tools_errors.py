"""Tests for parse_pdf error handling (never raises)."""

from unittest.mock import patch

import pytest


def test_file_not_found():
    from src.mcp_tools import parse_pdf
    result = parse_pdf("/nonexistent/file.pdf")
    assert result["error"] is True
    assert result["error_code"] == "FILE_NOT_FOUND"


def test_invalid_file_type(tmp_path):
    from src.mcp_tools import parse_pdf
    txt = tmp_path / "test.txt"
    txt.write_text("hello")
    result = parse_pdf(str(txt))
    assert result["error"] is True
    assert result["error_code"] == "INVALID_FILE_TYPE"


def test_parse_failed(corrupt_pdf):
    from src.mcp_tools import parse_pdf
    result = parse_pdf(corrupt_pdf)
    assert result["error"] is True
    assert result["error_code"] == "PARSE_FAILED"


def test_task_failed(text_pdf):
    from src.mcp_tools import parse_pdf
    from src.models.schemas import ParseResult, TaskError

    failed_result = ParseResult(
        task_id="fail1",
        filename="test.pdf",
        status="failed",
        total_pages=0,
        errors=[TaskError(message="文件损坏")],
    )
    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="fail1", filename="test.pdf", status="pending",
            total_pages=0, created_at="2026-01-01",
        ), "/tmp/test.pdf")
        mock_store.get.return_value = failed_result

        result = parse_pdf(text_pdf)

    assert result["error"] is True
    assert result["error_code"] == "TASK_FAILED"


def test_never_raises_on_unexpected_error(text_pdf):
    from src.mcp_tools import parse_pdf
    with patch("src.mcp_tools.create_task", side_effect=RuntimeError("unexpected")):
        result = parse_pdf(text_pdf)
    assert result["error"] is True
    assert "error_code" in result
