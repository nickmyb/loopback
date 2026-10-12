"""会话 = 只追加的事件日志；发给 API 的 messages 只是它的投影（docs/decisions.md D3）。

    events.jsonl  ──project()──>  [{"role": "user", ...}, {"role": "assistant", ...}, ...]

- 事件只追加、不修改、不删除。这样 preserved thinking 和 prompt 缓存要求的“历史前缀不变”天然成立。
- 投影是确定性的：同一串事件永远投影成同一串 messages。
- 相邻的同角色消息会合并（例如中断后补的 tool_result 后面紧跟用户的新输入）。
  tool_result 块排在合并后的消息最前面，这是 API 的要求。
- 不参与投影的事件（meta、turn_failed 等）只用于观测、eval 和反思。
- 撤回也是追加：一条用户输入的请求失败了（API 错误或 Ctrl-C），并且之后还没有任何回答，
  loop 就追加一个 turn_failed 事件，这条输入从此不进入投影，不会在下一轮被重复发出去。
  它之后从没产生过 thinking block，所以不跳过它也不会破坏 preserved thinking。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# 事件类型 -> 投影成的消息角色；不在表里的事件不进入 messages
_ROLE_OF = {"user": "user", "assistant": "assistant", "tool_results": "user"}


class Session:
    def __init__(self, path: Path, events: list[dict[str, Any]] | None = None) -> None:
        self.path = path
        self.events: list[dict[str, Any]] = events or []

    @classmethod
    def open(cls, path: Path) -> Session:
        """打开（或新建）一个会话。日志末尾如果有写了一半的行（进程崩溃导致），丢弃它。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        events: list[dict[str, Any]] = []
        if path.exists():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("skip corrupt event line %s:%d", path, lineno)
        return cls(path, events)

    def append(self, type_: str, **data: Any) -> dict[str, Any]:
        """追加一个事件：带上版本号和时间戳，写一行 JSON 并 fsync，确认落盘后才返回。"""
        event = {"v": SCHEMA_VERSION, "type": type_, "ts": datetime.now(UTC).isoformat(), **data}
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.events.append(event)
        return event

    def messages(self) -> list[dict[str, Any]]:
        """把事件日志投影成 Messages API 的 messages 参数。"""
        out: list[dict[str, Any]] = []
        retracted = _retracted_user_events(self.events)
        for i, ev in enumerate(self.events):
            role = _ROLE_OF.get(ev["type"])
            if role is None or i in retracted:
                continue
            blocks = _blocks_of(ev)
            if out and out[-1]["role"] == role:
                merged = out[-1]["content"] + blocks
                if role == "user":  # tool_result 必须排在同一条 user 消息的最前面（稳定排序）
                    merged.sort(key=lambda b: b.get("type") != "tool_result")
                out[-1] = {"role": role, "content": merged}
            else:
                out.append({"role": role, "content": blocks})
        return out

    def pending_tool_use_ids(self) -> list[str]:
        """最后一条 assistant 消息里还没有配上 tool_result 的 tool_use id（应当永远为空）。"""
        msgs = self.messages()
        if not msgs or msgs[-1]["role"] != "assistant":
            return []
        return [b["id"] for b in msgs[-1]["content"] if b.get("type") == "tool_use"]

    def usage_totals(self) -> dict[str, int]:
        """累加所有 assistant 事件的 token 用量（只统计整数字段）。"""
        totals: dict[str, int] = {}
        for ev in self.events:
            if ev["type"] == "assistant":
                for k, v in (ev.get("usage") or {}).items():
                    if isinstance(v, int):
                        totals[k] = totals.get(k, 0) + v
        return totals


def _retracted_user_events(events: list[dict[str, Any]]) -> set[int]:
    """找出“请求失败且尚未得到任何回答”的 user 事件下标。"""
    retracted: set[int] = set()
    unanswered: list[int] = []
    for i, ev in enumerate(events):
        if ev["type"] == "user":
            unanswered.append(i)
        elif ev["type"] == "assistant":
            unanswered.clear()
        elif ev["type"] == "turn_failed":
            retracted.update(unanswered)
            unanswered.clear()
    return retracted


def _blocks_of(ev: dict[str, Any]) -> list[dict[str, Any]]:
    """把一个事件转成消息内容块：tool_results 取出结果块；字符串输入包成 text 块。"""
    if ev["type"] == "tool_results":
        return list(ev["results"])
    content = ev["content"]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)
