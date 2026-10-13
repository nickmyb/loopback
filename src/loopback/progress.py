"""学习进度（个人状态，在 $LOOPBACK_HOME，docs/decisions.md D6）：学到哪了、下一步做什么。

进度在 progress.json：每个条目的状态（todo / in_progress / done）、当前页、学完后的一句话总结，
外加一条按日期记的学习日志。每天新开一个会话时，就靠这份文件续上（演进清单 #19）。
学习者说 next 时，下一步由这里的代码算出来，不让模型自己猜（D9）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from loopback.curriculum import Curriculum, Item
from loopback.store import read_json, write_json
from loopback.tools import ToolError

PROGRESS_VERSION = 1


class Progress:
    def __init__(self, home: Path) -> None:
        self.path = home / "progress.json"
        self.reload()

    def reload(self) -> None:
        """从磁盘重新读取进度：另一个前端（REPL 或 Claude Code）可能刚更新过它。"""
        data = read_json(self.path, version=PROGRESS_VERSION) or {}
        self.items: dict[str, dict[str, Any]] = data.get("items", {})
        self.current: str | None = data.get("current")
        self.log: list[dict[str, Any]] = data.get("log", [])

    def state(self, item_id: str) -> dict[str, Any]:
        """某个条目的进度；还没学过的返回 todo。"""
        return self.items.get(item_id, {"status": "todo", "section": 0})

    def update(
        self,
        item_id: str,
        *,
        section: int | None = None,
        n_sections: int | None = None,
        done: bool = False,
        summary: str | None = None,
        today: date | None = None,
    ) -> dict:
        """更新进度并原子写盘：首次学习记为开始；可设当前页；done=True 时必须带一句话总结。"""
        day = (today or date.today()).isoformat()
        st = self.items.setdefault(item_id, {"status": "todo", "section": 0, "started": day})
        if st["status"] == "todo":
            st["status"] = "in_progress"
            self._log(day, item_id, "start")
        if n_sections is not None:
            st["n_sections"] = n_sections
        if section is not None:
            st["section"] = section
        if done:
            if not summary:
                raise ToolError("标记完成时必须给出一句话总结 summary")
            st.update(status="done", finished=day, summary=summary)
            self._log(day, item_id, "done")
        self.current = None if done else item_id
        write_json(
            self.path,
            {"items": self.items, "current": self.current, "log": self.log},
            version=PROGRESS_VERSION,
        )
        return st

    def suggestions(self, curriculum: Curriculum, k: int = 2) -> list[Item]:
        """先接着学正在学的，再按课程顺序往下排。"""
        ordered = sorted(
            curriculum.items, key=lambda i: self.state(i.id)["status"] != "in_progress"
        )
        return [i for i in ordered if self.state(i.id)["status"] != "done"][:k]

    def _log(self, day: str, item_id: str, event: str) -> None:
        """往学习日志追加一条记录（日期、条目、事件）。"""
        self.log.append({"date": day, "item": item_id, "event": event})


def status_text(curriculum: Curriculum, progress: Progress, today: date | None = None) -> str:
    """生成进度摘要：今天的日期、正在学的条目和页、接下来的建议、完成数。"""
    lines = [f"今天：{(today or date.today()).isoformat()}"]
    if progress.current:
        st, item = progress.state(progress.current), curriculum.by_id.get(progress.current)
        if item:
            lines.append(
                f"正在学：{item.label()} 第 {st['section']}/{st.get('n_sections', '?')} 页"
            )
    lines.append("建议接下来学（按课程顺序）：")
    lines += [f"- {i.label()}" for i in progress.suggestions(curriculum, k=3)]
    done = sum(1 for i in curriculum.items if progress.state(i.id)["status"] == "done")
    lines.append(f"已完成 {done} / {len(curriculum.items)}")
    return "\n".join(lines)


def next_message(curriculum: Curriculum, progress: Progress) -> str:
    """根据进度算出下一步要做什么，生成一条明确的指令。"""
    if progress.current is None:  # 没有正在学的：开始课程顺序里的下一篇
        upcoming = progress.suggestions(curriculum, k=1)
        if not upcoming:
            return "课程已经全部学完了，请帮我回顾一下学过的内容。"
        item = upcoming[0]
        return f"开始学习 [{item.id}] {item.title}：先调用 fetch_material，给我整体概览。"
    item, state = curriculum.get(progress.current), progress.state(progress.current)
    total, nxt = state.get("n_sections"), state["section"] + 1
    if total and nxt > total:  # 全部讲完：该做总结、标记完成了
        return f"[{item.id}] 的 {total} 页都学完了：请做总结，并调用 update_progress 标记完成。"
    return f"继续学习 [{item.id}] {item.title} 第 {nxt} 页：调用 read_section 讲解，讲完记录进度。"
