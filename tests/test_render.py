"""HTML 课件：原文按段号插入、模型文本转义、SVG 消毒、块校验、目录与翻页、打分记录。"""

import json
from pathlib import Path

import pytest
from test_library import lib, md_fetch

from loopback.blocks import md
from loopback.feedback import feedback_tool, record_feedback
from loopback.render import LessonRenderer
from loopback.svg import sanitize_svg
from loopback.tools import ToolError, ToolSet


def renderer(tmp_path: Path, opened: list | None = None) -> LessonRenderer:
    """用样例文章（5 节）搭一个渲染器；opened 收集“打开浏览器”的调用。"""
    sink = opened if opened is not None else []
    return LessonRenderer(tmp_path, lib(tmp_path, md_fetch()), sink.append)


def test_section_page_puts_original_beside_explanation(tmp_path: Path) -> None:
    opened: list = []
    path = renderer(tmp_path, opened).render(
        "s1",
        "section",
        "增强型 LLM",
        section=2,
        blocks=[
            {"type": "explain", "para": 1, "text": "**一句话**：LLM 加上检索 <script>x</script>"},
            {"type": "mermaid", "code": 'flowchart LR\n  A["LLM"] --> B["工具 <b>"]'},
            {"type": "quiz", "q": "增强型 LLM 多了什么？", "a": "检索、工具、记忆"},
        ],
    )
    page = path.read_text(encoding="utf-8")
    assert path.name == "s02.html" and opened == [path]
    assert "An LLM with retrieval, tools and memory." in page  # 原文由代码插入
    assert "<strong>一句话</strong>" in page and "&lt;script&gt;" in page  # 模型文本转义
    assert "<script>x</script>" not in page
    assert '<pre class="mermaid">flowchart LR' in page and "工具 &lt;b&gt;" in page
    assert "第 2/5 页" in page and 'href="s01.html"' in page and 'href="s03.html"' in page


@pytest.mark.parametrize(
    ("blocks", "error"),
    [
        ([{"type": "explain", "para": 9, "text": "x"}], r"para 必须在 1\.\."),
        ([{"type": "text"}], "第 1 个块（text）缺少字段：text"),
        ([{"type": "video", "src": "x"}], "type='video' 不支持"),
        ([{"type": "mermaid", "code": "digraph G {}"}], "mermaid 类型无法识别"),
        ([{"type": "steps", "frames": [{"text": "only one"}]}], "2 到 12 帧"),
        ([{"type": "svg", "svg": "<svg><g></svg>"}], "不是合法的 XML"),
    ],
)
def test_bad_blocks_are_rejected_with_actionable_errors(tmp_path, blocks, error) -> None:
    with pytest.raises(ToolError, match=error):
        renderer(tmp_path).render("s1", "section", "t", blocks, section=2)


def test_explain_is_only_for_section_pages(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="只能用在 page=section"):
        renderer(tmp_path).render(
            "s1", "overview", "概览", [{"type": "explain", "para": 1, "text": "x"}]
        )


def test_svg_is_sanitized_but_animation_is_kept() -> None:
    dirty = (
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        "<script>alert(2)</script><foreignObject><div>x</div></foreignObject>"
        '<a href="https://evil.example"><circle r="5" onclick="x()"/></a>'
        '<rect width="10" height="10" style="fill:url(http://evil/x)">'
        '<animate attributeName="x" from="0" to="50" dur="2s" repeatCount="indefinite"/></rect>'
        '<use href="#ok"/></svg>'
    )
    clean = sanitize_svg(dirty)
    for bad in ("onload", "<script", "foreignObject", "evil.example", "onclick", "url(http"):
        assert bad not in clean
    assert "<animate" in clean and 'href="#ok"' in clean
    with pytest.raises(ToolError, match="根元素"):
        sanitize_svg("<div/>")


def test_steps_player_and_index_in_reading_order(tmp_path: Path) -> None:
    r = renderer(tmp_path)
    r.render("s1", "summary", "总结", [{"type": "text", "text": "回顾"}])
    r.render(
        "s1",
        "section",
        "工具调用的过程",
        [
            {
                "type": "steps",
                "frames": [
                    {"caption": "第一步", "text": "调用模型"},
                    {"caption": "第二步", "code": 'flowchart LR\n  A["工具"] --> B["结果"]'},
                ],
            }
        ],
        section=2,
    )
    r.render("s1", "overview", "概览", [{"type": "note", "text": "核心观点"}])
    folder = tmp_path / "lessons" / "s1"
    assert folder.joinpath("s02.html").read_text("utf-8").count('class="frame"') == 2
    index = folder.joinpath("index.html").read_text("utf-8")
    assert index.index("overview.html") < index.index("s02.html") < index.index("summary.html")


def test_feedback_is_appended_and_validated(tmp_path: Path) -> None:
    record_feedback(tmp_path, "s1", 2, 4, "讲得清楚")
    tool = ToolSet([feedback_tool(tmp_path)])
    assert tool.run("record_feedback", {"item_id": "s1", "section": 3, "score": 9}).is_error
    tool.run("record_feedback", {"item_id": "s1", "section": 3, "score": 5})
    rows = [json.loads(x) for x in (tmp_path / "feedback.jsonl").read_text("utf-8").splitlines()]
    assert [(r["section"], r["score"], r["source"]) for r in rows] == [
        (2, 4, "repl"),
        (3, 5, "agent"),
    ]


def test_mindmap_is_rejected_and_flowchart_is_suggested(tmp_path: Path) -> None:
    mindmap = "mindmap\n  root((loop.py))\n    1 模块说明\n    2 TurnResult"
    with pytest.raises(ToolError, match=r"mindmap.*节点互相压住.*flowchart LR"):
        renderer(tmp_path).render("s1", "overview", "概览", [{"type": "mermaid", "code": mindmap}])
    flow = 'flowchart LR\n  A["loop.py"] --> B["模块说明"]'
    renderer(tmp_path).render("s1", "overview", "概览", [{"type": "mermaid", "code": flow}])


def test_code_and_tables_stack_full_width_but_prose_stays_side_by_side(tmp_path: Path) -> None:
    blocks = [{"type": "explain", "para": p, "text": "讲解"} for p in (1, 3)]  # P3 是代码块
    page = renderer(tmp_path).render("s1", "section", "增强型 LLM", blocks, section=2).read_text()
    assert page.count('class="block explain wide"') == 1  # 只有代码块那段上下排
    assert page.count('class="block explain"') == 1


def test_br_in_table_cells_becomes_a_line_break_but_other_html_is_escaped() -> None:
    html_out = md(
        "| 怎么做 |\n|---|\n| 分类处理：<br>• API 错误<br/>• 工具异常 <script>x</script> |"
    )
    assert "分类处理：<br>• API 错误<br>• 工具异常" in html_out
    assert "<script>" not in html_out and "&lt;script&gt;" in html_out
