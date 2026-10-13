"""花费：开跑前按“典型用量”估算并请用户确认（真实花费以 API 返回的 usage 为准）。"""

from __future__ import annotations

from loopback.pricing import estimate_usd

# 估算花费用的“典型用量”（一次讲一页的试验 / 一次评审），实际花费以 API 返回的 usage 为准
TYPICAL_TRIAL = {
    "input_tokens": 3000,
    "cache_creation_input_tokens": 15000,
    "cache_read_input_tokens": 45000,
    "output_tokens": 7000,
}
TYPICAL_JUDGE = {"input_tokens": 6000, "output_tokens": 1500}


def confirm_cost(model: str, judge_model: str, n: int, use_judge: bool, args) -> bool:
    """打印预计花费并请用户确认（--yes 跳过）；无法估算时同样要求确认。"""
    per_trial = estimate_usd(model, TYPICAL_TRIAL)
    per_judge = estimate_usd(judge_model, TYPICAL_JUDGE) if use_judge else 0.0
    if per_trial is None or per_judge is None:
        msg = "（有模型不在价格表里，无法估算）"
    else:
        total = n * (per_trial + per_judge)
        msg = f"约 ${total:.2f}（被测 ${n * per_trial:.2f}，评审 ${n * per_judge:.2f}）"
    print(
        f"将运行 {n} 次试验 · 被测 {model} · 评审 {judge_model if use_judge else '无'}"
        f" · 预计花费 {msg} · 上限 ${args.max_usd}"
    )
    if args.yes:
        return True
    try:
        return input("继续？[y/N] ").strip().lower() == "y"
    except EOFError:
        return False
