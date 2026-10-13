"""反馈分两级（D32）：每页、每篇各一个分；next 4 由代码记分，记录里带上是哪一页、在哪打的。"""

import json
from pathlib import Path

from fakes import FakeLLM, reply, text
from test_library import lib, md_fetch
from test_mcp_server import call

from loopback.agents import AgentSpec
from loopback.config import Settings
from loopback.feedback import Origin, feedback_tool
from loopback.progress import Progress
from loopback.rating import Rater
from loopback.repl import App, handle
from loopback.session import Session
from loopback.tools import ToolSet

ORIGIN = Origin("repl", prompt_hash="p1", model="m1")


def rows(home: Path) -> list[dict]:
    path = home / "feedback.jsonl"
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()] if path.exists() else []


def app(tmp_path: Path, *replies) -> App:
    """一个最小的 REPL：样例文章 s1 学到第 1 页；教师只回文字（FakeLLM）。"""
    library = lib(tmp_path, md_fetch())
    progress = Progress(tmp_path)
    progress.update("s1", section=1, n_sections=len(library.get("s1").sections))
    settings = Settings.from_env({"LOOPBACK_HOME": str(tmp_path), "LOOPBACK_OPEN_BROWSER": "0"})
    spec = AgentSpec(name="teacher", system="sys", tools=ToolSet([]))
    llm = FakeLLM([reply(text(r)) for r in replies])
    rater = Rater(tmp_path, progress, library, ORIGIN, source="repl")
    return App(
        settings, Session.open(tmp_path / "s.jsonl"), spec, llm, library.curriculum, progress, rater
    )


def test_page_and_article_records_say_which_page_and_where_it_was_rated(tmp_path: Path) -> None:
    tools = ToolSet([feedback_tool(tmp_path, lib(tmp_path, md_fetch()), ORIGIN)])
    tools.run("record_feedback", {"item_id": "s1", "score": 5, "section": 2})
    tools.run("record_feedback", {"item_id": "s1", "score": 3, "level": "article", "note": "偏长"})
    page, article = rows(tmp_path)
    assert page["level"] == "page" and page["section"] == 2 and page["snapshot_at"]
    assert page["page_title"] == "Building blocks › The augmented LLM"
    assert (page["front_end"], page["prompt_hash"], page["model"]) == ("repl", "p1", "m1")
    assert article["level"] == "article" and article["section"] is None
    assert tools.run("record_feedback", {"item_id": "s1", "score": 9, "section": 1}).is_error
    assert tools.run("record_feedback", {"item_id": "s1", "score": 4}).is_error  # 页级要有页号
    assert tools.run("record_feedback", {"item_id": "s1", "score": 4, "section": 9}).is_error


def test_next_with_a_score_rates_the_page_just_finished_then_moves_on(tmp_path: Path) -> None:
    a = app(tmp_path, "好的")
    assert handle(a, "next 4 太长了")
    [r] = rows(tmp_path)
    assert (r["section"], r["score"], r["note"], r["source"]) == (1, 4, "太长了", "repl")
    sent = a.llm.requests[0]["messages"][0]["content"][0]["text"]
    assert "第 2 页" in sent  # 记完分照常讲下一页，打分这句不发给模型


def test_plain_next_records_nothing_and_rate_scores_the_whole_item(tmp_path: Path, capsys) -> None:
    a = app(tmp_path, "好的")
    handle(a, "next")
    assert rows(tmp_path) == []
    handle(a, "/rate 3 还行")
    handle(a, "/rate 很好")  # 没写分数：只提示用法，不记
    [r] = rows(tmp_path)
    assert (r["level"], r["item_id"], r["score"], r["note"]) == ("article", "s1", 3, "还行")
    assert "用法：/rate 1-5" in capsys.readouterr().out


def test_next_step_with_a_rating_records_it_over_mcp(tmp_path: Path) -> None:
    *_, nxt = call(
        tmp_path,
        [
            lambda c: c.call_tool("fetch_material", {"item_id": "repo-loop"}),
            lambda c: c.call_tool("update_progress", {"item_id": "repo-loop", "section": 1}),
            lambda c: c.call_tool("next_step", {"rating": 4, "note": "清楚"}),
        ],
    )
    [r] = rows(tmp_path)
    assert (r["section"], r["score"], r["front_end"], r["source"]) == (
        1,
        4,
        "claude-code",
        "next_step",
    )
    assert r["prompt_hash"] and "已记录" in nxt.content[0].text and "第 2 页" in nxt.content[0].text
