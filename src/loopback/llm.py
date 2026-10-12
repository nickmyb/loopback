"""模型调用层：`LLM` protocol + Anthropic 实现 + 请求构造（docs/decisions.md D4、D7）。

- loop 只依赖 `LLM.stream()`。测试里换成 FakeLLM，不花钱就能测完整的 harness。
- 响应统一成 `Response`：content 是原样的 dict 块（thinking 的签名等字段原封不动），
  下一轮原样回传。这是 preserved thinking 的要求。
- Claude 专属参数只在 profile.official 时加：自动缓存、effort。
- 后补（docs/plan.md 第 2 节）：server-side fallback（回传时有剔除规则）、eager_input_streaming。
"""

from __future__ import annotations

import importlib.util
import logging
import os
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import anthropic

from loopback.config import Settings

log = logging.getLogger(__name__)

OnText = Callable[[str], None]


@dataclass(frozen=True)
class Response:
    content: list[dict[str, Any]]
    stop_reason: str | None
    model: str  # 实际提供服务的模型，取自响应（兼容接口可能静默换模型）
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    stop_details: dict[str, Any] | None = None
    latency_ms: int = 0


class LLM(Protocol):
    """loop 唯一依赖的模型接口：生产用 AnthropicLLM，测试用 FakeLLM。"""

    def stream(self, request: dict[str, Any], on_text: OnText) -> Response:
        """发送请求并流式返回：每段文本回调 on_text，结束后返回完整的 Response。"""
        ...


def build_request(
    settings: Settings,
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
    effort: str | None = None,
) -> dict[str, Any]:
    """拼出 Messages API 请求：通用字段总是带上，缓存和 effort 只在官方接口时加。"""
    req: dict[str, Any] = {
        "model": settings.model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        req["tools"] = tools
    if settings.profile.official:
        req["cache_control"] = {"type": "ephemeral"}  # 自动缓存最后一个可缓存块
        req["output_config"] = {"effort": effort or settings.effort}
    return req


class AnthropicLLM:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 600.0,
    ) -> None:
        dropped = sanitize_proxy_env(os.environ)
        if dropped:
            log.warning("ignored unsupported proxy env vars: %s", ", ".join(dropped))
        # 重试（429、5xx、连接错误）交给 SDK 自带的指数退避；api_key 等凭证由 SDK 从环境读取
        # api_key=None 时由 SDK 从环境读取；evals 的评审可以显式传另一家接口的 key
        self.client = anthropic.Anthropic(
            api_key=api_key, base_url=settings.base_url, max_retries=max_retries, timeout=timeout
        )

    def stream(self, request: dict[str, Any], on_text: OnText) -> Response:
        """用 SDK 流式请求：边收边回调文本，最后把完整消息整理成 Response（content 原样保留）。"""
        t0 = time.monotonic()
        with self.client.messages.stream(**request) as s:
            for event in s:
                if event.type == "text":
                    on_text(event.text)
            msg = s.get_final_message()
        return Response(
            content=[b.to_dict() for b in msg.content],
            stop_reason=msg.stop_reason,
            model=msg.model,
            usage=msg.usage.to_dict() if msg.usage else {},
            request_id=getattr(msg, "_request_id", None),
            stop_details=msg.stop_details.to_dict() if msg.stop_details else None,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


def sanitize_proxy_env(env: MutableMapping[str, str]) -> list[str]:
    """去掉 HTTP 客户端用不了的 ALL_PROXY。

    桌面代理工具常导出 ALL_PROXY=socks://...，而 SDK 底层的 httpx2 只认
    http(s)，以及装了 socksio 时的 socks5(h)；遇到其他写法，连 client 都建不起来。
    HTTPS 请求本来就走 HTTPS_PROXY，去掉 ALL_PROXY 不影响访问。
    """
    ok = {"http", "https"}
    if importlib.util.find_spec("socksio") is not None:
        ok |= {"socks5", "socks5h"}
    dropped = []
    for name in ("ALL_PROXY", "all_proxy"):
        url = env.get(name)
        if url and urlparse(url).scheme not in ok:
            del env[name]
            dropped.append(name)
    return dropped
