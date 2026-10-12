"""命令行入口。

    uv run loopback                    开始学习（REPL）
    uv run loopback trace [文件] [--last N]   查看会话轨迹，默认最近一次会话；不调用模型
    uv run loopback --version

这里只做“启动装配”：读配置、准备目录和日志、加载课程，然后把对象交给 repl 或 trace。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from loopback import __version__, agents, repl
from loopback.config import ConfigError, Settings, setup_logging
from loopback.curriculum import Curriculum, CurriculumError, Progress
from loopback.library import Library
from loopback.llm import AnthropicLLM, sanitize_proxy_env
from loopback.session import Session
from loopback.trace import build_trace, latest_session, load_events, render_text

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """解析命令行，分派到“学习”或“查看轨迹”。返回进程退出码。"""
    parser = argparse.ArgumentParser(prog="loopback", description="终端里的 agent 学习系统")
    parser.add_argument("--version", action="version", version=f"loopback {__version__}")
    sub = parser.add_subparsers(dest="command")
    trace_p = sub.add_parser("trace", help="查看会话轨迹（默认最近一次会话）")
    trace_p.add_argument("path", nargs="?", type=Path, help="会话事件日志 .jsonl")
    trace_p.add_argument("--last", type=int, help="只看最近 N 轮")
    args = parser.parse_args(argv)

    load_dotenv(override=False)  # 已经 export 的环境变量优先于 .env
    try:
        settings = Settings.from_env()
    except ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2
    if args.command == "trace":
        return show_trace(settings, args.path, args.last)
    return learn(settings)


def show_trace(settings: Settings, path: Path | None, last: int | None) -> int:
    """打印一次会话的轨迹时间线：只读日志，不需要 API key。"""
    path = path or latest_session(settings.home)
    if path is None or not path.exists():
        print(f"没有找到会话日志（{settings.home / 'sessions'}）", file=sys.stderr)
        return 1
    print(f"轨迹：{path}")
    print(render_text(build_trace(load_events(path)), last=last))
    return 0


def learn(settings: Settings) -> int:
    """装配一次学习会话：日志、课程、进度、材料库、教师，然后进入 REPL。"""
    settings.home.mkdir(parents=True, exist_ok=True)
    dropped = sanitize_proxy_env(os.environ)  # 抓取材料和调用模型都要用 HTTP
    log_file = setup_logging(settings)
    log.info(
        "startup version=%s model=%s provider=%s", __version__, settings.model, settings.provider
    )
    if dropped:
        log.warning("ignored unsupported proxy env vars: %s", ", ".join(dropped))
    try:
        curriculum = Curriculum.load()
    except CurriculumError as e:
        print(f"课程表错误：{e}", file=sys.stderr)
        return 2

    print(f"loopback {__version__} · 模型 {settings.model} · 接口 {settings.provider}")
    print(f"个人状态 {settings.home} · 日志 {log_file} · 课程 {len(curriculum.items)} 篇")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        print("提示：没有检测到 ANTHROPIC_API_KEY，请先 cp .env.example .env 并填写")

    # 每次启动一个新的会话日志；跨天续学靠 progress.json，而不是续用旧会话
    session = Session.open(
        settings.home / "sessions" / f"{datetime.now():%Y%m%d-%H%M%S}-teacher.jsonl"
    )
    progress = Progress(settings.home)
    spec = agents.teacher(curriculum, progress, Library(settings.home, curriculum))
    session.append(
        "meta",
        agent=spec.name,
        model=settings.model,
        prompt_hash=spec.prompt_hash,
        tools=spec.tools.names,
        version=__version__,
    )
    repl.run(repl.App(settings, session, spec, AnthropicLLM(settings), curriculum, progress))
    return 0


if __name__ == "__main__":
    sys.exit(main())
