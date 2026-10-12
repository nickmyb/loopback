"""轨迹工具：从事件日志重建“轮 -> 调用 -> 工具”，并能渲染成时间线。"""

from pathlib import Path

from fakes import FakeLLM, reply, text, tool_use
from test_loop import echo_tool, make

from loopback.loop import run_turn
from loopback.trace import build_trace, latest_session, load_events, render_text


def recorded_session(tmp_path: Path):
    """跑一段真实的 loop（FakeLLM），得到一份有工具调用、有报错的事件日志。"""
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM(
        [
            reply(
                tool_use("t1", "echo", msg="hi"),
                tool_use("t2", "echo", msg="boom"),
                stop="tool_use",
            ),
            reply(text("讲完了")),
        ]
    )
    session.append("meta", agent="t", model="m", prompt_hash="abc", tools=["echo"], version="0")
    run_turn(session, spec, llm, settings, "第一个问题")
    return session


def test_trace_groups_calls_and_pairs_tool_results(tmp_path: Path) -> None:
    trace = build_trace(recorded_session(tmp_path).events)
    assert len(trace.turns) == 1
    turn = trace.turns[0]
    assert turn.user == "第一个问题" and len(turn.calls) == 2
    tools = turn.calls[0].tools
    assert [(t.name, t.result, t.is_error) for t in tools] == [
        ("echo", "echo:hi", False),
        ("echo", "ERROR: boom requested", True),
    ]
    assert turn.calls[1].text == "讲完了"
    assert trace.usage()["input_tokens"] == 20  # FakeLLM 每次 10


def test_render_shows_errors_failed_turns_and_totals(tmp_path: Path) -> None:
    session = recorded_session(tmp_path)
    session.append("user", content="第二个问题")
    session.append("turn_failed", step=1, error="APIConnectionError")
    out = render_text(build_trace(session.events))
    assert "第 1 轮" in out and "⚙ echo" in out and "✗ ERROR: boom requested" in out
    assert "本轮失败：APIConnectionError（这条输入已撤回" in out
    assert "合计 2 次模型调用" in out
    assert "第 1 轮" not in render_text(build_trace(session.events), last=1)


def test_missing_tool_result_is_flagged(tmp_path: Path) -> None:
    events = [
        {"type": "user", "content": "q"},
        {
            "type": "assistant",
            "content": [{"type": "tool_use", "id": "x", "name": "echo", "input": {}}],
        },
    ]
    assert "缺少 tool_result" in render_text(build_trace(events))


def test_latest_session_and_corrupt_lines(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "20261012-090000-teacher.jsonl").write_text('{"type":"user","content":"a"}\n')
    newest = sessions / "20261012-100000-teacher.jsonl"
    newest.write_text('{"type":"user","content":"b"}\n{"type":"assist')  # 末尾写坏
    assert latest_session(tmp_path) == newest
    assert [e["content"] for e in load_events(newest)] == ["b"]
