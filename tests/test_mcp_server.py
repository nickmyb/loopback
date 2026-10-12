"""Claude Code 前端：MCP server 暴露的工具和 REPL 教师用的是同一份 ToolSet。

用 mcp SDK 自带的进程内 Client 测：走完整的 MCP 协议，但不起子进程、不联网、不调模型。
"""

from pathlib import Path

import anyio
from mcp import Client

from loopback.config import Settings
from loopback.curriculum import Progress
from loopback.mcp_server import build_server


def call(home: Path, steps):
    """起一个 server，按顺序执行 steps（每步是 client -> awaitable），返回各步结果。"""

    async def main():
        env = {"LOOPBACK_HOME": str(home), "LOOPBACK_OPEN_BROWSER": "0"}
        server = build_server(Settings.from_env(env))
        async with Client(server) as client:
            return [await step(client) for step in steps]

    return anyio.run(main)


def test_lists_the_teacher_tools_plus_next_step(tmp_path: Path) -> None:
    [tools] = call(tmp_path, [lambda c: c.list_tools()])
    names = sorted(t.name for t in tools.tools)
    assert names == [
        "curriculum_status",
        "fetch_material",
        "find_material",
        "next_step",
        "read_section",
        "record_feedback",
        "render_lesson",
        "update_progress",
    ]
    find = next(t for t in tools.tools if t.name == "find_material")
    assert find.input_schema["required"] == ["query"]


def test_project_material_round_trip_over_mcp(tmp_path: Path) -> None:
    found, outline, section, progress, nxt = call(
        tmp_path,
        [
            lambda c: c.call_tool("find_material", {"query": "loop.py"}),
            lambda c: c.call_tool("fetch_material", {"item_id": "repo-loop"}),
            lambda c: c.call_tool("read_section", {"item_id": "repo-loop", "index": 1}),
            lambda c: c.call_tool("update_progress", {"item_id": "repo-loop", "section": 1}),
            lambda c: c.call_tool("next_step", {}),
        ],
    )
    text = [r.content[0].text for r in (found, outline, section, progress, nxt)]
    assert "[repo-loop]" in text[0]
    assert "模块说明与导入" in text[1]
    assert text[2].startswith('<material item="repo-loop" section="1/')
    assert "第 2 节" in text[4]
    assert Progress(tmp_path).state("repo-loop")["section"] == 1  # 进度真的写盘了


def test_tool_errors_are_flagged_not_raised(tmp_path: Path) -> None:
    [bad] = call(tmp_path, [lambda c: c.call_tool("fetch_material", {"item_id": "nope"})])
    assert bad.is_error and bad.content[0].text.startswith("ERROR:")


def test_progress_written_by_another_front_end_is_picked_up(tmp_path: Path) -> None:
    async def other_front_end_writes(client):
        Progress(tmp_path).update("repo-plan", section=0, n_sections=3)  # 比如 REPL 刚写过
        return await client.call_tool("next_step", {})

    [nxt] = call(tmp_path, [other_front_end_writes])
    assert "[repo-plan]" in nxt.content[0].text and "第 1 节" in nxt.content[0].text
