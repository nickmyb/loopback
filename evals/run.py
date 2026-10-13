"""命令行：冻结材料快照 -> 估算花费并确认 -> 逐个试验（代码评分 + LLM 评审）-> 汇总报告。

    uv run python -m evals.run --suite teacher --reps 2 [--cases a,b] [--model X]
                               [--judge-model Y] [--no-judge] [--max-usd 5] [--yes]
    uv run python -m evals.run --suite teacher --baseline oracle|null   # 不花钱，验证 eval 本身

产物在 $LOOPBACK_HOME/evals/runs/<时间>-<套件>/：
    manifest.json  results.jsonl（逐次试验）  errors.jsonl（基础设施错误，不计分）
    summary.json   report.html   trials/<用例>-r<k>/（每次试验的完整 LOOPBACK_HOME）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from evals import scripted
from evals.budget import confirm_cost
from evals.cases import load_suite
from evals.harness import snapshot_materials
from evals.report import summarize_rows, write_report
from evals.scoring import score_trial
from loopback.agents import AgentSpec, load_prompt
from loopback.config import Settings, setup_logging
from loopback.curriculum import Curriculum
from loopback.library import Library
from loopback.llm import AnthropicLLM, sanitize_proxy_env
from loopback.tools import ToolError, ToolSet


def main(argv: list[str] | None = None) -> int:
    """解析参数，准备被测模型和评审，跑完全部试验并写报告。返回退出码。"""
    args = _parser().parse_args(argv)
    load_dotenv(override=False)
    sanitize_proxy_env(os.environ)
    env = {k: v for k, v in os.environ.items() if k != "LOOPBACK_HOME"}
    if args.model:
        env["MODEL_ID"] = args.model
    settings = Settings.from_env(
        {**env, "LOOPBACK_HOME": os.environ.get("LOOPBACK_HOME", "workspace")}
    )
    setup_logging(settings)  # 日志写文件，终端只留进度和结果
    curriculum = Curriculum.load()  # 只读公共课程：eval 结果不随个人课程变化（D23）
    cases = load_suite(args.suite, args.cases.split(",") if args.cases else None)
    cache = settings.home / "evals" / "cache"
    try:  # 1) 冻结材料快照：唯一需要联网抓材料的地方
        hashes = snapshot_materials(cases, curriculum, cache)
    except ToolError as e:
        print(f"材料快照失败（网络问题？稍后重试）：{e}", file=sys.stderr)
        return 1

    # 2) 被测模型与评审模型；评审和被测相同会有“自我偏好”，在报告里警告
    use_judge = not args.no_judge and not args.baseline
    judge_model = (
        args.judge_model
        or env.get("LOOPBACK_JUDGE_MODEL")
        or ("claude-sonnet-5-5" if settings.profile.official else settings.model)
    )
    warning = (
        "评审模型与被测模型相同，存在自我偏好风险"
        if use_judge and judge_model == settings.model
        else ""
    )
    if not args.baseline and not confirm_cost(
        settings.model, judge_model, len(cases) * args.reps, use_judge, args
    ):
        return 1
    sut = None if args.baseline else AnthropicLLM(settings)
    judge_llm = _judge_llm(env, judge_model) if use_judge else None

    run_dir = (
        settings.home
        / "evals"
        / "runs"
        / (
            f"{datetime.now():%Y%m%d-%H%M%S}-{args.suite}"
            + (f"-{args.baseline}" if args.baseline else "")
        )
    )
    run_dir.mkdir(parents=True)
    manifest = {
        "suite": args.suite,
        "model": settings.model if sut else f"scripted-{args.baseline}",
        "judge_model": judge_model if use_judge else "-",
        "reps": args.reps,
        "cases": [c.id for c in cases],
        "materials": hashes,
        "git": _git_version(),
        "prompt_hash": AgentSpec("teacher", load_prompt("teacher"), ToolSet([])).prompt_hash,
        "started": datetime.now().isoformat(timespec="seconds"),
        "warning": warning,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    # 3) 逐个试验：评分、评审、记账；超过预算或按 Ctrl-C 就停，已完成的照样汇总
    rows, errors, spent, total = [], [], 0.0, len(cases) * args.reps
    try:
        for case in cases:
            for rep in range(1, args.reps + 1):
                llm = sut or (
                    scripted.oracle(case, Library(cache, curriculum).get(case.item), curriculum)
                    if args.baseline == "oracle"
                    else scripted.null(case)
                )
                row = score_trial(
                    case, rep, run_dir, llm, env, curriculum, cache, judge_llm, judge_model
                )
                if "error" in row:
                    errors.append(row)
                    _append(run_dir / "errors.jsonl", row)
                    print(
                        f"[{len(rows) + len(errors)}/{total}] {case.id} r{rep} 基础设施错误："
                        f"{row['error']}"
                    )
                    continue
                rows.append(row)
                _append(run_dir / "results.jsonl", row)
                spent += row["cost_usd"] + row.get("judge_cost_usd", 0.0)
                cov = row["grades"].get("explain_coverage")
                print(
                    f"[{len(rows) + len(errors)}/{total}] {case.id} r{rep} "
                    f"{'✓' if row['grades']['pass'] else '✗'}"
                    + (f" 覆盖 {cov:.0%}" if cov is not None else "")
                    + f" · ${row['cost_usd'] + row.get('judge_cost_usd', 0.0):.3f}"
                    + f" · {row['latency_ms'] / 1000:.0f}s"
                )
                if spent > args.max_usd:
                    print(f"已花费 ${spent:.2f}，超过上限 ${args.max_usd}，停止")
                    raise StopIteration
    except KeyboardInterrupt, StopIteration:
        print("提前结束：只汇总已完成的试验")

    summary = summarize_rows(rows, len(cases), args.reps)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    report = write_report(run_dir, manifest, summary, rows, errors)
    p = summary["metrics"].get("pass", {})
    if p:
        print(
            f"\n通过率 {p['mean']:.0%}（95% 区间 {p['lo']:.0%}–{p['hi']:.0%}，n={p['n']}）"
            f" · 噪声底线 ±{summary['noise_floor']:.0%} · 花费 ${spent:.3f}"
        )
    print(f"报告：{report.as_uri()}")
    return 0


def _judge_llm(env: dict[str, str], judge_model: str) -> AnthropicLLM:
    """评审可以用另一家接口（LOOPBACK_JUDGE_BASE_URL / LOOPBACK_JUDGE_API_KEY），默认同被测。"""
    base = env.get("LOOPBACK_JUDGE_BASE_URL", env.get("ANTHROPIC_BASE_URL", ""))
    settings = Settings.from_env({**env, "MODEL_ID": judge_model, "ANTHROPIC_BASE_URL": base})
    return AnthropicLLM(settings, api_key=env.get("LOOPBACK_JUDGE_API_KEY"))


def _git_version() -> str:
    """当前代码版本：短 commit，有未提交改动时加 -dirty（结果要能对应到代码）。"""

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()

    return git("rev-parse", "--short", "HEAD") + ("-dirty" if git("status", "--porcelain") else "")


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evals.run", description="loopback evals")
    p.add_argument("--suite", default="teacher")
    p.add_argument("--cases", help="只跑这些用例（逗号分隔的 id）")
    p.add_argument("--reps", type=int, default=2, help="每个用例重复几次")
    p.add_argument("--baseline", choices=["oracle", "null"], help="不调模型的基线，用来验证 eval")
    p.add_argument("--model", help="被测模型（默认 MODEL_ID）")
    p.add_argument("--judge-model", help="评审模型（默认官方接口 claude-sonnet-5-5）")
    p.add_argument("--no-judge", action="store_true", help="只做代码评分")
    p.add_argument("--max-usd", type=float, default=5.0, help="花费上限，超过就停")
    p.add_argument("--yes", action="store_true", help="不询问，直接运行")
    return p


if __name__ == "__main__":
    sys.exit(main())
