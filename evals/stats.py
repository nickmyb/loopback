"""统计：每个指标给出均值和 95% 置信区间，并给出“噪声底线”。

- 0/1 指标（通过与否）用 Wilson 区间：样本少、比例接近 0 或 1 时也不会越界。
- 连续指标（如覆盖率、忠实度比例）用正态近似：均值 ± 1.96 · 标准差 / √n。
- 噪声底线 ≈ 1/√(n·R)：两次运行的差异小于它时，不足以说明谁更好（eval-audit §5）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Z = 1.96


def wilson(successes: int, n: int) -> tuple[float, float]:
    """二项比例的 Wilson 95% 区间。"""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def summarize(values: Sequence[float | bool]) -> dict[str, float]:
    """一个指标的 n、均值、95% 区间；全是 0/1 时用 Wilson，否则用正态近似。"""
    xs = [float(v) for v in values]
    n = len(xs)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    mean = sum(xs) / n
    if all(x in (0.0, 1.0) for x in xs):
        lo, hi = wilson(int(sum(xs)), n)
    else:
        var = sum((x - mean) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
        half = Z * math.sqrt(var / n)
        lo, hi = mean - half, mean + half
    return {"n": n, "mean": mean, "lo": lo, "hi": hi}


def noise_floor(n_cases: int, reps: int) -> float:
    """通过率这类指标的大致噪声底线：1/√(n·R)。"""
    return 1 / math.sqrt(max(n_cases * reps, 1))
