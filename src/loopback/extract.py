"""网页 -> markdown 正文。

策略（docs/decisions.md D16）：
1. 已经是 markdown 的（Claude Code / Codex 文档的 .md 版本）原样使用。
2. HTML：找到“段落最密集的容器”当正文，删掉脚本、按钮等噪音，再用 markdownify 转成 markdown。
   这样小标题、配图、链接都能保留。
3. 第 2 步拿到的正文太短、而 trafilatura 的通用提取明显更长（两倍以上）时，改用后者。
标题、日期这些元数据由 trafilatura 提取。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import lxml.html
import trafilatura
from markdownify import markdownify

MIN_BODY_CHARS = 800
_BANNER = re.compile(r"(?:^>.*\n)*^>.*llms\.txt.*\n(?:^>.*\n)*\n?", re.M)
_NOISE = ".//script|.//style|.//noscript|.//button|.//form|.//svg|.//nav|.//iframe"


@dataclass(frozen=True)
class Extracted:
    markdown: str
    title: str | None
    date: str | None


def extract(body: str, url: str, content_type: str = "") -> Extracted:
    if _is_markdown(url, content_type):
        md = _strip_banner(body).strip()
        return Extracted(md, _md_title(md), None)
    meta = trafilatura.extract_metadata(body)
    title = meta.title if meta else None
    date = meta.date if meta else None
    md = _dense_container_markdown(body, url)
    if len(md) < MIN_BODY_CHARS:  # 正文偏短时才试通用提取，而且明显更长才采用
        alt = trafilatura.extract(
            body, output_format="markdown", include_links=True, include_images=True, url=url
        )
        if alt and len(alt) > 2 * len(md):
            md = alt
    return Extracted(md, title, date)


def _is_markdown(url: str, content_type: str) -> bool:
    path = urlparse(url).path
    return path.endswith((".md", ".txt")) or content_type.startswith(
        ("text/markdown", "text/plain")
    )


def _strip_banner(md: str) -> str:
    """去掉文档站塞在正文前的引用块横幅（例如指向 llms.txt 的 “Documentation Index”）。"""
    return _BANNER.sub("", md)


def _md_title(md: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else None


def _dense_container_markdown(html: str, url: str) -> str:
    doc = lxml.html.fromstring(html)
    weight: Counter = Counter()
    for p in doc.iter("p"):
        parent = p.getparent()
        if parent is not None:
            weight[parent] += len(p.text_content())
    if not weight:
        return ""
    root = weight.most_common(1)[0][0]
    for node in root.xpath(_NOISE):
        node.drop_tree()
    for a in root.iter("a"):
        if a.get("href"):
            a.set("href", urljoin(url, a.get("href")))
    for img in root.iter("img"):
        img.set("src", _image_src(img.get("src") or "", url))
    md = markdownify(lxml.html.tostring(root, encoding="unicode"), heading_style="ATX", bullets="-")
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _image_src(src: str, base: str) -> str:
    """Next.js 的 /_next/image?url=<原图> 还原成原图地址，相对路径转成绝对路径。"""
    if "/_next/image" in src:
        original = parse_qs(urlparse(src).query).get("url")
        if original:
            src = original[0]
    return urljoin(base, src)
