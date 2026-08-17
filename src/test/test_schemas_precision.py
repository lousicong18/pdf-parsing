"""Precision-first architecture: Block dual fields (extraction + presentation),
JSON export preserves bbox / merged cells / page_type."""

from src.models.schemas import (
    Block, ImageData, MergedCell, PageFeatures, PageResult, ParseResult,
    TableData, TaskError, TaskMetrics, VlmCallMetric,
)


def test_block_preserves_bbox_and_page_type():
    b = Block(type="text", bbox=[1, 2, 3, 4], page_type="text", order=0, content="hello")
    assert b.bbox == [1, 2, 3, 4]
    assert b.page_type == "text"


def test_block_extraction_vs_presentation():
    b = Block(
        type="text", bbox=[0, 0, 100, 20], page_type="text", order=0,
        text="structured truth", content="markdown view",
    )
    assert b.text == "structured truth"
    assert b.content == "markdown view"


def test_table_data_merged_cells():
    td = TableData(
        rows=[["A", "B"], ["C", "D"]],
        n_rows=2, n_cols=2,
        merged=[MergedCell(row=0, col=0, rowspan=1, colspan=2)],
    )
    assert td.merged[0].colspan == 2
    assert td.cross_page is False


def test_json_export_preserves_precision():
    td = TableData(
        rows=[["h1", "h2"], ["c1", "c2"]],
        n_rows=2, n_cols=2,
        merged=[MergedCell(row=0, col=0, rowspan=1, colspan=2)],
        cross_page=True,
        bbox=[10, 10, 500, 200],
    )
    b = Block(type="table", bbox=[10, 10, 500, 200], page_type="table", order=0,
              table=td, content="| h1 | h2 |")
    page = PageResult(page=1, type="table", blocks=[b])
    result = ParseResult(task_id="abc", filename="x.pdf", status="completed",
                         total_pages=1, pages=[page], created_at="2026-08-14T00:00:00Z")
    payload = result.model_dump()
    out_page = payload["pages"][0]
    out_block = out_page["blocks"][0]
    assert out_block["bbox"] == [10, 10, 500, 200]
    assert out_block["page_type"] == "table"
    assert out_block["table"]["merged"][0]["colspan"] == 2
    assert out_block["table"]["cross_page"] is True


def test_image_block_precision():
    img = ImageData(description="desc", image_url="/img/1", mime="image/png", width=100, height=50)
    b = Block(type="image", bbox=[5, 5, 105, 55], page_type="mixed", order=0,
              image=img, content="desc", image_url="/img/1")
    payload = b.model_dump()
    assert payload["image"]["description"] == "desc"
    assert payload["image"]["width"] == 100
    assert payload["bbox"] == [5, 5, 105, 55]


def test_task_metrics_accumulate():
    ctx = TaskMetrics()
    m = VlmCallMetric(kind="image", model="glm-4v", latency_ms=100, tokens=50,
                      cost_usd=0.001, retry=0, success=True)
    ctx.vlm_calls.append(m)
    ctx.total_cost += m.cost_usd
    assert len(ctx.vlm_calls) == 1
    assert ctx.total_cost == 0.001
