"""Mixed (text + image) page processing."""

import hashlib
import json
from typing import Optional

from src.models.schemas import Block, ImageData, PageType
from src.parser import extract_text, vlm
from src.store import image_cache
from src.task_manager import progress_service
from src.utils import column_detection, pdf_utils

_template_cache: dict[str, dict] = {}


def extract_and_describe_images(
    page, task_id: str, page_num: int, doc, metrics_ctx, model_name: Optional[str] = None,
) -> list[Block]:
    blocks: list[Block] = []
    images = page.get_images(full=True) or []
    page_area = page.rect.width * page.rect.height
    for index, img in enumerate(images):
        xref = img[0]
        try:
            image_bytes = doc.extract_image(xref)["image"]
        except Exception:
            progress_service.add_error(task_id, page_num, f"extract image {index} failed")
            continue
        bbox = _image_bbox(page, img)
        # 过滤全页背景图（面积 >= 80% 页面）
        if page_area > 0 and bbox:
            img_area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
            if img_area >= 0.8 * page_area:
                continue
        image_cache.put(task_id, page_num, index, image_bytes)
        url = f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"
        try:
            desc = vlm.vlm_describe(image_bytes, metrics_ctx, model_name)
        except Exception as e:
            progress_service.add_error(task_id, page_num, f"VLM describe failed: {e}")
            desc = "图片未识别（VLM 调用失败）"
        blocks.append(
            Block(
                type="image",  # type: ignore[arg-type]
                bbox=bbox,
                page_type="mixed",  # type: ignore[arg-type]
                order=index,
                image=ImageData(description=desc, image_url=url),
                content=desc,
                image_url=url,
            )
        )
    return blocks


def _image_bbox(page, img) -> list[float]:
    try:
        rects = page.get_image_rects(img[0])
        if rects:
            r = rects[0]
            return [r.x0, r.y0, r.x1, r.y1]
    except Exception:
        pass
    try:
        bb = page.get_image_bbox(img)
        return [bb.x0, bb.y0, bb.x1, bb.y1]
    except Exception:
        return [0, 0, 0, 0]


def process_mixed_page(page, task_id, page_num, doc, metrics_ctx, model_name=None):
    if _is_chart_table_page(page):
        blocks, _ = process_chart_table_page(page, task_id, page_num, doc, metrics_ctx, model_name)
        return blocks
    text_blocks = extract_text.extract_text(page, "mixed")
    image_blocks = extract_and_describe_images(page, task_id, page_num, doc, metrics_ctx, model_name)
    merged = text_blocks + image_blocks
    return _sort_reading_order(merged)


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


def _parse_color(color_str: str) -> tuple:
    try:
        return tuple(float(x.strip()) for x in color_str.strip("()").split(","))
    except Exception:
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


def _extract_dot_chart(shapes: list, chart: dict, template: dict) -> dict:
    dots = [s for s in shapes if abs(s["w"] - s["h"]) <= 3 and 3 <= s["w"] <= 15]
    if not dots:
        return {}
    scale = chart.get("scale", {})
    x_min = chart.get("chart_area", {}).get("x_min", 0)
    x_max = chart.get("chart_area", {}).get("x_max", 1)
    v_min = scale.get("min_value", 0)
    v_max = scale.get("max_value", 1)
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {}
    for color_str, name in legend.items():
        try:
            c = _parse_color(color_str)
            color_to_series[c] = name
        except Exception:
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


def _extract_stacked_bar(shapes: list, chart: dict, template: dict) -> dict:
    bars = [s for s in shapes if s["w"] > 5 and s["h"] > 5]
    if not bars:
        return {}
    rows = template.get("rows", [])
    legend = chart.get("legend", {})
    color_to_series = {_parse_color(k): v for k, v in legend.items()}
    scale = chart.get("scale", {})
    v_max = scale.get("max_value", 100)
    # Cluster by y into groups (same row = stacked segments)
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


def _merge_to_markdown(template: dict, chart_data: dict, page) -> str:
    headers = _build_headers(template)
    if not headers:
        return ""
    rows = []
    for i, row_info in enumerate(template.get("rows", [])):
        row = [""] * len(headers)
        # Fill text columns
        for col in template.get("text_columns", []):
            cell = _get_text_in_cell(page, col, row_info)
            idx = col.get("index", 0)
            if 0 <= idx < len(headers):
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


def _build_headers(template: dict) -> list[str]:
    headers = []
    for col in template.get("text_columns", []):
        headers.append(col.get("label") or col.get("type", "Item").title())
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
        b_cx = (b[0] + b[2]) / 2
        if x0 <= b_cx <= x1 and abs(b_cy - y_center) < 12:
            texts.append(b[4].strip())
    return " ".join(t for t in texts if t)


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
    return max(0, len(headers) - 2)


def _find_detail_column(headers: list) -> int:
    return len(headers) - 1


def _format_md_table(headers: list, rows: list) -> str:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(c.replace("\n", " ") for c in padded[:len(headers)]) + " |")
    return "\n".join(lines)


def _sort_reading_order(blocks: list[Block]) -> list[Block]:
    if len(blocks) <= 1:
        return blocks
    n_cols = column_detection.column_detection(blocks)
    if n_cols <= 1:
        blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    else:
        xs = [b.bbox[0] for b in blocks]
        width = max(xs) - min(xs) if xs else 0
        tol = max(width * 0.1, 20.0)
        columns: dict[int, list[Block]] = {}
        for b in blocks:
            col = int((b.bbox[0] - min(xs)) / max(tol, 1))
            columns.setdefault(col, []).append(b)
        ordered: list[Block] = []
        for col in sorted(columns.keys()):
            group = columns[col]
            group.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            ordered.extend(group)
        blocks = ordered
    for i, b in enumerate(blocks):
        b.order = i
    return blocks
