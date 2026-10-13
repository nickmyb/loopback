"""跑一次试验（一个用例的一次重复）：独立的临时 LOOPBACK_HOME + 真实入口。

    runs/<run>/trials/<case>-r<k>/      <- 这次试验的 LOOPBACK_HOME（完整保留，供排查和报告）
        library/<item>/                 <- 从冻结的材料快照复制过来，不联网
        progress.json                   <- 按用例类型预置的进度
        sessions/trial.jsonl            <- 完整事件日志（轨迹）
        lessons/<item>/*.html           <- 生成的课件

eval 配置必须和生产一致（eval-audit §2）：这里用的就是 learning.teacher_tools + loop.run_turn，
不是另写一份。API 错误、网络错误归为 InfraError：记到 errors.jsonl，不算 agent 的分。
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import anthropic

from evals.cases import Case
from loopback import agents
from loopback.config import Settings
from loopback.curriculum import Curriculum
from loopback.feedback import Origin
from loopback.learning import teacher_tools
from loopback.library import Library, Material
from loopback.llm import LLM
from loopback.loop import run_turn
from loopback.materials import SPLIT_VERSION
from loopback.progress import Progress, next_message
from loopback.session import Session


class InfraError(Exception):
    """基础设施故障（API、网络、限流、超时）：不是 agent 的错，不计分。"""


@dataclass
class Trial:
    case: Case
    rep: int
    home: Path
    session: Session
    material: Material
    user_input: str
    final_text: str
    stop_reason: str


def snapshot_materials(cases: list[Case], curriculum: Curriculum, cache_home: Path) -> dict:
    """开跑前把用到的材料抓好、切好，冻结成快照；返回每篇的 sections.json 的 sha256。

    之后每次试验都从快照复制，不再联网，避免网络抖动被算成 agent 失败。
    hash 写进 manifest，材料变了（文章更新）在报告里能看出来。
    """
    library = Library(cache_home, curriculum)
    hashes = {}
    for item in sorted({c.item for c in cases}):
        # 切页规则升级了：用缓存的原文按新规则重切（不联网），eval 测的是当前的规则
        if library.get(item).split_version < SPLIT_VERSION:
            library.refresh(item)
        data = (cache_home / "library" / item / "sections.json").read_bytes()
        hashes[item] = hashlib.sha256(data).hexdigest()[:12]
    return hashes


def prepare_home(home: Path, case: Case, curriculum: Curriculum, cache_home: Path) -> str:
    """建好这次试验的 LOOPBACK_HOME：复制材料快照、按用例类型预置进度；返回学习者的输入。"""
    shutil.copytree(cache_home / "library" / case.item, home / "library" / case.item)
    progress = Progress(home)
    total = len(Library(home, curriculum).get(case.item).sections)
    if case.kind == "section":  # 停在上一页，next 会要求讲第 section 页
        progress.update(case.item, section=(case.section or 1) - 1, n_sections=total)
    elif case.kind == "finish":  # 所有页都讲完了，next 会要求做总结
        progress.update(case.item, section=total, n_sections=total)
    if case.kind == "start":
        return case.say or ""
    return next_message(curriculum, progress)  # 和 REPL 里输入 next 完全一样


def run_trial(
    case: Case,
    rep: int,
    run_dir: Path,
    llm: LLM,
    env: dict[str, str],
    curriculum: Curriculum,
    cache_home: Path,
) -> Trial:
    """跑一次试验并返回全部产物；API 和网络错误转成 InfraError。"""
    home = run_dir / "trials" / f"{case.id}-r{rep}"
    settings = Settings.from_env({**env, "LOOPBACK_HOME": str(home), "LOOPBACK_OPEN_BROWSER": "0"})
    user_input = prepare_home(home, case, curriculum, cache_home)
    progress, library = Progress(home), Library(home, curriculum)
    spec = agents.teacher(teacher_tools(home, curriculum, progress, library, origin=Origin("eval")))
    session = Session.open(home / "sessions" / "trial.jsonl")
    session.append(
        "meta",
        agent=spec.name,
        model=spec.model_in(settings),
        prompt_hash=spec.prompt_hash,
        tools=spec.tools.names,
        eval_case=case.id,
        rep=rep,
    )
    try:
        result = run_turn(session, spec, llm, settings, user_input)
    except anthropic.APIError as e:
        raise InfraError(f"{type(e).__name__}: {e}") from e
    return Trial(
        case,
        rep,
        home,
        session,
        library.get(case.item),
        user_input,
        result.text,
        result.stop_reason,
    )
