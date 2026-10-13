"""REPL：学习者在终端里和教师对话。

- 启动时先在本地打印学习进度（不调用模型、不花钱），然后等你输入。
- `next`：由 harness 根据 progress.json 算出“下一步该讲哪一页”，再把明确的指令交给教师。
  确定性的事交给代码（D9），模型不需要自己记位置。
- `next 4 太长了`：先给刚学完的那一页打 4 分，再接着讲；`/rate 4 一句话` 给整篇打分（D32）。
- `/trace`：随时查看当前会话的轨迹（审计和排查用）；`/cost`：用量和花费。
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from loopback.agents import AgentSpec
from loopback.config import Settings
from loopback.curriculum import Curriculum
from loopback.display import describe_api_error, describe_stop, format_cost, show_tool
from loopback.llm import LLM
from loopback.loop import run_turn
from loopback.progress import Progress, next_message, status_text
from loopback.rating import ARTICLE_HINT, PAGE_HINT, Rater, parse_next, parse_rate
from loopback.session import Session
from loopback.tools import ToolError
from loopback.trace import build_trace, render_text

log = logging.getLogger(__name__)

HELP = """命令：
  next, n            开始或继续学习：自动定位到下一页
  next 4 [一句话]     先给刚学完的那一页打 4 分（1-5），再继续
  /rate 4 [一句话]    给整篇打分，比如 /rate 4 最有用的是第 3 页
  /trace [N]         查看本次会话的轨迹（最近 N 轮，默认全部）
  /cost              本次会话的 token 用量、缓存命中率、估算花费
  /help              显示这段帮助
  /quit              退出（Ctrl-D 也可以）
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
    rater: Rater  # 记分员：next 4 和 /rate 的分数由它记进 feedback.jsonl（D32）


def run(app: App) -> None:
    """主循环：读一行交给 handle，handle 返回 False 就退出。"""
    with contextlib.suppress(ImportError):
        import readline  # noqa: F401  # 让 input() 支持方向键和历史
    print(status_text(app.curriculum, app.progress))
    print("\n输入 next 开始或继续学习，/help 查看命令。\n")
    while True:
        try:
            line = input("you> ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            return
        if line and not handle(app, line):
            return


def handle(app: App, line: str) -> bool:
    """处理一行输入：命令在本地处理，其余发给教师。返回 False 表示退出。"""
    word = line.split()[0]
    if line in ("/quit", "/exit"):
        return False
    if line == "/help":
        print(HELP)
    elif line == "/cost":
        print(format_cost(app.session))
    elif word == "/trace":
        parts = line.split()
        last = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        print(render_text(build_trace(app.session.events), last=last))
    elif word == "/rate":
        rated = parse_rate(line)
        if rated is None:
            print("用法：/rate 1-5 一句话，比如 /rate 4 最有用的是第 3 页")
        else:
            print(_receipt(lambda: app.rater.article(*rated)))
    elif (nxt := parse_next(line)) is not None:
        score, note = nxt
        if score is not None:  # next 4：先给刚学完的那一页记分
            print(_receipt(lambda: app.rater.page(score, note)))
        go_next(app)
    else:
        ask_teacher(app, line)
    return True


def go_next(app: App) -> None:
    """next：由代码算出下一步交给教师；这一轮学完一页或一整篇，就提示怎么打分。"""
    before = _position(app.progress)
    message = next_message(app.curriculum, app.progress)
    print(f"（next → {message}）")
    ask_teacher(app, message)
    item, section = _position(app.progress)
    if item is not None and item == before[0] and section > before[1]:
        print(f"（{PAGE_HINT}）")
    elif before[0] and item is None and app.progress.state(before[0])["status"] == "done":
        print(f"（{ARTICLE_HINT}）")


def ask_teacher(app: App, text: str) -> None:
    """把一条输入交给教师跑完一整轮；流式打印回答，处理中断和接口错误。"""
    print("tutor> ", end="", flush=True)
    try:
        result = run_turn(
            app.session,
            app.spec,
            app.llm,
            app.settings,
            text,
            on_text=lambda t: print(t, end="", flush=True),
            on_tool=show_tool,
        )
    except KeyboardInterrupt:
        print("\n（已中断）")
        return
    except anthropic.APIError as e:
        log.exception("api error")
        print(f"\n[接口错误] {describe_api_error(e)}")
        return
    print()
    if note := describe_stop(result, app.spec.max_steps):
        print(note)


def _receipt(record: Callable[[], str]) -> str:
    """执行一次记分，返回给学习者看的回执；记不了就说明原因。"""
    try:
        return f"（{record()}）"
    except ToolError as e:
        return f"（没有记分：{e}）"


def _position(progress: Progress) -> tuple[str | None, int]:
    """当前在学哪个条目、学到第几页。"""
    current = progress.current
    return current, progress.state(current)["section"] if current else 0
