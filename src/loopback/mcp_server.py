"""Claude Code 前端：把 loopback 的学习工具做成一个 MCP server（stdio）。

    Claude Code (subscription login)            loopback mcp (this process)
      agent loop + /learn skill  ──tools/call──>  ToolSet.run() ──> curriculum/library/progress
                                 <── text result ──

- agent loop 由 Claude Code 提供，用量计入 Claude 订阅，不消耗 API 额度（docs/decisions.md D20）。
- 工具和我们自己的 REPL 用的是同一份 ToolSet，只是换了一个“前端”；适配层只做格式转换。
- stdio 协议独占 stdout：这里不能 print，日志一律写文件（setup_logging）。
"""

from __future__ import annotations

import logging
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from loopback import __version__
from loopback.config import Settings
from loopback.curriculum import Curriculum, Progress
from loopback.learning import next_step_tool, teacher_tools
from loopback.library import Library
from loopback.render import open_in_browser
from loopback.tools import ToolSet

log = logging.getLogger(__name__)

INSTRUCTIONS = (
    "loopback learning tools: curriculum, materials split into sections, and saved progress. "
    "Use them through the /learn skill: find_material to resolve titles to ids, "
    "next_step to know what to teach next, read_section to get original text."
)


def build_server(settings: Settings) -> Server[Any]:
    """装配 MCP server：加载课程、进度、材料库，把学习工具挂到 tools/list 和 tools/call 上。"""
    curriculum = Curriculum.load(home=settings.home)
    progress = Progress(settings.home)
    library = Library(settings.home, curriculum)
    opener = open_in_browser if settings.open_browser else (lambda _p: None)
    tools = ToolSet(
        [
            *teacher_tools(settings.home, curriculum, progress, library, opener),
            next_step_tool(curriculum, progress),
        ]
    )

    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        """把 ToolSet 的工具定义原样转成 MCP 的 Tool 列表（名字、描述、JSON Schema）。"""
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=s["name"], description=s["description"], input_schema=s["input_schema"]
                )
                for s in tools.specs()
            ]
        )

    async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        """执行一次工具调用：先重读进度（可能被另一个前端改过），再在线程里跑（抓取会阻塞）。"""
        progress.reload()
        args = dict(params.arguments or {})
        result = await anyio.to_thread.run_sync(tools.run, params.name, args)
        log.info("mcp tool %s error=%s", params.name, result.is_error)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result.content)],
            is_error=result.is_error,
        )

    return Server(
        "loopback",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def serve(settings: Settings) -> int:
    """以 stdio 方式运行，直到 Claude Code 关闭连接。"""
    server = build_server(settings)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    log.info("mcp server start home=%s", settings.home)
    anyio.run(run)
    return 0
