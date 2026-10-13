from datetime import date
from pathlib import Path

import httpx2
import pytest

from loopback.curriculum import Curriculum, Item
from loopback.fetch import FetchResult
from loopback.learning import learning_tools
from loopback.library import Library
from loopback.materials import SPLIT_VERSION
from loopback.progress import Progress, status_text
from loopback.reading import outline, render_section
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
    assert "5 页" in outline(m) and "Building blocks › The augmented LLM" in outline(m)
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
    assert "5 页" in tools.run("fetch_material", {"item_id": "s1"}).content
    assert "<material" in tools.run("read_section", {"item_id": "s1", "index": 1}).content
    assert tools.run("update_progress", {"item_id": "s1", "section": 1}).content.endswith("1/5 页")
    bad = tools.run("update_progress", {"item_id": "s1", "section": 7})
    assert bad.is_error and "0..5" in bad.content
    assert tools.run("fetch_material", {"item_id": "nope"}).is_error
    assert "正在学：[s1] Sample⭐" in status_text(library.curriculum, Progress(tmp_path))


def edit_source(home: Path) -> None:
    """模拟快照之后原文被改了：在 Building blocks 前插一个新标题，后面每页的页号都往后挪一位。"""
    src = home / "library" / "s1" / "source.md"
    text = src.read_text(encoding="utf-8")
    new = "## Inserted part\n\nThis part was added after the snapshot.\n\n## Building blocks"
    src.write_text(text.replace("## Building blocks", new), encoding="utf-8")


def test_snapshot_stays_frozen_until_refreshed(tmp_path: Path) -> None:
    library = lib(tmp_path, md_fetch())
    first = library.get("s1")
    edit_source(tmp_path)
    frozen = library.get("s1")
    assert frozen.sections == first.sections and frozen.stale  # 页号不变，但知道原文改过
    assert "原文在快照之后改过" in outline(frozen)
    fresh = library.refresh("s1")
    assert len(fresh.sections) == 6 and fresh.split_version == SPLIT_VERSION
    assert not library.get("s1").stale


def test_starting_an_item_resplits_from_the_latest_source(tmp_path: Path) -> None:
    library = lib(tmp_path, md_fetch())
    tools = ToolSet(learning_tools(library.curriculum, Progress(tmp_path), library))
    tools.run("fetch_material", {"item_id": "s1"})
    edit_source(tmp_path)
    tools.run("fetch_material", {"item_id": "s1"})  # 还没开始学：直接按新原文重切
    assert len(library.get("s1").sections) == 6 and not library.get("s1").stale


def test_mid_study_keeps_the_snapshot_until_the_learner_refreshes(tmp_path: Path) -> None:
    library = lib(tmp_path, md_fetch())
    tools = ToolSet(learning_tools(library.curriculum, Progress(tmp_path), library))
    tools.run("fetch_material", {"item_id": "s1"})
    tools.run("update_progress", {"item_id": "s1", "section": 2})  # 学完了 The augmented LLM
    edit_source(tmp_path)
    mid = tools.run("fetch_material", {"item_id": "s1"}).content
    assert "原文在快照之后改过" in mid and len(library.get("s1").sections) == 5
    tools.run("fetch_material", {"item_id": "s1", "refresh": True})
    assert len(library.get("s1").sections) == 6
    assert Progress(tmp_path).state("s1")["section"] == 3  # 进度跟着标题挪到了新的第 3 页


def test_old_snapshots_without_the_new_fields_still_load(tmp_path: Path) -> None:
    library = lib(tmp_path, md_fetch())
    library.get("s1")
    snap = tmp_path / "library" / "s1" / "sections.json"
    data = read_json(snap, version=1) or {}
    for key in ("version", "source_hash", "split_version", "snapshot_at"):
        data.pop(key)
    write_json(snap, data, version=1)
    m = library.get("s1")
    assert m.split_version == 1 and not m.stale and len(m.sections) == 5


def test_store_refuses_newer_schema(tmp_path: Path) -> None:
    write_json(tmp_path / "x.json", {"a": 1}, version=3)
    with pytest.raises(StoreError):
        read_json(tmp_path / "x.json", version=1)
    assert read_json(tmp_path / "x.json", version=3) == {"version": 3, "a": 1}
