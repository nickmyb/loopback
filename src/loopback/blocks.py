"""课件的“内容块”：校验每个块，再把它转成一段安全的 HTML（render.py 负责拼成整页）。

块类型：explain、text、note、mermaid、svg、steps、quiz、deeper（含义见 BLOCK_SCHEMA）。
- 模型写的文本都按 markdown 渲染，原始 HTML 一律转义（html=False）。
- explain 的原文由代码按段号取，模型只写讲解。
- 出错就抛 ToolError，并说明是第几个块、哪里不对，模型据此修正后重试。
"""

from __future__ import annotations

import html
import re
from typing import Any

from markdown_it import MarkdownIt

from loopback.materials import is_table_or_code
from loopback.svg import sanitize_svg
from loopback.tools import ToolError

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")
_BR = re.compile(r"&lt;br\s*/?&gt;")  # 被转义掉的 <br>：表格单元格里常用它换行
# fmt: off
MERMAID_KINDS = (
    "graph", "flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram",
    "gantt", "pie", "mindmap", "timeline", "journey", "quadrantChart", "gitGraph",
    "xychart-beta", "block-beta", "sankey-beta",
)
# fmt: on
# 每种块必须有的字段
REQUIRED = {
    "explain": ("para", "text"),
    "text": ("text",),
    "note": ("text",),
    "mermaid": ("code",),
    "svg": ("svg",),
    "steps": ("frames",),
    "quiz": ("q", "a"),
    "deeper": ("title", "text"),
}


def md(text: str) -> str:
    """markdown -> 安全的 HTML 片段。原始 HTML 一律转义，只放行 <br>（D30）。"""
    return _BR.sub("<br>", _MD.render(text or ""))


def block_html(n: int, b: dict[str, Any], section: Any) -> str:
    """校验第 n 个块并转成 HTML。section 是当前这一页（概览、总结页为 None）。"""
    kind = b.get("type")
    if kind not in REQUIRED:
        raise ToolError(f"第 {n} 个块的 type={kind!r} 不支持，可选：{', '.join(REQUIRED)}")
    missing = [k for k in REQUIRED[kind] if b.get(k) in (None, "", [])]
    if missing:
        raise ToolError(f"第 {n} 个块（{kind}）缺少字段：{', '.join(missing)}")
    if kind == "explain":  # 左边原文（代码按段号取），右边讲解
        if section is None:
            raise ToolError("explain 块只能用在 page=section 的课件里")
        p = b["para"]
        if not isinstance(p, int) or not 1 <= p <= len(section.paras):
            raise ToolError(f"第 {n} 个块的 para 必须在 1..{len(section.paras)}")
        para = section.paras[p - 1]
        wide = " wide" if is_table_or_code(para) else ""  # 代码块和表格上下排，原文占满整行
        return (
            f'<section class="block explain{wide}"><div class="original">'
            f'<div class="pnum">P{p}</div>{md(para)}</div><div>{md(b["text"])}</div></section>'
        )
    if kind in ("text", "note"):
        return f'<section class="block {kind}">{md(b["text"])}</section>'
    if kind in ("quiz", "deeper"):  # 都是默认折叠的 <details>
        head, inner = (b["q"], b["a"]) if kind == "quiz" else (b["title"], b["text"])
        return (
            f'<details class="block {kind}"><summary>{html.escape(head)}</summary>'
            f"{md(inner)}</details>"
        )
    if kind == "steps":
        return _steps(n, b["frames"])
    return f'<section class="block figure">{_figure(n, b)}</section>'  # mermaid / svg


def _figure(n: int, b: dict[str, Any]) -> str:
    """一张图：mermaid（code）、svg 或一段文字（text），带可选的图注。"""
    if b.get("code") is not None or b.get("type") == "mermaid":
        code = b.get("code", "").strip()
        if not code.startswith(MERMAID_KINDS):
            raise ToolError(
                f"第 {n} 个图的 mermaid 类型无法识别，第一行应以这些开头："
                f"{', '.join(MERMAID_KINDS[:8])} 等"
            )
        _lint_mermaid(n, code)
        inner = f'<pre class="mermaid">{html.escape(code)}</pre>'
    elif b.get("svg"):
        inner = sanitize_svg(b["svg"])
    elif b.get("text"):
        inner = md(b["text"])
    else:
        raise ToolError(f"第 {n} 个块需要 code（mermaid）、svg 或 text 之一")
    caption = f'<div class="caption">{html.escape(b["caption"])}</div>' if b.get("caption") else ""
    return inner + caption


def _lint_mermaid(n: int, code: str) -> None:
    """拦下已知会出问题的写法，让模型当场改（Python 里跑不了 mermaid 本身）。"""
    if code.startswith("mindmap"):  # 力导向布局，节点经常互相压住（D30）
        raise ToolError(
            f"第 {n} 个图是 mindmap：它的布局会让节点互相压住，不能用。"
            "全篇结构请改用 flowchart LR：每个一级标题一个节点，下面挂 1 到 3 个要点"
        )


def _steps(n: int, frames: Any) -> str:
    """分步播放器：2 到 12 帧，每帧是一张图或一段文字；播放逻辑在模板的 JS 里。"""
    if not isinstance(frames, list) or not 2 <= len(frames) <= 12:
        raise ToolError(f"第 {n} 个块（steps）的 frames 必须是 2 到 12 帧的列表")
    html_frames = "".join(f'<div class="frame">{_figure(n, f)}</div>' for f in frames)
    controls = (
        '<div class="controls"><button class="prev">◀ 上一步</button><span class="pos"></span>'
        '<button class="next">下一步 ▶</button><button class="play">▶ 自动播放</button></div>'
    )
    return f'<section class="block figure steps">{html_frames}{controls}</section>'


BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(REQUIRED)},
        "para": {"type": "integer", "description": "explain: paragraph number [P#] of the section"},
        "text": {"type": "string", "description": "markdown (Chinese explanation / content)"},
        "code": {"type": "string", "description": "mermaid source, first line = diagram type"},
        "svg": {"type": "string", "description": "a complete <svg>...</svg> (may animate)"},
        "caption": {"type": "string"},
        "q": {"type": "string"},
        "a": {"type": "string"},
        "title": {"type": "string"},
        "frames": {
            "type": "array",
            "items": {"type": "object"},
            "description": "steps: 2-12 frames, each {caption, code|svg|text}",
        },
    },
    "required": ["type"],
}
