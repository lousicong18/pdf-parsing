"""OpenAI-compatible VLM client (synchronous httpx).

Each call records a VlmCallMetric into the explicitly passed metrics_ctx.
No module-level task context — metrics_ctx is always passed in.
"""

import base64
import hashlib
import re
import time
from typing import Optional

import httpx

from src.utils import env, vlm_models
from src.utils.metrics import record_vlm_call

# MiniMax (and some compat providers) embed thinking in <think>…</think> tags.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()

DESCRIBE_PROMPT = (
    "请详细描述这张图片的内容，包括可见的文字、数据、结构、颜色与布局。"
    "用中文输出，保持简洁准确。"
)

CHART_PROMPT = (
    "这是一张表格中的图表区域（如散点图、柱状图等）。请按以下格式解析：\n"
    "1. 图表类型：说明是什么类型的图表\n"
    "2. 数据系列：只描述可见的颜色和形状特征（如'深蓝色圆点'、'红色三角'），禁止猜测或编造任何品牌名、系列名\n"
    "3. 坐标轴：说明X轴和Y轴的含义和刻度范围\n"
    "4. 整体趋势：描述数据的总体分布特征（如哪些系列偏高/低、差距大小）\n"
    "严格规则：\n"
    "- 不得编造、推测任何品牌名称、产品名称或数据系列名称\n"
    "- 图例文字过小无法读取时，只描述颜色/形状，不猜测文字内容\n"
    "- 如果无法确定某个信息，直接写'无法识别'，不要编造\n"
    "用中文输出。"
)

OCR_PROMPT = (
    "请对这张扫描件图片进行 OCR 识别，输出其中所有可读文字。"
    "尽量保持原始段落与结构，用中文输出。"
)

_client = httpx.Client(timeout=60.0)

# response cache: key = hash(image_bytes + prompt) -> text
_vlm_cache: dict[str, str] = {}


def _cache_key(image_bytes: bytes, prompt: str) -> str:
    return hashlib.sha256(image_bytes + prompt.encode("utf-8")).hexdigest()


def _call_vlm(
    image_bytes: bytes,
    prompt: str,
    metrics_ctx,
    model_name: Optional[str] = None,
    kind: str = "image",
) -> str:
    cfg = vlm_models.get_model(model_name)
    key = _cache_key(image_bytes, prompt)
    if env.VLM_RESPONSE_CACHE == "on" and key in _vlm_cache:
        return _vlm_cache[key]

    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
    }

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    last_err: Optional[Exception] = None
    final_latency = 0
    final_retry = 0
    for attempt in range(2):
        t0 = time.time()
        try:
            resp = _client.post(url, json=payload, headers=headers)
            latency = int((time.time() - t0) * 1000)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                final_latency = latency
                final_retry = attempt + 1
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            raw = (data["choices"][0]["message"] or {}).get("content") or ""
            content = _strip_thinking(raw)
            if not content.strip():
                last_err = RuntimeError("empty vlm response")
                record_vlm_call(metrics_ctx, kind, cfg.model, latency, 0, 0.0, attempt, False)
                raise last_err
            usage = data.get("usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            total_tokens = int(usage.get("total_tokens", 0))
            cost = _calc_cost(cfg.model, prompt_tokens, completion_tokens)
            record_vlm_call(metrics_ctx, kind, cfg.model, latency, total_tokens, cost, attempt, True, prompt_tokens, completion_tokens)
            if env.VLM_RESPONSE_CACHE == "on":
                _vlm_cache[key] = content
            return content
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            latency = int((time.time() - t0) * 1000)
            last_err = e
            final_latency = latency
            final_retry = attempt + 1
            time.sleep(2)
    # exhausted retries — single failure record
    record_vlm_call(metrics_ctx, kind, cfg.model, final_latency, 0, 0.0, final_retry, False)
    raise last_err or RuntimeError("vlm call failed")


# 真实定价表（¥ / 百万 tokens），按 model name 模糊匹配
# input_cache_hit / input_cache_miss / output
_PRICING = {
    "deepseek-v4-pro": (0.15, 4.5, 13.5),
    "deepseek-v4-flash": (0.05, 1.5, 4.5),
    "MiniMax-M3": (0.42, 2.10, 8.40),  # 缓存命中价作为默认，实际按上下文长度切换
    "kimi-k2.7-code": (1.30, 6.50, 27.00),
}


def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """按真实定价计算成本（¥）。缓存命中按 25% 估算（保守按缓存未命中算）。"""
    if not prompt_tokens and not completion_tokens:
        return 0.0
    hit, miss, out = 0.15, 4.5, 13.5  # 默认 deepseek-v4-pro 空闲价
    for key, prices in _PRICING.items():
        if key in model:
            hit, miss, out = prices
            break
    # 缓存命中比例：保守估计 25%，其余按缓存未命中
    input_cost = (prompt_tokens * 0.25 * hit + prompt_tokens * 0.75 * miss) / 1e6
    output_cost = completion_tokens * out / 1e6
    return input_cost + output_cost


def vlm_describe(image_bytes: bytes, metrics_ctx, model_name: Optional[str] = None,
                 prompt: Optional[str] = None) -> str:
    return _call_vlm(image_bytes, prompt or DESCRIBE_PROMPT, metrics_ctx, model_name, kind="image")


def vlm_describe_chart(image_bytes: bytes, metrics_ctx, model_name: Optional[str] = None,
                       prompt: Optional[str] = None) -> str:
    """专门用于解析图表（散点图、柱状图等）的 VLM 调用。"""
    return _call_vlm(image_bytes, prompt or CHART_PROMPT, metrics_ctx, model_name, kind="chart")


def vlm_ocr(image_bytes: bytes, metrics_ctx, model_name: Optional[str] = None) -> str:
    return _call_vlm(image_bytes, OCR_PROMPT, metrics_ctx, model_name, kind="scan")
