# Mixed Route Chart-Embedded Table Parser Design

> Chart-embedded table pages (page10/24/25/38/58) currently route to `table` path and produce unusable output. This design routes them through `mixed` with VLM structure detection + vector graphics data extraction.

## Problem

Chart-embedded table pages have no table grid lines (dots/bars/areas are drawn as vector fills, not cells). `HybridExtractor` (pdfplumber + camelot) cannot detect them as tables, producing broken output.

Five sample PDFs reveal four distinct layouts:

| PDF | Dots | Rects | Lines | Type |
|-----|------|-------|-------|------|
| page10 | 6 | 14 (horizontal) | 1185 | Horizontal bar chart (trend) |
| page24 | 135 | 5 | 250 | Dot chart (3 colors x 45 rows) |
| page25 | 144 | 9 | 250 | Dot + bar mixed |
| page38 | 65 | 2 | 91 | Ranking table (multi-color, full-width) |
| page58 | 54 | 55 (46h+9v) | 71 | Mixed: dots + horizontal + vertical bars |

Chart types needed: dot, line, bar_horizontal, bar_vertical, bar_stacked, area, pie, scatter, radar.

## Architecture

```
classify_page()
  └── many fills + few grid lines → "mixed" (not "table")

dispatch_page("mixed")
  └── process_mixed_page()
        ├── _is_chart_table_page() → bool
        │     └── filled_path_count > 50 and line_count < 20
        └── process_chart_table_page()
              ├── 1. _page_fingerprint() → cache lookup
              ├── 2. cache miss → _vlm_detect_structure() (with few-shot examples)
              ├── 3. _extract_chart_data() (dispatch by chart_type)
              │     ├── dot → _extract_dot_chart (x/y → value via scale)
              │     ├── bar_horizontal → _extract_hbar_chart (width → value)
              │     ├── bar_vertical → _extract_vbar_chart (height → value)
              │     ├── bar_stacked → _extract_stacked_bar (segment heights)
              │     ├── area → _extract_area_chart (boundary → value)
              │     ├── pie → _extract_pie_chart (angle → percentage)
              │     ├── scatter → _extract_scatter_chart (x/y → values)
              │     └── radar → _extract_radar_chart (distance → value)
              └── 4. _merge_to_markdown() (table + inline annotations)
```

## Division of Responsibilities

**VLM (whole page image):**
- Identify chart type per region
- Locate chart area, text columns, annotation area
- Parse legend (color → series name)
- Determine scale (axis, min, max, unit)
- Output structured JSON (no numeric data values)

**Vector graphics (`get_drawings()`):**
- Precise geometric measurement (position, size, angle, distance)
- Map geometry to values using VLM-provided scale
- Chart-type-specific extraction logic

**Merge:**
- Combine structure (VLM) + data (vector) + text → Markdown table
- Attach per-row annotations inline (y-coordinate matching)

## VLM Prompt (Generic with Few-Shot)

```
Analyze the chart/data visualization elements in this PDF page image.

Tasks:
1. Identify the type of each chart or data visualization
2. Locate each chart's area and scale/axis
3. Parse the legend (color → series name mapping)
4. Determine page position of each data row/column

Chart types: dot, line, bar_horizontal, bar_vertical, bar_stacked, area, pie, scatter, radar

Output JSON:
{
  "charts": [{
    "chart_type": "dot|line|bar_horizontal|...",
    "chart_area": {"x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0},
    "legend": {"(r,g,b)": "series name"},
    "scale": {"axis": "x|y|radius|angle", "min_value": 0, "max_value": 0, "unit": ""},
    "rows": [{"y_center": 0, "label": "row label"}]
  }],
  "text_columns": [{"x_range": [0, 0], "type": "label|annotation|data"}]
}

Rules:
- Normalize colors to 0-1 range
- Coordinates in PDF points (pt)
- Use "unknown" if chart type cannot be determined
- Do not guess or fill numeric values
```

Few-shot examples embedded for dot chart and horizontal bar chart.

## Template Cache

```python
_template_cache: dict[str, dict] = {}

def _page_fingerprint(page) -> str:
    # Feature: block count, drawing count, distinct color count
    # MD5 hash → 12 char key
```

Same-layout pages (e.g. page24/25) hit cache after first VLM call. 99-page report ≈ 3-5 VLM calls total.

## Output Format (Option B: Table + Inline Annotations)

```markdown
| Details | Grouped by topics | Competitive Comparison | Details/Best in market |
|---|---|---|---|
| Comfort | Driving position | VW:8.8, Toyota:8.5 | Sales staff competence: Lacking product knowledge... |
| Comfort | Quality of ride | VW:8.6, Toyota:8.8 | After-sales service: Slow response... |
```

Each row is self-contained (data + annotation). Natural chunk boundary for knowledge base.

## Schema Changes

`PageFeatures` new field:
```python
filled_path_count: int = 0  # count of filled paths (dots/bars/areas/pies)
```

## File Changes

### `src/parser/classify.py`
- Add `filled_path_count` to `classify_features()`
- Add chart-table detection in `_classify_with_features()`:
  ```python
  if feats.filled_path_count > 50 and feats.line_count < 20:
      return "mixed"
  ```

### `src/parser/mixed.py` (major rewrite)
New functions:
- `_is_chart_table_page(page) -> bool`
- `process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name)`
- `_page_fingerprint(page) -> str`
- `_vlm_detect_structure(page, ...) -> dict`
- `_extract_chart_data(page, structure) -> dict`
- `_extract_dot_chart(page, structure) -> dict`
- `_extract_hbar_chart(page, structure) -> dict`
- `_extract_vbar_chart(page, structure) -> dict`
- `_extract_stacked_bar(page, structure) -> dict`
- `_extract_area_chart(page, structure) -> dict`
- `_extract_pie_chart(page, structure) -> dict`
- `_extract_scatter_chart(page, structure) -> dict`
- `_extract_radar_chart(page, structure) -> dict`
- `_collect_colored_shapes(drawings, chart_area) -> list`
- `_is_background_color(fill) -> bool`
- `_cluster_by_color(shapes, thresh) -> dict`
- `_merge_to_markdown(template, chart_data, page) -> str`
- `_get_row_annotation(page, annotation_area, row_info) -> str`

### `src/parser/extract_table.py` (cleanup)
Remove chart-related functions:
- `_extract_dot_chart_scores()`
- `_build_color_brand_map()`
- `_color_close()`
- `_find_brand_for_dot()`
- `_extract_total_market_bars()`
- `_extract_chart_dots()`
- `_extract_legend_color_map()`
- `_process_chart_columns()`
- `_extend_for_legend()`
- `_attach_annotations()`
- `_group_consecutive_columns()`
- `_keywords_match()`

Keep pure table functions: `extract_tables()`, `_has_content()`, `_is_header_repeat()`, `tables_to_markdown()`, `_fill_merged_cells()`, `_pad_row()`

## Phased Scope

| Phase | Chart Types | Covers |
|-------|-------------|--------|
| P0 | dot, line, bar_horizontal, bar_vertical, bar_stacked | page10/24/25/38/58 |
| P1 | area, scatter | future PDFs |
| P2 | pie, radar | future PDFs |

## Error Handling

- VLM failure → fallback to `_try_rebuild_chart_table()` from `table_extractor.py` (existing logic)
- Unknown chart type → `_extract_generic()` (collect shapes, output positions without scale mapping)
- Empty chart data → output text-only table (no chart columns)

## Testing

1. **P0 pages**: page10/24/25/38/58 all produce valid Markdown with data + annotations
2. **Cache hit**: page25 (same layout as page24) skips VLM, uses cache
3. **Pure table unaffected**: pages with grid lines still route to `table` path
4. **Pure text unaffected**: text-only pages still route to `text` path
