"""工具注册表：模型发出 tool_use，harness 在这里校验、执行、包装成 tool_result。

设计要点
- 工具是“确定性系统与非确定性 agent 之间的契约”（演进清单 #13），schema 和描述都要认真写。
- 每次调用都会返回一个结果，绝不抛异常给 loop。
  原因：每个 tool_use 都必须有 tool_result（CLAUDE.md 不变量 2）。
- 出错的结果同时做两件事：设置 is_error，并在正文前加 "ERROR: "。
  DeepSeek 等兼容接口会忽略 is_error，所以正文里也要写明。
- specs() 按名字排序，保证工具列表的字节稳定，prompt 缓存才能命中。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 50_000
_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ToolError(Exception):
    """工具预期内的失败（参数不对、文件不存在……）。消息会原样反馈给模型，让它自己修正。"""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., str]
    read_only: bool = True

    def spec(self) -> dict[str, Any]:
        """这个工具交给 API 的定义：name、description、input_schema。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False

    def block(self, tool_use_id: str) -> dict[str, Any]:
        """转成 tool_result 块；只有出错时才带 is_error。"""
        b: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": self.content,
        }
        if self.is_error:
            b["is_error"] = True
        return b


def error(message: str) -> ToolResult:
    """构造一个错误结果：is_error=True，并且正文以 "ERROR: " 开头。"""
    return ToolResult(f"ERROR: {message}", is_error=True)


class ToolSet:
    """一个 agent 能用的全部工具。会话开始时确定，中途不增减（CLAUDE.md 不变量 3）。"""

    def __init__(self, tools: Iterable[Tool]) -> None:
        self._tools = {t.name: t for t in sorted(tools, key=lambda t: t.name)}

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    @property
    def names(self) -> list[str]:
        """全部工具名（已按名字排序）。"""
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        """全部工具定义，按名字排序，保证每次请求字节一致、prompt 缓存能命中。"""
        return [t.spec() for t in self._tools.values()]

    def run(self, name: str, args: Any) -> ToolResult:
        """执行一次工具调用。

        未知工具、参数不合法、预期内失败、代码崩溃，都变成错误结果返回，从不抛异常。
        """
        # 1) 工具存在吗？不存在就把可用工具列出来，让模型自己改
        tool = self._tools.get(name)
        if tool is None:
            return error(f"unknown tool {name!r}; available: {', '.join(self._tools)}")
        # 2) 参数符合 schema 吗？不符合就说清楚哪里不对
        problem = validate(tool.input_schema, args)
        if problem:
            return error(f"invalid input for {name}: {problem}")
        # 3) 执行：ToolError 是预期内失败（原样告诉模型）；其他异常是工具的 bug（记日志）
        try:
            out = tool.handler(**args)
        except ToolError as e:
            return error(str(e))
        except Exception as e:  # 工具实现的 bug：记日志，同时告诉模型，loop 不中断
            log.exception("tool %s crashed", name)
            return error(f"internal error in {name}: {type(e).__name__}: {e}")
        return ToolResult(_truncate(out if isinstance(out, str) else json.dumps(out)))


def validate(schema: dict[str, Any], args: Any) -> str | None:
    """最小的 JSON Schema 校验：顶层的 required 和基本类型。完整校验放到后补项。"""
    if not isinstance(args, dict):
        return "input must be a JSON object"
    props: dict[str, Any] = schema.get("properties", {})
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    for key, value in args.items():
        if key not in props:
            if schema.get("additionalProperties") is False:
                return f"unexpected field {key!r}"
            continue
        expected = _JSON_TYPES.get(props[key].get("type", ""))
        if expected and (not isinstance(value, expected) or _is_bool_for_number(value, expected)):
            return f"field {key!r} must be {props[key]['type']}"
    return None


def _is_bool_for_number(value: Any, expected: type | tuple[type, ...]) -> bool:
    """Python 里 bool 是 int 的子类；这里挡住用 true/false 冒充数字的输入。"""
    return isinstance(value, bool) and expected is not bool


def _truncate(text: str) -> str:
    """工具输出过长时截断，并注明截掉了多少字符，避免撑爆上下文。"""
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + f"\n...[truncated {len(text) - MAX_RESULT_CHARS} chars]"
