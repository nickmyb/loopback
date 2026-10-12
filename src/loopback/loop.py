"""agent_loop：所有角色共用的那一个循环。

    user input ─> [ request ─> stream ─> assistant event ─> tool_results event ] x N ─> done
                     ^ messages = session.messages()   (projection of the event log)

不变量（对应 docs/decisions.md 和 CLAUDE.md 的“不变量”一节）
1. 只追加（D3）：所有状态变化都是 session.append(...)，不修改历史。
2. 配对（CLAUDE.md 不变量 2）：只要 assistant 内容里有 tool_use，
   就一定紧跟一个 tool_results 事件覆盖所有 id。
   这包括不该执行的情况（max_tokens 截断、refusal）和用户按 Ctrl-C 的情况。
3. 失败可恢复（D15）：API 异常和 Ctrl-C 都会抛给调用方。抛出之前先追加一个 turn_failed 事件。
   如果这条用户输入还没得到任何回答，投影时就会跳过它，会话保持一致，可以继续。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loopback.agents import AgentSpec
from loopback.config import Settings
from loopback.llm import LLM, OnText, build_request
from loopback.session import Session
from loopback.tools import ToolResult, error

log = logging.getLogger(__name__)

OnTool = Callable[[str, dict[str, Any]], None]
CONTINUE = {"tool_use", "pause_turn"}  # pause_turn：服务端工具暂停，原样再发一次即可续上


@dataclass(frozen=True)
class TurnResult:
    stop_reason: str  # end_turn / max_tokens / refusal / max_steps ...
    text: str  # 最后一次模型回复里的文本
    steps: int
    stop_details: dict[str, Any] | None = None


def run_turn(
    session: Session,
    spec: AgentSpec,
    llm: LLM,
    settings: Settings,
    user_input: str | list[dict[str, Any]],
    *,
    on_text: OnText = lambda _: None,
    on_tool: OnTool = lambda _name, _args: None,
) -> TurnResult:
    """处理学习者的一次输入：

    反复“请求模型 -> 记录回复 -> 执行工具 -> 记录结果”，直到模型不再要工具。
    """
    session.append("user", content=user_input)
    for step in range(1, spec.max_steps + 1):
        # 1) 用事件日志的投影拼请求：messages 永远是上一轮请求的原样延续（只追加）
        request = build_request(
            settings,
            system=spec.system,
            messages=session.messages(),
            tools=spec.tools.specs(),
            max_tokens=spec.max_tokens,
            effort=spec.effort,
        )
        # 2) 调模型（流式打印）；失败就记一笔 turn_failed 再往上抛
        try:
            resp = llm.stream(request, on_text)
        except BaseException as e:  # API 错误或 Ctrl-C：这次请求没有写入任何回答
            session.append("turn_failed", step=step, error=type(e).__name__)
            raise
        # 3) 原样记录回复，连同实际服务的模型、用量、耗时、prompt 版本，供审计和 eval 使用
        session.append(
            "assistant",
            agent=spec.name,
            content=resp.content,
            model=resp.model,
            stop_reason=resp.stop_reason,
            stop_details=resp.stop_details,
            usage=resp.usage,
            request_id=resp.request_id,
            latency_ms=resp.latency_ms,
            prompt_hash=spec.prompt_hash,
        )
        if resp.model != settings.model:
            log.warning("served model %s != requested %s", resp.model, settings.model)

        # 4) 回复里有工具调用：执行并记录结果（每个 tool_use 都必须有 tool_result）
        tool_uses = [b for b in resp.content if b.get("type") == "tool_use"]
        if tool_uses:
            _answer_tool_uses(session, spec, tool_uses, resp.stop_reason, on_tool)
        # 5) 模型不再需要工具（end_turn、截断、拒答……）：本轮结束；否则带着工具结果再请求一次
        if resp.stop_reason not in CONTINUE:
            return TurnResult(
                resp.stop_reason or "unknown", _text(resp.content), step, resp.stop_details
            )

    log.warning("agent %s hit max_steps=%d", spec.name, spec.max_steps)
    return TurnResult("max_steps", "", spec.max_steps)


def _answer_tool_uses(
    session: Session,
    spec: AgentSpec,
    tool_uses: list[dict[str, Any]],
    stop_reason: str | None,
    on_tool: OnTool,
) -> None:
    """给一条回复里的每个 tool_use 产生结果并一次性记录；不该执行或被中断的也补上错误结果。"""
    results: dict[str, ToolResult] = {}
    try:
        for block in tool_uses:
            if stop_reason != "tool_use":  # 截断的输入或拒答：不执行，但必须回一个结果
                results[block["id"]] = error(f"not executed: response stopped with {stop_reason}")
                continue
            on_tool(block["name"], block.get("input") or {})
            results[block["id"]] = spec.tools.run(block["name"], block.get("input"))
    finally:  # 包括 KeyboardInterrupt：补齐剩下的 id，再让中断继续往上抛
        for block in tool_uses:
            results.setdefault(block["id"], error("interrupted by the user before running"))
        session.append(
            "tool_results",
            results=[results[b["id"]].block(b["id"]) for b in tool_uses],
        )


def _text(content: list[dict[str, Any]]) -> str:
    """拼出一条回复里的全部文本块。"""
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")
