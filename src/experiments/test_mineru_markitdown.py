"""Evaluate MinerU and Markitdown on chart-embedded PDF pages.

Tests 6 PDF pages with:
1. MinerU (layout analysis + OCR pipeline)
2. Markitdown (lightweight file-to-markdown)
3. Current VLM OCR approach (baseline comparison)

Results saved to JSON for comparison.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import fitz
from src.parser import vlm
from src.utils import pdf_utils
from src.utils.metrics import new_task_metrics

PAGES = {
    "page3": "/Users/lou/ai_agent/pdf-parsing/page3.pdf",
    "page10": "/Users/lou/ai_agent/pdf-parsing/page10.pdf",
    "page24": "/Users/lou/ai_agent/pdf-parsing/page24.pdf",
    "page25": "/Users/lou/ai_agent/pdf-parsing/page25.pdf",
    "page38": "/Users/lou/ai_agent/pdf-parsing/page38.pdf",
    "page58": "/Users/lou/ai_agent/pdf-parsing/page58.pdf",
}

OCR_PROMPT = """Please perform OCR on this PDF page image.
Extract ALL visible text content, preserving the layout and structure.
Include ALL titles, headers, table data, chart descriptions, legends, footnotes, and source citations.
Output as markdown with proper formatting:
- Use ## for main titles
- Use **bold** for subtitles
- Use markdown tables for tabular data
- Use --- for separators
- Preserve all content - do not skip anything."""


def test_mineru(pdf_path: str) -> dict:
    """Run MinerU on a PDF page. Returns result dict with markdown output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        t0 = time.time()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mineru.cli.client", "-p", pdf_path, "-o", str(output_dir), "-m", "ocr", "-b", "pipeline"],
                capture_output=True, text=True, timeout=300
            )
            elapsed = time.time() - t0

            # Find markdown output in subdirectories
            md_files = list(output_dir.rglob("*.md"))
            if md_files:
                md_content = md_files[0].read_text(encoding="utf-8")
                return {
                    "tool": "mineru",
                    "success": True,
                    "time": round(elapsed, 2),
                    "markdown": md_content,
                    "md_file": str(md_files[0]),
                    "stdout": result.stdout[-500:] if result.stdout else "",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                }
            else:
                return {
                    "tool": "mineru",
                    "success": False,
                    "time": round(elapsed, 2),
                    "error": "No markdown output found",
                    "stdout": result.stdout[-500:] if result.stdout else "",
                    "stderr": result.stderr[-500:] if result.stderr else "",
                }
        except FileNotFoundError:
            return {"tool": "mineru", "success": False, "error": "mineru CLI not found"}
        except subprocess.TimeoutExpired:
            return {"tool": "mineru", "success": False, "error": "Timeout (300s)"}
        except Exception as e:
            return {"tool": "mineru", "success": False, "error": str(e)}


def test_mineru_api(pdf_path: str) -> dict:
    """Run MinerU via Python API using subprocess (models must be pre-downloaded)."""
    return {"tool": "mineru_api", "success": False, "error": "Use mineru CLI instead"}


def test_markitdown(pdf_path: str) -> dict:
    """Run MarkItDown on a PDF page."""
    try:
        from markitdown import MarkItDown
        t0 = time.time()
        md = MarkItDown()
        result = md.convert(pdf_path)
        elapsed = time.time() - t0
        return {
            "tool": "markitdown",
            "success": True,
            "time": round(elapsed, 2),
            "markdown": result.text_content,
        }
    except ImportError as e:
        return {"tool": "markitdown", "success": False, "error": f"Import error: {e}"}
    except Exception as e:
        return {"tool": "markitdown", "success": False, "error": str(e)}


def test_vlm_ocr(pdf_path: str, metrics) -> dict:
    """Run current VLM OCR approach as baseline."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        img_bytes = pdf_utils.page_to_png(page, dpi=200)

        t0 = time.time()
        ocr_text = vlm.vlm_ocr(img_bytes, metrics)
        elapsed = time.time() - t0
        doc.close()
        return {
            "tool": "vlm_ocr",
            "success": True,
            "time": round(elapsed, 2),
            "markdown": ocr_text,
        }
    except Exception as e:
        return {"tool": "vlm_ocr", "success": False, "error": str(e)}


def run_all_tests():
    metrics = new_task_metrics()
    all_results = {}

    for page_name, pdf_path in sorted(PAGES.items()):
        print(f"\n{'='*60}")
        print(f"Testing: {page_name} ({pdf_path})")
        print(f"{'='*60}")

        page_results = {"page": page_name, "file": pdf_path}

        # Test 1: MinerU
        print("  [MinerU CLI]...", end=" ", flush=True)
        r1 = test_mineru(pdf_path)
        status = "OK" if r1.get("success") else f"FAIL ({r1.get('error', '?')[:60]})"
        print(f"{status} ({r1.get('time', '?')}s)")
        page_results["mineru_cli"] = r1

        # Test 1b: MinerU API
        print("  [MinerU API]...", end=" ", flush=True)
        r1b = test_mineru_api(pdf_path)
        status = "OK" if r1b.get("success") else f"FAIL ({r1b.get('error', '?')[:60]})"
        print(f"{status} ({r1b.get('time', '?')}s)")
        page_results["mineru_api"] = r1b

        # Test 2: MarkItDown
        print("  [MarkItDown]...", end=" ", flush=True)
        r2 = test_markitdown(pdf_path)
        status = "OK" if r2.get("success") else f"FAIL ({r2.get('error', '?')[:60]})"
        print(f"{status} ({r2.get('time', '?')}s)")
        page_results["markitdown"] = r2

        # Test 3: VLM OCR (baseline)
        print("  [VLM OCR]...", end=" ", flush=True)
        r3 = test_vlm_ocr(pdf_path, metrics)
        status = "OK" if r3.get("success") else f"FAIL ({r3.get('error', '?')[:60]})"
        print(f"{status} ({r3.get('time', '?')}s)")
        page_results["vlm_ocr"] = r3

        all_results[page_name] = page_results

    return all_results


def print_comparison(all_results: dict):
    """Print a comparison table of results."""
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Page':<10} {'Tool':<15} {'Time':<8} {'Chars':<8} {'Status'}")
    print("-" * 80)

    for page_name, page_data in sorted(all_results.items()):
        for tool_key in ["mineru_cli", "mineru_api", "markitdown", "vlm_ocr"]:
            tool_data = page_data.get(tool_key, {})
            tool_name = tool_key.replace("_", " ")
            time_s = tool_data.get("time", "?")
            md = tool_data.get("markdown", "")
            chars = len(md) if md else 0
            status = "OK" if tool_data.get("success") else f"FAIL: {tool_data.get('error', '?')[:30]}"
            print(f"{page_name:<10} {tool_name:<15} {time_s:<8} {chars:<8} {status}")
        print()


def main():
    print("MinerU / MarkItDown / VLM OCR Evaluation")
    print(f"Pages: {list(PAGES.keys())}")

    results = run_all_tests()

    # Save full results
    output_path = Path(__file__).parent / "mineru_markitdown_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results saved to: {output_path}")

    # Save individual markdown files for easy review
    md_dir = Path(__file__).parent / "mineru_markitdown_outputs"
    md_dir.mkdir(exist_ok=True)
    for page_name, page_data in results.items():
        for tool_key, tool_data in page_data.items():
            if isinstance(tool_data, dict) and tool_data.get("success") and tool_data.get("markdown"):
                md_path = md_dir / f"{page_name}_{tool_key}.md"
                md_path.write_text(tool_data["markdown"], encoding="utf-8")
    print(f"Individual markdown files saved to: {md_dir}")

    print_comparison(results)


if __name__ == "__main__":
    main()
