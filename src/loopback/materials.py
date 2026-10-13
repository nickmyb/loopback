"""切页：把 markdown 正文切成一页一页（代码里叫 section，中文叫“页”，D29）。

切页是确定性的代码，不交给模型（docs/decisions.md D9）：
- 每个标题开一页，标题带上层级路径“A › B”；没有正文的父标题不单独成页。
- 一个标题下超过 MAX_SECTION_WORDS 的内容，按段落边界拆成“（1/2）（2/2）”。
- 表格和代码块不拆开；它前面的短引导段跟着它，不和它分在两页。
- 分隔线（---）不算段落；拆出来太短的尾巴并进前一页。
- 每页的外链编号 L1、L2…，配图编号 I1、I2…。
规则一改，SPLIT_VERSION 就加一，快照里会记下用的是哪一版（D28）。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin

SPLIT_VERSION = 2  # 1：最初的规则；2：去掉分隔线、引导段跟着表格和代码块、短尾巴合并
MAX_SECTION_WORDS = 350
LEAD_IN_WORDS = 80  # 不超过这么多词的段落，紧挨在表格或代码块前面时算引导段
MIN_TAIL_WORDS = 80  # 拆出来的最后一页不到这么多词，就并进前一页
_BREAK = re.compile(r"^ {0,3}([-*_])(?: *\1){2,} *$")  # 分隔线：--- *** ___
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
    """数词：英文按单词算，中文按字算。"""
    return len(_WORD.findall(text))


def split_sections(md: str, base_url: str, doc_title: str | None = None) -> list[Section]:
    """把 markdown 正文切成页：每个标题开一页、标题带层级路径、超长的按段落再拆。"""
    raw: list[tuple[str, list[str]]] = []
    stack: list[tuple[int, str]] = []  # 当前所处的标题层级，例如 [(2, "A"), (3, "B")]
    title, paras = doc_title or "导言", []
    for block in _blocks(md):
        if _BREAK.match(block):  # 分隔线只是排版，不是内容
            continue
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
        if body and not _BREAK.match(body):
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
    """去掉标题里的锚点链接、链接语法和强调符号，只留文字。"""
    text = re.sub(r"\[​?\]\(#[^)]*\)", "", text)  # 文档站的锚点链接
    text = _LINK.sub(r"\1", text)
    return re.sub(r"[*_`]", "", text).strip(" #")


def _chunk(paras: list[str]) -> list[list[str]]:
    """按词数预算把一个标题下的段落分成几页，每页不超过 MAX_SECTION_WORDS（单段超长时独占一页）。"""
    chunks: list[list[str]] = [[]]
    words = 0
    for p in paras:
        n = count_words(p)
        if chunks[-1] and words + n > MAX_SECTION_WORDS:
            # 放不下要换页。表格和代码块前面的短引导段跟着它走，不留在上一页
            short_lead = count_words(chunks[-1][-1]) <= LEAD_IN_WORDS
            carry = [chunks[-1].pop()] if is_table_or_code(p) and short_lead else []
            if chunks[-1]:
                chunks.append(carry)
            else:  # 上一页只有这段引导：不换页，让表格直接接在它后面
                chunks[-1] = carry
            words = sum(count_words(x) for x in carry)
        chunks[-1].append(p)
        words += n
    if len(chunks) > 1 and sum(count_words(p) for p in chunks[-1]) < MIN_TAIL_WORDS:
        tail = chunks.pop()  # 太短的尾巴并进前一页，不单独占一页
        chunks[-1] += tail
    return chunks


def is_table_or_code(p: str) -> bool:
    """这一段是不是表格或代码块：切页时整块不拆、引导段跟着它；课件里上下排（D30）。"""
    return p.lstrip().startswith("```") or all(
        line.lstrip().startswith("|") for line in p.splitlines()
    )


def _build(index: int, title: str, paras: list[str], base_url: str) -> Section:
    """组装 Section：收集本页外链（绝对化、去重、编号 L#）和配图（编号 I#），并统计词数。"""
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
    """把 Section 列表转成可写入 JSON 的字典列表（缓存用）。"""
    return [asdict(s) for s in sections]


def sections_from_json(data: list[dict[str, Any]]) -> list[Section]:
    """从缓存的 JSON 还原 Section 列表。"""
    return [Section(**s) for s in data]
