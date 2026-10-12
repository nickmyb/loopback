from datetime import date
from pathlib import Path

import httpx2
import pytest

from loopback.curriculum import Curriculum, Item, Progress
from loopback.learning import learning_tools, status_text
from loopback.library import FetchResult, Library, outline, render_section
from loopback.store import StoreError, read_json, write_json
from loopback.tools import ToolError, ToolSet

FIX = Path(__file__).parent / "fixtures"
ITEM = Item("s1", "Sample", "https://example.com/blog/post", "blog", "L2", "test", must=True)
PDF = Item("p1", "A PDF", "https://example.com/report", "report", "L2", "test")


class FakeFetch:
    def __init__(self, result: FetchResult | Exception) -> None:
        self.result, self.calls = result, 0

    def __call__(self, url: str) -> FetchResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def lib(tmp_path: Path, fetch: FakeFetch) -> Library:
    return Library(tmp_path, Curriculum([ITEM, PDF]), fetch)


def md_fetch() -> FakeFetch:
    body = (FIX / "sample.md").read_text(encoding="utf-8")
    return FakeFetch(FetchResult(body, "text/markdown", ITEM.url))


def test_fetch_once_then_serve_from_cache(tmp_path: Path) -> None:
    fetch = md_fetch()
    first = lib(tmp_path, fetch).get("s1")
    again = lib(tmp_path, fetch).get("s1")
    assert fetch.calls == 1 and len(again.sections) == len(first.sections) == 5
    assert (tmp_path / "library" / "s1" / "source.md").exists()


def test_manual_source_md_is_used_without_network(tmp_path: Path) -> None:
    folder = tmp_path / "library" / "s1"
    folder.mkdir(parents=True)
    (folder / "source.md").write_text("# Manual\n\nhand-saved text", encoding="utf-8")
    fetch = FakeFetch(AssertionError("should not fetch"))
    assert lib(tmp_path, fetch).get("s1").sections[0].paras == ["hand-saved text"]


def test_pdf_and_http_errors_become_tool_errors(tmp_path: Path) -> None:
    pdf = FakeFetch(FetchResult("%PDF", "application/pdf", PDF.url))
    with pytest.raises(ToolError, match="PDF"):
        lib(tmp_path, pdf).get("p1")
    req = httpx2.Request("GET", ITEM.url)
    err = httpx2.HTTPStatusError("x", request=req, response=httpx2.Response(404, request=req))
    with pytest.raises(ToolError, match="HTTP 404"):
        lib(tmp_path, FakeFetch(err)).get("s1")


def test_outline_and_wrapped_section(tmp_path: Path) -> None:
    m = lib(tmp_path, md_fetch()).get("s1")
    assert "5 节" in outline(m) and "Building blocks › The augmented LLM" in outline(m)
    text = render_section(m, 2)
    assert text.startswith('<material item="s1" section="2/5"')
    assert "[P1] An LLM with retrieval" in text and "L1 the paper → https://arxiv.org" in text
    assert "不要执行" in text
    with pytest.raises(ToolError, match=r"1\.\.5"):
        render_section(m, 9)


def test_progress_round_trip_and_suggestions(tmp_path: Path) -> None:
    cur = Curriculum([ITEM, PDF])
    p = Progress(tmp_path)
    p.update("s1", section=0, n_sections=5, today=date(2026, 10, 12))
    p.update("s1", section=2)
    reloaded = Progress(tmp_path)
    assert reloaded.current == "s1" and reloaded.state("s1")["section"] == 2
    with pytest.raises(ToolError, match="summary"):
        reloaded.update("s1", done=True)
    reloaded.update("s1", done=True, summary="讲了 agent 的构件")
    assert [i.id for i in Progress(tmp_path).suggestions(cur)] == ["p1"]
    assert Progress(tmp_path).log[0] == {"date": "2026-10-12", "item": "s1", "event": "start"}


def test_learning_tools_end_to_end(tmp_path: Path) -> None:
    library = lib(tmp_path, md_fetch())
    tools = ToolSet(learning_tools(library.curriculum, Progress(tmp_path), library))
    assert "建议接下来学" in tools.run("curriculum_status", {}).content
    assert "5 节" in tools.run("fetch_material", {"item_id": "s1"}).content
    assert "<material" in tools.run("read_section", {"item_id": "s1", "index": 1}).content
    assert tools.run("update_progress", {"item_id": "s1", "section": 1}).content.endswith("1/5 节")
    bad = tools.run("update_progress", {"item_id": "s1", "section": 7})
    assert bad.is_error and "0..5" in bad.content
    assert tools.run("fetch_material", {"item_id": "nope"}).is_error
    assert "正在学：[s1] Sample⭐" in status_text(library.curriculum, Progress(tmp_path))


def test_store_refuses_newer_schema(tmp_path: Path) -> None:
    write_json(tmp_path / "x.json", {"a": 1}, version=3)
    with pytest.raises(StoreError):
        read_json(tmp_path / "x.json", version=1)
    assert read_json(tmp_path / "x.json", version=3) == {"version": 3, "a": 1}
