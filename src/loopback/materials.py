"""学习材料：抓取 -> markdown -> 切节 -> 缓存到 library/<id>/；按节读取（just-in-time 上下文）。

切节是确定性的代码，不交给模型（docs/decisions.md D9）：
- 每个标题开一节，标题带上层级路径“A › B”；没有正文的父标题不单独成节。
- 超过 MAX_SECTION_WORDS 的节，按段落边界拆成“（1/2）（2/2）”。
- 代码块不拆开；每节的外链编号 L1、L2…，配图编号 I1、I2…。
教师只拿到大纲；正文一次读一节，并用定界符标成“不可信资料”（D8）。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin

MAX_SECTION_WORDS = 350
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)")
_WORD = re.compile(r"[A-Za-z0-9_'’-]+|[一-鿿]")


@dataclass
class Section:
    index: int
    title: str
    paras: list[str]
    links: list[dict[str, str]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    words: int = 0


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def split_sections(md: str, base_url: str, doc_title: str | None = None) -> list[Section]:
    raw: list[tuple[str, list[str]]] = []
    stack: list[tuple[int, str]] = []  # 当前所处的标题层级，例如 [(2, "A"), (3, "B")]
    title, paras = doc_title or "导言", []
    for block in _blocks(md):
        head, *rest = block.split("\n")
        m = _HEADING.match(head)  # 代码块的首行是 ```，不会被当成标题
        if not m:
            paras.append(block)
            continue
        level, heading = len(m.group(1)), _clean_heading(m.group(2))
        if paras:  # 上一节有正文：收尾
            raw.append((title, paras))
            paras = []
        if level == 1 and not raw and not stack:  # 文首的 H1 是文档标题，导言归它
            title = heading
        else:  # 标题带上层级路径，例如“A › B”，同名小节（How it works）也能区分
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, heading))
            title = " › ".join(h for _, h in stack)
        body = "\n".join(rest).strip()
        if body:
            paras.append(body)
    if paras:
        raw.append((title, paras))

    sections: list[Section] = []
    for title, ps in raw:
        chunks = _chunk(ps)
        for k, chunk in enumerate(chunks, 1):
            label = f"{title}（{k}/{len(chunks)}）" if len(chunks) > 1 else title
            sections.append(_build(len(sections) + 1, label, chunk, base_url))
    return sections


def _blocks(md: str) -> list[str]:
    """按空行切块，但代码块内部的空行不切。"""
    blocks, buf, in_fence = [], [], False
    for line in md.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if buf:
                blocks.append("\n".join(buf).strip())
                buf = []
            continue
        buf.append(line.rstrip())
    if buf:
        blocks.append("\n".join(buf).strip())
    return [b for b in blocks if b]


def _clean_heading(text: str) -> str:
    text = re.sub(r"\[​?\]\(#[^)]*\)", "", text)  # 文档站的锚点链接
    text = _LINK.sub(r"\1", text)
    return re.sub(r"[*_`]", "", text).strip(" #")


def _chunk(paras: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    words = 0
    for p in paras:
        n = count_words(p)
        if chunks[-1] and words + n > MAX_SECTION_WORDS:
            chunks.append([])
            words = 0
        chunks[-1].append(p)
        words += n
    return chunks


def _build(index: int, title: str, paras: list[str], base_url: str) -> Section:
    links, seen = [], set()
    images = [
        {"id": f"I{i}", "alt": alt, "src": urljoin(base_url, src)}
        for i, (alt, src) in enumerate(_IMAGE.findall("\n\n".join(paras)), 1)
    ]
    for text, href in _LINK.findall("\n\n".join(paras)):
        url = urljoin(base_url, href)
        if href.startswith(("#", "mailto:", "javascript:")) or url in seen:
            continue
        seen.add(url)
        links.append({"id": f"L{len(links) + 1}", "text": _clean_heading(text), "url": url})
    return Section(index, title, paras, links, images, sum(count_words(p) for p in paras))


def sections_to_json(sections: list[Section]) -> list[dict[str, Any]]:
    return [asdict(s) for s in sections]


def sections_from_json(data: list[dict[str, Any]]) -> list[Section]:
    return [Section(**s) for s in data]
