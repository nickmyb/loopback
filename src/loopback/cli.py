"""命令行入口：`uv run loopback`。

M0 只做启动自检：读配置、建好个人状态目录、打开日志，再打印当前配置。
REPL 在 M1 加入。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from loopback import __version__
from loopback.config import ConfigError, Settings, setup_logging

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loopback", description="终端里的 agent 学习系统")
    parser.add_argument("--version", action="version", version=f"loopback {__version__}")
    parser.parse_args(argv)

    load_dotenv(override=False)  # 已经 export 的环境变量优先于 .env
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2

    settings.home.mkdir(parents=True, exist_ok=True)
    log_file = setup_logging(settings)
    log.info(
        "startup version=%s model=%s provider=%s", __version__, settings.model, settings.provider
    )

    print(f"loopback {__version__}")
    print(f"  模型      {settings.model}")
    print(f"  接口      {settings.provider}")
    print(f"  个人状态  {settings.home}")
    print(f"  日志      {log_file}")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        print("  提示：没有检测到 ANTHROPIC_API_KEY，请先 cp .env.example .env 并填写")
    return 0


if __name__ == "__main__":
    sys.exit(main())
