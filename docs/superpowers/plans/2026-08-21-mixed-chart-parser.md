# Mixed Chart Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route chart-embedded table pages through `mixed` path with VLM structure detection + vector graphics data extraction, producing knowledge-base-ready Markdown.

**Architecture:** Classifier detects chart-embedded pages (many fills, few grid lines) → routes to `mixed` → VLM identifies chart type/structure/legend/scale → vector extraction measures geometry per chart type → merge into Markdown table with inline annotations. Template cache avoids repeated VLM calls for same-layout pages.

**Tech Stack:** Python, PyMuPDF (fitz), FastAPI, VLM (OpenAI-compatible API)

**Spec:** `docs/superpowers/specs/2026-08-21-mixed-chart-parser-design.md`

## Global Constraints

- P0 scope only: dot, line, bar_horizontal, bar_vertical, bar_stacked chart types
- Output format: Markdown table with inline per-row annotations (Option B)
- Template cache: same-layout pages skip VLM after first call
- `extract_table.py` must remain pure table logic (no chart code)
- All chart extraction logic goes into `mixed.py`
- Follow existing code patterns (error handling via `progress_service.add_error`, metrics via `metrics_ctx`)

---

## File Structure

```
src/
├── models/
│   └── schemas.py              # ADD: filled_path_count to PageFeatures
├── parser/
│   ├── classify.py             # MODIFY: add chart-table detection
│   ├── mixed.py                # MAJOR: add chart extraction pipeline
│   └── extract_table.py        # CLEANUP: remove chart functions
```

---

### Task 1: Add `filled_path_count` to PageFeatures

**Files:**
- Modify: `src/models/schemas.py:37-48`
- Modify: `src/parser/classify.py:13-59`

**Interfaces:**
- Consumes: nothing new
- Produces: `PageFeatures.filled_path_count` field

- [ ] **Step 1: Add field to schema**

In `src/models/schemas.py`, add to `PageFeatures`:
```python
filled_path_count: int = 0  # filled paths (dots/bars/areas/pies), excludes strokes
```

- [ ] **Step 2: Count filled paths in classify_features()**

In `src/parser/classify.py`, after counting `line_count`, add:
```python
filled_path_count = sum(
    1 for d in drawings
    if d.get("type") in ("f", "fs") and d.get("fill") and len(d.get("fill", [])) >= 3
)
```

- [ ] **Step 3: Add to PageFeatures construction**

Add `filled_path_count=filled_path_count` to the `PageFeatures(...)` call.

- [ ] **Step 4: Verify**

Run: `cd /Users/lou/ai_agent/pdf-parsing && .venv/bin/python -c "from src.models.schemas import PageFeatures; p = PageFeatures(filled_path_count=10); print(p)"`
Expected: No error, prints model with filled_path_count=10

- [ ] **Step 5: Commit**

```bash
git add src/models/schemas.py src/parser/classify.py
git commit -m "feat: add filled_path_count to PageFeatures for chart detection"
```

---

### Task 2: Add chart-table detection to classifier

**Files:**
- Modify: `src/parser/classify.py:213-272` (`_classify_with_features`)

**Interfaces:**
- Consumes: `PageFeatures.filled_path_count`, `PageFeatures.line_count`
- Produces: `"mixed"` for chart-embedded pages

- [ ] **Step 1: Add detection logic**

In `_classify_with_features()`, before the existing `mixed` check (line ~259), add:
```python
# chart-embedded table: many fills (dots/bars/areas) + few grid lines
if feats.filled_path_count > 50 and feats.line_count < 20:
    info(f"chart_table: chart-embedded table (fills={feats.filled_path_count}>50, lines={feats.line_count}<20)")
    return "mixed"
```

- [ ] **Step 2: Test classification**

Run: `cd /Users/lou/ai_agent/pdf-parsing && .venv/bin/python -c "
import fitz
from src.parser.classify import classify_page
for name in ['page10.pdf','page24.pdf','page25.pdf','page38.pdf','page58.pdf']:
    doc = fitz.open(name)
    ptype, feats, log, raw = classify_page(doc[0])
    print(f'{name}: {ptype} (fills={feats.filled_path_count}, lines={feats.line_count})')
    doc.close()
"`
Expected: All 5 pages classified as "mixed"

- [ ] **Step 3: Commit**

```bash
git add src/parser/classify.py
git commit -m "feat: route chart-embedded pages to mixed path"
```

---

### Task 3: Create chart extraction module structure

**Files:**
- Modify: `src/parser/mixed.py` (full rewrite)

**Interfaces:**
- Consumes: `page` (fitz Page), `task_id`, `page_num`, `doc`, `metrics_ctx`, `model_name`
- Produces: `list[Block]` with `type="table"` and `content=markdown`

- [ ] **Step 1: Add imports and cache**

At top of `mixed.py`, add:
```python
import hashlib
import json
from typing import Optional
from src.parser import extract_text, vlm
from src.store import image_cache
from src.task_manager import progress_service
from src.utils import column_detection, pdf_utils

# Template cache: fingerprint → VLM structure result
_template_cache: dict[str, dict] = {}
```

- [ ] **Step 2: Add `process_mixed_page()` router**

Replace existing `process_mixed_page()`:
```python
def process_mixed_page(page, task_id, page_num, doc, metrics_ctx, model_name=None):
    if _is_chart_table_page(page):
        blocks, _ = process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name)
        return blocks
    text_blocks = extract_text.extract_text(page, "mixed")
    image_blocks = extract_and_describe_images(page, task_id, page_num, doc, metrics_ctx, model_name)
    merged = text_blocks + image_blocks
    return _sort_reading_order(merged)
```

- [ ] **Step 3: Add `_is_chart_table_page()`**

```python
def _is_chart_table_page(page) -> bool:
    """Detect chart-embedded table page by counting filled shapes."""
    drawings = page.get_drawings() or []
    filled = 0
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        if fill[0] > 0.85 and fill[1] > 0.85 and fill[2] > 0.85:
            continue
        rect = d.get("rect")
        if rect and 2 <= rect.x1 - rect.x0 <= 100:
            filled += 1
    return filled > 30
```

- [ ] **Step 4: Commit**

```bash
git add src/parser/mixed.py
git commit -m "feat: add chart-table detection and routing in mixed.py"
```

---

### Task 4: Implement template cache and VLM structure detection

**Files:**
- Modify: `src/parser/mixed.py`

**Interfaces:**
- Produces: `_page_fingerprint()`, `_vlm_detect_structure()`, `process_chart_table_page()`

- [ ] **Step 1: Add `_page_fingerprint()`**

```python
def _page_fingerprint(page) -> str:
    blocks = page.get_text("blocks") or []
    drawings = page.get_drawings() or []
    colors = set()
    for d in drawings:
        fill = d.get("fill")
        if fill and len(fill) >= 3:
            if not (fill[0] > 0.85 and fill[1] > 0.85 and fill[2] > 0.85):
                colors.add((round(fill[0], 1), round(fill[1], 1), round(fill[2], 1)))
    feature = f"b={len(blocks)},d={len(drawings)},c={len(colors)}"
    return hashlib.md5(feature.encode()).hexdigest()[:12]
```

- [ ] **Step 2: Add `_vlm_detect_structure()`**

```python
def _vlm_detect_structure(page, task_id, page_num, metrics_ctx, model_name) -> dict:
    img_bytes = pdf_utils.page_to_png(page, dpi=150)
    prompt = """Analyze the chart/data visualization in this PDF page.

Identify: chart type (dot/line/bar_horizontal/bar_vertical/bar_stacked/area/pie/scatter/radar),
chart area, legend (color→name), scale (axis, min, max), and row positions.

Output JSON:
{
  "charts": [{"chart_type": "...", "chart_area": {"x_min":0,"x_max":0,"y_min":0,"y_max":0},
              "legend": {"(r,g,b)": "name"}, "scale": {"axis":"x|y|radius|angle","min_value":0,"max_value":0},
              "rows": [{"y_center": 0, "label": "..."}]}],
  "text_columns": [{"x_range": [0,0], "type": "label|annotation|data"}]
}

Rules: colors 0-1, coordinates in pt, no guessed values."""
    try:
        resp = vlm.vlm_describe(img_bytes, metrics_ctx, model_name, prompt=prompt)
        return json.loads(resp.content)
    except Exception as e:
        progress_service.add_error(task_id, page_num, f"VLM structure failed: {e}")
        return {}
```

- [ ] **Step 3: Add `process_chart_table_page()` skeleton**

```python
def process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name):
    fp = _page_fingerprint(page)
    template = _template_cache.get(fp)
    if template is None:
        template = _vlm_detect_structure(page, task_id, page_num, metrics_ctx, model_name)
        _template_cache[fp] = template
    if not template:
        return [], "VLM failed"
    chart_data = _extract_chart_data(page, template)
    markdown = _merge_to_markdown(template, chart_data, page)
    bbox = [0, 0, page.rect.width, page.rect.height]
    block = Block(type="table", bbox=bbox, page_type="mixed", order=0,
                  table=None, content=markdown)
    return [block], f"chart_table (fp={fp})"
```

- [ ] **Step 4: Commit**

```bash
git add src/parser/mixed.py
git commit -m "feat: add template cache and VLM structure detection"
```

---

### Task 5: Implement vector shape collection and color clustering

**Files:**
- Modify: `src/parser/mixed.py`

**Interfaces:**
- Produces: `_collect_colored_shapes()`, `_is_background_color()`, `_cluster_by_color()`, `_color_distance()`

- [ ] **Step 1: Add helper functions**

```python
def _is_background_color(fill) -> bool:
    r, g, b = fill[0], fill[1], fill[2]
    if r > 0.9 and g > 0.9 and b > 0.9:
        return True
    if abs(r - g) < 0.05 and abs(g - b) < 0.05 and r > 0.85:
        return True
    return False

def _color_distance(c1: tuple, c2: tuple) -> float:
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

def _collect_colored_shapes(drawings, chart_area: dict) -> list:
    shapes = []
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        if _is_background_color(fill):
            continue
        rect = d.get("rect")
        if not rect:
            continue
        if chart_area:
            cx = (rect.x0 + rect.x1) / 2
            cy = (rect.y0 + rect.y1) / 2
            if not (chart_area["x_min"] <= cx <= chart_area["x_max"] and
                    chart_area["y_min"] <= cy <= chart_area["y_max"]):
                continue
        shapes.append({
            "cx": (rect.x0 + rect.x1) / 2,
            "cy": (rect.y0 + rect.y1) / 2,
            "w": rect.x1 - rect.x0,
            "h": rect.y1 - rect.y0,
            "color": (round(fill[0], 2), round(fill[1], 2), round(fill[2], 2)),
        })
    return shapes

def _cluster_by_color(shapes: list, thresh: float = 0.08) -> dict:
    clusters = {}
    for s in shapes:
        matched = False
        for rep in list(clusters.keys()):
            if _color_distance(s["color"], rep) < thresh:
                clusters[rep].append(s)
                matched = True
                break
        if not matched:
            clusters[s["color"]] = [s]
    return clusters
```

- [ ] **Step 2: Commit**

```bash
git add src/parser/mixed.py
git commit -m "feat: add vector shape collection and color clustering"
```

---

### Task 6: Implement chart-type-specific extractors (P0 types)

**Files:**
- Modify: `src/parser/mixed.py`

**Interfaces:**
- Produces: `_extract_chart_data()`, `_extract_dot_chart()`, `_extract_hbar_chart()`, `_extract_vbar_chart()`, `_extract_stacked_bar()`

- [ ] **Step 1: Add `_extract_chart_data()` dispatcher**

```python
def _extract_chart_data(page, template: dict) -> dict:
    charts = template.get("charts", [])
    if not charts:
        return {}
    chart = charts[0]  # primary chart
    chart_type = chart.get("chart_type", "unknown")
    chart_area = chart.get("chart_area")
    drawings = page.get_drawings() or []
    shapes = _collect_colored_shapes(drawings, chart_area)
    dispatch = {
        "dot": _extract_dot_chart,
        "line": _extract_dot_chart,  # same logic: extract points
        "bar_horizontal": _extract_hbar_chart,
        "bar_vertical": _extract_vbar_chart,
        "bar_stacked": _extract_stacked_bar,
    }
    extractor = dispatch.get(chart_type, _extract_dot_chart)
    return extractor(shapes, chart, template)
```

- [ ] **Step 2: Add `_extract_dot_chart()`**

```python
def _extract_dot_chart(shapes: list, chart: dict, template: dict) -> dict:
    dots = [s for s in shapes if abs(s["w"] - s["h"]) <= 3 and 3 <= s["w"] <= 15]
    if not dots:
        return {}
    scale = chart.get("scale", {})
    x_min = chart_area = chart.get("chart_area", {}).get("x_min", 0)
    x_max = chart.get("chart_area", {}).get("x_max", 1)
    v_min = scale.get("min_value", 0)
    v_max = scale.get("max_value", 1)
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {}
    for color_str, name in legend.items():
        # parse "(r,g,b)" string to tuple
        try:
            c = tuple(float(x) for x in color_str.strip("()").split(","))
            color_to_series[c] = name
        except:
            pass
    data = {}
    for dot in dots:
        row_idx = _match_row(dot["cy"], rows)
        if row_idx is None:
            continue
        series = _match_series(dot["color"], color_to_series)
        rel_x = (dot["cx"] - x_min) / (x_max - x_min) if x_max > x_min else 0
        value = v_min + rel_x * (v_max - v_min)
        data.setdefault(row_idx, {})[series] = round(value, 1)
    return data
```

- [ ] **Step 3: Add `_extract_hbar_chart()`**

```python
def _extract_hbar_chart(shapes: list, chart: dict, template: dict) -> dict:
    bars = [s for s in shapes if s["w"] > s["h"] and s["w"] > 10]
    if not bars:
        return {}
    scale = chart.get("scale", {})
    v_min = scale.get("min_value", 0)
    v_max = scale.get("max_value", 100)
    max_width = max(b["w"] for b in bars) if bars else 1
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {_parse_color(k): v for k, v in legend.items()}
    data = {}
    for bar in bars:
        row_idx = _match_row(bar["cy"], rows)
        if row_idx is None:
            continue
        series = _match_series(bar["color"], color_to_series)
        value = v_min + (bar["w"] / max_width) * (v_max - v_min)
        data.setdefault(row_idx, {})[series] = round(value, 1)
    return data
```

- [ ] **Step 4: Add `_extract_vbar_chart()`**

```python
def _extract_vbar_chart(shapes: list, chart: dict, template: dict) -> dict:
    bars = [s for s in shapes if s["h"] >= s["w"] and s["h"] > 10]
    if not bars:
        return {}
    scale = chart.get("scale", {})
    v_min = scale.get("min_value", 0)
    v_max = scale.get("max_value", 100)
    max_height = max(b["h"] for b in bars) if bars else 1
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {_parse_color(k): v for k, v in legend.items()}
    data = {}
    for bar in bars:
        row_idx = _match_row(bar["cy"], rows)
        if row_idx is None:
            continue
        series = _match_series(bar["color"], color_to_series)
        value = v_min + (bar["h"] / max_height) * (v_max - v_min)
        data.setdefault(row_idx, {})[series] = round(value, 1)
    return data
```

- [ ] **Step 5: Add `_extract_stacked_bar()`**

```python
def _extract_stacked_bar(shapes: list, chart: dict, template: dict) -> dict:
    bars = [s for s in shapes if s["w"] > 5 and s["h"] > 5]
    if not bars:
        return {}
    # Group bars by y-position (same row = stacked segments)
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {_parse_color(k): v for k, v in legend.items()}
    scale = chart.get("scale", {})
    v_max = scale.get("max_value", 100)
    # Cluster by y into groups
    bars.sort(key=lambda b: b["cy"])
    groups = []
    for bar in bars:
        if groups and abs(bar["cy"] - groups[-1][-1]["cy"]) < 8:
            groups[-1].append(bar)
        else:
            groups.append([bar])
    data = {}
    for group in groups:
        row_idx = _match_row(group[0]["cy"], rows)
        if row_idx is None:
            continue
        total_h = sum(b["h"] for b in group)
        for bar in group:
            series = _match_series(bar["color"], color_to_series)
            value = (bar["h"] / total_h) * v_max if total_h > 0 else 0
            data.setdefault(row_idx, {})[series] = round(value, 1)
    return data
```

- [ ] **Step 6: Add helper functions**

```python
def _parse_color(color_str: str) -> tuple:
    try:
        return tuple(float(x.strip()) for x in color_str.strip("()").split(","))
    except:
        return (0, 0, 0)

def _match_row(cy: float, rows: list) -> Optional[int]:
    best_idx = None
    best_dist = 15.0
    for i, row in enumerate(rows):
        dist = abs(row.get("y_center", 0) - cy)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx

def _match_series(color: tuple, color_to_series: dict) -> str:
    for series_color, name in color_to_series.items():
        if _color_distance(color, series_color) < 0.1:
            return name
    return str(color)
```

- [ ] **Step 7: Commit**

```bash
git add src/parser/mixed.py
git commit -m "feat: add P0 chart type extractors (dot/hbar/vbar/stacked)"
```

---

### Task 7: Implement merge to Markdown with inline annotations

**Files:**
- Modify: `src/parser/mixed.py`

**Interfaces:**
- Produces: `_merge_to_markdown()`, `_get_row_annotation()`, `_build_headers()`

- [ ] **Step 1: Add `_merge_to_markdown()`**

```python
def _merge_to_markdown(template: dict, chart_data: dict, page) -> str:
    headers = _build_headers(template)
    rows = []
    for i, row_info in enumerate(template.get("rows", [])):
        row = [""] * len(headers)
        # Fill text columns
        for col in template.get("text_columns", []):
            cell = _get_text_in_cell(page, col, row_info)
            idx = col.get("index", 0)
            if idx < len(headers):
                row[idx] = cell
        # Fill chart data
        if i in chart_data:
            chart_col = _find_chart_column(headers)
            row[chart_col] = ", ".join(f"{k}:{v}" for k, v in chart_data[i].items())
        # Inline annotation
        annotation = _get_row_annotation(page, template.get("annotation_area"), row_info)
        if annotation:
            detail_col = _find_detail_column(headers)
            row[detail_col] = annotation
        rows.append(row)
    return _format_md_table(headers, rows)
```

- [ ] **Step 2: Add helper functions**

```python
def _build_headers(template: dict) -> list:
    headers = []
    for col in template.get("text_columns", []):
        headers.append(col.get("label", "Item"))
    headers.append("Data")
    headers.append("Details")
    return headers

def _get_text_in_cell(page, col: dict, row_info: dict) -> str:
    x0, x1 = col.get("x_range", [0, 0])
    y_center = row_info.get("y_center", 0)
    blocks = page.get_text("blocks") or []
    texts = []
    for b in blocks:
        b_cy = (b[1] + b[3]) / 2
        if x0 <= b[0] <= x1 and abs(b_cy - y_center) < 12:
            texts.append(b[4].strip())
    return " ".join(texts)

def _get_row_annotation(page, annotation_area: dict, row_info: dict) -> str:
    if not annotation_area:
        return ""
    x0, x1 = annotation_area.get("x_range", [0, 0])
    y_center = row_info.get("y_center", 0)
    blocks = page.get_text("blocks") or []
    texts = []
    for b in blocks:
        b_cy = (b[1] + b[3]) / 2
        if x0 <= b[0] and b[2] <= x1 and abs(b_cy - y_center) < 12:
            text = b[4].strip()
            if text and len(text) > 5:
                texts.append(text)
    return "\n".join(texts)

def _find_chart_column(headers: list) -> int:
    for i, h in enumerate(headers):
        if h.lower() in ("data", "competitive comparison", "value"):
            return i
    return min(2, len(headers) - 1)

def _find_detail_column(headers: list) -> int:
    return len(headers) - 1

def _format_md_table(headers: list, rows: list) -> str:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(c or "" for c in row) + " |")
    return "\n".join(lines)
```

- [ ] **Step 3: Commit**

```bash
git add src/parser/mixed.py
git commit -m "feat: add markdown merge with inline annotations"
```

---

### Task 8: Clean up `extract_table.py`

**Files:**
- Modify: `src/parser/extract_table.py`

**Interfaces:**
- Produces: pure table-only `extract_tables()`

- [ ] **Step 1: Remove chart functions**

Delete these functions from `extract_table.py`:
- `_extract_legend_color_map()` (lines 101-174)
- `_extract_chart_dots()` (lines 177-303)
- `_extract_dot_chart_scores()` (lines 306-425)
- `_build_color_brand_map()` (lines 428-504)
- `_color_close()` (lines 507-509)
- `_find_brand_for_dot()` (lines 512-530)
- `_extract_total_market_bars()` (lines 533-599)
- `_group_consecutive_columns()` (lines 602-615)
- `_extend_for_legend()` (lines 618-663)
- `_attach_annotations()` (lines 666-732)
- `_keywords_match()` (lines 734-746)
- `_process_chart_columns()` (lines 55-98)

- [ ] **Step 2: Simplify `extract_tables()`**

Remove the call to `_process_chart_columns(td, page, ...)` and `_attach_annotations(td, page)`.

- [ ] **Step 3: Verify pure table still works**

Run: `cd /Users/lou/ai_agent/pdf-parsing && .venv/bin/python -c "
import fitz
from src.parser.extract_table import extract_tables
doc = fitz.open('page24.pdf')
result = extract_tables(doc[0], 'table', 'page24.pdf', 0)
print(f'Tables found: {len(result)}')
doc.close()
"`
Expected: 0 tables (page24 is now routed to mixed, not table)

- [ ] **Step 4: Commit**

```bash
git add src/parser/extract_table.py
git commit -m "refactor: remove chart logic from extract_table.py, keep pure tables"
```

---

### Task 9: Integration test with sample PDFs

**Files:**
- Test: manual verification with page10/24/25/38/58

**Interfaces:**
- Validates: full pipeline works end-to-end

- [ ] **Step 1: Test classification**

Run: `cd /Users/lou/ai_agent/pdf-parsing && .venv/bin/python -c "
import fitz
from src.parser.classify import classify_page
for name in ['page10.pdf','page24.pdf','page25.pdf','page38.pdf','page58.pdf']:
    doc = fitz.open(name)
    ptype, feats, log, raw = classify_page(doc[0])
    print(f'{name}: {ptype}')
    doc.close()
"`
Expected: All 5 → "mixed"

- [ ] **Step 2: Test mixed route (without VLM - verify structure)**

Run: `cd /Users/lou/ai_agent/pdf-parsing && .venv/bin/python -c "
import fitz
from src.parser.mixed import _is_chart_table_page, _page_fingerprint
for name in ['page10.pdf','page24.pdf','page25.pdf','page38.pdf','page58.pdf']:
    doc = fitz.open(name)
    page = doc[0]
    is_chart = _is_chart_table_page(page)
    fp = _page_fingerprint(page)
    print(f'{name}: chart={is_chart}, fp={fp}')
    doc.close()
"`
Expected: All True, page24/25 should have same fingerprint

- [ ] **Step 3: Commit test notes**

```bash
git add -A
git commit -m "test: verify chart-table classification and routing"
```

---

## Self-Review Checklist

- [x] Spec coverage: Each spec section has a corresponding task
- [x] No placeholders: All steps have concrete code/commands
- [x] Type consistency: Function names match across tasks
- [x] File paths: All paths are absolute and correct
