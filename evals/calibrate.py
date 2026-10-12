"""评审校准：LLM 评审的结论要和人工判断对得上（eval-audit §4：一致率 ≥90% 才能用来指导改动）。

    uv run python -m evals.calibrate export <run_dir> [--n 30]   # 导出 labels.csv，人工填 human 列
    uv run python -m evals.calibrate score  <run_dir>/labels.csv # 计算一致率和混淆矩阵

人工标注时只看“原文”和“讲解”两列，先不看 judge 列，避免被评审的结论带偏。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

FIELDS = ["id", "case", "rep", "para", "human", "judge", "original", "explanation"]
TARGET = 0.90


def export(run_dir: Path, n: int) -> Path:
    """把 results.jsonl 里评审过的逐段对照项（前 n 条，顺序稳定）写成 labels.csv。"""
    rows = [json.loads(x) for x in (run_dir / "results.jsonl").read_text("utf-8").splitlines() if x]
    items = [(r, i) for r in rows for i in r.get("judge_items", [])][:n]
    path = run_dir / "labels.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k, (r, i) in enumerate(items, 1):
            w.writerow(
                {
                    "id": k,
                    "case": r["case"],
                    "rep": r["rep"],
                    "para": i["para"],
                    "human": "",
                    "judge": int(bool(i.get("judge_faithful"))),
                    "original": i["original"],
                    "explanation": i["explanation"],
                }
            )
    return path


def score(path: Path) -> dict[str, float | int]:
    """读取人工标注（human 列填 1/0），算评审与人工的一致率和混淆矩阵。"""
    with path.open(encoding="utf-8") as f:
        labeled = [r for r in csv.DictReader(f) if r["human"].strip() in ("0", "1")]
    pairs = [(int(r["judge"]), int(r["human"])) for r in labeled]
    agree = sum(j == h for j, h in pairs)
    return {
        "labeled": len(pairs),
        "agreement": agree / len(pairs) if pairs else 0.0,
        "judge_yes_human_no": sum(j == 1 and h == 0 for j, h in pairs),  # 评审放过了不忠实的讲解
        "judge_no_human_yes": sum(j == 0 and h == 1 for j, h in pairs),  # 评审冤枉了忠实的讲解
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evals.calibrate")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("run_dir", type=Path)
    e.add_argument("--n", type=int, default=30)
    s = sub.add_parser("score")
    s.add_argument("labels", type=Path)
    args = p.parse_args(argv)
    if args.cmd == "export":
        print(f"已导出：{export(args.run_dir, args.n)}（在 human 列填 1=忠实 / 0=不忠实）")
        return 0
    result = score(args.labels)
    ok = result["labeled"] > 0 and result["agreement"] >= TARGET
    print(
        f"标注 {result['labeled']} 条 · 一致率 {result['agreement']:.0%}（要求 ≥{TARGET:.0%}）"
        f" · 评审放过 {result['judge_yes_human_no']} · 评审冤枉 {result['judge_no_human_yes']}"
        f" → {'评审可信' if ok else '评审需要改进后再用'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
