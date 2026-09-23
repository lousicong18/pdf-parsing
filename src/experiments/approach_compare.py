"""Compare 3 approaches for PDF content recognition:
1. OCR + VLM structure understanding
2. Page chunking (split into regions)
3. Specialized table/data extraction prompts"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz
from src.parser import vlm
from src.utils import pdf_utils, vlm_models
from src.utils.metrics import new_task_metrics

PAGES = {
    "page24": "/Users/lou/ai_agent/pdf-parsing/page24.pdf",
    "page38": "/Users/lou/ai_agent/pdf-parsing/page38.pdf",
    "page58": "/Users/lou/ai_agent/pdf-parsing/page58.pdf",
}

DPI = 200  # Fixed DPI for fair comparison


def approach_ocr_then_vlm(page, metrics):
    """Approach 1: OCR to extract text, then VLM for structure."""
    # Step 1: OCR the full page
    ocr_prompt = """Please perform OCR on this PDF page image.
Extract ALL visible text content, preserving the layout and structure.
Include:
- All category labels
- All numeric values
- All brand names
- Headers and footers
Output as plain text, maintaining the spatial layout."""

    img_bytes = pdf_utils.page_to_png(page, dpi=DPI)
    t0 = time.time()
    ocr_result = vlm.vlm_ocr(img_bytes, metrics)
    ocr_time = time.time() - t0

    # Step 2: Ask VLM to structure the OCR text
    structure_prompt = f"""Based on the following OCR text extracted from a PDF page, structure it into a data table.

OCR Text:
{ocr_result[:3000]}

Output JSON:
{{
  "title": "page title",
  "chart_type": "dot/line/bar/etc",
  "headers": ["col1", "col2", ...],
  "rows": [
    ["row1_col1", "row1_col2", ...],
    ...
  ],
  "row_count": 0
}}"""

    t1 = time.time()
    structure_result = vlm.vlm_describe(img_bytes, metrics, prompt=structure_prompt)
    structure_time = time.time() - t1

    return {
        "approach": "ocr_then_vlm",
        "ocr_time": round(ocr_time, 2),
        "structure_time": round(structure_time, 2),
        "total_time": round(ocr_time + structure_time, 2),
        "ocr_text": ocr_result[:2000],
        "structure_response": structure_result[:2000],
    }


def approach_chunking(page, metrics):
    """Approach 2: Split page into regions and process each separately."""
    pw, ph = page.rect.width, page.rect.height
    img_bytes = pdf_utils.page_to_png(page, dpi=DPI)

    # Define regions: left labels, center chart, right scores
    regions = {
        "left_labels": (0, 0, pw * 0.35, ph),  # Left 35% - category labels
        "center_chart": (pw * 0.35, 0, pw * 0.6, ph),  # Center - chart area
        "right_data": (pw * 0.6, 0, pw, ph),  # Right 40% - scores/values
        "header": (0, 0, pw, ph * 0.15),  # Top 15% - headers
        "footer": (0, ph * 0.85, pw, ph),  # Bottom 15% - footers
    }

    region_prompts = {
        "left_labels": "List all text labels visible in this left region, one per line. These are category names.",
        "center_chart": "Describe the chart type and data series visible. List colors and what they represent.",
        "right_data": "Extract all numeric values and associated brand names. Format as: brand: value",
        "header": "Extract the title, subtitle, and any header text.",
        "footer": "Extract footer text, source citations, and page numbers.",
    }

    results = {}
    total_time = 0
    for region_name, (rx0, ry0, rx1, ry1) in regions.items():
        # Render region
        clip = fitz.Rect(rx0, ry0, rx1, ry1)
        region_pix = page.get_pixmap(matrix=fitz.Matrix(DPI / 72, DPI / 72), clip=clip)
        region_img = region_pix.tobytes("png")

        prompt = f"""This is a {region_name} region of a PDF page.

{region_prompts[region_name]}

Be precise and complete. Output as JSON:
{{
  "region": "{region_name}",
  "content": ["item1", "item2", ...],
  "chart_type": "if applicable",
  "values": ["val1", "val2"]
}}"""

        t0 = time.time()
        resp = vlm.vlm_describe(region_img, metrics, prompt=prompt)
        elapsed = time.time() - t0
        total_time += elapsed

        results[region_name] = {
            "time": round(elapsed, 2),
            "response": resp[:1000],
        }

    results["total_time"] = round(total_time, 2)
    results["approach"] = "chunking"
    return results


def approach_specialized_prompt(page, metrics):
    """Approach 3: Specialized table/data extraction prompt."""
    img_bytes = pdf_utils.page_to_png(page, dpi=DPI)

    specialized_prompt = """This PDF page contains a data chart with structured information.
Your task is to extract ALL data with maximum precision.

Follow these steps:
1. Identify the chart type (dot plot, bar chart, line chart, etc.)
2. Identify ALL data series (legend entries)
3. For EACH row/category, extract:
   - The row label (exact text)
   - The value for each series (exact number)
4. Do NOT skip any rows or values
5. If text is small, zoom in mentally and read carefully

Output JSON with this exact structure:
{
  "chart_type": "dot/bar/line/etc",
  "series_names": ["Series1", "Series2", ...],
  "scale": {"min": 0, "max": 100, "unit": "score/percent/etc"},
  "data": [
    {"label": "Row 1", "values": {"Series1": 8.7, "Series2": 8.8}},
    {"label": "Row 2", "values": {"Series1": 8.5, "Series2": 9.0}},
    ...
  ],
  "total_rows": 0,
  "notes": "any additional observations"
}

CRITICAL: Extract EVERY row. Do not abbreviate or skip any data."""

    t0 = time.time()
    resp = vlm.vlm_describe(img_bytes, metrics, prompt=specialized_prompt)
    elapsed = time.time() - t0

    return {
        "approach": "specialized_prompt",
        "total_time": round(elapsed, 2),
        "response": resp[:3000],
    }


def run_comparison():
    metrics = new_task_metrics()
    all_results = {}

    for page_name, pdf_path in PAGES.items():
        print(f"\n{'='*60}")
        print(f"Testing: {page_name}")
        print(f"{'='*60}")

        doc = fitz.open(pdf_path)
        page = doc[0]
        page_results = {}

        # Approach 1: OCR + VLM
        print("\n  [1] OCR + VLM...", end=" ", flush=True)
        try:
            r1 = approach_ocr_then_vlm(page, metrics)
            print(f"OK ({r1['total_time']}s)")
            page_results["ocr_then_vlm"] = r1
        except Exception as e:
            print(f"FAIL ({e})")
            page_results["ocr_then_vlm"] = {"error": str(e)}

        # Approach 2: Chunking
        print("  [2] Chunking...", end=" ", flush=True)
        try:
            r2 = approach_chunking(page, metrics)
            print(f"OK ({r2['total_time']}s)")
            page_results["chunking"] = r2
        except Exception as e:
            print(f"FAIL ({e})")
            page_results["chunking"] = {"error": str(e)}

        # Approach 3: Specialized prompt
        print("  [3] Specialized prompt...", end=" ", flush=True)
        try:
            r3 = approach_specialized_prompt(page, metrics)
            print(f"OK ({r3['total_time']}s)")
            page_results["specialized_prompt"] = r3
        except Exception as e:
            print(f"FAIL ({e})")
            page_results["specialized_prompt"] = {"error": str(e)}

        all_results[page_name] = page_results
        doc.close()

    return all_results


def main():
    print("Approach Comparison Experiment")
    print(f"Model: {vlm_models.get_model().model}")
    print(f"DPI: {DPI}")
    print(f"Pages: {list(PAGES.keys())}")

    results = run_comparison()

    output_path = Path(__file__).parent / "approach_compare_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\nResults saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for page_name, page_data in results.items():
        print(f"\n{page_name}:")
        for approach, data in page_data.items():
            if "error" in data:
                print(f"  {approach}: ERROR - {data['error']}")
            else:
                total_time = data.get("total_time", "?")
                print(f"  {approach}: {total_time}s")


if __name__ == "__main__":
    main()
