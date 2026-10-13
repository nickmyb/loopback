"""抓取：把一个 URL 下载下来，并把网络错误转成给模型看的 ToolError。

材料库只调用 download，不用关心网络细节；测试时换一个假的抓取函数，不联网。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from loopback.tools import ToolError

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) loopback-learning-agent"


@dataclass(frozen=True)
class FetchResult:
    body: str
    content_type: str
    url: str


def http_fetch(url: str, retries: int = 2) -> FetchResult:
    """下载一个 URL：跟随跳转、30 秒超时、带 User-Agent；HTTP 错误抛异常。

    连接类错误（代理断开、超时）是偶发的，退避后重试最多 retries 次；HTTP 4xx/5xx 不重试。
    """
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries + 1):
        try:
            with httpx2.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
                r = client.get(url)
                r.raise_for_status()
                return FetchResult(r.text, r.headers.get("content-type", ""), str(r.url))
        except httpx2.ConnectError, httpx2.TimeoutException:
            if attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise AssertionError("unreachable")


def download(fetch: Callable[[str], FetchResult], url: str) -> FetchResult:
    """调用抓取函数，把网络和 HTTP 错误转成给模型看的 ToolError。"""
    try:
        return fetch(url)
    except httpx2.HTTPStatusError as e:
        raise ToolError(f"抓取失败：HTTP {e.response.status_code} {url}") from e
    except httpx2.HTTPError as e:
        raise ToolError(f"抓取失败（网络）：{type(e).__name__} {url}") from e
