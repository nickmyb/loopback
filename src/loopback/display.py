"""终端里的显示（REPL 用）：工具调用提示、一轮结束时的说明、用量和花费、接口错误。"""

from __future__ import annotations

from typing import Any

import anthropic

from loopback.loop import TurnResult
from loopback.pricing import cache_hit_rate, estimate_usd
from loopback.session import Session


def show_tool(name: str, args: dict[str, Any]) -> None:
    """模型每调用一次工具，就在终端里显示一行，让学习者看到 agent 在做什么。"""
    brief = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
    print(f"\n  ⚙ {name}({brief})", flush=True)


def describe_stop(result: TurnResult, max_steps: int) -> str | None:
    """一轮不是正常结束（拒答、截断、步数用完）时，告诉学习者发生了什么、怎么办。"""
    if result.stop_reason == "refusal":
        category = (result.stop_details or {}).get("category")
        return f"[模型拒绝回答：{category or '未注明类别'}] 换个问法试试。"
    if result.stop_reason == "max_tokens":
        return "[回答达到长度上限被截断] 可以说“继续”。"
    if result.stop_reason == "max_steps":
        return f"[已连续调用模型 {max_steps} 次，先停下来] 可以说“继续”。"
    return None


def format_cost(session: Session) -> str:
    """汇总用量；按每个 assistant 事件里“实际服务的模型”计价（兼容接口可能静默换模型）。"""
    u = session.usage_totals()
    costs = [
        estimate_usd(ev.get("model", ""), ev.get("usage") or {})
        for ev in session.events
        if ev["type"] == "assistant"
    ]
    known = [c for c in costs if c is not None]
    money = f"约 ${sum(known):.4f}" if known else "（未知模型，不估算）"
    if known and len(known) < len(costs):
        money += "（部分模型未知，未计入）"
    return (
        f"输入 {u.get('input_tokens', 0)} · 输出 {u.get('output_tokens', 0)} · "
        f"缓存读 {u.get('cache_read_input_tokens', 0)} · "
        f"缓存写 {u.get('cache_creation_input_tokens', 0)}\n"
        f"缓存命中率 {cache_hit_rate(u):.0%} · 花费 {money}"
    )


def describe_api_error(e: anthropic.APIError) -> str:
    """把 SDK 的异常翻译成学习者看得懂、知道怎么处理的提示。"""
    if isinstance(e, anthropic.AuthenticationError):
        return "认证失败：检查 .env 里的 ANTHROPIC_API_KEY"
    if isinstance(e, anthropic.NotFoundError):
        return "模型或接口不存在：检查 MODEL_ID / ANTHROPIC_BASE_URL"
    if isinstance(e, anthropic.RateLimitError):
        return "触发限流，SDK 已自动重试仍失败，稍后再试"
    if isinstance(e, anthropic.APIConnectionError):
        return "网络连接失败：检查网络或代理（HTTPS_PROXY）"
    if isinstance(e, anthropic.APIStatusError):
        return f"HTTP {e.status_code}：{e.message}"
    return str(e)


def _short(value: Any, limit: int = 40) -> str:
    """把参数值压成一行并截断，用在终端的工具调用提示里。"""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
