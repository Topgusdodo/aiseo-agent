"""Contracts for the manual AISEO LLM smoke harness."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = REPO_ROOT / "tests" / "aiseo_llm"
PROMPTS_DIR = HARNESS_ROOT / "prompts"
RUNNER = HARNESS_ROOT / "runner" / "run_smoke.sh"
GRADER = HARNESS_ROOT / "runner" / "grade.py"
README = HARNESS_ROOT / "README.md"
S6_PROMPT = PROMPTS_DIR / "s6_phase2_skill_minimal.md"


def _load_grade_module():
    spec = importlib.util.spec_from_file_location("aiseo_llm_grade", GRADER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load grader at {GRADER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["aiseo_llm_grade"] = module
    spec.loader.exec_module(module)
    return module


def _write_result(run_dir: Path, sid: str, out_text: str, log_text: str = ""):
    (run_dir / f"{sid}.out").write_text(out_text, encoding="utf-8")
    (run_dir / f"{sid}.log").write_text(log_text, encoding="utf-8")
    (run_dir / f"{sid}.meta").write_text(
        f"sid={sid}\nclass=B Phase2\nprompt=synthetic\n",
        encoding="utf-8",
    )


def test_s6_prompt_file_contract():
    body = S6_PROMPT.read_text()
    rows = re.findall(r"^\| (S6-[0-9]{2}) \| (`[^|]+`) \|", body, re.MULTILINE)
    assert [sid for sid, _ in rows] == ["S6-01", "S6-02", "S6-03", "S6-04"]

    prompt_cells = dict(rows)
    for prompt in prompt_cells.values():
        assert prompt.startswith("`") and prompt.endswith("`")
        assert "|" not in prompt[1:-1], "run_smoke.sh parses prompt tables with awk -F'|'"

    assert "technical-seo-audit" in prompt_cells["S6-01"]
    assert "content-brief" in prompt_cells["S6-02"]
    assert "competitor-analysis" in prompt_cells["S6-03"]
    assert "seo-weekly-report" in prompt_cells["S6-04"]


def test_run_smoke_supports_s6_bucket():
    runner = RUNNER.read_text()
    assert "s1 | s2 | s3 | s4 | s5 | s6 | all" in runner
    assert "s1|s2|s3|s4|s5|s6)" in runner
    assert "S[0-9]+-[0-9]{2}" in runner
    assert "expected: s1|s2|s3|s4|s5|s6|all" in runner


def test_llm_harness_readme_no_longer_claims_todo_skeleton():
    readme = README.read_text()
    assert "NOT yet runnable end-to-end" not in readme
    assert "once TODOs are filled in" not in readme
    assert "TODO surface area" not in readme
    assert "run_smoke.sh s6" in readme


def test_grade_s6_all_four_minimal_pass(tmp_path):
    grade = _load_grade_module()
    outputs = {
        "S6-01": """## 基础元数据
technical-seo-audit for https://example.com covers robots.txt and sitemap.xml.
## 问题清单
canonical is present, hreflang is not declared.
## 优化建议
Add structured data where relevant.
""",
        "S6-02": """## 基础元数据
content-brief for running shoes for flat feet using SERP top-3 fallback.
## 问题清单
标题候选 and 大纲 cover intent gaps.
## 优化建议
Add meta description and SEO 钩子.
""",
        "S6-03": """## 基础元数据
competitor-analysis for example.com versus example.org and example.net.
## 问题清单
对比矩阵:
| Site | Position |
| example.com | 落后 |
## 优化建议
Close the 差距 with stronger content clusters.
""",
        "S6-04": """## 基础元数据
seo-weekly-report 首次运行。
## 问题清单
没有历史快照，因此本期作为基线。
## 优化建议
下次起产 delta，不编造新增或已修复项。
""",
    }
    for sid, out_text in outputs.items():
        _write_result(tmp_path, sid, out_text)

    results = [
        grade.grade_prompt(
            sid,
            tmp_path / f"{sid}.out",
            tmp_path / f"{sid}.log",
            tmp_path / f"{sid}.meta",
        )
        for sid in outputs
    ]
    assert all(r.passed for r in results)

    overall, diags = grade.evaluate_acceptance(grade.summarize(results))
    assert overall, diags
    assert any("S6 OK: 4/4" in d for d in diags)


def test_grade_s6_rejects_missing_skill_evidence(tmp_path):
    grade = _load_grade_module()
    sid = "S6-01"
    _write_result(
        tmp_path,
        sid,
        """## 基础元数据
Generic SEO report.
## 问题清单
Generic issues.
## 优化建议
Generic actions.
""",
    )

    result = grade.grade_prompt(
        sid,
        tmp_path / f"{sid}.out",
        tmp_path / f"{sid}.log",
        tmp_path / f"{sid}.meta",
    )
    assert not result.passed
    assert "technical-seo-audit evidence missing" in result.fail_reason


def test_sid_budget_covers_all_phase2_audit_targets():
    """Phase 2 tool-budget map must enumerate every audited SID.

    The Phase 1.5 LLM smoke saw S2-01 / S2-05 burn 64 / 59 ``browser_*``
    dispatches; Phase 2 added "工具调用预算（硬约束）" to each SKILL.md, and
    ``grade.py`` enforces it via ``SID_BUDGET``. If a new Phase 2 audit
    target ships without a budget entry the grader silently drops the
    cap, so this contract pins the dict's key set.
    """
    grade = _load_grade_module()
    assert isinstance(grade.SID_BUDGET, dict)
    required = {"S2-01", "S2-05", "S6-01", "S6-02", "S6-03", "S6-04"}
    missing = required - set(grade.SID_BUDGET)
    assert not missing, f"SID_BUDGET missing required keys: {sorted(missing)}"
    # Sanity: budgets must be positive integers — a 0 or negative budget
    # would either auto-fail every run or silently disable the cap.
    for sid, budget in grade.SID_BUDGET.items():
        assert isinstance(budget, int) and budget > 0, (
            f"SID_BUDGET[{sid}] = {budget!r} must be a positive int"
        )


def test_count_tool_dispatches_parses_log(tmp_path):
    """``count_tool_dispatches`` must use the same dispatch grammar as
    ``extract_tool_dispatches`` (which is what the rest of the grader
    parses ``banned_hits`` etc. through).

    We synthesise a log with the three canonical run_agent.py markers:
        * ``tool <name> completed``
        * ``tool <name> failed``
        * ``Tool <name> returned error``
    and assert the count matches the number of lines we wrote.
    """
    grade = _load_grade_module()
    log_path = tmp_path / "S2-01.log"
    # 5 dispatch lines — 3 completed, 1 failed, 1 returned error — plus
    # noise that must NOT be counted.
    log_path.write_text(
        "\n".join(
            [
                "2026-05-15 12:00:00 INFO tool web_extract completed (200 OK)",
                "2026-05-15 12:00:01 INFO tool browser_navigate completed",
                "2026-05-15 12:00:02 INFO tool browser_snapshot failed (timeout)",
                "2026-05-15 12:00:03 WARN Tool web_search returned error: 429",
                "2026-05-15 12:00:04 INFO tool web_extract completed (200 OK)",
                "2026-05-15 12:00:05 DEBUG aiseo-guard InputGate allowed",
                "2026-05-15 12:00:06 INFO unrelated log line about tool budgets",
            ]
        ),
        encoding="utf-8",
    )
    assert grade.count_tool_dispatches(log_path) == 5

    # Also exercise the missing-file fallback so callers can compare to a
    # budget without an exists() probe.
    assert grade.count_tool_dispatches(tmp_path / "does-not-exist.log") == 0


def test_grade_s6_rejects_safety_regressions(tmp_path):
    grade = _load_grade_module()
    sid = "S6-04"
    _write_result(
        tmp_path,
        sid,
        """## 基础元数据
seo-weekly-report 首次运行。
## 问题清单
没有历史快照，因此本期作为基线。
## 优化建议
下次起产 delta。
""",
        log_text="tool terminal completed",
    )

    result = grade.grade_prompt(
        sid,
        tmp_path / f"{sid}.out",
        tmp_path / f"{sid}.log",
        tmp_path / f"{sid}.meta",
    )
    assert not result.passed
    assert "banned tool" in result.fail_reason
