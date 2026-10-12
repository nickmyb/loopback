"""项目自学：仓库文件当学习材料；以及 next 的下一步计算。"""

from datetime import date
from pathlib import Path

import pytest

from loopback.curriculum import Curriculum, Item, Progress
from loopback.learning import next_message
from loopback.library import Library, render_section
from loopback.repo import code_sections, repo_file
from loopback.tools import ToolError

SOURCE = '''"""Module doc."""

import os

CONST = 1


# helper comment belongs to the next def
def helper(x):
    return x + 1


@decorator
class Thing:
    def method(self):
        return os.sep
'''


def test_code_sections_split_by_top_level_defs_with_line_ranges() -> None:
    secs = code_sections(SOURCE)
    assert [s.title for s in secs] == [
        "模块说明与导入（L1-L5）",
        "def helper（L6-L10）",  # 前面的空行和注释归到下一个定义
        "class Thing（L11-L16）",  # 装饰器算在类里
    ]
    assert "   8| # helper comment belongs to the next def" in secs[1].paras[0]
    assert "  13| @decorator" in secs[2].paras[0]


def test_repo_items_read_live_files_and_never_cache(tmp_path: Path) -> None:
    item = Item("repo-loop", "loop", "repo:src/loopback/loop.py", "repo", "PJ", "g")
    lib = Library(tmp_path, Curriculum([item]))
    m = lib.get("repo-loop")
    assert any(s.title.startswith("def run_turn") for s in m.sections)
    assert "| def run_turn(" in render_section(m, 2) or any(
        "| def run_turn(" in p for s in m.sections for p in s.paras
    )
    assert not (tmp_path / "library").exists()  # 不写缓存


def test_repo_paths_cannot_escape_the_repository() -> None:
    with pytest.raises(ToolError):
        repo_file("repo:src/loopback/../../../etc/passwd")


def test_packaged_curriculum_starts_with_the_project_track() -> None:
    cur = Curriculum.load()
    assert cur.items[0].id == "repo-claude-md" and cur.items[0].level == "PJ"
    lib = Library(Path("/nonexistent-home"), cur)
    for item in cur.items:
        if item.url.startswith("repo:"):
            assert lib.get(item.id).sections, item.id  # 每个项目条目都真实存在且能切节


def test_next_message_follows_progress(tmp_path: Path) -> None:
    cur = Curriculum(
        [
            Item("a", "A", "https://x/a", "blog", "L2", "g"),
            Item("b", "B", "https://x/b", "blog", "L2", "g"),
        ]
    )
    p = Progress(tmp_path)
    assert next_message(cur, p).startswith("开始学习 [a] A")
    p.update("a", section=0, n_sections=2, today=date(2026, 10, 12))
    assert "第 1 节" in next_message(cur, p)
    p.update("a", section=2)
    assert "都学完了" in next_message(cur, p)
    p.update("a", done=True, summary="s")
    assert next_message(cur, p).startswith("开始学习 [b] B")
