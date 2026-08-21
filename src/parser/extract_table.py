"""Table extraction via pluggable TableExtractor, with cross-page annotation."""

from typing import Optional

from src.models.schemas import Block, MergedCell, PageType, TableData
from src.parser import table_extractor


def extract_tables(
    page,
    page_type: PageType,
    pdf_path: str,
    page_num: int,
    prev_type: Optional[str] = None,
    prev_header: Optional[list[str]] = None,
    task_id: Optional[str] = None,
    metrics_ctx=None,
    model_name: Optional[str] = None,
) -> list[Block]:
    extractor = table_extractor.get_table_extractor()
    try:
        tables = extractor.extract(page, pdf_path, page_num)
    except Exception:
        return []
    tables = [t for t in tables if _has_content(t)]  # 过滤空表格
    blocks: list[Block] = []
    for i, td in enumerate(tables):
        td.cross_page = prev_type == "table"
        # 检测续表行是否与上一页表头重复
        if td.cross_page and prev_header and td.rows and _is_header_repeat(td.rows[0], prev_header):
            td.header_repeat = True
            td.rows = td.rows[1:]
            td.n_rows = max(td.n_rows - 1, 0)
        # 处理图表列：渲染为图片 + VLM 描述
        _process_chart_columns(td, page, task_id, metrics_ctx, model_name)
        # 关联表格外的注解文本到对应行
        _attach_annotations(td, page)
        content = tables_to_markdown(td)
        if td.cross_page:
            content = "> （跨页续表）\n" + content
        bbox = td.bbox if td.bbox else [0, 0, page.rect.width, page.rect.height]
        blocks.append(
            Block(
                type="table",  # type: ignore[arg-type]
                bbox=bbox,
                page_type=page_type,
                order=i,
                table=td,
                content=content,
            )
        )
    return blocks


def _process_chart_columns(
    td: TableData,
    page,
    task_id: Optional[str] = None,
    metrics_ctx=None,
    model_name: Optional[str] = None,
) -> None:
    """处理表格中的图表列：通过矢量图形几何提取数据，不使用 VLM。

    从页面彩色圆点图表提取每行品牌分数，将 x 坐标映射为刻度值（7.0-9.5）。
    输出格式：品牌名:分数（如 "Total market:8.7, Volkswagen:8.8, Toyota:8.5, Honda:8.6"）
    """
    if not td.rows or not page:
        return

    # 使用检测到的图表列索引
    chart_columns = td.chart_columns
    if not chart_columns:
        return

    # 提取圆点图表数据（每行品牌分数）
    dot_data = _extract_dot_chart_scores(page)

    # 将提取的数据填入第一个图表列单元格，表头设为 "Competitive Comparison"
    # dot_data row_idx 从 0 开始（第一个数据行），对应 td.rows[row_idx + 1]（跳过表头）
    primary_chart_col = chart_columns[0]
    for dot_row_idx, scores in dot_data.items():
        table_row_idx = dot_row_idx + 1  # +1 跳过表头
        if table_row_idx < len(td.rows) and scores:
            td.rows[table_row_idx][primary_chart_col] = ", ".join(scores)
    # 将第一个图表列的表头设为 "Competitive Comparison"，清空其他同名表头避免重复
    for c in range(len(td.rows[0])):
        if td.rows[0][c] == "Competitive Comparison" and c != primary_chart_col:
            td.rows[0][c] = ""
    td.rows[0][primary_chart_col] = "Competitive Comparison"

    # 删除多余的图表列（从后往前删，避免索引偏移）
    for c in reversed(chart_columns[1:]):
        for row in td.rows:
            if len(row) > c:
                row.pop(c)
        td.n_cols -= 1

    # 注意：页面右侧 x>700 的标签是折线图图例（品牌颜色说明），不是独立柱状图


def _extract_legend_color_map(page, table_x0: float, table_y0: float, table_x1: float, table_y1: float) -> dict[tuple, str]:
    """从图表图例区域提取颜色到品牌的映射。

    图例通常在图表右侧，包含品牌名和对应颜色标记。
    返回: {RGB元组: 品牌名}
    """
    color_map: dict[tuple, str] = {}
    try:
        # 获取图例区域文本和颜色
        d = page.get_text("dict")
        drawings = page.get_drawings() or []
    except Exception:
        return color_map

    # 收集图例文本（x > table_x1 - 100, y 在图表区域内）
    legend_texts = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                x0 = span["bbox"][0]
                y0 = span["bbox"][1]
                text = span.get("text", "").strip()
                if not text:
                    continue
                # 图例区域：x 在表格右侧，y 在图表底部
                if x0 > table_x1 - 150 and table_y0 < y0 < table_y1 + 20:
                    legend_texts.append({
                        "cy": (span["bbox"][1] + span["bbox"][3]) / 2,
                        "text": text,
                        "color": span.get("color", 0),
                    })

    # 收集图例颜色标记（小彩色方块）
    legend_colors = []
    for d2 in drawings:
        if d2.get("type") not in ("f", "fs"):
            continue
        fill = d2.get("fill")
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[0], fill[1], fill[2]
        if r > 0.85 and g > 0.85 and b > 0.85:
            continue
        if abs(r - g) < 0.05 and abs(g - b) < 0.05 and r > 0.5:
            continue
        rect = d2.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        cx = (rect.x0 + rect.x1) / 2
        cy = (rect.y0 + rect.y1) / 2
        # 小方块（图例标记通常 5-15pt）
        if w < 20 and h < 20 and cx > table_x1 - 150 and table_y0 < cy < table_y1 + 20:
            legend_colors.append({
                "cy": cy,
                "color": (round(r, 2), round(g, 2), round(b, 2)),
            })

    # 匹配颜色和文本（按 y 坐标最近匹配）
    for lc in legend_colors:
        best_text = ""
        best_dy = 10.0
        for lt in legend_texts:
            dy = abs(lc["cy"] - lt["cy"])
            if dy < best_dy:
                best_dy = dy
                best_text = lt["text"]
        if best_text and lc["color"] not in color_map:
            color_map[lc["color"]] = best_text

    return color_map


def _extract_chart_dots(
    page,
    table_x0: float,
    table_y0: float,
    col_width: float,
    row_height: float,
    chart_columns: list[int],
    n_rows: int,
    color_to_brand: dict[tuple, str] | None = None,
    data_row_ys: list[float] | None = None,
) -> dict[tuple[int, int], list[str]]:
    """从页面矢量图形中提取图表列中的彩色圆点位置。

    返回: {(row_idx, col_idx): ["品牌:分数", ...]}

    策略：按颜色分组 → 按 y 坐标聚类为若干行 → 映射到表格行索引。
    """
    result: dict[tuple[int, int], list[str]] = {}
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return result

    if not drawings:
        return result

    if color_to_brand is None:
        color_to_brand = {}

    # 颜色到品牌的映射（基于大众集团 NCBS 报告的标准图例）
    # 深蓝色 = Audi, 浅棕色 = Mercedes-Benz, 紫红色 = BMW
    def color_name(rgb):
        r, g, b = rgb
        if r < 0.2 and g < 0.4 and b > 0.3:
            return "Audi"
        if r > 0.8 and g > 0.6 and b > 0.4:
            return "Mercedes"
        if r > 0.4 and g < 0.4 and b > 0.2:
            return "BMW"
        return f"({r:.1f},{g:.1f},{b:.1f})"

    # 收集所有非灰色、非白色的填充圆点
    dot_candidates = []
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        r, g, b = fill[0], fill[1], fill[2]
        if r > 0.85 and g > 0.85 and b > 0.85:
            continue
        if abs(r - g) < 0.05 and abs(g - b) < 0.05 and r > 0.5:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        if abs(w - h) > 3 or w < 3 or w > 15:
            continue
        dot_candidates.append({
            "cx": (rect.x0 + rect.x1) / 2,
            "cy": (rect.y0 + rect.y1) / 2,
            "color": (round(r, 2), round(g, 2), round(b, 2)),
        })

    if not dot_candidates:
        return result

    scale_min, scale_max = 7.0, 9.5

    # 图表可能横跨所有 [chart] 列（如 dumbbell 图表），将第一个到最后一个 chart 列视为一个整体区域
    region_x0 = table_x0 + chart_columns[0] * col_width
    region_x1 = table_x0 + (chart_columns[-1] + 1) * col_width
    region_width = region_x1 - region_x0
    if region_width <= 0:
        return result

    # 提取该区域内的所有圆点
    group_dots = [d for d in dot_candidates if region_x0 <= d["cx"] < region_x1]
    if not group_dots:
        return result

    group_x0, group_x1, group_width = region_x0, region_x1, region_width

    group_dots.sort(key=lambda d: d["cy"])
    tolerance = max(row_height * 0.5, 5.0)
    clusters: list[list[dict]] = []
    for dot in group_dots:
        if clusters and abs(dot["cy"] - clusters[-1][-1]["cy"]) < tolerance:
            clusters[-1].append(dot)
        else:
            clusters.append([dot])

    for cluster in clusters:
            avg_y = sum(d["cy"] for d in cluster) / len(cluster)
            if data_row_ys:
                # 精确匹配：找最近的 data_row_ys，映射回行索引（+1 跳过表头行）
                best_i = min(range(len(data_row_ys)), key=lambda i: abs(data_row_ys[i] - avg_y))
                if abs(data_row_ys[best_i] - avg_y) > row_height * 1.5:
                    continue
                row_idx = best_i + 1
            else:
                row_idx = round((avg_y - table_y0) / row_height)
            if row_idx < 1 or row_idx >= n_rows:
                continue
            # 去重：同色点取中心
            color_groups: dict[tuple, list[float]] = {}
            for d in cluster:
                c = d["color"]
                if c not in color_groups:
                    color_groups[c] = []
                rel_x = max(0.0, min(1.0, (d["cx"] - group_x0) / group_width))
                color_groups[c].append(rel_x)
            scores = []
            for color, x_vals in color_groups.items():
                avg_x = sum(x_vals) / len(x_vals)
                score = round((scale_min + avg_x * (scale_max - scale_min)) * 10) / 10
                brand = color_to_brand.get(color, color_name(color))
                scores.append(f"{brand}:{score}")
            if scores:
                # 所有 [chart] 列共享相同数据
                for col_idx in chart_columns:
                    result[(row_idx, col_idx)] = scores

    return result


def _extract_dot_chart_scores(page) -> dict[int, list[str]]:
    """从页面圆点图表提取每行品牌分数。

    每行有多个彩色圆点（代表不同品牌），x 坐标映射分数（7.0-9.5）。
    通过页面底部的刻度标签校准 x→分数映射。
    返回: {row_idx: ["品牌:分数", ...]}
    """
    try:
        drawings = page.get_drawings() or []
        d = page.get_text("dict")
    except Exception:
        return {}

    # 1. 找刻度标签（页面底部 x=340-570, y>475, 值为 7.0/7.5/8.0/8.5/9.0/9.5）
    #    注意：柱状图分数也在 7.0-9.5 范围，但位于 x≈705, y≈370-470，需要排除
    scale_labels = []
    for blk in d.get("blocks", []):
        if "lines" not in blk:
            continue
        for line in blk["lines"]:
            for span in line["spans"]:
                text = span.get("text", "").strip()
                try:
                    val = float(text)
                    if val in (7.0, 7.5, 8.0, 8.5, 9.0, 9.5):
                        x0 = span["bbox"][0]
                        cy = (span["bbox"][1] + span["bbox"][3]) / 2
                        # 刻度标签特征：x 在 340-570 范围，y>475（页面底部）
                        if 340 < x0 < 570 and cy > 475:
                            scale_labels.append({"cx": x0, "cy": cy, "val": val})
                except ValueError:
                    pass

    # 构建 x→分数线性映射: score = scale_a * x + scale_b
    if len(scale_labels) >= 2:
        scale_labels.sort(key=lambda s: s["cx"])
        s0, s1 = scale_labels[0], scale_labels[-1]
        scale_a = (s1["val"] - s0["val"]) / (s1["cx"] - s0["cx"])
        scale_b = s0["val"] - scale_a * s0["cx"]
    else:
        scale_a, scale_b = None, None  # 无刻度时使用默认映射

    # 2. 找图表区域内的彩色圆点（近似圆形，非纯白）
    #    图表区域：x=300-560（刻度范围），y=100-470（表格数据区）
    #    注意：不过滤灰色圆点！折线图可能使用浅灰/深灰/蓝色等多种颜色
    dot_candidates = []
    for dr in drawings:
        if dr.get("type") not in ("f", "fs"):
            continue
        fill = dr.get("fill")
        if not fill or len(fill) < 3:
            continue
        fr, fg, fb = fill[0], fill[1], fill[2]
        # 只排除纯白/近白背景
        if fr > 0.9 and fg > 0.9 and fb > 0.9:
            continue
        rect = dr.get("rect")
        if not rect:
            continue
        w = rect.x1 - rect.x0
        h = rect.y1 - rect.y0
        if abs(w - h) > 3 or w < 3 or w > 15:
            continue
        cx = (rect.x0 + rect.x1) / 2
        cy = (rect.y0 + rect.y1) / 2
        # 只保留图表区域内的圆点
        if not (300 < cx < 560 and 100 < cy < 470):
            continue
        dot_candidates.append({
            "cx": cx,
            "cy": cy,
            "color": (round(fr, 2), round(fg, 2), round(fb, 2)),
        })

    if not dot_candidates:
        return {}

    # 3. 按颜色分组
    color_groups: dict[tuple, list[dict]] = {}
    for dot in dot_candidates:
        c = dot["color"]
        if c not in color_groups:
            color_groups[c] = []
        color_groups[c].append(dot)

    # 4. 动态构建颜色→品牌映射
    dot_color_list = sorted(color_groups.keys(), key=lambda c: sum(d["cy"] for d in color_groups[c]) / len(color_groups[c]))
    color_brand_map = _build_color_brand_map(page, dot_colors=dot_color_list)

    # 5. 行聚类：以点数最多的颜色为锚点，其他颜色按 y 匹配
    primary_color = max(color_groups, key=lambda c: len(color_groups[c]))
    primary_dots = sorted(color_groups[primary_color], key=lambda d: d["cy"])
    other_dots = []
    for color, dots in color_groups.items():
        if color != primary_color:
            other_dots.extend(dots)

    result = {}
    for row_idx, primary_dot in enumerate(primary_dots):
        row_dots = [primary_dot]
        for other_dot in other_dots:
            if abs(other_dot["cy"] - primary_dot["cy"]) < 8:
                row_dots.append(other_dot)

        scores = []
        for dot in row_dots:
            if scale_a is not None:
                score = round((scale_a * dot["cx"] + scale_b) * 10) / 10
            else:
                # fallback: 默认线性映射
                all_x = [d["cx"] for d in dot_candidates]
                x0, x1 = min(all_x), max(all_x)
                rel = max(0.0, min(1.0, (dot["cx"] - x0) / (x1 - x0))) if x1 > x0 else 0
                score = round((7.0 + rel * 2.5) * 10) / 10
            score = max(7.0, min(9.5, score))
            brand = _find_brand_for_dot({"brand_color": dot["color"]}, color_brand_map)
            scores.append(f"{brand}:{score}")
        result[row_idx] = scores

    return result


def _build_color_brand_map(page, dot_colors: list[tuple] | None = None) -> dict[tuple, str]:
    """动态构建折线图颜色→品牌映射。

    从页面右侧图例区域采样颜色，匹配折线图品牌。
    注意：Total market 是柱状图图例（无彩色圆点），需排除。
    返回: {RGB元组: 品牌名}
    """
    import fitz as fz
    color_map: dict[tuple, str] = {}
    try:
        d = page.get_text("dict")
    except Exception:
        return color_map

    # 1. 收集图例标签（x > 700，y 370-470，短文本）
    labels = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                text = span.get("text", "").strip()
                if not text:
                    continue
                x0 = span["bbox"][0]
                if x0 > 700 and len(text.split()) <= 3 and not text.replace(".", "").replace(",", "").isdigit():
                    cy = (span["bbox"][1] + span["bbox"][3]) / 2
                    if 370 < cy < 470:
                        labels.append({"cy": cy, "text": text, "x0": x0})

    if not labels:
        return color_map

    labels.sort(key=lambda l: l["cy"])

    # 2. 对每个标签，采样其左侧图例色块的颜色
    mat = fz.Matrix(4, 4)
    label_x0 = min(l["x0"] for l in labels)

    for label in labels:
        # 采样区域：标签左侧 15-60pt（图例色块位置）
        clip = fz.Rect(label_x0 - 65, label["cy"] - 8, label_x0 - 15, label["cy"] + 8)
        pix = page.get_pixmap(matrix=mat, clip=clip)
        if pix.n < 3:
            continue

        from collections import Counter
        samples = []
        for y in range(0, pix.height, 2):
            for x in range(0, pix.width, 2):
                idx = y * pix.stride + x * pix.n
                r, g, b = pix.samples[idx] / 255, pix.samples[idx + 1] / 255, pix.samples[idx + 2] / 255
                # 排除白色背景
                if r > 0.85 and g > 0.85 and b > 0.85:
                    continue
                samples.append((round(r, 2), round(g, 2), round(b, 2)))

        if not samples:
            continue  # 无彩色标记（如 Total market）

        # 排除白色后最常见的颜色
        most_common = Counter(samples).most_common(1)[0][0]
        color_map[most_common] = label["text"]

    # 3. fallback: 颜色采样未覆盖所有 dot_colors 时，按位置对齐
    if dot_colors and len(color_map) < len(dot_colors):
        mapped_colors = set(color_map.keys())
        unmatched_dot_colors = [c for c in dot_colors if not any(_color_close(c, mc) for mc in mapped_colors)]
        mapped_brands = set(color_map.values())
        # 排除 Total market（柱状图专属）
        unmatched_brands = [l for l in labels if l["text"] not in mapped_brands and l["text"].lower() != "total market"]
        unmatched_brands.sort(key=lambda l: l["cy"])
        for i, brand in enumerate(unmatched_brands):
            if i < len(unmatched_dot_colors):
                color_map[unmatched_dot_colors[i]] = brand["text"]

    return color_map


def _color_close(c1: tuple, c2: tuple, thresh: float = 0.1) -> bool:
    """判断两个颜色是否接近（欧氏距离 < thresh）。"""
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5 < thresh


def _find_brand_for_dot(dot: dict, color_brand_map: dict[tuple, str]) -> str:
    """根据颜色→品牌映射确定品牌名（支持模糊匹配）。"""
    dot_color = dot["brand_color"]
    # 精确匹配
    if dot_color in color_brand_map:
        return color_brand_map[dot_color]
    # 模糊匹配（欧氏距离 < 0.1）
    best_brand = None
    best_dist = 0.1
    for map_color, brand in color_brand_map.items():
        dist = sum((a - b) ** 2 for a, b in zip(dot_color, map_color)) ** 0.5
        if dist < best_dist:
            best_dist = dist
            best_brand = brand
    if best_brand:
        return best_brand
    # fallback: 返回颜色描述
    r, g, b = dot_color
    return f"({r:.1f},{g:.1f},{b:.1f})"


def _extract_total_market_bars(td: TableData, page) -> None:
    """提取柱状图数据（页面右侧汇总图表）。

    柱状图有4个品牌（Total market/Volkswagen/Toyota/Honda），
    通过标签 y 坐标匹配分数文本提取。
    """
    try:
        d = page.get_text("dict")
    except Exception:
        return

    # 收集柱状图区域的品牌标签（x > 700，y 370-470，短文本）
    labels = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                text = span.get("text", "").strip()
                if not text:
                    continue
                x0 = span["bbox"][0]
                cy = (span["bbox"][1] + span["bbox"][3]) / 2
                # 品牌标签：x > 700，短文本，y 在柱状图区域
                if x0 > 700 and len(text.split()) <= 3 and not text.replace(".", "").replace(",", "").isdigit():
                    if 370 < cy < 470:
                        labels.append({"cy": cy, "text": text})

    if not labels:
        return

    labels.sort(key=lambda l: l["cy"])

    # 找柱状图附近的分数文本（x=695-720, y 在图表区域内）
    chart_min_y = min(l["cy"] for l in labels) - 15
    chart_max_y = max(l["cy"] for l in labels) + 15
    score_texts = []
    for b in d.get("blocks", []):
        if "lines" not in b:
            continue
        for line in b["lines"]:
            for span in line["spans"]:
                x0 = span["bbox"][0]
                y0 = span["bbox"][1]
                text = span.get("text", "").strip()
                try:
                    val = float(text)
                    if 7.0 <= val <= 9.5 and 695 < x0 < 720 and chart_min_y < y0 < chart_max_y:
                        score_texts.append({"cy": (span["bbox"][1] + span["bbox"][3]) / 2, "val": val})
                except ValueError:
                    pass

    # 将分数匹配到最近的标签
    bar_scores = {}
    for label in labels:
        if score_texts:
            best_score = min(score_texts, key=lambda s: abs(s["cy"] - label["cy"]))
            if abs(best_score["cy"] - label["cy"]) < 15:
                bar_scores[label["text"]] = best_score["val"]

    if not bar_scores:
        return

    # 柱状图是页面底部独立图表，不属于表格内容，不写入表格行
    # 数据存入 features 供前端展示
    if bar_scores and hasattr(td, 'features'):
        td.features["bar_chart_summary"] = bar_scores


def _group_consecutive_columns(columns: list[int]) -> list[list[int]]:
    """将连续的列索引分组，如 [2,3,4,7,8] → [[2,3,4], [7,8]]。"""
    if not columns:
        return []
    groups = []
    current = [columns[0]]
    for c in columns[1:]:
        if c == current[-1] + 1:
            current.append(c)
        else:
            groups.append(current)
            current = [c]
    groups.append(current)
    return groups


def _extend_for_legend(col_bbox: list[float], page, table_bbox: list[float]) -> list[float]:
    """扩展图表列区域，包含上方图例、左右刻度和下方标注。

    策略：图例通常在表格标题行上方或内部，因此大幅向上扩展；
    左右扩展包含刻度值和图例色块；底部包含 X 轴标注。
    """
    if not col_bbox or len(col_bbox) < 4:
        return col_bbox
    x0, y0, x1, y1 = col_bbox
    page_w, page_h = page.rect.width, page.rect.height

    # 基础扩展：上 120pt（图例在标题行上方/内部），左右各 120pt（刻度/图例），下 40pt（X轴标注）
    new_x0 = max(x0 - 120, 0)
    new_y0 = max(y0 - 120, 0)
    new_x1 = min(x1 + 120, page_w)
    new_y1 = min(y1 + 40, page_h)

    # 检测附近矢量图形进一步扩展
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    for d in drawings:
        if d.get("type") not in ("f", "fs"):
            continue
        fill = d.get("fill")
        if not fill or len(fill) < 3:
            continue
        if fill[0] > 0.9 and fill[1] > 0.9 and fill[2] > 0.9:
            continue
        rect = d.get("rect")
        if not rect:
            continue
        area = max(0, rect.x1 - rect.x0) * max(0, rect.y1 - rect.y0)
        if area > 500 or area < 3:
            continue
        # 扩大检测范围到 150pt
        h_dist = max(0, max(x0 - rect.x1, rect.x0 - x1))
        v_dist = max(0, max(y0 - rect.y1, rect.y0 - y1))
        if h_dist < 150 and v_dist < 150:
            new_x0 = min(new_x0, rect.x0)
            new_y0 = min(new_y0, rect.y0)
            new_x1 = max(new_x1, rect.x1)
            new_y1 = max(new_y1, rect.y1)

    return [new_x0, new_y0, new_x1, new_y1]


def _attach_annotations(td: TableData, page) -> None:
    """将表格外的注解文本关联到对应行。

    某些 PDF 页面在表格右侧放置详细注解（如 "Sales staff competence: • Lacking..."），
    这些注解与左侧主题行对应。此函数检测这类注解并将其附加到对应行的末尾。
    """
    if not td.rows or not page or not td.bbox:
        return
    table_x0, table_y0, table_x1, table_y1 = td.bbox
    n_cols = td.n_cols
    if n_cols < 2:
        return
    # 获取页面文本块
    text_blocks = page.get_text("blocks") or []
    # 找出位于表格右侧的文本块（注解），扩展检测范围到表格下方
    # 注解特征：x > 表格中点，内容包含换行或列表符号
    mid_x = table_x0 + (table_x1 - table_x0) * 0.5
    # 扩展表格底部边界，包含下方的注解区域
    extended_y1 = table_y1 + 100
    annotations = []
    for b in text_blocks:
        if len(b) < 5 or not isinstance(b[4], str):
            continue
        bx0, by0, bx1, by1 = b[0], b[1], b[2], b[3]
        text = b[4].strip()
        # 注解位于表格右半部分，y 在表格范围内或下方延伸区域
        if bx0 < mid_x or by0 < table_y0 or by1 > extended_y1:
            continue
        # 排除已经是表格内容的文本（简短、无换行、无冒号列表）
        if "\n" not in text and "•" not in text and len(text) < 30:
            continue
        annotations.append({"y_center": (by0 + by1) / 2, "text": text})
    if not annotations:
        return
    # 计算每行的 y 中心位置
    row_height = (table_y1 - table_y0) / max(td.n_rows, 1)
    # 将注解匹配到最近的行
    for ann in annotations:
        ann_y = ann["y_center"]
        # 找到 y 坐标最近的行
        best_row = -1
        best_dist = float("inf")
        for r_idx in range(1, len(td.rows)):  # 跳过表头
            row_y = table_y0 + (r_idx + 0.5) * row_height
            dist = abs(row_y - ann_y)
            if dist < best_dist and dist < row_height * 1.5:
                best_dist = dist
                best_row = r_idx
        if best_row < 0:
            continue
        # 验证：注解文本是否与该行的主题相关
        row_text = " ".join(c for c in td.rows[best_row] if c.strip())
        ann_text = ann["text"]
        # 提取注解的关键词（冒号前的部分）
        ann_key = ann_text.split(":")[0].strip() if ":" in ann_text else ann_text.split("\n")[0].strip()
        # 检查关键词是否匹配行文本（模糊匹配：关键词的主要单词出现在行文本中）
        if _keywords_match(row_text, ann_key):
            # 将注解附加到该行的最后一个非空单元格
            row = td.rows[best_row]
            annotation_suffix = f"\n[注解] {ann_text}"
            # 找到最后一个非空单元格
            for c_idx in range(len(row) - 1, -1, -1):
                if row[c_idx].strip():
                    if "[注解]" not in row[c_idx]:
                        row[c_idx] = row[c_idx] + annotation_suffix
                    break


def _keywords_match(row_text: str, ann_key: str) -> bool:
    """检查注解关键词是否与行文本相关（基于单词重叠）。"""
    import re
    if not row_text or not ann_key:
        return False
    def normalize(s):
        return set(re.findall(r'[a-z]+', s.lower()))
    row_words = normalize(row_text)
    key_words = normalize(ann_key)
    if not key_words:
        return False
    overlap = row_words & key_words
    return len(overlap) >= len(key_words) * 0.5


def _has_content(t: TableData) -> bool:
    """表格是否有实质内容（至少 2 个非空单元格）。"""
    if not t.rows:
        return False
    non_empty = sum(1 for r in t.rows for c in r if c and c.strip())
    return non_empty >= 2


def _is_header_repeat(row: list[str], header: list[str]) -> bool:
    """判断续表首行是否与上一页表头相同（允许少量空白差异）。"""
    if not row or not header:
        return False
    norm = lambda s: s.strip().replace(" ", "")
    return [norm(c) for c in row] == [norm(c) for c in header]


def tables_to_markdown(table: TableData, title: str = "") -> str:
    """将 TableData 转为 Markdown 表格。

    - 合并单元格：把值填充到被合并的空单元格，使每列自描述（适合知识库）
    - title: 表格标题（取自相邻文本块），让 chunk 自包含上下文
    """
    if not table.rows:
        return ""
    n_cols = table.n_cols or max((len(r) for r in table.rows), default=0)
    filled = _fill_merged_cells(table.rows, table.merged)
    normalized = [_pad_row(r, n_cols) for r in filled]
    lines: list[str] = []
    if title:
        lines.append(f"**{title}**")
    header = normalized[0] if normalized else ["" for _ in range(n_cols)]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * n_cols) + " |")
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _fill_merged_cells(rows: list[list[str]], merged: list[MergedCell]) -> list[list[str]]:
    """将合并单元格的值填充到被合并的空单元格。"""
    if not merged:
        return rows
    filled = [row[:] for row in rows]
    for m in merged:
        if m.rowspan == 1 and m.colspan == 1:
            continue
        value = filled[m.row][m.col] if m.row < len(filled) and m.col < len(filled[m.row]) else ""
        for dr in range(m.rowspan):
            for dc in range(m.colspan):
                r, c = m.row + dr, m.col + dc
                if r < len(filled) and c < len(filled[r]) and (dr != 0 or dc != 0):
                    filled[r][c] = value
    return filled


def _pad_row(row: list[str], n: int) -> list[str]:
    if len(row) >= n:
        return row[:n]
    return row + ["" for _ in range(n - len(row))]
