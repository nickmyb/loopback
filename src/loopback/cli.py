"""命令行入口：`uv run loopback`。

M1：最小 REPL。和教师对话，支持 /cost、/help、/quit。
每次启动开一个新的会话日志（workspace/sessions/）；跨天续学在 M3 接上。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
from datetime import datetime
from typing import Any

import anthropic
from dotenv import load_dotenv

from loopback import __version__, agents
from loopback.config import ConfigError, Settings, setup_logging
from loopback.llm import AnthropicLLM
from loopback.loop import run_turn
from loopback.pricing import cache_hit_rate, estimate_usd
from loopback.session import Session

log = logging.getLogger(__name__)

HELP = """命令：
  /cost   本次会话的 token 用量、缓存命中率、估算花费
  /help   显示这段帮助
  /quit   退出（Ctrl-D 也可以）
其他输入都会发给教师。回答过程中按 Ctrl-C 可以打断当前回答。"""


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

    print(f"loopback {__version__} · 模型 {settings.model} · 接口 {settings.provider}")
    print(f"个人状态 {settings.home} · 日志 {log_file}")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        print("提示：没有检测到 ANTHROPIC_API_KEY，请先 cp .env.example .env 并填写")

    session = Session.open(
        settings.home / "sessions" / f"{datetime.now():%Y%m%d-%H%M%S}-teacher.jsonl"
    )
    spec = agents.teacher(settings)
    session.append(
        "meta",
        agent=spec.name,
        model=settings.model,
        prompt_hash=spec.prompt_hash,
        tools=spec.tools.names,
        version=__version__,
    )
    repl(session, spec, AnthropicLLM(settings), settings)
    return 0


def repl(session: Session, spec: agents.AgentSpec, llm: AnthropicLLM, settings: Settings) -> None:
    _enable_line_editing()
    print("输入 /help 查看命令。\n")
    while True:
        try:
            line = input("you> ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            return
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return
        if line == "/help":
            print(HELP)
            continue
        if line == "/cost":
            print(format_cost(session))
            continue
        print("tutor> ", end="", flush=True)
        try:
            result = run_turn(
                session,
                spec,
                llm,
                settings,
                line,
                on_text=lambda t: print(t, end="", flush=True),
                on_tool=_show_tool,
            )
        except KeyboardInterrupt:
            print("\n（已中断）")
            continue
        except anthropic.APIError as e:
            log.exception("api error")
            print(f"\n[接口错误] {_describe_api_error(e)}")
            continue
        print()
        if result.stop_reason == "refusal":
            category = (result.stop_details or {}).get("category")
            print(f"[模型拒绝回答：{category or '未注明类别'}] 换个问法试试。")
        elif result.stop_reason == "max_tokens":
            print("[回答达到长度上限被截断] 可以说“继续”。")
        elif result.stop_reason == "max_steps":
            print(f"[已连续调用模型 {spec.max_steps} 次，先停下来] 可以说“继续”。")


def format_cost(session: Session) -> str:
    """按每个 assistant 事件里“实际服务的模型”计价：兼容接口可能静默换模型。"""
    u = session.usage_totals()
    costs = [
        estimate_usd(ev.get("model", ""), ev.get("usage") or {})
        for ev in session.events
        if ev["type"] == "assistant"
    ]
    known = [c for c in costs if c is not None]
    money = f"约 ${sum(known):.4f}" if known else "（未知模型，不估算）"
    if known and len(known) < len(costs):
        money += "（部分模型未知，未计入）"
    return (
        f"输入 {u.get('input_tokens', 0)} · 输出 {u.get('output_tokens', 0)} · "
        f"缓存读 {u.get('cache_read_input_tokens', 0)} · "
        f"缓存写 {u.get('cache_creation_input_tokens', 0)}\n"
        f"缓存命中率 {cache_hit_rate(u):.0%} · 花费 {money}"
    )


def _show_tool(name: str, args: dict[str, Any]) -> None:
    brief = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in args.items())
    print(f"\n  ⚙ {name}({brief})", flush=True)


def _describe_api_error(e: anthropic.APIError) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "认证失败：检查 .env 里的 ANTHROPIC_API_KEY"
    if isinstance(e, anthropic.NotFoundError):
        return "模型或接口不存在：检查 MODEL_ID / ANTHROPIC_BASE_URL"
    if isinstance(e, anthropic.RateLimitError):
        return "触发限流，SDK 已自动重试仍失败，稍后再试"
    if isinstance(e, anthropic.APIConnectionError):
        return "网络连接失败：检查网络或代理（HTTPS_PROXY）"
    if isinstance(e, anthropic.APIStatusError):
        return f"HTTP {e.status_code}：{e.message}"
    return str(e)


def _enable_line_editing() -> None:
    with contextlib.suppress(ImportError):
        import readline  # noqa: F401  # 让 input() 支持方向键和历史


if __name__ == "__main__":
    sys.exit(main())
