"""文档自检（D25）：文档和代码不能各说各的。

检查五件事：
- architecture.md 的模块表和实际文件一致；
- plan 的每个里程碑都有状态；
- R、D 编号连续，而且不重复；
- 活文档里引用的决策都存在；
- 活文档里确认点的叫法统一（D26）。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
# 活文档：随项目更新、同一内容只写一份。决策和里程碑记录是冻结的历史，不在其中
LIVING = ["CLAUDE.md", "README.md", "docs/plan.md", "docs/requirements.md", "docs/architecture.md"]
STATUS = ("✅", "🟡", "🔄", "⏸", "⬜")
BANNED = ("运行确认", "等确认", "等用户确认")  # 统一用四个确认点的名字


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def table_after(text: str, heading: str) -> list[list[str]]:
    """取某个标题下第一张 markdown 表的数据行（去掉表头和分隔行），每行拆成去掉空白的单元格。"""
    lines = text[text.index(heading) :].splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("|"))
    rows = []
    for line in lines[start + 2 :]:  # 跳过表头和 |---| 分隔行
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def test_module_table_matches_the_files() -> None:
    listed = {}
    for cells in table_after(read("docs/architecture.md"), "## 模块"):
        path = re.fullmatch(r"`([^`]+)`", cells[0])
        assert path, f"模块表第一列要写成 `路径`：{cells[0]}"
        listed[path.group(1)] = cells[1]
    for path, what in listed.items():
        planned = what.startswith("未实现")
        assert (ROOT / path).exists() != planned, (
            f"{path} 已经存在，去掉“未实现”" if planned else f"表里列了不存在的文件：{path}"
        )
    dirs = (ROOT / "src/loopback", ROOT / "evals")
    actual = {p.relative_to(ROOT).as_posix() for d in dirs for p in d.glob("*.py")}
    assert not actual - set(listed), f"模块表缺少：{sorted(actual - set(listed))}"


def test_every_milestone_has_a_status() -> None:
    rows = table_after(read("docs/plan.md"), "## 4. 执行顺序")
    ids = [r[0].strip("*") for r in rows if r[0] != "—"]
    assert len(ids) == len(set(ids)), "里程碑编号重复"
    for r in rows:
        if r[0] != "—":
            assert r[1].startswith(STATUS), f"{r[0]} 没有状态标记：{r[1]!r}"


def test_requirement_and_decision_ids_are_continuous() -> None:
    for path, pattern, prefix in (
        ("docs/requirements.md", r"^\| (R\d+) \|", "R"),
        ("docs/decisions.md", r"^## (D\d+) ", "D"),
    ):
        ids = re.findall(pattern, read(path), re.M)
        expected = [f"{prefix}{i}" for i in range(1, len(ids) + 1)]
        wrong = [f"{a}（应为 {b}）" for a, b in zip(ids, expected, strict=True) if a != b]
        assert not wrong, f"{path} 的编号要从 {prefix}1 连续往后编，不能重复或跳号：{wrong[:3]}"


def test_referenced_decisions_exist() -> None:
    last = len(re.findall(r"^## D\d+ ", read("docs/decisions.md"), re.M))
    for path in LIVING:
        for d in re.findall(r"\bD(\d+)\b", read(path)):
            assert 1 <= int(d) <= last, f"{path} 引用了不存在的决策 D{d}"


def test_living_docs_use_the_checkpoint_names() -> None:
    for path in LIVING:
        for word in BANNED:
            assert word not in read(path), f"{path} 里有“{word}”，请改用四个确认点的名字（D26）"


def test_doc_map_paths_exist() -> None:
    for path in re.findall(r"`((?:docs|src|evals|tests)/[^`*<]*)`", read("CLAUDE.md")):
        assert (ROOT / path).exists(), f"CLAUDE.md 引用了不存在的路径：{path}"
