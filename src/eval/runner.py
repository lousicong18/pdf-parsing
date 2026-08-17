"""Eval runner CLI: uv run python -m src.eval.runner."""

import argparse
import json
import sys
from pathlib import Path

from src.eval import metrics, sample_set
from src.eval.metrics import SampleResult
from src.store import task_store
from src.task_manager import task_service
from src.utils import env as env


def run(samples_dir: str, report: str, table_backends: str = "", compare_vlm: str = "",
        cls_overrides: str = "") -> None:
    # optional cls overrides (comma-separated key=value)
    if cls_overrides:
        _apply_cls_overrides(cls_overrides)

    samples = sample_set.load_sample_set(samples_dir)
    sample_results: list[SampleResult] = []
    for s in samples:
        try:
            pdf_bytes = Path(s.pdf_path).read_bytes()
            resp, pdf_path = task_service.create_task(pdf_bytes, Path(s.pdf_path).name)
            task_service.run_parse(resp.task_id, pdf_path)
            result = task_store.get(resp.task_id)
            if result is None:
                continue
            sample_results.append(SampleResult(sample=s, result=result))
        except Exception as e:
            print(f"sample {s.pdf_path} failed: {e}", file=sys.stderr)

    badcases: list[dict] = []
    for sr in sample_results:
        badcases.extend(metrics.output_diff(sr))

    table_results = {}
    if table_backends:
        for backend in table_backends.split(","):
            backend = backend.strip()
            if not backend:
                continue
            old = env.TABLE_EXTRACTOR
            env.TABLE_EXTRACTOR = backend
            try:
                sub: list[SampleResult] = []
                for s in samples:
                    pdf_bytes = Path(s.pdf_path).read_bytes()
                    resp, pdf_path = task_service.create_task(pdf_bytes, Path(s.pdf_path).name)
                    task_service.run_parse(resp.task_id, pdf_path)
                    result = task_store.get(resp.task_id)
                    if result is not None:
                        sub.append(SampleResult(sample=s, result=result))
                table_results[backend] = sub
            except Exception as e:
                print(f"backend {backend} failed: {e}", file=sys.stderr)
            finally:
                env.TABLE_EXTRACTOR = old

    vlm_results = {}
    if compare_vlm:
        for model in compare_vlm.split(","):
            model = model.strip()
            if not model:
                continue
            sub = []
            for s in samples:
                pdf_bytes = Path(s.pdf_path).read_bytes()
                resp, pdf_path = task_service.create_task(pdf_bytes, Path(s.pdf_path).name)
                task_service.run_parse(resp.task_id, pdf_path, vlm_model=model)
                result = task_store.get(resp.task_id)
                if result is not None:
                    sub.append(SampleResult(sample=s, result=result))
            vlm_results[model] = sub

    report_obj = metrics.build_report(
        sample_results, badcases,
        table_backend_results=table_results,
        vlm_model_results=vlm_results,
    )
    Path(report).write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = Path(report).with_suffix(".md")
    md_path.write_text(metrics.render_report_md(report_obj), encoding="utf-8")
    print(f"report written: {report}, {md_path}")


def _apply_cls_overrides(overrides: str) -> None:
    for item in overrides.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if hasattr(env, k):
            try:
                cur = getattr(env, k)
                if isinstance(cur, int):
                    setattr(env, k, int(v))
                elif isinstance(cur, float):
                    setattr(env, k, float(v))
                else:
                    setattr(env, k, v)
            except ValueError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF parser eval runner")
    parser.add_argument("--samples-dir", default="")
    parser.add_argument("--report", default="report.json")
    parser.add_argument("--table-backends", default="")
    parser.add_argument("--compare-vlm", default="")
    parser.add_argument("--cls-overrides", default="")
    args = parser.parse_args()
    run(args.samples_dir, args.report, args.table_backends, args.compare_vlm, args.cls_overrides)


if __name__ == "__main__":
    main()
