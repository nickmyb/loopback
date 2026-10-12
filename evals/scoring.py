"""单次试验的打分与记账：跑试验 -> 代码评分 -> LLM 评审 -> 一行结果（写进 results.jsonl）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anthropic

from evals.cases import Case
from evals.graders import grade
from evals.harness import InfraError, run_trial
from evals.judge import JudgeError, judge
from loopback.curriculum import Curriculum
from loopback.llm import LLM
from loopback.pricing import estimate_usd


def score_trial(
    case: Case,
    rep: int,
    run_dir: Path,
    llm: LLM,
    env: dict[str, str],
    curriculum: Curriculum,
    cache: Path,
    judge_llm: LLM | None,
    judge_model: str,
) -> dict[str, Any]:
    """跑一次试验并打分；基础设施错误返回 {"error": ...}，评审失败只记 judge_error。"""
    t0 = time.monotonic()
    try:
        trial = run_trial(case, rep, run_dir, llm, env, curriculum, cache)
    except InfraError as e:
        return {"case": case.id, "rep": rep, "error": str(e)}
    assistant = [ev for ev in trial.session.events if ev["type"] == "assistant"]
    usage: dict[str, int] = {}
    for ev in assistant:
        for k, v in (ev.get("usage") or {}).items():
            if isinstance(v, int):
                usage[k] = usage.get(k, 0) + v
    row: dict[str, Any] = {
        "case": case.id,
        "rep": rep,
        "kind": case.kind,
        "input": trial.user_input,
        "grades": grade(trial),
        "usage": usage,
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "cost_usd": sum(
            estimate_usd(ev.get("model", ""), ev.get("usage") or {}) or 0.0 for ev in assistant
        ),
        "served_models": sorted({ev.get("model") for ev in assistant}),
    }
    if judge_llm is not None:
        try:
            j = judge(judge_llm, judge_model, trial)
            row |= {
                "judge": j["metrics"],
                "judge_raw": j["raw"],
                "judge_items": j["items"],
                "judge_cost_usd": estimate_usd(j["model"], j["usage"]) or 0.0,
            }
        except (JudgeError, anthropic.APIError) as e:
            row["judge_error"] = f"{type(e).__name__}: {e}"
    return row
