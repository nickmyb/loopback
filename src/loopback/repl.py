"""REPL：学习者在终端里和教师对话。

- 启动时先在本地打印学习进度（不调用模型、不花钱），然后等你输入。
- `next`：由 harness 根据 progress.json 算出“下一步该讲哪一页”，再把明确的指令交给教师。
  确定性的事交给代码（D9），模型不需要自己记位置。
- `/trace`：随时查看当前会话的轨迹（审计和排查用）；`/cost`：用量和花费。
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from loopback.agents import AgentSpec
from loopback.config import Settings
from loopback.curriculum import Curriculum
from loopback.feedback import record_feedback
from loopback.llm import LLM
from loopback.loop import run_turn
from loopback.pricing import cache_hit_rate, estimate_usd
from loopback.progress import Progress, next_message, status_text
from loopback.session import Session
from loopback.trace import build_trace, render_text

log = logging.getLogger(__name__)

HELP = """命令：
  next, n      开始或继续学习：自动定位到下一页
  /trace [N]   查看本次会话的轨迹（最近 N 轮，默认全部）：每次模型调用、工具调用、token、耗时
  /cost        本次会话的 token 用量、缓存命中率、估算花费
  /help        显示这段帮助
  /quit        退出（Ctrl-D 也可以）
其他输入都会发给教师。回答过程中按 Ctrl-C 可以打断当前回答。"""


@dataclass
class App:
    """一次运行需要的全部对象。progress 和教师的工具共用同一个实例，两边看到的进度一致。"""

    settings: Settings
    session: Session
    spec: AgentSpec
    llm: LLM
    curriculum: Curriculum
    progress: Progress


def run(app: App) -> None:
    """主循环：读一行 -> 是命令就本地处理，否则发给教师。"""
    _enable_line_editing()
    print(status_text(app.curriculum, app.progress))
    print("\n输入 next 开始或继续学习，/help 查看命令。\n")
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
        elif line == "/cost":
            print(format_cost(app.session))
        elif line.split()[0] == "/trace":
            parts = line.split()
            last = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            print(render_text(build_trace(app.session.events), last=last))
        elif line in ("next", "n"):
            before = _position(app.progress)
            message = next_message(app.curriculum, app.progress)
            print(f"（next → {message}）")
            ask_teacher(app, message)
            ask_rating(app, before)
        else:
            ask_teacher(app, line)


def _position(progress: Progress) -> tuple[str | None, int]:
    """当前在学哪个条目、学到第几页。"""
    current = progress.current
    return current, progress.state(current)["section"] if current else 0


def ask_rating(app: App, before: tuple[str | None, int]) -> None:
    """这一轮里进度往前走了一页，就请学习者打个分（回车跳过）；分数写进 feedback.jsonl。"""
    item, section = _position(app.progress)
    if item is None or item != before[0] or section <= before[1]:
        return
    try:
        answer = input(f"这一页（{item} 第 {section} 页）打几分？1-5，可加一句意见，回车跳过 > ")
    except EOFError, KeyboardInterrupt:
        print()
        return
    answer = answer.strip()
    if answer[:1] in "12345" and answer:
        record_feedback(app.settings.home, item, section, int(answer[0]), answer[1:].strip())
        print("（已记录，谢谢）")


def ask_teacher(app: App, text: str) -> None:
    """把一条输入交给教师跑完一整轮；流式打印回答，处理中断、接口错误和异常的结束原因。"""
    print("tutor> ", end="", flush=True)
    try:
        result = run_turn(
            app.session,
            app.spec,
            app.llm,
            app.settings,
            text,
            on_text=lambda t: print(t, end="", flush=True),
            on_tool=_show_tool,
        )
    except KeyboardInterrupt:
        print("\n（已中断）")
        return
    except anthropic.APIError as e:
        log.exception("api error")
        print(f"\n[接口错误] {_describe_api_error(e)}")
        return
    print()
    if result.stop_reason == "refusal":
        category = (result.stop_details or {}).get("category")
        print(f"[模型拒绝回答：{category or '未注明类别'}] 换个问法试试。")
    elif result.stop_reason == "max_tokens":
        print("[回答达到长度上限被截断] 可以说“继续”。")
    elif result.stop_reason == "max_steps":
        print(f"[已连续调用模型 {app.spec.max_steps} 次，先停下来] 可以说“继续”。")


def format_cost(session: Session) -> str:
    """汇总用量；按每个 assistant 事件里“实际服务的模型”计价（兼容接口可能静默换模型）。"""
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
    """模型每调用一次工具，就在终端里显示一行，让学习者看到 agent 在做什么。"""
    brief = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
    print(f"\n  ⚙ {name}({brief})", flush=True)


def _short(value: Any, limit: int = 40) -> str:
    """把参数值压成一行并截断，用在终端的工具调用提示里。"""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _describe_api_error(e: anthropic.APIError) -> str:
    """把 SDK 的异常翻译成学习者看得懂、知道怎么处理的提示。"""
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
    """导入 readline，让 input() 支持方向键和历史记录。"""
    with contextlib.suppress(ImportError):
        import readline  # noqa: F401  # 让 input() 支持方向键和历史
