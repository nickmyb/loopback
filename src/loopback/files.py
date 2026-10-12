"""限定在个人状态目录里的文件工具（docs/decisions.md D8：最小权限，不提供 bash）。

模型给出的 path 是不可信输入：先 resolve，再确认仍在根目录之内。
这一步同时挡住了 `..`、绝对路径和指向外面的符号链接。
"""

from __future__ import annotations

from pathlib import Path

from loopback.tools import Tool, ToolError

MAX_READ_CHARS = 100_000


def confine(root: Path, path: str) -> Path:
    root = root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ToolError(f"path {path!r} is outside the workspace")
    return target


def workspace_tools(root: Path, *, writable: bool) -> list[Tool]:
    def read_file(path: str) -> str:
        target = confine(root, path)
        if not target.is_file():
            raise ToolError(f"no such file: {path}")
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:MAX_READ_CHARS]

    def list_files(path: str = ".") -> str:
        target = confine(root, path)
        if not target.is_dir():
            raise ToolError(f"no such directory: {path}")
        entries = sorted(p.relative_to(root.resolve()).as_posix() for p in target.iterdir())
        return "\n".join(entries) or "(empty)"

    def write_file(path: str, content: str) -> str:
        target = confine(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)  # 原子写
        return f"wrote {len(content)} chars to {path}"

    path_prop = {"type": "string", "description": "Path relative to the workspace root."}
    tools = [
        Tool(
            "read_file",
            "Read a UTF-8 text file from the learner's workspace.",
            {"type": "object", "properties": {"path": path_prop}, "required": ["path"]},
            read_file,
        ),
        Tool(
            "list_files",
            "List entries of a directory in the learner's workspace.",
            {"type": "object", "properties": {"path": path_prop}},
            list_files,
        ),
    ]
    if writable:
        tools.append(
            Tool(
                "write_file",
                "Create or overwrite a UTF-8 text file in the learner's workspace.",
                {
                    "type": "object",
                    "properties": {"path": path_prop, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
                write_file,
                read_only=False,
            )
        )
    return tools
