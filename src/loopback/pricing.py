"""按 API 返回的 usage 估算花费（美元）。价格表只收常用模型，未知模型只显示 token 数。

价格单位：美元 / 百万 token。DeepSeek 取高峰价（上限），闲时实际只要一半。
核对日期：2026-10-12（Claude 价格取自 claude-api skill，DeepSeek 取自官方定价页）。
"""

from __future__ import annotations

from typing import Any

# model: (input, output, cache_read, cache_write_5m)
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-4-5": (1.00, 5.00, 0.10, 1.25),
    "deepseek-flash": (0.30, 1.20, 0.006, 0.30),
    "deepseek-v4-pro": (1.32, 3.96, 0.044, 1.32),
}


def estimate_usd(model: str, usage: dict[str, Any]) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    p_in, p_out, p_read, p_write = price
    return (
        usage.get("input_tokens", 0) * p_in
        + usage.get("output_tokens", 0) * p_out
        + usage.get("cache_read_input_tokens", 0) * p_read
        + usage.get("cache_creation_input_tokens", 0) * p_write
    ) / 1_000_000


def cache_hit_rate(usage: dict[str, Any]) -> float:
    read = usage.get("cache_read_input_tokens", 0) or 0
    total = read + (usage.get("input_tokens", 0) or 0)
    total += usage.get("cache_creation_input_tokens", 0) or 0
    return read / total if total else 0.0
