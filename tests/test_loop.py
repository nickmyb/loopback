"""agent_loop 的核心不变量：只追加、tool 配对、错误路径、中断补齐、步数上限。"""

from pathlib import Path

import pytest
from fakes import FakeLLM, reply, text, tool_use

from loopback.agents import AgentSpec
from loopback.config import Settings
from loopback.loop import run_turn
from loopback.session import Session
from loopback.tools import Tool, ToolError, ToolSet


def make(tmp_path: Path, *tools: Tool, max_steps: int = 5):
    settings = Settings.from_env({"LOOPBACK_HOME": str(tmp_path)})
    spec = AgentSpec(name="t", system="sys", tools=ToolSet(tools), max_steps=max_steps)
    return settings, spec, Session.open(tmp_path / "s.jsonl")


def echo_tool(calls: list | None = None) -> Tool:
    def echo(msg: str) -> str:
        if calls is not None:
            calls.append(msg)
        if msg == "boom":
            raise ToolError("boom requested")
        if msg == "crash":
            raise RuntimeError("bug")
        return f"echo:{msg}"

    schema = {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]}
    return Tool("echo", "Echo back.", schema, echo)


def assert_paired(session: Session) -> None:
    """每条含 tool_use 的 assistant 消息后，紧跟的 user 消息必须覆盖全部 id。"""
    msgs = session.messages()
    for i, m in enumerate(msgs):
        ids = {b["id"] for b in m["content"] if b.get("type") == "tool_use"}
        if m["role"] == "assistant" and ids:
            nxt = msgs[i + 1]
            got = {b["tool_use_id"] for b in nxt["content"] if b.get("type") == "tool_result"}
            assert nxt["role"] == "user" and got == ids


def test_tool_round_trip_appends_events_and_pairs_ids(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM([reply(tool_use("t1", "echo", msg="hi"), stop="tool_use"), reply(text("done"))])

    result = run_turn(session, spec, llm, settings, "go")

    assert result.stop_reason == "end_turn" and result.text == "done" and result.steps == 2
    assert [e["type"] for e in session.events] == ["user", "assistant", "tool_results", "assistant"]
    second = llm.requests[1]["messages"]
    assert second[-1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": "echo:hi",
    }
    assert_paired(session)


def test_requests_are_append_only_prefixes(tmp_path: Path) -> None:
    """后一次请求的 messages 一定以前一次请求的 messages 开头。

    这是 prompt 缓存与 preserved thinking 的前提。
    """
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM(
        [
            reply(tool_use("t1", "echo", msg="a"), stop="tool_use"),
            reply(text("ok")),
            reply(text("again")),
        ]
    )
    run_turn(session, spec, llm, settings, "one")
    run_turn(session, spec, llm, settings, "two")
    for prev, cur in zip(llm.requests, llm.requests[1:], strict=False):
        assert cur["messages"][: len(prev["messages"])] == prev["messages"]
        assert cur["tools"] == prev["tools"] and cur["system"] == prev["system"]


@pytest.mark.parametrize(
    ("msg", "expected"),
    [
        ("boom", "ERROR: boom requested"),
        ("crash", "ERROR: internal error in echo: RuntimeError: bug"),
    ],
)
def test_tool_failures_become_error_results(tmp_path: Path, msg: str, expected: str) -> None:
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM([reply(tool_use("t1", "echo", msg=msg), stop="tool_use"), reply(text("sorry"))])
    run_turn(session, spec, llm, settings, "go")
    block = session.events[2]["results"][0]
    assert block["content"] == expected and block["is_error"] is True


def test_unknown_tool_and_invalid_input_are_reported_not_raised(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM(
        [
            reply(
                tool_use("t1", "nope"),
                tool_use("t2", "echo", msg=3),
                tool_use("t3", "echo"),
                stop="tool_use",
            ),
            reply(text("ok")),
        ]
    )
    run_turn(session, spec, llm, settings, "go")
    contents = [r["content"] for r in session.events[2]["results"]]
    assert "unknown tool 'nope'" in contents[0]
    assert "must be string" in contents[1]
    assert "missing required field(s): msg" in contents[2]


@pytest.mark.parametrize("stop", ["max_tokens", "refusal"])
def test_tool_use_in_truncated_or_refused_reply_is_answered_but_not_run(
    tmp_path: Path, stop: str
) -> None:
    calls: list[str] = []
    settings, spec, session = make(tmp_path, echo_tool(calls))
    llm = FakeLLM([reply(tool_use("t1", "echo", msg="x"), stop=stop)])
    result = run_turn(session, spec, llm, settings, "go")
    assert result.stop_reason == stop and calls == []
    assert session.events[-1]["results"][0]["content"].startswith("ERROR: not executed")
    assert_paired(session)


def test_ctrl_c_during_tools_fills_every_id_then_reraises(tmp_path: Path) -> None:
    def interrupting(msg: str) -> str:
        raise KeyboardInterrupt

    schema = {"type": "object", "properties": {"msg": {"type": "string"}}}
    settings, spec, session = make(tmp_path, Tool("slow", "Slow.", schema, interrupting))
    llm = FakeLLM(
        [reply(tool_use("a", "slow", msg="1"), tool_use("b", "slow", msg="2"), stop="tool_use")]
    )

    with pytest.raises(KeyboardInterrupt):
        run_turn(session, spec, llm, settings, "go")

    ids = [r["tool_use_id"] for r in session.events[-1]["results"]]
    assert ids == ["a", "b"]
    assert_paired(session)
    # 中断后继续对话：新输入与补齐的 tool_result 合并成一条 user 消息，tool_result 在前
    llm.script.append(reply(text("resumed")))
    run_turn(session, spec, llm, settings, "continue")
    last_user = llm.requests[-1]["messages"][-1]["content"]
    assert [b["type"] for b in last_user] == ["tool_result", "tool_result", "text"]


def test_pause_turn_resends_and_merges_assistant_turns(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path)
    llm = FakeLLM([reply(text("part1 "), stop="pause_turn"), reply(text("part2"))])
    result = run_turn(session, spec, llm, settings, "go")
    assert result.text == "part2"
    msgs = session.messages()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert [b["text"] for b in msgs[1]["content"]] == ["part1 ", "part2"]


def test_max_steps_stops_runaway_loops(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path, echo_tool(), max_steps=3)
    llm = FakeLLM([lambda: reply(tool_use("t", "echo", msg="again"), stop="tool_use")] * 3)
    result = run_turn(session, spec, llm, settings, "go")
    assert result.stop_reason == "max_steps" and result.steps == 3
    assert_paired(session)


def test_served_model_and_prompt_hash_are_recorded(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path)
    llm = FakeLLM([reply(text("hi"), model="deepseek-v4-pro")])
    run_turn(session, spec, llm, settings, "go")
    ev = session.events[-1]
    assert ev["model"] == "deepseek-v4-pro" and ev["prompt_hash"] == spec.prompt_hash


def test_each_role_asks_for_its_own_model(tmp_path: Path) -> None:
    env = {"LOOPBACK_HOME": str(tmp_path), "MODEL_ID": "base", "LOOPBACK_T_MODEL": "for-t"}
    settings = Settings.from_env(env)
    spec = AgentSpec(name="t", system="sys", tools=ToolSet([]))
    llm = FakeLLM([reply(text("hi")), reply(text("hi"))])
    run_turn(Session.open(tmp_path / "a.jsonl"), spec, llm, settings, "go")
    pinned = AgentSpec(name="t", system="sys", tools=ToolSet([]), model="pinned")
    run_turn(Session.open(tmp_path / "b.jsonl"), pinned, llm, settings, "go")
    assert [r["model"] for r in llm.requests] == ["for-t", "pinned"]  # 代码里写死的最优先


class Boom(Exception):
    pass


def failing() -> None:
    raise Boom("network down")


def test_failed_first_request_retracts_the_unanswered_input(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path)
    llm = FakeLLM([failing, reply(text("answer"))])
    with pytest.raises(Boom):
        run_turn(session, spec, llm, settings, "lost question")
    run_turn(session, spec, llm, settings, "new question")
    sent = llm.requests[-1]["messages"]
    assert sent == [{"role": "user", "content": [{"type": "text", "text": "new question"}]}]
    assert any(e["type"] == "turn_failed" for e in session.events)  # 仍留在日志里供排查


def test_failure_after_tool_results_keeps_the_partially_answered_turn(tmp_path: Path) -> None:
    settings, spec, session = make(tmp_path, echo_tool())
    llm = FakeLLM([reply(tool_use("t1", "echo", msg="a"), stop="tool_use"), failing])
    with pytest.raises(Boom):
        run_turn(session, spec, llm, settings, "go")
    msgs = session.messages()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert_paired(session)
