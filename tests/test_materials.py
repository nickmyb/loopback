from pathlib import Path

from loopback.extract import extract
from loopback.materials import MAX_SECTION_WORDS, count_words, split_sections

FIX = Path(__file__).parent / "fixtures"
BASE = "https://example.com/blog/post"


def sections():
    return split_sections((FIX / "sample.md").read_text(encoding="utf-8"), BASE)


def test_titles_follow_headings_and_merge_empty_parents() -> None:
    titles = [s.title for s in sections()]
    assert titles == [
        "Sample Article on Agents",  # 文首 H1 = 文档标题，导言归它
        "Building blocks › The augmented LLM",  # 空的父标题合并成路径
        "A very long section（1/2）",  # 超长按段落拆分
        "A very long section（2/2）",
        "中文小节",
    ]
    assert [s.index for s in sections()] == [1, 2, 3, 4, 5]


def test_code_block_with_blank_lines_and_hash_comment_stays_one_paragraph() -> None:
    llm = sections()[1]
    code = [p for p in llm.paras if p.startswith("```")]
    assert len(code) == 1 and "# this comment is code" in code[0] and "def loop" in code[0]


def test_links_are_absolute_numbered_and_deduplicated() -> None:
    intro, llm = sections()[0], sections()[1]
    assert intro.links == [
        {"id": "L1", "text": "guide", "url": "https://example.com/docs/guide"},
        {"id": "L2", "text": "home", "url": "https://example.com/"},
    ]
    assert [x["url"] for x in llm.links] == ["https://arxiv.org/abs/2210.03629"]  # 去重、跳过锚点
    assert llm.images == [
        {
            "id": "I1",
            "alt": "Augmented LLM diagram",
            "src": "https://example.com/images/augmented.png",
        }
    ]


def test_long_sections_respect_the_word_budget_and_cjk_counts() -> None:
    assert all(s.words <= MAX_SECTION_WORDS for s in sections())
    assert count_words("智能体 agent loop") == 5


def test_html_extraction_keeps_headings_images_links_and_drops_noise() -> None:
    ex = extract((FIX / "sample.html").read_text(encoding="utf-8"), BASE, "text/html")
    md = ex.markdown
    assert "## Part one" in md
    assert "[the next post](https://example.com/next)" in md
    assert "![Diagram](https://cdn.example.com/diagram.png)" in md  # Next.js 图片还原成原图
    assert "alert" not in md and "Copy" not in md and "Menu item" not in md and "Footer" not in md
    assert ex.title == "Sample Post"


def test_markdown_sources_pass_through() -> None:
    ex = extract("# Title\n\nbody", "https://code.claude.com/docs/en/overview.md")
    assert ex.markdown == "# Title\n\nbody" and ex.title == "Title"


def test_subsections_carry_their_parent_heading() -> None:
    md = "## Pattern 1\n\nintro\n\n### How it works\n\nA\n\n## Pattern 2\n\n### How it works\n\nB"
    assert [s.title for s in split_sections(md, BASE)] == [
        "Pattern 1",
        "Pattern 1 › How it works",
        "Pattern 2 › How it works",
    ]


def test_docs_site_banner_is_stripped_from_markdown_sources() -> None:
    md = (
        "> ## Documentation Index\n> Fetch the index at: https://x/llms.txt\n"
        "> Use this file to discover pages.\n\n# Real Title\n\n> Summary quote stays.\n\nBody."
    )
    ex = extract(md, "https://code.claude.com/docs/en/x.md")
    assert ex.markdown.startswith("# Real Title") and "Summary quote stays." in ex.markdown
    assert ex.title == "Real Title"


def words(n: int, w: str = "word") -> str:
    """一段恰好 n 个词的文字，用来精确控制切页。"""
    return " ".join([w] * n)


def test_thematic_breaks_are_not_content_and_never_form_a_page() -> None:
    md = f"# Doc\n\n{words(20)}\n\n---\n\n## A\n\n***\n\n## B\n\n{words(20)}\n\n___\n"
    secs = split_sections(md, BASE)
    assert [s.title for s in secs] == ["Doc", "B"]  # A 下面只有分隔线，不成页
    assert all(p.strip() not in ("---", "***", "___") for s in secs for p in s.paras)


def test_a_short_lead_in_stays_with_the_table_it_introduces() -> None:
    table = "| a | b |\n|---|---|\n" + "\n".join(f"| {words(10)} | x |" for _ in range(40))
    md = f"# Doc\n\n{words(300)}\n\nThe table below lists each step:\n\n{table}\n"
    first, second = split_sections(md, BASE)
    assert first.paras == [words(300)]
    assert second.paras[0] == "The table below lists each step:" and second.paras[1] == table


def test_a_short_tail_joins_the_previous_page() -> None:
    # 340 + 30 超出预算：旧规则会让 30 词的尾巴单独成第 3 页
    md = f"# Doc\n\n{words(340)}\n\n{words(340, 'more')}\n\n{words(30, 'tail')}\n"
    secs = split_sections(md, BASE)
    assert len(secs) == 2 and secs[-1].paras[-1] == words(30, "tail")  # 尾巴没有单独成页
