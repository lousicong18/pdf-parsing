"""Tests for parse_pdf with include_images=true/false, OSS upload, fallback."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_image_task():
    """Mock task with an image block."""
    from src.models.schemas import (
        ParseResult, PageResult, Block, ImageData, TaskMetrics,
    )

    img_block = Block(
        type="image",
        bbox=[0, 0, 100, 100],
        page_type="mixed",
        order=0,
        content="A bar chart showing revenue",
        image=ImageData(description="A bar chart showing revenue", image_url="/api/v1/tasks/img123/images/0/0"),
        image_url="/api/v1/tasks/img123/images/0/0",
    )
    page = PageResult(page=0, type="mixed", blocks=[img_block])
    return ParseResult(
        task_id="img123",
        filename="chart.pdf",
        status="completed",
        total_pages=1,
        pages=[page],
        metrics=TaskMetrics(vlm_calls=[], total_cost=0.0, total_latency_ms=50),
    )


def _mock_create_and_store(task):
    from src.models.schemas import CreateTaskResponse
    return (
        patch("src.mcp_tools.create_task", return_value=(CreateTaskResponse(
            task_id=task.task_id, filename=task.filename, status="pending",
            total_pages=task.total_pages, created_at="2026-01-01",
        ), "/tmp/chart.pdf")),
        patch("src.mcp_tools.run_parse"),
        patch("src.mcp_tools.task_store") ,
    )


def test_include_images_false_no_oss(mock_image_task, text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="img123", filename="chart.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/chart.pdf")
        mock_store.get.return_value = mock_image_task
        mock_oss.is_oss_enabled.return_value = False

        result = parse_pdf(text_pdf, include_images=False)

    assert "error" not in result
    for chunk in result["chunks"]:
        assert "![" not in chunk["content"]


def test_include_images_true_oss_enabled(mock_image_task, text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss, \
         patch("src.controller.kb_export_controller.image_cache") as mock_cache:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="img123", filename="chart.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/chart.pdf")
        mock_store.get.return_value = mock_image_task
        mock_oss.is_oss_enabled.return_value = True
        mock_oss.upload_image.return_value = "https://oss.example.com/tasks/img123/0_0.png"
        mock_cache.get.return_value = b"fake_image_bytes"

        result = parse_pdf(text_pdf, include_images=True)

    assert "error" not in result
    found_image = False
    for chunk in result["chunks"]:
        if "![A bar chart showing revenue](https://oss.example.com/tasks/img123/0_0.png)" in chunk["content"]:
            found_image = True
    assert found_image


def test_oss_upload_failure_fallback(mock_image_task, text_pdf):
    from src.mcp_tools import parse_pdf

    with patch("src.mcp_tools.create_task") as mock_create, \
         patch("src.mcp_tools.run_parse"), \
         patch("src.mcp_tools.task_store") as mock_store, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss, \
         patch("src.controller.kb_export_controller.image_cache") as mock_cache:
        from src.models.schemas import CreateTaskResponse
        mock_create.return_value = (CreateTaskResponse(
            task_id="img123", filename="chart.pdf", status="pending",
            total_pages=1, created_at="2026-01-01",
        ), "/tmp/chart.pdf")
        mock_store.get.return_value = mock_image_task
        mock_oss.is_oss_enabled.return_value = True
        mock_oss.upload_image.return_value = None
        mock_cache.get.return_value = b"fake_image_bytes"

        result = parse_pdf(text_pdf, include_images=True)

    assert "error" not in result
    for chunk in result["chunks"]:
        assert "![" not in chunk["content"]
