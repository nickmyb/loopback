"""运行配置：从环境变量读出一个只读的 Settings，并给出“能力档案”Profile。

- 配置只在启动时读一次，之后到处传同一个 Settings 对象，不在业务代码里零散地读 os.environ。
- Profile 决定 Claude 专属能力的开关（docs/decisions.md D7）：
  官方接口全部打开；兼容接口（DeepSeek 等）默认全部关闭，可以用环境变量逐项打开。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "high"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
OFFICIAL_HOSTS = ("api.anthropic.com",)


class ConfigError(ValueError):
    """配置不合法。启动时直接报给用户，不往下运行。"""


@dataclass(frozen=True)
class Profile:
    """当前接口支持哪些能力。"""

    official: bool  # Anthropic 官方接口：缓存参数、effort、fallback 等
    vision: bool  # 能读图片（文章里的原图）
    server_tools: bool  # 服务端工具，例如 web_search


@dataclass(frozen=True)
class Settings:
    model: str
    base_url: str | None
    home: Path  # 个人状态目录（docs/decisions.md D6）
    effort: str
    log_level: str
    profile: Profile

    @property
    def provider(self) -> str:
        if self.profile.official:
            return "Anthropic 官方"
        return urlparse(self.base_url).hostname or "?"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        base_url = env.get("ANTHROPIC_BASE_URL") or None
        official = base_url is None or urlparse(base_url).hostname in OFFICIAL_HOSTS
        profile = Profile(
            official=official,
            vision=_flag(env, "LOOPBACK_VISION", default=official),
            server_tools=_flag(env, "LOOPBACK_SERVER_TOOLS", default=official),
        )

        effort = env.get("LOOPBACK_EFFORT", DEFAULT_EFFORT).lower()
        if effort not in EFFORTS:
            raise ConfigError(f"LOOPBACK_EFFORT={effort!r} 不合法，可选值：{', '.join(EFFORTS)}")

        log_level = env.get("LOOPBACK_LOG_LEVEL", "INFO").upper()
        if not isinstance(logging.getLevelName(log_level), int):
            raise ConfigError(f"LOOPBACK_LOG_LEVEL={log_level!r} 不是合法的日志级别")

        return cls(
            model=env.get("MODEL_ID") or DEFAULT_MODEL,
            base_url=base_url,
            home=Path(env.get("LOOPBACK_HOME", "workspace")).expanduser().resolve(),
            effort=effort,
            log_level=log_level,
            profile=profile,
        )


def _flag(env: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    if raw.lower() in ("1", "true", "yes", "on"):
        return True
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name}={raw!r} 不合法，用 1/0、true/false")


def setup_logging(settings: Settings) -> Path:
    """日志写进文件，不写终端：终端留给学习对话。返回日志文件路径。"""
    log_dir = settings.home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "loopback.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    return log_file
