"""课程表（公共内容，进 git）+ 学习进度（个人状态，在 $LOOPBACK_HOME，docs/decisions.md D6）。

课程表在 src/loopback/data/curriculum.yaml，加载时做校验：字段齐全、id 唯一、kind 合法。
个人想学的课外文章写在 $LOOPBACK_HOME/curriculum.local.yaml（格式相同，不进 git），
加载时追加在公共课程后面，id 不能和公共课程重复（D23）。
进度在 progress.json：每个条目的状态（todo / in_progress / done）、当前节、学完后的一句话总结，
外加一条按日期记的学习日志。每天新开一个会话时，就靠这份文件续上（演进清单 #19）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import date
from difflib import SequenceMatcher
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from loopback.store import read_json, write_json
from loopback.tools import ToolError

KINDS = {"doc", "blog", "research", "news", "paper", "report", "spec", "video", "repo"}
REQUIRED = ("id", "title", "url", "kind", "level", "group")
LOCAL_FILE = "curriculum.local.yaml"  # $LOOPBACK_HOME 下的个人课程（D23）
PROGRESS_VERSION = 1


def _norm(text: str) -> str:
    """统一成小写、去掉标点，方便做不区分大小写的模糊匹配。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text.lower()).strip()


class CurriculumError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    url: str
    kind: str
    level: str
    group: str
    date: str | None = None
    must: bool = False  # ⭐ 必读
    evals: bool = False  # 🧪 evals 主线

    def label(self) -> str:
        """一行展示：[id] 标题 + ⭐/🧪 标记 +（级别 · 分组 · 日期）。"""
        flags = ("⭐" if self.must else "") + ("🧪" if self.evals else "")
        when = f" · {self.date}" if self.date else ""
        return f"[{self.id}] {self.title}{flags}（{self.level} · {self.group}{when}）"


def _parse_items(text: str, source: str, seen: set[str]) -> list[Item]:
    """解析并校验一份课程表 YAML。seen 在多份文件间共用，保证合并后 id 仍然唯一；报错带上文件名。"""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:  # 手写的个人课程表最常见的错：标题里有冒号却没加引号
        raise CurriculumError(f"{source}: 不是合法的 YAML（含冒号的值要加引号）：{e}") from None
    if not isinstance(data, dict):
        raise CurriculumError(f"{source}: 顶层应该是 version 和 items 两个字段")
    items, known = [], {f.name for f in fields(Item)}
    for n, raw in enumerate(data.get("items") or [], 1):
        missing = [k for k in REQUIRED if not raw.get(k)] if isinstance(raw, dict) else REQUIRED
        if missing:
            raise CurriculumError(f"{source}: item #{n} 缺少字段：{', '.join(missing)}")
        if raw["id"] in seen:
            raise CurriculumError(f"{source}: 重复的 id：{raw['id']}")
        if raw["kind"] not in KINDS:
            raise CurriculumError(f"{source}: {raw['id']} 的 kind={raw['kind']!r} 不合法")
        if unknown := sorted(set(raw) - known):
            raise CurriculumError(f"{source}: {raw['id']} 有不认识的字段：{', '.join(unknown)}")
        url = str(raw["url"])
        if url.startswith("repo:"):  # 项目自学条目：仓库内的相对路径，不许 .. 和绝对路径
            if url[5:].startswith("/") or ".." in Path(url[5:]).parts:
                raise CurriculumError(f"{source}: {raw['id']} 的 repo 路径必须是仓库内的相对路径")
        elif not url.startswith(("https://", "http://")):
            raise CurriculumError(f"{source}: {raw['id']} 的 url 必须是 http(s) 或 repo:")
        seen.add(raw["id"])
        items.append(Item(**{k: (str(v) if k == "date" else v) for k, v in raw.items()}))
    return items


class Curriculum:
    def __init__(self, items: list[Item]) -> None:
        self.items = items
        self.by_id = {i.id: i for i in items}

    @classmethod
    def load(cls, path: Path | None = None, home: Path | None = None) -> Curriculum:
        """读取并校验课程表：先读公共课程表（默认是包内的 data/curriculum.yaml），
        给了 home 时，再把 $LOOPBACK_HOME/curriculum.local.yaml 的个人条目追加在后面（D23）。"""
        text = (
            path.read_text(encoding="utf-8")
            if path
            else resources.files("loopback").joinpath("data/curriculum.yaml").read_text("utf-8")
        )
        seen: set[str] = set()
        items = _parse_items(text, path.name if path else "curriculum.yaml", seen)
        local = home / LOCAL_FILE if home else None
        if local and local.exists():
            items += _parse_items(local.read_text(encoding="utf-8"), str(local), seen)
        return cls(items)

    def get(self, item_id: str) -> Item:
        """id 不存在时，错误信息直接给出最接近的候选，让模型一步改对，而不是乱猜。"""
        try:
            return self.by_id[item_id]
        except KeyError:
            hits = self.search(item_id, k=3)
            hint = "；最接近的是：" + "；".join(i.label() for i in hits) if hits else ""
            raise ToolError(
                f"课程里没有 id {item_id!r}{hint}。可以用 find_material 按标题搜索"
            ) from None

    def search(self, query: str, k: int = 5) -> list[Item]:
        """按 id、标题、分组做不区分大小写的匹配：先找整词包含，再用相似度兜底。"""
        q = _norm(query)
        if not q:
            return []
        scored = []
        for item in self.items:
            hay = _norm(f"{item.id} {item.title} {item.group}")
            words = q.split()
            if q in hay:
                score = 2.0
            elif all(w in hay for w in words):
                score = 1.5
            else:
                score = SequenceMatcher(None, q, _norm(item.title)).ratio()
            if score >= 0.6:
                scored.append((score, item))
        scored.sort(key=lambda x: -x[0])  # 稳定排序：同分时保持课程顺序
        return [item for _, item in scored[:k]]


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
        """更新进度并原子写盘：首次学习记为开始；可设当前节；done=True 时必须带一句话总结。"""
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
