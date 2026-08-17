"""Eval metrics: classification accuracy, confusion matrix, feature distribution, etc.

Each function takes explicit params — no module-level task context.
A "sample_result" is a SampleResult(sample, result) carrying both the label and the parse result.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from src.eval.sample_set import Sample
from src.models.schemas import PageFeatures, ParseResult


@dataclass
class SampleResult:
    sample: Sample
    result: ParseResult
    extra: dict = field(default_factory=dict)


def classification_accuracy(sample_results: list) -> dict:
    total = 0
    correct = 0
    per_type: dict[str, dict] = {}
    for sr in sample_results:
        expected = sr.sample.expected_types
        for i, page in enumerate(sr.result.pages):
            if i >= len(expected):
                continue
            exp = expected[i]
            total += 1
            ok = exp == page.type
            if ok:
                correct += 1
            bucket = per_type.setdefault(exp, {"correct": 0, "total": 0})
            bucket["total"] += 1
            if ok:
                bucket["correct"] += 1
    return {
        "overall": correct / total if total else 0.0,
        "total": total,
        "correct": correct,
        "per_type": {t: v["correct"] / v["total"] if v["total"] else 0.0 for t, v in per_type.items()},
    }


def confusion_matrix(sample_results: list) -> dict:
    labels = ["text", "table", "mixed", "scan"]
    idx = {l: i for i, l in enumerate(labels)}
    mat = [[0] * 4 for _ in range(4)]
    for sr in sample_results:
        expected = sr.sample.expected_types
        for i, page in enumerate(sr.result.pages):
            if i >= len(expected):
                continue
            exp = expected[i]
            got = page.type
            if exp in idx and got in idx:
                mat[idx[exp]][idx[got]] += 1
    return {"labels": labels, "matrix": mat}


def feature_distribution_by_type(sample_results: list) -> dict:
    by_type: dict[str, list[PageFeatures]] = defaultdict(list)
    for sr in sample_results:
        for page in sr.result.pages:
            if page.features is not None:
                by_type[page.type].append(page.features)
    return _aggregate_features(by_type)


def _aggregate_features(by_type: dict[str, list[PageFeatures]]) -> dict:
    out: dict = {}
    for t, fs in by_type.items():
        n = len(fs)
        if n == 0:
            continue
        out[t] = {
            "count": n,
            "line_count": _mean([f.line_count for f in fs]),
            "area_ratio": _mean([f.area_ratio for f in fs]),
            "overlap_rate": _mean([f.overlap_rate for f in fs]),
            "char_density": _mean([f.char_density for f in fs]),
            "orthogonality": _mean([f.orthogonality for f in fs]),
            "drawings_path_count": _mean([f.drawings_path_count for f in fs]),
            "columns": _mean([f.columns for f in fs]),
        }
    return out


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def table_backend_compare(results_by_backend: dict) -> dict:
    return {backend: _table_accuracy(srs) for backend, srs in results_by_backend.items()}


def _table_accuracy(sample_results: list) -> dict:
    matched = 0
    total = 0
    for sr in sample_results:
        expected_blocks = sr.sample.expected_blocks
        for i, page in enumerate(sr.result.pages):
            if page.type != "table":
                continue
            for b in page.blocks:
                if b.type != "table" or b.table is None:
                    continue
                total += 1
                exp = expected_blocks[i] if i < len(expected_blocks) else {}
                exp_rows = exp.get("n_rows")
                exp_cols = exp.get("n_cols")
                if exp_rows is not None and exp_cols is not None:
                    if abs(b.table.n_rows - exp_rows) <= 1 and abs(b.table.n_cols - exp_cols) <= 1:
                        matched += 1
    return {"accuracy": matched / total if total else 0.0, "total": total, "matched": matched}


def vlm_cost_aggregate(sample_results: list) -> dict:
    total_cost = 0.0
    total_latency = 0
    by_kind: dict[str, int] = {}
    calls = 0
    for sr in sample_results:
        m = sr.result.metrics
        if not m:
            continue
        total_cost += m.total_cost or 0.0
        total_latency += m.total_latency_ms or 0
        for k, v in (m.by_kind or {}).items():
            by_kind[k] = by_kind.get(k, 0) + v
        calls += len(m.vlm_calls or [])
    return {"total_cost": total_cost, "total_latency_ms": total_latency, "by_kind": by_kind, "calls": calls}


def output_diff(sample_result) -> list[dict]:
    diffs: list[dict] = []
    expected_blocks = sample_result.sample.expected_blocks
    actual_blocks = []
    for page in sample_result.result.pages:
        actual_blocks.extend(page.blocks)
    for i, exp in enumerate(expected_blocks):
        act = actual_blocks[i] if i < len(actual_blocks) else None
        if act is None:
            diffs.append({"index": i, "expected": exp, "actual": None, "match": False})
            continue
        match = _block_match(act, exp)
        if not match:
            diffs.append({"index": i, "expected": exp, "actual": act.model_dump(), "match": False})
    return diffs


def _block_match(act, exp: dict) -> bool:
    if exp.get("type") and exp["type"] != act.type:
        return False
    if act.type == "text" and exp.get("text"):
        return _sim(act.text or "", exp["text"]) > 0.6
    if act.type == "table" and exp.get("n_rows") and act.table:
        return abs(act.table.n_rows - exp["n_rows"]) <= 2
    return True


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_s, b_s = set(a), set(b)
    if not a_s or not b_s:
        return 0.0
    return len(a_s & b_s) / len(a_s | b_s)


def build_report(
    sample_results: list,
    diff_badcases: list[dict],
    table_backend_results: Optional[dict] = None,
    vlm_model_results: Optional[dict] = None,
) -> dict:
    return {
        "classification": classification_accuracy(sample_results),
        "confusion_matrix": confusion_matrix(sample_results),
        "feature_distribution": feature_distribution_by_type(sample_results),
        "table_backend_compare": table_backend_compare(table_backend_results or {}),
        "vlm_cost": vlm_cost_aggregate(sample_results),
        "badcases": diff_badcases[:50],
        "vlm_model_compare": vlm_model_compare(vlm_model_results or {}),
    }


def render_report_md(report: dict) -> str:
    lines = ["# Eval Report\n"]
    cls = report.get("classification", {})
    lines.append("## Classification accuracy\n")
    lines.append(f"- overall: {cls.get('overall', 0):.3f} ({cls.get('correct', 0)}/{cls.get('total', 0)})")
    for t, v in (cls.get("per_type") or {}).items():
        lines.append(f"  - {t}: {v:.3f}")
    cm = report.get("confusion_matrix", {})
    lines.append("\n## Confusion matrix\n")
    labels = cm.get("labels", [])
    if labels:
        lines.append("| | " + " | ".join(labels) + " |")
        lines.append("| " + " | ".join(["---"] * len(labels)) + " |")
        for row_label, row in zip(labels, cm.get("matrix", [])):
            lines.append("| " + row_label + " | " + " | ".join(str(x) for x in row) + " |")
    cost = report.get("vlm_cost", {})
    lines.append(f"\n## VLM cost\n- total_cost: {cost.get('total_cost', 0):.6f}")
    lines.append(f"- total_latency_ms: {cost.get('total_latency_ms', 0)}")
    lines.append(f"- calls: {cost.get('calls', 0)}")
    bc = report.get("badcases", [])
    lines.append(f"\n## Badcases ({len(bc)})\n")
    for c in bc[:20]:
        lines.append(f"- {c}")
    return "\n".join(lines)


def vlm_model_compare(results_by_model: dict) -> dict:
    return {model: vlm_cost_aggregate(srs) for model, srs in results_by_model.items()}
