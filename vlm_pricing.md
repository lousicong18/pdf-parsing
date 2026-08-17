# VLM 模型定价表

> 日期：2026-08-14
> 单位：¥ / 百万 tokens

## DeepSeek

| 模型 | 缓存命中 | 缓存未命中 | 输出 | 时段 |
|------|---------|-----------|------|------|
| deepseek-v4-flash | 0.05 | 1.5 | 4.5 | 空闲 |
| deepseek-v4-flash | 0.10 | 3.0 | 9.0 | 高峰 |
| deepseek-v4-pro | 0.15 | 4.5 | 13.5 | 空闲 |
| deepseek-v4-pro | 0.30 | 9.0 | 27.0 | 高峰 |

## MiniMax

| 模型 | 输入 | 输出 | 缓存读取 | 备注 |
|------|------|------|---------|------|
| MiniMax-M3 | 2.10 | 8.40 | 0.42 | ≤ 512k tokens（五折后） |
| MiniMax-M3 | 4.20 | 16.80 | 0.84 | > 512k tokens（五折后） |

## Kimi（月之暗面）

| 模型 | 缓存命中 | 缓存未命中 | 输出 | 上下文窗口 |
|------|---------|-----------|------|-----------|
| kimi-k2.7-code | 1.30 | 6.50 | 27.00 | 262,144 tokens |
| kimi-k2.7-code-highspeed | 2.60 | 13.00 | 54.00 | 262,144 tokens |

---

## 当前代码中的占位算法

```python
# src/parser/vlm.py:98
cost = tokens * 1e-6  # $1/百万 tokens，粗略估算
```

## 真实成本计算公式

```
cost_cny = input_tokens × input_price + output_tokens × output_price
```

> 注：API 返回的 usage 通常包含 prompt_tokens / completion_tokens，需区分计价。
