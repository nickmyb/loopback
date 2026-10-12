"""轨迹：把事件日志整理成“轮 -> 模型调用 -> 工具调用”的结构，并渲染成可读的时间线。

    events.jsonl ──build_trace()──> Trace(meta, turns=[Turn(calls=[Call(tools=[ToolCall])])])
                                        └── render_text() 终端时间线（/trace、loopback trace）
                                        └── （M5）HTML 轨迹页、eval 报告复用同一个结构

用途：审计（模型到底看到了什么、做了什么）、排查（D17 那种只有看轨迹才能发现的问题）、
evals（每条用例的完整轨迹）。这里只读事件，不修改事件。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loopback.pricing import cache_hit_rate, estimate_usd


@dataclass
class ToolCall:
    """一次工具调用：模型给的参数，加上 harness 回给模型的结果。"""

    name: str
    input: dict[str, Any]
    result: str | None = None  # None = 日志里没有找到对应的 tool_result（违反不变量）
    is_error: bool = False


@dataclass
class Call:
    """一次模型请求的结果（对应一个 assistant 事件）。"""

    agent: str
    model: str
    stop_reason: str | None
    usage: dict[str, Any]
    latency_ms: int
    prompt_hash: str | None
    text: str
    thinking_blocks: int
    tools: list[ToolCall] = field(default_factory=list)


@dataclass
class Turn:
    """一轮：学习者的一次输入，以及为回答它而发生的全部模型调用。"""

    index: int
    user: str
    calls: list[Call] = field(default_factory=list)
    failed: str | None = None  # turn_failed 的错误类型（API 错误 / KeyboardInterrupt）


@dataclass
class Trace:
    meta: dict[str, Any]
    turns: list[Turn]

    def usage(self) -> dict[str, int]:
        """全部模型调用的 token 用量合计。"""
        total: dict[str, int] = {}
        for call in (c for t in self.turns for c in t.calls):
            for k, v in call.usage.items():
                if isinstance(v, int):
                    total[k] = total.get(k, 0) + v
        return total


def load_events(path: Path) -> list[dict[str, Any]]:
    """读取事件日志；写了一半的坏行直接跳过（与 Session.open 一致）。"""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def build_trace(events: list[dict[str, Any]]) -> Trace:
    """按事件顺序归并：user 开新轮；assistant 成为一次 Call；tool_results 按 id 回填到 Call。"""
    meta: dict[str, Any] = {}
    turns: list[Turn] = []
    pending: dict[str, ToolCall] = {}  # tool_use_id -> 等待结果的工具调用
    for ev in events:
        kind = ev.get("type")
        if kind == "meta":
            meta = ev
        elif kind == "user":
            content = ev.get("content")
            turns.append(Turn(len(turns) + 1, content if isinstance(content, str) else "[blocks]"))
        elif kind == "assistant" and turns:
            call = _call_from(ev)
            turns[-1].calls.append(call)
            for block in ev.get("content", []):
                if block.get("type") == "tool_use":
                    pending[block["id"]] = _add_tool(call, block)
        elif kind == "tool_results":
            for r in ev.get("results", []):
                tool = pending.pop(r.get("tool_use_id"), None)
                if tool is not None:
                    tool.result, tool.is_error = str(r.get("content")), bool(r.get("is_error"))
        elif kind == "turn_failed" and turns:
            turns[-1].failed = ev.get("error", "error")
    return Trace(meta, turns)


def _call_from(ev: dict[str, Any]) -> Call:
    """从 assistant 事件里取出展示需要的字段：文本、thinking 块数、用量、耗时等。"""
    content = ev.get("content", [])
    return Call(
        agent=ev.get("agent", "?"),
        model=ev.get("model", "?"),
        stop_reason=ev.get("stop_reason"),
        usage=ev.get("usage") or {},
        latency_ms=ev.get("latency_ms", 0),
        prompt_hash=ev.get("prompt_hash"),
        text="".join(b.get("text", "") for b in content if b.get("type") == "text"),
        thinking_blocks=sum(1 for b in content if b.get("type") == "thinking"),
    )


def _add_tool(call: Call, block: dict[str, Any]) -> ToolCall:
    """把一个 tool_use 块挂到 Call 上，返回它，等 tool_results 来回填结果。"""
    tool = ToolCall(block.get("name", "?"), block.get("input") or {})
    call.tools.append(tool)
    return tool


def render_text(trace: Trace, *, last: int | None = None, width: int = 100) -> str:
    """渲染成终端时间线。last=N 只看最近 N 轮。"""
    out = []
    if trace.meta:
        m = trace.meta
        out.append(
            f"会话 · agent {m.get('agent')} · 模型 {m.get('model')} · prompt {m.get('prompt_hash')}"
            f" · 工具 {len(m.get('tools', []))} 个 · v{m.get('version')}"
        )
    turns = trace.turns[-last:] if last else trace.turns
    for turn in turns:
        out.append(f"\n━━ 第 {turn.index} 轮 ━━ 你：{_clip(turn.user, width - 16)}")
        for n, call in enumerate(turn.calls, 1):
            u = call.usage
            out.append(
                f"  [{n}] {call.model} → {call.stop_reason} · {call.latency_ms} ms"
                f" · 输入 {u.get('input_tokens', 0)} 缓存读 {u.get('cache_read_input_tokens', 0)}"
                f" 缓存写 {u.get('cache_creation_input_tokens', 0)}"
                f" · 输出 {u.get('output_tokens', 0)}"
                + (f" · thinking×{call.thinking_blocks}" if call.thinking_blocks else "")
            )
            for tool in call.tools:
                args = json.dumps(tool.input, ensure_ascii=False)
                out.append(f"      ⚙ {tool.name} {_clip(args, width - 20)}")
                mark = "✗" if tool.is_error else "↳"
                result = "（缺少 tool_result！）" if tool.result is None else tool.result
                out.append(f"        {mark} {_clip(result, width - 12)}")
            if call.text:
                out.append(f"      💬 {_clip(call.text, width - 10)}")
        if turn.failed:
            out.append(
                f"  ✗ 本轮失败：{turn.failed}（这条输入已撤回，不会再发给模型）"
                if not turn.calls
                else f"  ✗ 本轮中途失败：{turn.failed}"
            )
    usage = trace.usage()
    costs = [estimate_usd(c.model, c.usage) for t in trace.turns for c in t.calls]
    known = [c for c in costs if c is not None]
    out.append(
        f"\n合计 {sum(len(t.calls) for t in trace.turns)} 次模型调用 · "
        f"缓存命中率 {cache_hit_rate(usage):.0%}" + (f" · 约 ${sum(known):.4f}" if known else "")
    )
    return "\n".join(out)


def _clip(text: str, limit: int) -> str:
    """压成一行并截断，保证时间线一屏能看清。"""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: max(limit - 1, 1)] + "…"


def latest_session(home: Path) -> Path | None:
    """找到最近一次会话的事件日志（文件名以启动时间开头，按名字排序即可）。"""
    files = sorted((home / "sessions").glob("*.jsonl"))
    return files[-1] if files else None
