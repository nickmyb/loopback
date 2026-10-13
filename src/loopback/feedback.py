"""学习者对每一页的打分（1 到 5）和一句话意见：以后的 evals 和自我进化的原始数据（D10）。

追加写入 $LOOPBACK_HOME/feedback.jsonl，一行一条，只追加。两个前端都能写：
REPL 在讲完一页后直接问；Claude Code 里由教师调用 record_feedback 工具。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from loopback.tools import Tool, ToolError


def record_feedback(
    home: Path, item_id: str, section: int, score: int, note: str = "", source: str = "repl"
) -> dict:
    """校验分数后追加一条反馈记录，返回写入的记录。"""
    if not 1 <= score <= 5:
        raise ToolError("score 必须是 1 到 5 的整数")
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "item_id": item_id,
        "section": section,
        "score": score,
        "note": note,
        "source": source,
    }
    home.mkdir(parents=True, exist_ok=True)
    with (home / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def feedback_tool(home: Path) -> Tool:
    """record_feedback：学习者说“这页 4 分”之类时，由教师记录下来。"""

    def record(item_id: str, section: int, score: int, note: str = "") -> str:
        record_feedback(home, item_id, section, score, note, source="agent")
        return f"已记录：{item_id} 第 {section} 页 {score} 分"

    return Tool(
        "record_feedback",
        "Record the learner's 1-5 rating (and optional short note) for a section they just "
        "studied. Call only when the learner gives a rating; never invent one.",
        {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "section": {"type": "integer"},
                "score": {"type": "integer", "minimum": 1, "maximum": 5},
                "note": {"type": "string"},
            },
            "required": ["item_id", "section", "score"],
        },
        record,
        read_only=False,
    )
