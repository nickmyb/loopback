from pathlib import Path

import pytest

from loopback.curriculum import KINDS, Curriculum, CurriculumError


def test_packaged_curriculum_is_valid() -> None:
    cur = Curriculum.load()
    assert len(cur.items) >= 70
    assert len(cur.by_id) == len(cur.items)  # id 唯一
    assert {i.kind for i in cur.items} <= KINDS
    assert cur.items[0].level == "PJ"  # 先学项目自身，再学官方文档
    bea = cur.by_id["ae-04"]
    assert bea.title == "Building Effective Agents" and bea.must and bea.date == "2024-12"
    assert any(i.evals for i in cur.items)


@pytest.mark.parametrize(
    ("yaml_text", "error"),
    [
        ("items:\n- {id: a, title: t, url: https://x, kind: blog, level: L2}", "缺少字段：group"),
        (
            "items:\n- {id: a, title: t, url: https://x, kind: blog, level: L2, group: g}\n"
            "- {id: a, title: t, url: https://y, kind: blog, level: L2, group: g}",
            "重复的 id",
        ),
        ("items:\n- {id: a, title: t, url: https://x, kind: tweet, level: L2, group: g}", "kind"),
        ("items:\n- {id: a, title: t, url: ftp://x, kind: blog, level: L2, group: g}", "http"),
    ],
)
def test_invalid_curriculum_is_rejected(tmp_path: Path, yaml_text: str, error: str) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(CurriculumError, match=error):
        Curriculum.load(path)


def test_search_finds_items_by_title_keywords_and_typos() -> None:
    cur = Curriculum.load()
    assert cur.search("Building Effective Agents")[0].id == "ae-04"
    assert cur.search("building-effective-agents")[0].id == "ae-04"
    assert cur.search("agents md")[0].id == "cx-agents-md"
    assert cur.search("Bulding Efective Agent")[0].id == "ae-04"  # 拼写错误
    assert cur.search("zzz-not-there") == []


def test_unknown_id_error_suggests_the_closest_items() -> None:
    from loopback.tools import ToolError

    with pytest.raises(ToolError, match=r"最接近的是：\[ae-04\] Building Effective Agents"):
        Curriculum.load().get("building-effective-agents")
