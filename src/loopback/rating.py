"""打分的入口（D32）：学习者怎么打分、分数记到哪一页或哪一篇。REPL 和 MCP 共用。

- 每页：`next 4 太长了`。REPL 由 harness 解析；Claude Code 里由教师调用 next_step(rating=4)。
  分数记到刚学完的那一页。
- 每篇：REPL 用 `/rate 4 一句话`；也可以由教师调用 record_feedback(level=article)。
  分数记到正在学或刚学完的那一篇。
记录的格式和存储在 feedback.py。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from loopback.feedback import Origin, rate_page, record_feedback
from loopback.library import Library
from loopback.progress import Progress
from loopback.tools import ToolError

PAGE_HINT = "给这一页打分：下次输入 next 1-5，可以加一句，比如 next 4 太长了；直接 next 就跳过"
ARTICLE_HINT = "这篇学完了：输入 /rate 1-5 加一句话给整篇打分，比如 /rate 4 最有用的是第 3 页"
_NEXT = re.compile(r"(?:next|n)(?:\s+([1-5])(?:\s+(.*))?)?", re.S)
_RATE = re.compile(r"/rate\s+([1-5])(?:\s+(.*))?", re.S)


def parse_next(line: str) -> tuple[int | None, str] | None:
    """把 `next`、`n`、`next 4 太长了` 拆成（分数, 一句话）；不是 next 命令就返回 None。"""
    m = _NEXT.fullmatch(line.strip())
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else None), (m.group(2) or "").strip()


def parse_rate(line: str) -> tuple[int, str] | None:
    """把 `/rate 4 一句话` 拆成（分数, 一句话）；格式不对就返回 None。"""
    m = _RATE.fullmatch(line.strip())
    return (int(m.group(1)), (m.group(2) or "").strip()) if m else None


@dataclass(frozen=True)
class Rater:
    """一个前端里的记分员：带着个人目录、进度、材料库，以及记录里要写的“在哪打的、由谁记”。"""

    home: Path
    progress: Progress
    library: Library
    origin: Origin
    source: str  # 谁记的：repl（harness 解析 next 4）或 next_step（Claude Code）

    def page(self, score: int, note: str = "") -> str:
        """给刚学完的那一页打分（`next 4` 里的 4）；没有正在学的条目就报错。返回一句回执。"""
        item = self.progress.current
        if item is None:
            raise ToolError("现在没有正在学的条目，不用给页打分")
        section = self.progress.state(item)["section"]
        return rate_page(
            self.home,
            self.library,
            item,
            section,
            score,
            note,
            origin=self.origin,
            source=self.source,
        )

    def article(self, score: int, note: str = "") -> str:
        """给正在学或刚学完的那一篇打分；还没学过任何一篇就报错。返回一句回执。"""
        item = self.progress.latest()
        if item is None:
            raise ToolError("还没有学过任何一篇，没法打分")
        record_feedback(
            self.home,
            item,
            score,
            origin=self.origin,
            source=self.source,
            level="article",
            note=note,
        )
        return f"已记录：{item} 整篇 {score} 分"
