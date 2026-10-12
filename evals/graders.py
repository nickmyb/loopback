"""代码评分：从轨迹（事件日志）和产物（课件、进度）里做确定性的检查。

原则（eval-audit §4）：
- 评结果，不评路径：检查“课件生成了、覆盖了每段、进度对了”，不要求固定的工具调用顺序。
- 原子化：每一项单独一个指标，不揉成一个总分；另给一个严格的 pass（所有布尔检查都通过）。
- 诊断性指标（工具报错次数、查找次数）只展示，不计入 pass。
"""

from __future__ import annotations

import re
from typing import Any

from evals.harness import Trial
from loopback.curriculum import Progress
from loopback.trace import ToolCall, build_trace

FIGURES = {"mermaid", "svg", "steps"}


def tool_calls(trial: Trial) -> list[ToolCall]:
    """按发生顺序拿到这次试验里的所有工具调用（含参数和结果）。"""
    trace = build_trace(trial.session.events)
    return [tool for turn in trace.turns for call in turn.calls for tool in call.tools]


def last_render(calls: list[ToolCall], page: str, section: int | None = None) -> dict | None:
    """最后一次成功生成指定页面的 render_lesson 参数（失败后重试成功的也算）。"""
    for t in reversed(calls):
        args = t.input
        is_render = t.name == "render_lesson" and not t.is_error and args.get("page") == page
        if is_render and (section is None or args.get("section") == section):
            return args
    return None


def _first_sentence(text: str) -> str:
    """终端回答的第一句：取第一行，再截到第一个句号/冒号之前，去掉 markdown 符号。"""
    first = next((line for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"[*_`#>]", "", first).strip()
    return re.split(r"[。！？!?]", first, maxsplit=1)[0]


def grade(trial: Trial) -> dict[str, Any]:
    """返回这次试验的全部代码评分。布尔值是检查项，整数是诊断项。"""
    case, calls = trial.case, tool_calls(trial)
    lines = [line for line in trial.final_text.splitlines() if line.strip()]
    g: dict[str, Any] = {
        "completed": trial.stop_reason == "end_turn",
        "terminal_brief": 0 < len(lines) <= 8,  # 大白话规则 4：终端不超过约 8 行
        "conclusion_first": 0
        < len(_first_sentence(trial.final_text))
        <= 40,  # 规则 1（放宽到 40 字）
        "n_tool_errors": sum(t.is_error for t in calls),  # 诊断：包括被自我修正掉的错误
        "n_tool_calls": len(calls),
    }
    state = Progress(trial.home).state(case.item)
    if case.kind == "section":
        n = case.section
        render = last_render(calls, "section", n)
        blocks = render.get("blocks", []) if render else []
        paras = len(trial.material.sections[n - 1].paras)
        covered = {b.get("para") for b in blocks if b.get("type") == "explain"}
        g |= {
            "read_section": any(
                t.name == "read_section" and t.input.get("index") == n for t in calls
            ),
            "lesson_rendered": render is not None,
            "explain_coverage": len(covered & set(range(1, paras + 1))) / paras,
            "has_figure": any(b.get("type") in FIGURES for b in blocks),
            "has_quiz": any(b.get("type") == "quiz" for b in blocks),
            "progress_ok": state.get("section") == n,
        }
    elif case.kind == "start":  # D17 回归：按标题找文章，不能乱猜 id、乱抓别的文章
        fetched = [t.input.get("item_id") for t in calls if t.name == "fetch_material"]
        render = last_render(calls, "overview")
        g |= {
            "no_wasted_fetch": all(i == case.item for i in fetched) and case.item in fetched,
            "n_lookups": sum(t.name in ("find_material", "fetch_material") for t in calls),
            "lesson_rendered": render is not None,
            "has_figure": any(b.get("type") in FIGURES for b in (render or {}).get("blocks", [])),
            "progress_ok": state.get("status") == "in_progress" and state.get("section") == 0,
        }
    else:  # finish
        render = last_render(calls, "summary")
        blocks = (render or {}).get("blocks", [])
        g |= {
            "lesson_rendered": render is not None,
            "has_quiz": any(b.get("type") == "quiz" for b in blocks),
            "progress_ok": state.get("status") == "done" and bool(state.get("summary")),
        }
    checks = [v for k, v in g.items() if isinstance(v, bool)]
    g["pass"] = all(checks) and g.get("explain_coverage", 1.0) == 1.0
    return g
