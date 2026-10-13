"""材料库：每篇材料第一次读取时切好页，冻结成快照，之后一直读快照（D28）。

    library/<id>/source.md       网页提取出的 markdown 正文
                                 （也可以手动放一份，比如需要登录才能看的 PDF）
    library/<id>/sections.json   快照：切好的页，另记 source_hash、split_version、snapshot_at

- get：有快照就读快照，没有就先建一份。学到一半时原文改了，页号也不会跟着变。
- refresh：按最新的原文和当前的切页规则重建快照。什么时候重建，由 fetch_material 决定。
- 项目文件（repo:）的原文就是仓库里的文件；网页材料重建时用已存的 source.md，不重新下载。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loopback.curriculum import Curriculum, Item
from loopback.extract import extract
from loopback.fetch import FetchResult, download, http_fetch
from loopback.materials import (
    SPLIT_VERSION,
    Section,
    sections_from_json,
    sections_to_json,
    split_sections,
)
from loopback.repo import repo_file, repo_split
from loopback.store import read_json, write_json
from loopback.tools import ToolError

LIBRARY_VERSION = 1  # 快照新加的字段都可以缺省，旧快照照样能读，所以不用升版本


@dataclass(frozen=True)
class Material:
    item_id: str
    title: str
    url: str
    date: str | None
    sections: list[Section]
    split_version: int = 1  # 快照用的是哪一版切页规则；旧快照没记，按 1 算
    snapshot_at: str | None = None
    stale: bool = False  # 原文在快照之后改过


class Library:
    def __init__(
        self, home: Path, curriculum: Curriculum, fetch: Callable[[str], FetchResult] = http_fetch
    ) -> None:
        self.root = home / "library"
        self.curriculum = curriculum
        self._fetch = fetch

    def get(self, item_id: str) -> Material:
        """读这篇材料的快照；还没有快照就先建一份。"""
        return self._load(item_id) or self.refresh(item_id)

    def refresh(self, item_id: str) -> Material:
        """按最新的原文和当前的切页规则重建快照。"""
        item = self.curriculum.get(item_id)
        old = read_json(self._snapshot(item_id), version=LIBRARY_VERSION) or {}
        text, found_date = self._source(item)
        sections = _split(item, text)
        if not sections:
            manual = self.root / item_id / "source.md"
            raise ToolError(f"{item_id} 没有提取到正文。可以手动把正文保存为 {manual}")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        date = item.date or found_date or old.get("date")  # 重切时不丢掉第一次抓取时找到的日期
        snapshot = {
            "item_id": item_id,
            "title": item.title,
            "url": item.url,
            "date": date,
            "snapshot_at": now,
            "source_hash": _hash(text),
            "split_version": SPLIT_VERSION,
            "sections": sections_to_json(sections),
        }
        write_json(self._snapshot(item_id), snapshot, version=LIBRARY_VERSION)
        return Material(item_id, item.title, item.url, date, sections, SPLIT_VERSION, now)

    def _load(self, item_id: str) -> Material | None:
        """读已有的快照，并看看原文在快照之后有没有改过。"""
        data = read_json(self._snapshot(item_id), version=LIBRARY_VERSION)
        if not data:
            return None
        known, current = data.get("source_hash"), self._current(self.curriculum.get(item_id))
        return Material(
            item_id,
            data["title"],
            data["url"],
            data.get("date"),
            sections_from_json(data["sections"]),
            data.get("split_version", 1),
            data.get("snapshot_at") or data.get("fetched_at"),
            stale=bool(known and current is not None and _hash(current) != known),
        )

    def _source(self, item: Item) -> tuple[str, str | None]:
        """取最新的原文和日期：项目文件读仓库；网页材料用已存的 source.md，没有才联网抓。"""
        if item.url.startswith("repo:"):
            return repo_file(item.url).read_text(encoding="utf-8"), None
        manual = self.root / item.id / "source.md"
        if manual.exists():
            return manual.read_text(encoding="utf-8"), None
        got = download(self._fetch, item.url)
        if "pdf" in got.content_type:
            raise ToolError(f"{item.id} 是 PDF，暂不支持自动提取。请把正文另存为 {manual}")
        ex = extract(got.body, got.url, got.content_type)
        manual.parent.mkdir(parents=True, exist_ok=True)
        manual.write_text(ex.markdown, encoding="utf-8")
        return ex.markdown, ex.date

    def _current(self, item: Item) -> str | None:
        """原文现在的内容，用来判断快照是否过时；读不到就返回 None（不算过时）。"""
        try:
            if item.url.startswith("repo:"):
                return repo_file(item.url).read_text(encoding="utf-8")
            manual = self.root / item.id / "source.md"
            return manual.read_text(encoding="utf-8") if manual.exists() else None
        except ToolError, OSError:
            return None

    def _snapshot(self, item_id: str) -> Path:
        return self.root / item_id / "sections.json"


def same_page(old: Material, new: Material, index: int) -> int:
    """快照重建后，把旧快照的第 index 页对到新快照里同标题的页；找不到就保留页号。"""
    if 1 <= index <= len(old.sections):
        title = old.sections[index - 1].title
        for s in new.sections:
            if s.title == title:
                return s.index
    return min(index, len(new.sections))


def _split(item: Item, text: str) -> list[Section]:
    """项目文件交给 repo_split（.py 按函数和类切），其余按 markdown 切页。"""
    if item.url.startswith("repo:"):
        return repo_split(item.url, text, item.title)
    return split_sections(text, item.url, item.title)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
