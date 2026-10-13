"""evals 本身也要被测试：oracle 必须满分、null 必须不及格，评审解析、统计、校准、报告都可复算。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_library import ITEM, md_fetch

from evals import scripted
from evals.calibrate import export, score
from evals.cases import Case, load_suite
from evals.graders import grade
from evals.harness import run_trial, snapshot_materials
from evals.judge import JudgeError, judge, parse
from evals.report import summarize_rows, write_report
from evals.stats import noise_floor, summarize, wilson
from loopback.curriculum import Curriculum
from loopback.library import Library
from loopback.llm import Response
from loopback.materials import SPLIT_VERSION

CUR = Curriculum([ITEM])  # 样例文章 s1：5 节，第 2 节有 3 段
SECTION = Case("s1-sec2", "s1", "section", section=2)
START = Case("s1-start", "s1", "start", say="我们学 Sample 吧")
FINISH = Case("s1-finish", "s1", "finish")


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    """预先把样例文章放进材料缓存（不联网），snapshot_materials 直接读缓存。"""
    home = tmp_path / "cache"
    Library(home, CUR, md_fetch()).get("s1")
    return home


def trial(case: Case, llm, tmp_path: Path, cache: Path, rep: int = 1):
    return run_trial(case, rep, tmp_path / "run", llm, {}, CUR, cache)


@pytest.mark.parametrize("case", [SECTION, START, FINISH])
def test_oracle_passes_every_code_check(case, tmp_path, cache) -> None:
    material = Library(cache, CUR).get("s1")
    g = grade(trial(case, scripted.oracle(case, material, CUR), tmp_path, cache))
    failed = {k: v for k, v in g.items() if v is False}
    assert g["pass"], f"oracle 应该满分，失败项：{failed}"
    if case.kind == "section":
        assert g["explain_coverage"] == 1.0


@pytest.mark.parametrize("case", [SECTION, START, FINISH])
def test_null_fails(case, tmp_path, cache) -> None:
    g = grade(trial(case, scripted.null(case), tmp_path, cache))
    assert not g["pass"] and not g["lesson_rendered"] and not g["terminal_brief"]


def test_trials_are_isolated_and_inputs_match_the_repl(tmp_path, cache) -> None:
    t1 = trial(SECTION, scripted.null(SECTION), tmp_path, cache, rep=1)
    t2 = trial(SECTION, scripted.null(SECTION), tmp_path, cache, rep=2)
    assert t1.home != t2.home and (t1.home / "library" / "s1").exists()
    assert "第 2 页" in t1.user_input  # 和 REPL 输入 next 时一样
    assert snapshot_materials([SECTION], CUR, cache)["s1"]  # 快照带 hash


def test_snapshot_is_resplit_when_the_split_rules_change(cache) -> None:
    snap = cache / "library" / "s1" / "sections.json"
    data = json.loads(snap.read_text("utf-8"))
    data.pop("split_version")  # 旧规则切的快照没有这个字段
    snap.write_text(json.dumps(data), encoding="utf-8")
    snapshot_materials([SECTION], CUR, cache)
    assert json.loads(snap.read_text("utf-8"))["split_version"] == SPLIT_VERSION


class FakeJudge:
    def __init__(self, text: str) -> None:
        self.text = text

    def stream(self, request, on_text):
        return Response(
            [{"type": "text", "text": self.text}],
            "end_turn",
            "judge-x",
            {"input_tokens": 1, "output_tokens": 1},
        )


def test_judge_scores_faithfulness_per_paragraph(tmp_path, cache) -> None:
    material = Library(cache, CUR).get("s1")
    t = trial(SECTION, scripted.oracle(SECTION, material, CUR), tmp_path, cache)
    verdict = {
        "paras": [{"para": 1, "faithful": True}, {"para": 2, "faithful": False}],
        "conclusion_first": True,
        "one_analogy": False,
        "terms_explained": True,
        "beginner_friendly": True,
    }
    j = judge(FakeJudge("好的：\n```json\n" + json.dumps(verdict) + "\n```"), "judge-x", t)
    paras = len(material.sections[1].paras)
    assert j["metrics"]["judge_faithfulness"] == pytest.approx(1 / paras)  # 漏判的段按不忠实
    assert j["metrics"]["judge_one_analogy"] is False and len(j["items"]) == paras
    with pytest.raises(JudgeError):
        parse("我觉得挺好")


def test_stats_bounds_and_noise_floor() -> None:
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.6 < lo < 0.8
    s = summarize([0.5, 1.0, 0.75])
    assert s["n"] == 3 and s["lo"] < s["mean"] < s["hi"]
    assert noise_floor(25, 4) == pytest.approx(0.1)


def test_report_and_calibration_round_trip(tmp_path, cache) -> None:
    material = Library(cache, CUR).get("s1")
    t = trial(SECTION, scripted.oracle(SECTION, material, CUR), tmp_path, cache)
    verdict = {"paras": [{"para": p, "faithful": True} for p in range(1, 4)]}
    j = judge(FakeJudge(json.dumps(verdict)), "judge-x", t)
    row = {
        "case": SECTION.id,
        "rep": 1,
        "kind": "section",
        "grades": grade(t),
        "usage": {},
        "latency_ms": 10,
        "cost_usd": 0.0,
        "judge": j["metrics"],
        "judge_items": j["items"],
    }
    run_dir = tmp_path / "run"
    (run_dir / "results.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize_rows([row], 1, 1)
    assert summary["metrics"]["pass"]["mean"] == 1.0  # 能从逐行结果复算
    manifest = {
        "suite": "t",
        "model": "m",
        "judge_model": "j",
        "reps": 1,
        "prompt_hash": "p",
        "git": "g",
        "materials": {},
    }
    html = write_report(run_dir, manifest, summary, [row], []).read_text("utf-8")
    assert "s1-sec2" in html and "render_lesson" in html  # 轨迹嵌在报告里
    labels = export(run_dir, 10)
    text = labels.read_text("utf-8").replace(",,1,", ",1,1,")  # 模拟人工全部标 1
    labels.write_text(text, encoding="utf-8")
    assert score(labels)["agreement"] == 1.0


def test_packaged_teacher_suite_is_valid() -> None:
    cases = load_suite("teacher")
    assert len(cases) >= 10 and {c.kind for c in cases} == {"section", "start", "finish"}
    with pytest.raises(ValueError, match="没有"):
        load_suite("teacher", ["nope"])


def test_section_numbers_in_the_teachers_own_words_fail(tmp_path, cache) -> None:
    material = Library(cache, CUR).get("s1")
    t = trial(SECTION, scripted.oracle(SECTION, material, CUR), tmp_path, cache)
    assert grade(t)["no_section_numbers"]
    bad = replace(t, final_text="对照第 14 节的里程碑表就能看出来。")  # 应该写原文标题（D29）
    assert not grade(bad)["no_section_numbers"] and not grade(bad)["pass"]
