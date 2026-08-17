"""Eval sample set loader: samples/<name>.pdf + samples/<name>.label.json."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from src.utils import env


class Sample(BaseModel):
    pdf_path: str
    label_path: str
    expected_types: list[str] = []
    expected_blocks: list[dict] = []


def load_sample_set(samples_dir: Optional[str] = None) -> list[Sample]:
    base = Path(samples_dir or env.EVAL_SAMPLES_DIR)
    if not base.is_dir():
        return []
    samples: list[Sample] = []
    for pdf in sorted(base.glob("*.pdf")):
        label = pdf.with_suffix(".label.json")
        if not label.is_file():
            continue
        try:
            data = json.loads(label.read_text(encoding="utf-8"))
        except Exception:
            continue
        samples.append(
            Sample(
                pdf_path=str(pdf),
                label_path=str(label),
                expected_types=data.get("expected_types", []),
                expected_blocks=data.get("expected_blocks", []),
            )
        )
    return samples
