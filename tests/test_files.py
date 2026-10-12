from pathlib import Path

import pytest

from loopback.files import workspace_tools
from loopback.tools import ToolSet


@pytest.fixture
def tools(tmp_path: Path) -> ToolSet:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("hello", encoding="utf-8")
    return ToolSet(workspace_tools(tmp_path, writable=True))


def test_read_list_write_inside_workspace(tools: ToolSet, tmp_path: Path) -> None:
    assert tools.run("read_file", {"path": "notes/a.md"}).content == "hello"
    assert tools.run("list_files", {"path": "notes"}).content == "notes/a.md"
    assert not tools.run("write_file", {"path": "notes/b.md", "content": "x"}).is_error
    assert (tmp_path / "notes" / "b.md").read_text(encoding="utf-8") == "x"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "notes/../../x"])
def test_paths_outside_workspace_are_rejected(tools: ToolSet, path: str) -> None:
    for name, args in [
        ("read_file", {"path": path}),
        ("write_file", {"path": path, "content": "x"}),
    ]:
        r = tools.run(name, args)
        assert r.is_error and "outside the workspace" in r.content


def test_symlink_escape_is_rejected(tools: ToolSet, tmp_path: Path) -> None:
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    r = tools.run("read_file", {"path": "link.txt"})
    assert r.is_error and "outside the workspace" in r.content


def test_read_only_toolset_has_no_write(tmp_path: Path) -> None:
    assert "write_file" not in ToolSet(workspace_tools(tmp_path, writable=False))
