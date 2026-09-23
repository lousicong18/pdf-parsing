"""Tests for _build_segments with include_images parameter."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_result_with_image():
    from src.models.schemas import (
        ParseResult, PageResult, Block, ImageData, TaskMetrics,
    )

    text_block = Block(
        type="text",
        bbox=[0, 0, 100, 20],
        page_type="text",
        order=0,
        content="Some text before image",
    )
    img_block = Block(
        type="image",
        bbox=[0, 30, 100, 130],
        page_type="mixed",
        order=1,
        content="A chart showing data",
        image=ImageData(description="A chart showing data", image_url="/api/v1/tasks/t1/images/0/1"),
        image_url="/api/v1/tasks/t1/images/0/1",
    )
    page = PageResult(page=0, type="mixed", blocks=[text_block, img_block])
    return ParseResult(
        task_id="t1",
        filename="test.pdf",
        status="completed",
        total_pages=1,
        pages=[page],
        metrics=TaskMetrics(),
    )


def test_build_segments_without_images(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    segments = _build_segments(mock_result_with_image, 500, 50, include_images=False)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![" not in image_segs[0]["text"]


def test_build_segments_with_images_oss_success(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    with patch("src.controller.kb_export_controller.image_cache") as mock_cache, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss:
        mock_cache.get.return_value = b"fake_image_bytes"
        mock_oss.upload_image.return_value = "https://oss.example.com/tasks/t1/0_1.png"
        segments = _build_segments(mock_result_with_image, 500, 50, include_images=True)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![A chart showing data](https://oss.example.com/tasks/t1/0_1.png)" in image_segs[0]["text"]


def test_build_segments_with_images_oss_fail(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    with patch("src.controller.kb_export_controller.image_cache") as mock_cache, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss:
        mock_cache.get.return_value = b"fake_image_bytes"
        mock_oss.upload_image.return_value = None
        segments = _build_segments(mock_result_with_image, 500, 50, include_images=True)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![" not in image_segs[0]["text"]


def test_build_segments_with_images_no_cache(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    with patch("src.controller.kb_export_controller.image_cache") as mock_cache, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss:
        mock_cache.get.return_value = None
        segments = _build_segments(mock_result_with_image, 500, 50, include_images=True)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![" not in image_segs[0]["text"]
    mock_oss.upload_image.assert_not_called()


def test_build_segments_default_include_images_false(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    segments = _build_segments(mock_result_with_image, 500, 50)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![" not in image_segs[0]["text"]


def test_build_segments_image_url_parse_error(mock_result_with_image):
    from src.controller.kb_export_controller import _build_segments
    # Corrupt image_url so index parsing fails
    for page in mock_result_with_image.pages:
        for block in page.blocks:
            if block.type == "image":
                block.image_url = "/invalid/url"
    with patch("src.controller.kb_export_controller.image_cache") as mock_cache, \
         patch("src.controller.kb_export_controller.oss_client") as mock_oss:
        segments = _build_segments(mock_result_with_image, 500, 50, include_images=True)
    image_segs = [s for s in segments if s["type"] == "image"]
    assert len(image_segs) == 1
    assert "![" not in image_segs[0]["text"]
    mock_oss.upload_image.assert_not_called()
