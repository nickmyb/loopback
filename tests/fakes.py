"""FakeLLM：按剧本返回预设响应，并记录每次收到的请求。harness 的单元测试都用它，不花钱。"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from loopback.llm import OnText, Response


def text(t: str) -> dict[str, Any]:
    return {"type": "text", "text": t}


def tool_use(id_: str, name: str, **input_: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": id_, "name": name, "input": input_}


def reply(*blocks: dict[str, Any], stop: str = "end_turn", model: str = "fake-model") -> Response:
    return Response(
        content=list(blocks),
        stop_reason=stop,
        model=model,
        usage={"input_tokens": 10, "output_tokens": 5},
    )


class FakeLLM:
    def __init__(self, script: list[Response | Callable[[], Response]]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    def stream(self, request: dict[str, Any], on_text: OnText) -> Response:
        self.requests.append(copy.deepcopy(request))  # 记录发送时的快照
        if not self.script:
            raise AssertionError("FakeLLM script exhausted")
        step = self.script.pop(0)
        resp = step() if callable(step) else step
        for b in resp.content:
            if b.get("type") == "text":
                on_text(b["text"])
        return resp
