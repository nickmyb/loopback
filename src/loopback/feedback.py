"""反馈的记录：每页一个分、每篇一个分，外加一句话意见（D32）。evals 和自我进化的原始数据（D10）。

追加写入 $LOOPBACK_HOME/feedback.jsonl，一行一条，只追加。每条记下是哪一页（页标题 + 快照时间，
快照换了也能对上，D28）、在哪打的（前端、教师 prompt 的版本、模型）、由谁记的。
学习者怎么打分（next 4、/rate、next_step）在 rating.py；学习者直接对教师说分数时，
教师调用这里的 record_feedback 工具。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loopback.library import Library
from loopback.tools import Tool, ToolError

FEEDBACK_VERSION = 2  # 1：只有页级；2：加了 level、页标题、快照时间、前端、prompt 版本、模型


@dataclass(frozen=True)
class Origin:
    """一条反馈是在哪打的：哪个前端、教师 prompt 的哪个版本、哪个模型（拿不到就是 None）。"""

    front_end: str
    prompt_hash: str | None = None
    model: str | None = None


def record_feedback(
    home: Path,
    item_id: str,
    score: int,
    *,
    origin: Origin,
    source: str,
    level: str = "page",
    section: int | None = None,
    page_title: str | None = None,
    snapshot_at: str | None = None,
    note: str = "",
) -> dict:
    """校验后追加一条反馈（页级必须有页号，篇级不带页号），返回写入的记录。"""
    if not (isinstance(score, int) and 1 <= score <= 5) or level not in ("page", "article"):
        raise ToolError("score 必须是 1 到 5 的整数，level 只能是 page 或 article")
    if level == "page" and section is None:
        raise ToolError("给一页打分时要说明是第几页（section，0 是概览）")
    entry = {
        "version": FEEDBACK_VERSION,
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "item_id": item_id,
        "level": level,
        "section": section if level == "page" else None,
        "page_title": page_title,
        "snapshot_at": snapshot_at,
        "score": score,
        "note": note,
        "source": source,
        "front_end": origin.front_end,
        "prompt_hash": origin.prompt_hash,
        "model": origin.model,
    }
    home.mkdir(parents=True, exist_ok=True)
    with (home / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def rate_page(
    home: Path,
    library: Library,
    item_id: str,
    section: int,
    score: int,
    note: str,
    *,
    origin: Origin,
    source: str,
) -> str:
    """给某一页打分：页标题和快照时间从材料快照里取（0 是概览）。返回一句回执。"""
    m = library.get(item_id)
    if not 0 <= section <= len(m.sections):
        raise ToolError(f"section 必须在 0..{len(m.sections)}")
    title = "概览" if section == 0 else m.sections[section - 1].title
    record_feedback(
        home,
        item_id,
        score,
        origin=origin,
        source=source,
        section=section,
        page_title=title,
        snapshot_at=m.snapshot_at,
        note=note,
    )
    return f"已记录：{item_id} 第 {section} 页 {score} 分"


def feedback_tool(home: Path, library: Library, origin: Origin) -> Tool:
    """record_feedback：学习者直接说“这页 4 分”“这篇整体 3 分”时，由教师记下来。"""

    def record(
        item_id: str, score: int, level: str = "page", section: int | None = None, note: str = ""
    ) -> str:
        if level == "article":
            record_feedback(
                home, item_id, score, origin=origin, source="teacher", level="article", note=note
            )
            return f"已记录：{item_id} 整篇 {score} 分"
        if section is None:
            raise ToolError("给一页打分时要说明是第几页（section，0 是概览）")
        return rate_page(
            home, library, item_id, section, score, note, origin=origin, source="teacher"
        )

    return Tool(
        "record_feedback",
        "Record a 1-5 rating the learner gave, with an optional short note: level=page for one "
        "page (needs section; 0 = overview) or level=article for the whole item. Call only "
        "when the learner gives a rating; never invent one.",
        {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "score": {"type": "integer", "minimum": 1, "maximum": 5},
                "level": {"type": "string", "enum": ["page", "article"]},
                "section": {"type": "integer"},
                "note": {"type": "string"},
            },
            "required": ["item_id", "score"],
        },
        record,
        read_only=False,
    )
