"""汇总与报告：summary.json（机器读）和 report.html（人读）。

报告里的每个数字都能从 results.jsonl 的逐行结果重新算出来（eval-audit §5）；
每次试验都附完整轨迹（复用 trace.py）和生成的课件链接，分数可疑时直接点开看发生了什么。
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from statistics import median
from typing import Any

from evals.stats import noise_floor, summarize
from loopback.pricing import cache_hit_rate
from loopback.trace import build_trace, render_text


def summarize_rows(rows: list[dict[str, Any]], n_cases: int, reps: int) -> dict[str, Any]:
    """按指标汇总：均值 + 95% 区间；另附噪声底线、花费、耗时、缓存命中率。"""
    metrics: dict[str, list] = {}
    for row in rows:
        for k, v in {**row["grades"], **row.get("judge", {})}.items():
            if isinstance(v, bool | int | float):
                metrics.setdefault(k, []).append(v)
    usage: dict[str, int] = {}
    for row in rows:
        for k, v in row["usage"].items():
            usage[k] = usage.get(k, 0) + v
    return {
        "trials": len(rows),
        "metrics": {k: summarize(v) for k, v in sorted(metrics.items())},
        "noise_floor": noise_floor(n_cases, reps),
        "cost_usd": {
            "sut": sum(r["cost_usd"] for r in rows),
            "judge": sum(r.get("judge_cost_usd", 0.0) for r in rows),
        },
        "latency_ms_median": median([r["latency_ms"] for r in rows]) if rows else 0,
        "cache_hit_rate": cache_hit_rate(usage),
    }


def write_report(
    run_dir: Path, manifest: dict, summary: dict, rows: list[dict], errors: list[dict]
) -> Path:
    """写 report.html：运行信息、指标表（含区间）、逐题结果、每次试验的轨迹与课件链接。"""
    m = summary["metrics"]
    metric_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v['mean']:.2f}</td>"
        f"<td>[{v['lo']:.2f}, {v['hi']:.2f}]</td><td>{v['n']}</td></tr>"
        for k, v in m.items()
    )
    trials = "".join(_trial_html(run_dir, r) for r in rows)
    errs = (
        "".join(
            f"<li>{html.escape(e['case'])} r{e['rep']}：{html.escape(e['error'])}</li>"
            for e in errors
        )
        or "<li>无</li>"
    )
    cost = summary["cost_usd"]
    info = (
        f"套件 {manifest['suite']} · 被测模型 {manifest['model']} · 评审 {manifest['judge_model']}"
        f" · {manifest['reps']} 次重复 · prompt {manifest['prompt_hash']}"
        f" · 代码 {manifest['git']} · 材料快照 {manifest['materials']}"
    )
    warn = (
        f"<p class='warn'>⚠ {html.escape(manifest['warning'])}</p>"
        if manifest.get("warning")
        else ""
    )
    body = f"""<h1>loopback eval · {html.escape(manifest["suite"])}</h1>
<p class="muted">{html.escape(info)}</p>{warn}
<p>试验 {summary["trials"]} 次 · 噪声底线 ≈ ±{summary["noise_floor"]:.2f}（小于它的差异不下结论）
· 花费 被测 ${cost["sut"]:.3f} / 评审 ${cost["judge"]:.3f}
· 中位耗时 {summary["latency_ms_median"] / 1000:.1f}s
· 缓存命中率 {summary["cache_hit_rate"]:.0%}</p>
<h2>指标（均值与 95% 区间）</h2>
<table><tr><th>指标</th><th>均值</th><th>95% 区间</th><th>n</th></tr>{metric_rows}</table>
<h2>基础设施错误（不计分）</h2><ul>{errs}</ul>
<h2>逐次试验</h2>{trials}"""
    path = run_dir / "report.html"
    path.write_text(_PAGE.replace("{{BODY}}", body), encoding="utf-8")
    return path


def _trial_html(run_dir: Path, row: dict) -> str:
    """一次试验：评分一览 + 可展开的完整轨迹 + 课件链接。"""
    home = run_dir / "trials" / f"{row['case']}-r{row['rep']}"
    marks = " ".join(
        f"{'✓' if v else '✗'} {k}" for k, v in row["grades"].items() if isinstance(v, bool)
    )
    judged = " ".join(
        f"{k}={v:.2f}" if isinstance(v, float) else f"{'✓' if v else '✗'} {k}"
        for k, v in row.get("judge", {}).items()
    )
    events = [
        json.loads(line)
        for line in (home / "sessions" / "trial.jsonl").read_text("utf-8").splitlines()
        if line
    ]
    links = " ".join(
        f'<a href="{p.relative_to(run_dir).as_posix()}">{p.name}</a>'
        for p in sorted((home / "lessons").glob("*/*.html"))
    )
    status = "pass" if row["grades"].get("pass") else "fail"
    return (
        f'<details class="{status}"><summary>{"✅" if status == "pass" else "❌"} '
        f"{html.escape(row['case'])} r{row['rep']} · {row['latency_ms'] / 1000:.1f}s · "
        f"${row['cost_usd']:.3f}</summary><p>{html.escape(marks)}</p><p>{html.escape(judged)}"
        f"</p><p>课件：{links or '无'}</p><pre>{html.escape(render_text(build_trace(events)))}"
        "</pre></details>"
    )


_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>loopback eval</title>
<style>
:root { --bg:#fbfaf7; --text:#1f2328; --muted:#6b7280; --line:#e6e2d8; --bad:#b91c1c; }
@media (prefers-color-scheme: dark) { :root { --bg:#16171a; --text:#e6e6e6; --muted:#9aa0a6;
  --line:#2e3036; --bad:#f87171; } }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.6 system-ui,
  "Noto Sans CJK SC", sans-serif; } main { max-width:1100px; margin:0 auto; padding:24px 16px; }
table { border-collapse:collapse; } td, th { border:1px solid var(--line); padding:4px 10px; }
.muted { color:var(--muted); } .warn { color:var(--bad); }
details { border:1px solid var(--line); border-radius:8px; padding:6px 12px; margin:8px 0; }
details.fail summary { color:var(--bad); } pre { white-space:pre-wrap; font-size:12px; }
</style></head><body><main>{{BODY}}</main></body></html>"""
