"""Experiment: does higher DPI improve VLM recognition precision for small-text pages."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz
from src.parser import vlm
from src.utils import pdf_utils, vlm_models
from src.utils.metrics import new_task_metrics

DPI_LEVELS = [150, 200, 300, 400]
PAGES = {
    "page24": "/Users/lou/ai_agent/pdf-parsing/page24.pdf",
    "page38": "/Users/lou/ai_agent/pdf-parsing/page38.pdf",
    "page58": "/Users/lou/ai_agent/pdf-parsing/page58.pdf",
}

STRUCTURE_PROMPT = """Analyze this PDF page image carefully.
Identify:
1. All visible text content (transcribe as much as you can read)
2. Chart type if any (dot, line, bar_horizontal, bar_vertical, bar_stacked, area, pie, scatter, radar)
3. Number of data rows/categories visible
4. Any numeric values you can read

Output JSON:
{{
  "text_content": "transcribed text here...",
  "chart_type": "...",
  "row_count": 0,
  "sample_values": ["value1", "value2"],
  "confidence": "high|medium|low"
}}"""


def run_experiment():
    results = {}
    metrics = new_task_metrics()

    for page_name, pdf_path in PAGES.items():
        print(f"\n{'='*60}")
        print(f"Testing: {page_name}")
        print(f"{'='*60}")

        doc = fitz.open(pdf_path)
        page = doc[0]
        page_results = {}

        for dpi in DPI_LEVELS:
            print(f"\n  DPI={dpi}...", end=" ", flush=True)
            img_bytes = pdf_utils.page_to_png(page, dpi=dpi)
            img_size_kb = len(img_bytes) / 1024

            t0 = time.time()
            try:
                resp = vlm.vlm_describe(
                    img_bytes, metrics, prompt=STRUCTURE_PROMPT
                )
                elapsed = time.time() - t0

                # Try to parse JSON from response
                parsed = None
                try:
                    parsed = json.loads(resp)
                except json.JSONDecodeError:
                    import re
                    m = re.search(r'\{[\s\S]*\}', resp)
                    if m:
                        try:
                            parsed = json.loads(m.group())
                        except json.JSONDecodeError:
                            pass

                result = {
                    "dpi": dpi,
                    "image_size_kb": round(img_size_kb, 1),
                    "latency_seconds": round(elapsed, 2),
                    "response_length": len(resp),
                    "parsed_json": parsed,
                    "raw_response": resp[:2000],
                }
                print(f"OK ({elapsed:.1f}s, {img_size_kb:.0f}KB)")

            except Exception as e:
                elapsed = time.time() - t0
                result = {
                    "dpi": dpi,
                    "image_size_kb": round(img_size_kb, 1),
                    "latency_seconds": round(elapsed, 2),
                    "error": str(e),
                }
                print(f"FAIL ({e})")

            page_results[f"dpi_{dpi}"] = result

        results[page_name] = {
            "page_width": page.rect.width,
            "page_height": page.rect.height,
            "results": page_results,
        }
        doc.close()

    return results


def main():
    print("DPI Sweep Experiment")
    print(f"Model: {vlm_models.get_model().model}")
    print(f"DPI levels: {DPI_LEVELS}")
    print(f"Pages: {list(PAGES.keys())}")

    results = run_experiment()

    output_path = Path(__file__).parent / "dpi_sweep_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n\nResults saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for page_name, page_data in results.items():
        print(f"\n{page_name}:")
        for dpi_key, res in page_data["results"].items():
            dpi = res["dpi"]
            if "error" in res:
                print(f"  DPI {dpi}: ERROR - {res['error']}")
            else:
                parsed = res.get("parsed_json", {}) or {}
                row_count = parsed.get("row_count", "?")
                confidence = parsed.get("confidence", "?")
                print(f"  DPI {dpi}: {res['latency_seconds']}s, {res['image_size_kb']}KB, "
                      f"rows={row_count}, confidence={confidence}")


if __name__ == "__main__":
    main()
