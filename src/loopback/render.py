"""HTML 课件：教师给出“内容块”，代码负责排版成页面（docs/decisions.md D21）。

    render_lesson(item_id, page, title, blocks)
        -> workspace/lessons/<item_id>/{overview.html, s01.html, ..., summary.html, index.html}

单个块怎么变成 HTML 在 blocks.py；这里负责整页：模板、翻页导航、目录页、打开浏览器。
"""

from __future__ import annotations

import html
import json
import webbrowser
from collections.abc import Callable
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from loopback.blocks import BLOCK_SCHEMA, block_html
from loopback.library import Library
from loopback.tools import Tool, ToolError


def page_file(page: str, section: int | None) -> str:
    """页面文件名：overview.html / s03.html / summary.html。"""
    return f"s{section:02d}.html" if page == "section" else f"{page}.html"


class LessonRenderer:
    def __init__(
        self, home: Path, library: Library, open_page: Callable[[Path], None] = lambda _p: None
    ) -> None:
        self.root = home / "lessons"
        self.library = library
        self.open_page = open_page

    def render(
        self,
        item_id: str,
        page: str,
        title: str,
        blocks: list[dict[str, Any]],
        section: int | None = None,
    ) -> Path:
        """生成一页课件并更新目录页，返回文件路径。"""
        # 1) 校验页面参数，找到这一页（原文从这里取）
        material = self.library.get(item_id)
        if page not in ("overview", "section", "summary"):
            raise ToolError("page 必须是 overview、section 或 summary")
        sec = None
        if page == "section":
            if section is None or not 1 <= section <= len(material.sections):
                raise ToolError(f"page=section 时必须给出 section（1..{len(material.sections)}）")
            sec = material.sections[section - 1]
        if not blocks:
            raise ToolError("blocks 不能为空")
        # 2) 逐块转成 HTML（任何一块出错都不写文件，模型修正后整页重来）
        body = "\n".join(block_html(i, b, sec) for i, b in enumerate(blocks, 1))
        # 3) 套模板写文件，更新目录，打开浏览器
        folder = self.root / item_id
        folder.mkdir(parents=True, exist_ok=True)
        name = page_file(page, section)
        where = f" · 第 {section}/{len(material.sections)} 页 · {sec.title}" if sec else ""
        nav = _nav(name, len(material.sections))
        path = folder / name
        path.write_text(
            _page(title, f"《{material.title}》{where}", nav, body, material.url), "utf-8"
        )
        self._update_index(folder, material.title, name, title)
        self.open_page(path)
        return path

    def _update_index(self, folder: Path, doc_title: str, name: str, title: str) -> None:
        """记录本篇已生成的页面（pages.json），并按阅读顺序重写目录页 index.html。"""
        pages_file = folder / "pages.json"
        pages = json.loads(pages_file.read_text("utf-8")) if pages_file.exists() else {}
        pages[name] = title
        pages_file.write_text(json.dumps(pages, ensure_ascii=False, indent=2), "utf-8")
        order = sorted(pages, key=lambda f: (f != "overview.html", f == "summary.html", f))
        items = "".join(f'<li><a href="{f}">{html.escape(pages[f])}</a></li>' for f in order)
        body = f'<section class="block"><ol>{items}</ol></section>'
        (folder / "index.html").write_text(
            _page(f"{doc_title} · 课件目录", "", "", body, ""), "utf-8"
        )


def _nav(name: str, total: int) -> str:
    """上一页 / 目录 / 下一页（按预期的页面顺序，不管下一页是否已经生成）。"""
    order = ["overview.html", *[f"s{i:02d}.html" for i in range(1, total + 1)], "summary.html"]
    i = order.index(name)
    prev = f'<a href="{order[i - 1]}">◀ 上一页</a>' if i > 0 else "<span></span>"
    nxt = f'<a href="{order[i + 1]}">下一页 ▶</a>' if i + 1 < len(order) else "<span></span>"
    return f'<nav class="pager">{prev}<a href="index.html">目录</a>{nxt}</nav>'


def _page(title: str, subtitle: str, nav: str, body: str, source: str) -> str:
    """把各部分填进模板。BODY 最后替换，避免正文里恰好出现占位符时被误替换。"""
    tpl = resources.files("loopback").joinpath("templates/lesson.html").read_text("utf-8")
    src = f'原文：<a href="{html.escape(source)}">{html.escape(source)}</a> · ' if source else ""
    footer = f"{src}loopback 生成于 {datetime.now():%Y-%m-%d %H:%M}"
    out = tpl.replace("{{TITLE}}", html.escape(title))
    out = out.replace("{{SUBTITLE}}", html.escape(subtitle))
    out = out.replace("{{NAV}}", nav).replace("{{FOOTER}}", footer)
    return out.replace("{{BODY}}", body)


def open_in_browser(path: Path) -> None:
    """用系统默认浏览器打开课件；没有图形界面时 webbrowser 会静默失败。"""
    webbrowser.open(path.as_uri())


def lesson_tool(renderer: LessonRenderer) -> Tool:
    """render_lesson：把内容块排版成 HTML 课件并在浏览器打开。"""

    def render_lesson(
        item_id: str, page: str, title: str, blocks: list, section: int | None = None
    ) -> str:
        path = renderer.render(item_id, page, title, blocks, section)
        return f"课件已生成并打开：{path.as_uri()}（共 {len(blocks)} 个块）"

    return Tool(
        "render_lesson",
        "Render an HTML lesson page and open it in the learner's browser. page=overview|"
        "section|summary (section needs `section`). Block types: explain{para,text} shows the "
        "original paragraph [P#] beside your Chinese explanation (section pages only); "
        "text{text}; note{text} highlighted key point; mermaid{code,caption?}; "
        "svg{svg,caption?} custom (animated) diagram; steps{frames:[{caption,code|svg|text}]} "
        "step-by-step player for processes; quiz{q,a}; deeper{title,text} collapsible detail.",
        {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "page": {"type": "string", "enum": ["overview", "section", "summary"]},
                "section": {"type": "integer"},
                "title": {"type": "string", "description": "page title, Chinese"},
                "blocks": {"type": "array", "items": BLOCK_SCHEMA},
            },
            "required": ["item_id", "page", "title", "blocks"],
        },
        render_lesson,
        read_only=False,
    )
