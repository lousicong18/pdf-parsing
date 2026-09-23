"""MinerU wrapper: call CLI, parse JSON output, convert to Block format."""

import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from src.models.schemas import Block, PageType, TableData

logger = logging.getLogger("pdf_parser")


def process_with_mineru(pdf_path: str, page_num: int, page_type: PageType) -> list[Block]:
    """Run MinerU on a single page, return Block list.

    Args:
        pdf_path: Path to PDF file
        page_num: 0-based page index
        page_type: Classified page type

    Returns:
        List of Block objects
    """
    if not Path(pdf_path).exists():
        logger.warning("MinerU: pdf not found %s", pdf_path)
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        if not _run_mineru_cli(pdf_path, output_dir, page_num):
            return []
        return _parse_mineru_output(output_dir, page_type, page_num)


def _run_mineru_cli(pdf_path: str, output_dir: Path, page_num: int) -> bool:
    """Execute MinerU CLI for a specific page range."""
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "mineru.cli.client",
                "-p", pdf_path,
                "-o", str(output_dir),
                "-m", "ocr",
                "-b", "pipeline",
                "-s", str(page_num),
                "-e", str(page_num),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("MinerU CLI failed: %s", result.stderr[-300:] if result.stderr else "")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.warning("MinerU CLI timeout for page %s", page_num)
        return False
    except FileNotFoundError:
        logger.warning("MinerU not installed")
        return False
    except Exception as e:
        logger.warning("MinerU CLI error: %s", e)
        return False


def _parse_mineru_output(output_dir: Path, page_type: PageType, page_num: int) -> list[Block]:
    """Parse MinerU JSON output into Block list."""
    # Find content_list.json in subdirectories
    json_files = list(output_dir.rglob("*.json"))
    content_files = [f for f in json_files if "content_list" in f.name and "v2" not in f.name]

    if not content_files:
        logger.warning("MinerU: no content_list.json found for page %s", page_num)
        return []

    content_file = content_files[0]
    try:
        data = json.loads(content_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("MinerU: failed to parse JSON: %s", e)
        return []

    if not isinstance(data, list):
        logger.warning("MinerU: unexpected JSON format (not a list)")
        return []

    blocks = []
    order = 0
    for item in data:
        block = _convert_item_to_block(item, page_type, order, content_file.parent)
        if block:
            blocks.append(block)
            order += 1

    # If no blocks parsed, try v2 format
    if not blocks:
        v2_files = [f for f in json_files if "content_list_v2" in f.name]
        if v2_files:
            blocks = _parse_content_list_v2(v2_files[0], page_type)

    return blocks


def _convert_item_to_block(item: dict, page_type: PageType, order: int, base_dir: Path) -> Block | None:
    """Convert a single MinerU content item to Block."""
    item_type = item.get("type", "")
    bbox = item.get("bbox", [0, 0, 0, 0])
    page_idx = item.get("page_idx", 0)

    if item_type == "text":
        text = item.get("text", "").strip()
        if not text:
            return None
        text_level = item.get("text_level", 0)
        if text_level == 1:
            content = f"# {text}"
        elif text_level == 2:
            content = f"## {text}"
        else:
            content = text
        return Block(
            type="text",
            bbox=bbox,
            page_type=page_type,
            order=order,
            text=text,
            content=content,
        )

    if item_type == "equation":
        text = item.get("text", "").strip()
        if not text:
            return None
        return Block(
            type="text",
            bbox=bbox,
            page_type=page_type,
            order=order,
            text=text,
            content=f"$$\n{text}\n$$",
        )

    if item_type == "table":
        return _parse_table_item(item, page_type, order, base_dir)

    if item_type == "image":
        return _parse_image_item(item, page_type, order, base_dir)

    if item_type == "chart":
        return _parse_chart_item(item, page_type, order, base_dir)

    if item_type in ("header", "footer", "page_number"):
        text = item.get("text", "").strip()
        if not text:
            return None
        return Block(
            type="text",
            bbox=bbox,
            page_type=page_type,
            order=order,
            text=text,
            content=text,
        )

    return None


def _parse_table_item(item: dict, page_type: PageType, order: int, base_dir: Path) -> Block | None:
    """Parse table item - use HTML if available, else image."""
    html = item.get("html", "")
    text = item.get("text", "").strip()
    bbox = item.get("bbox", [0, 0, 0, 0])
    caption = item.get("table_caption", [])
    footnote = item.get("table_footnote", [])

    # If has HTML table, convert to markdown
    if html:
        md = _html_table_to_md(html)
        title = caption[0] if caption else ""
        if title:
            md = f"**{title}**\n{md}"
        if footnote:
            md += "\n" + "\n".join(f"^{f}" for f in footnote)
        return Block(
            type="table",
            bbox=bbox,
            page_type=page_type,
            order=order,
            table=None,
            content=md,
        )

    # If has text content, use it
    if text:
        title = caption[0] if caption else ""
        md = f"**{title}**\n{text}" if title else text
        return Block(
            type="table",
            bbox=bbox,
            page_type=page_type,
            order=order,
            table=None,
            content=md,
        )

    # Fallback: describe as image
    img_path = item.get("img_path", "")
    if img_path:
        full_path = base_dir / img_path
        desc = _describe_table_image(full_path) if full_path.exists() else "表格（图片）"
        title = caption[0] if caption else ""
        if title:
            desc = f"**{title}**\n{desc}"
        return Block(
            type="table",
            bbox=bbox,
            page_type=page_type,
            order=order,
            table=None,
            content=desc,
        )

    return None


def _parse_image_item(item: dict, page_type: PageType, order: int, base_dir: Path) -> Block | None:
    """Parse image item."""
    bbox = item.get("bbox", [0, 0, 0, 0])
    img_path = item.get("img_path", "")
    caption = item.get("img_caption", [])
    footnote = item.get("img_footnote", [])

    title = caption[0] if caption else "图片"
    desc = footnote[0] if footnote else ""

    content_parts = [f"**{title}**"]
    if desc:
        content_parts.append(desc)
    if img_path:
        content_parts.append(f"[图片: {img_path}]")

    return Block(
        type="image",
        bbox=bbox,
        page_type=page_type,
        order=order,
        image=None,
        content="\n".join(content_parts),
    )


def _parse_chart_item(item: dict, page_type: PageType, order: int, base_dir: Path) -> Block | None:
    """Parse chart item - MinerU saves as image, we note it."""
    bbox = item.get("bbox", [0, 0, 0, 0])
    img_path = item.get("img_path", "")
    caption = item.get("chart_caption", [])
    footnote = item.get("chart_footnote", [])

    title = caption[0] if caption else "图表"
    desc = footnote[0] if footnote else ""

    content_parts = [f"**{title}**"]
    if desc:
        content_parts.append(desc)
    content_parts.append("[图表数据需 VLM 识别]")

    return Block(
        type="image",
        bbox=bbox,
        page_type=page_type,
        order=order,
        image=None,
        content="\n".join(content_parts),
    )


def _html_table_to_md(html: str) -> str:
    """Simple HTML table to markdown conversion."""
    import re

    # Extract rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    if not rows:
        return ""

    md_rows = []
    for i, row in enumerate(rows):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        md_rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")

    return "\n".join(md_rows)


def _describe_table_image(img_path: Path) -> str:
    """Fallback description for table saved as image."""
    return f"表格（详见图片: {img_path.name}）"


def _parse_content_list_v2(json_file: Path, page_type: PageType) -> list[Block]:
    """Parse content_list_v2 format (alternative MinerU output)."""
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    if not isinstance(data, list):
        return []

    blocks = []
    order = 0
    for item in data:
        block = _convert_item_to_block(item, page_type, order, json_file.parent)
        if block:
            blocks.append(block)
            order += 1

    return blocks


def is_mineru_available() -> bool:
    """Check if MinerU CLI is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mineru.cli.client", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False
