"""Formula recognition: Unicode symbol detection + VLM structure restoration."""

from abc import ABC, abstractmethod

from src.utils import env

# LaTeX-style formula commands
_LATEX_HINTS = ("\\frac", "\\sum", "\\int", "\\sqrt", "\\lim", "\\begin", "\\text")
# Unicode math symbols that indicate formula content
_UNICODE_MATH = set("αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΣΠΩ∑∏∫∮∂∇√∞≤≥≠≈±×÷°∠∥∈∉⊂⊃∪∩∀∃→⇒↔≡∝²³ⁿ₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹")
# Flat formula patterns (lost superscript/subscript structure)
_FLAT_FORMULA_RE = (" = mc", "x²", "x³", "a²", "b²", "ₙ", "ᵢ")


class FormulaRecognizer(ABC):
    @abstractmethod
    def recognize(self, page) -> list[dict]:
        """Return suspected formula annotations with bbox + snippet."""
        ...


class AnnotateRecognizer(FormulaRecognizer):
    """Detect text blocks containing LaTeX commands or Unicode math symbols."""

    def recognize(self, page) -> list[dict]:
        out: list[dict] = []
        try:
            blocks = page.get_text("dict").get("blocks", [])
        except Exception:
            return out
        for b in blocks:
            if b.get("type", 0) != 0:
                continue
            snippet = _block_text(b)
            if not snippet or len(snippet) < 2:
                continue
            kind = _detect_formula_kind(snippet)
            if kind:
                out.append({"bbox": b.get("bbox"), "snippet": snippet[:200], "kind": kind})
        return out


def _detect_formula_kind(snippet: str) -> str:
    """Detect if snippet contains formula content. Returns kind or ''."""
    if any(h in snippet for h in _LATEX_HINTS):
        return "latex"
    # Unicode math symbol density check
    math_chars = sum(1 for c in snippet if c in _UNICODE_MATH)
    if math_chars >= 2 or (math_chars >= 1 and len(snippet) < 50):
        return "unicode"
    return ""


class LatexRecognizer(FormulaRecognizer):
    """Probe get_text('latex') and expose its raw output as annotations."""

    def recognize(self, page) -> list[dict]:
        sample = probe_latex(page)
        if not sample.get("available"):
            return []
        return [{"bbox": None, "snippet": sample.get("sample", "")[:200]}]


def probe_latex(page) -> dict:
    """Probe whether get_text('latex') yields meaningful output."""
    try:
        text = page.get_text("latex") or ""
    except Exception:
        return {"available": False, "sample": "", "length": 0}
    text = text.strip()
    return {"available": len(text) > 0, "sample": text[:200], "length": len(text)}


def get_formula_recognizer() -> FormulaRecognizer:
    mode = env.FORMULA_MODE
    if mode == "latex":
        return LatexRecognizer()
    if mode == "model":
        return LatexRecognizer()  # reserved stub
    return AnnotateRecognizer()


def restore_formula_structure(text: str, vlm_describe_fn=None) -> str:
    """用 VLM 还原公式的上下标结构（如 'E = mc2' → 'E = mc²'）。
    需开启 FORMULA_MODE=latex 且传入 vlm_describe_fn。"""
    if not vlm_describe_fn or env.FORMULA_MODE != "latex":
        return text
    try:
        prompt = f"以下是一个丢失了上下标结构的公式文本，请还原为标准 LaTeX 格式（如 mc2 → mc^2）：\n{text}\n只返回还原后的 LaTeX 公式。"
        result = vlm_describe_fn(prompt=prompt)
        return result.content.strip() if result and result.content else text
    except Exception:
        return text


def _block_text(block: dict) -> str:
    parts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
    return "".join(parts)
