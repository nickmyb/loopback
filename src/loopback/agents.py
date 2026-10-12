"""角色 = AgentSpec：prompt 文件 + 工具集 + 运行参数（docs/decisions.md D2、D5）。

所有角色都交给同一个 agent_loop 运行。一个“新 agent”只是一份新的 AgentSpec。
prompt 放在 src/loopback/prompts/<name>.md，加载时计算 hash，写进每个 assistant 事件。
这样每一条 eval 分数、每一次进化记录，都能对应到某一个 prompt 版本。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from importlib import resources

from loopback.curriculum import Curriculum, Progress
from loopback.learning import learning_tools
from loopback.library import Library
from loopback.tools import ToolSet


@dataclass(frozen=True)
class AgentSpec:
    name: str
    system: str
    tools: ToolSet
    max_tokens: int = 64_000  # 流式请求可以给足，避免中途截断
    effort: str | None = None  # None = 用 settings.effort
    max_steps: int = 40  # 单次用户输入里最多调用模型的次数，防止失控循环
    prompt_hash: str = field(init=False)

    def __post_init__(self) -> None:
        digest = hashlib.sha256(self.system.encode()).hexdigest()[:12]
        object.__setattr__(self, "prompt_hash", digest)


def load_prompt(name: str) -> str:
    """读取 src/loopback/prompts/<name>.md 作为 system prompt。"""
    return resources.files("loopback.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")


def teacher(curriculum: Curriculum, progress: Progress, library: Library) -> AgentSpec:
    """任课教师（主会话）。只拿学习类工具，不给通用文件读写（最小权限，D8）。"""
    return AgentSpec(
        name="teacher",
        system=load_prompt("teacher"),
        tools=ToolSet(learning_tools(curriculum, progress, library)),
    )
