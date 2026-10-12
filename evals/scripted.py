"""剧本 LLM：不调用模型，按固定剧本回应。用来在不花钱的情况下验证 eval 本身（eval-audit §2）。

- oracle：一条“标准答案”轨迹（读对的节、课件覆盖每一段、有图有自测、进度正确、终端简短）。
  代码评分必须全部通过；不通过说明评分器或 harness 有 bug，而不是 agent 不行。
- null：直接返回空回答。必须不及格；如果它也能拿分，说明评分器太宽松。
"""

from __future__ import annotations

from typing import Any

from evals.cases import Case
from loopback.curriculum import Curriculum
from loopback.library import Material
from loopback.llm import OnText, Response


class ScriptedLLM:
    """实现 LLM protocol：每次 stream() 按顺序返回剧本里的下一条回复。"""

    def __init__(self, name: str, script: list[list[dict[str, Any]]]) -> None:
        self.name, self.script, self.calls = name, list(script), 0

    def stream(self, request: dict[str, Any], on_text: OnText) -> Response:
        """返回剧本的下一条回复（有 tool_use 就是 tool_use，否则 end_turn）。"""
        blocks = self.script.pop(0) if self.script else []
        self.calls += 1
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocks) else "end_turn"
        return Response(blocks, stop, self.name, {"input_tokens": 0, "output_tokens": 0})


def _tool(name: str, **args: Any) -> list[dict[str, Any]]:
    return [{"type": "tool_use", "id": f"oracle-{name}", "name": name, "input": args}]


def _text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def oracle(case: Case, material: Material, curriculum: Curriculum) -> ScriptedLLM:
    """按用例类型写出标准轨迹。"""
    item = case.item
    figure = {"type": "mermaid", "code": 'flowchart LR\n  A["输入"] --> B["输出"]'}
    quiz = {"type": "quiz", "q": "这一节的核心是什么？", "a": "见上文。"}
    reply = _text("一句话：这一节讲清了核心概念。\n课件已打开。")
    if case.kind == "section":
        n = case.section or 1
        paras = len(material.sections[n - 1].paras)
        explains = [{"type": "explain", "para": p, "text": "讲解。"} for p in range(1, paras + 1)]
        script = [
            _tool("read_section", item_id=item, index=n),
            _tool(
                "render_lesson",
                item_id=item,
                page="section",
                section=n,
                title="第 n 节",
                blocks=[*explains, figure, quiz],
            ),
            _tool("update_progress", item_id=item, section=n),
            reply,
        ]
    elif case.kind == "start":
        script = [
            _tool("find_material", query=case.say),
            _tool("fetch_material", item_id=item),
            _tool(
                "render_lesson",
                item_id=item,
                page="overview",
                title="概览",
                blocks=[
                    {"type": "text", "text": "要解决的问题。"},
                    figure,
                    {"type": "note", "text": "核心观点。"},
                ],
            ),
            _tool("update_progress", item_id=item, section=0),
            reply,
        ]
    else:  # finish
        script = [
            _tool(
                "render_lesson",
                item_id=item,
                page="summary",
                title="总结",
                blocks=[{"type": "text", "text": "回顾。"}, figure, quiz],
            ),
            _tool("update_progress", item_id=item, done=True, summary="一句话总结。"),
            reply,
        ]
    return ScriptedLLM("scripted-oracle", script)


def null(case: Case) -> ScriptedLLM:
    """空回答：什么工具都不调，什么也不说。"""
    return ScriptedLLM("scripted-null", [[]])
