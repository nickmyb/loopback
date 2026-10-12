from pathlib import Path

from loopback.session import Session


def test_reopen_gives_identical_projection(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    s = Session.open(path)
    s.append("meta", agent="t")
    s.append("user", content="你好")
    s.append(
        "assistant",
        content=[
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "hi"},
        ],
    )
    reopened = Session.open(path)
    assert reopened.messages() == s.messages()
    assert reopened.messages()[1]["content"][0]["signature"] == "sig"  # 原样保留


def test_meta_events_are_not_projected(tmp_path: Path) -> None:
    s = Session.open(tmp_path / "s.jsonl")
    s.append("meta", agent="t")
    s.append("interrupt", stage="model")
    assert s.messages() == []


def test_half_written_last_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    s = Session.open(path)
    s.append("user", content="a")
    with path.open("a", encoding="utf-8") as f:
        f.write('{"v":1,"type":"assistant","content":[')  # 模拟写到一半崩溃
    assert Session.open(path).messages() == [
        {"role": "user", "content": [{"type": "text", "text": "a"}]}
    ]


def test_usage_totals_sum_assistant_events(tmp_path: Path) -> None:
    s = Session.open(tmp_path / "s.jsonl")
    s.append("assistant", content=[], usage={"input_tokens": 3, "cache_read_input_tokens": 7})
    s.append("assistant", content=[], usage={"input_tokens": 2, "service_tier": "standard"})
    assert s.usage_totals() == {"input_tokens": 5, "cache_read_input_tokens": 7}
