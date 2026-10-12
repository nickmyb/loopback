"""用例集：evals/suites/<name>.yaml 的加载与校验。用例和评分标准进 git（D6 公共内容）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SUITES = Path(__file__).parent / "suites"
KINDS = {"section", "start", "finish"}


@dataclass(frozen=True)
class Case:
    id: str
    item: str  # 课程条目 id
    kind: str  # section | start | finish
    section: int | None = None  # kind=section：要讲的节号
    say: str | None = None  # kind=start：学习者说的话
    tags: tuple[str, ...] = field(default_factory=tuple)


def load_suite(name: str, only: list[str] | None = None) -> list[Case]:
    """读取并校验用例集；only 给出 id 列表时只取这些用例（顺序按用例集）。"""
    data = yaml.safe_load((SUITES / f"{name}.yaml").read_text(encoding="utf-8"))
    cases, seen = [], set()
    for raw in data["cases"]:
        case = Case(**{**raw, "tags": tuple(raw.get("tags", ()))})
        if case.id in seen:
            raise ValueError(f"用例 id 重复：{case.id}")
        if case.kind not in KINDS:
            raise ValueError(f"{case.id}: kind 必须是 {sorted(KINDS)} 之一")
        if case.kind == "section" and not case.section:
            raise ValueError(f"{case.id}: kind=section 需要 section")
        if case.kind == "start" and not case.say:
            raise ValueError(f"{case.id}: kind=start 需要 say")
        seen.add(case.id)
        cases.append(case)
    if only:
        missing = set(only) - seen
        if missing:
            raise ValueError(f"用例集里没有：{', '.join(sorted(missing))}")
        cases = [c for c in cases if c.id in only]
    return cases
