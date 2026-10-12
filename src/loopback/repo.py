"""“用 loopback 学 loopback”：把本仓库的文件当学习材料（课程里 url 以 repo: 开头的条目）。

- markdown 文件（plan、decisions、CLAUDE.md）：和网页文章一样切节。
- Python 文件：按顶层函数和类切节，每节是一段带行号范围的代码，教师逐段讲解。
- 仓库文件开发期间一直在变，所以每次都重新读取，不写缓存。
"""

from __future__ import annotations

import ast
from pathlib import Path

from loopback.materials import Section, count_words, split_sections
from loopback.tools import ToolError

# src/loopback/repo.py -> 仓库根目录（只在源码仓库里运行时存在）
REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_file(url: str) -> Path:
    """把 repo:<相对路径> 解析成仓库内的文件路径，并确认没有跳出仓库。"""
    rel = url.removeprefix("repo:")
    path = (REPO_ROOT / rel).resolve()
    if not path.is_relative_to(REPO_ROOT) or not path.is_file():
        raise ToolError(f"仓库里找不到 {rel}（项目自学只能在 loopback 源码仓库里使用）")
    return path


def repo_sections(url: str, title: str) -> list[Section]:
    """读取仓库文件并切节：.py 按函数/类切，其余按 markdown 切。"""
    path = repo_file(url)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return code_sections(text)
    return split_sections(text, path.as_uri(), title)


def code_sections(source: str) -> list[Section]:
    """按顶层语句切 Python 源码：模块说明和导入合成一节，之后每个顶层函数或类各成一节。

    每节的标题带行号范围（例如“def run_turn（L40-L86）”），正文是一段带行号前缀的代码块。
    这样讲解时可以说“第 52 行”，和 code review 的习惯一致。
    """
    lines = source.splitlines()
    tree = ast.parse(source)
    # 1) 找出每个顶层函数/类的起止行（含装饰器），以及第一个定义之前的普通语句结束在哪一行
    spans: list[tuple[str, int, int]] = []
    header_end = 0  # “模块说明与导入”（docstring、import、常量）的最后一行
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            spans.append((f"{kind} {node.name}", start, node.end_lineno or start))
        elif not spans:
            header_end = node.end_lineno or node.lineno
    if not spans:  # 没有函数和类：整个文件一节
        header_end = len(lines)
    chunks = [("模块说明与导入", 1, header_end)] if header_end else []
    # 2) 定义之前的空行和注释，挂到这个定义上（注释通常是在说明下面的代码）
    for i, (name, start, end) in enumerate(spans):
        prev_end = spans[i - 1][2] if i else header_end
        chunks.append((name, min(start, prev_end + 1), end))
    # 3) 生成 Section：标题带行号范围，正文是带行号的代码块
    sections = []
    for name, start, end in chunks:
        body = "\n".join(f"{n:>4}| {lines[n - 1]}" for n in range(start, end + 1)).rstrip()
        para = f"```python\n{body}\n```"
        title = f"{name}（L{start}-L{end}）"
        sections.append(Section(len(sections) + 1, title, [para], words=count_words(para)))
    return sections
