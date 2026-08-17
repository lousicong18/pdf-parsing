from src.models.schemas import TaskMetrics, VlmCallMetric


def new_task_metrics() -> TaskMetrics:
    return TaskMetrics()


def record_vlm_call(
    metrics_ctx: TaskMetrics,
    kind: str,
    model: str,
    latency_ms: int,
    tokens: int,
    cost_usd: float,
    retry: int,
    success: bool,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    metric = VlmCallMetric(
        kind=kind,
        model=model,
        latency_ms=latency_ms,
        tokens=tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        retry=retry,
        success=success,
    )
    metrics_ctx.vlm_calls.append(metric)
    metrics_ctx.total_cost += cost_usd
    metrics_ctx.total_latency_ms += latency_ms
    metrics_ctx.by_kind[kind] = metrics_ctx.by_kind.get(kind, 0) + 1
