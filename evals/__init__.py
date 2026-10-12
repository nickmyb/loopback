"""loopback 的 evals：度量“教师讲得好不好”，而且度量本身要可信（docs/decisions.md D10、D22）。

    uv run python -m evals.run --suite teacher --reps 2          # 真实评测（会花钱，先估算再确认）
    uv run python -m evals.run --suite teacher --baseline oracle # 不花钱：标准答案必须满分
    uv run python -m evals.run --suite teacher --baseline null   # 不花钱：空回答必须不及格

模块分工：
    cases.py    用例集（suites/*.yaml）的加载与校验
    harness.py  跑一次试验：独立的临时 LOOPBACK_HOME + 真实入口（teacher_tools + run_turn）
    graders.py  代码评分（确定性的检查）
    judge.py    LLM 评审（忠实度、大白话规则的原子检查）
    scripted.py oracle / null 基线用的“剧本 LLM”
    stats.py    置信区间与噪声底线
    report.py   summary.json 与 report.html（复用 trace.py 展示每次试验的轨迹）
    run.py      命令行：估算花费 -> 确认 -> 逐个试验 -> 汇总
    calibrate.py 评审与人工标注的一致率
"""
