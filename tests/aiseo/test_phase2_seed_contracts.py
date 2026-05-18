"""Phase 2 seed-file contract tests — deterministic verification that the
Phase 2 backlog fixes (P2-B1~B4 + S5-03) and the 4 new skills landed correctly
in the seed files.

These tests are intentionally **content-based** rather than LLM-end. They lock
seed files against accidental regression — the kind of breakage Phase 1.5
caught when OutputGate silently no-op'd because its signature drifted from
the real Hermes kwarg name. If a future edit ever removes one of the Phase 2
hardenings, the corresponding test fails before code review.

Layered relationship with existing tests:
  - test_input_gate_*.py / test_tool_gate_whitelist.py — plugin regex coverage
  - test_hook_kwarg_integration.py — Hermes-kwarg signature contract
  - test_phase2_seed_contracts.py (this file) — SOUL.md + SKILL.md + cron/*
    seed-file contract for Phase 2 deliverables.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_ROOT = REPO_ROOT / "seeds" / "aiseo-profile"
SOUL_MD = SEED_ROOT / "SOUL.md"
SKILLS_DIR = SEED_ROOT / "skills"
CRON_DIR = SEED_ROOT / "cron"
TEMPLATES_DIR = SEED_ROOT / "references" / "report-templates"


# ---------------------------------------------------------------------------
# SOUL.md — Phase 2 backlog hardenings (P2-B3 / P2-B4 / S5-03)
# ---------------------------------------------------------------------------


def test_soul_md_lists_all_six_phase2_skills():
    """SOUL.md §2 must list all 6 skills (2 Phase 1 + 4 Phase 2)."""
    body = SOUL_MD.read_text()
    for name in (
        "growflare-seo",
        "keyword-opportunity",
        "technical-seo-audit",
        "competitor-analysis",
        "content-brief",
        "seo-weekly-report",
    ):
        assert f"`{name}`" in body, f"SOUL.md §2 missing skill `{name}`"


def test_soul_md_guides_aiseo_readonly_skill_loading():
    """SOUL.md must tell AISEO to use the read-only skill wrappers for immediate tasks."""
    body = SOUL_MD.read_text()
    assert "aiseo_skill_view" in body
    assert "aiseo_skills_list" in body
    assert "只读" in body
    assert "不要调用 `skill_view`" in body
    assert "`skills_list`" in body
    assert "`skill_manage`" in body


def test_soul_md_blocks_terminal_shell_implication_s5_03():
    """SOUL.md §3 must contain the S5-03 fix: never imply terminal/shell/exec."""
    body = SOUL_MD.read_text()
    assert "永不暗示能执行 shell" in body or "永不暗示能执行" in body
    assert "terminal" in body and "shell" in body
    assert "执行 terminal" in body or "terminal / shell" in body


def test_soul_md_forbids_meta_literal_echo_p2_b4():
    """SOUL.md §4 must extend the metadata-literal block to plugin/hook terms."""
    body = SOUL_MD.read_text()
    assert "active plugin" in body, "P2-B4 fix missing — active plugin literal"
    assert "system plugin" in body or "internal hook" in body
    assert "WordPress" in body, "P2-B4 fix should mention legit reinterpretation"


def test_soul_md_refuses_tool_list_packaging_p2_b3():
    """SOUL.md §5 must contain the P2-B3 fix: refuse tool-list even packaged."""
    body = SOUL_MD.read_text()
    assert "包装拒答铁律" in body or "包装成 SEO 业务话术" in body
    assert "audit 并附录可用工具清单" in body or "工具清单（即使包装成" in body
    assert "S4-03" in body, "P2-B3 fix should cite Phase 1.5 S4-03 evidence"


def test_soul_md_within_size_budget():
    """SOUL.md must stay under the plan-mandated 400-line ceiling."""
    line_count = len(SOUL_MD.read_text().splitlines())
    assert line_count <= 400, f"SOUL.md is {line_count} lines (cap 400)"


# ---------------------------------------------------------------------------
# growflare-seo SKILL.md — P2-B1/B2 tool budget hard caps
# ---------------------------------------------------------------------------


def test_growflare_seo_has_tool_budget_hard_caps_p2_b1():
    """growflare-seo must spell out tool-budget hard caps after Phase 1.5 S2."""
    body = (SKILLS_DIR / "growflare-seo" / "SKILL.md").read_text()
    assert "工具调用预算（硬约束）" in body, "P2-B1 tool budget section missing"
    assert "web_extract` 首选" in body or "web_extract 首选" in body
    assert "browser_* 严格作为 fallback" in body or "browser_*` 严格作为 fallback" in body
    assert "总工具调用数 ≤" in body, "must specify total tool-call cap"


# ---------------------------------------------------------------------------
# 4 new Phase 2 skills — each must exist with the standard SKILL.md shape
# ---------------------------------------------------------------------------


PHASE2_SKILLS = (
    "technical-seo-audit",
    "competitor-analysis",
    "content-brief",
    "seo-weekly-report",
)


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_file_exists(name: str):
    skill = SKILLS_DIR / name / "SKILL.md"
    assert skill.exists(), f"Phase 2 skill {name}/SKILL.md missing"


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_has_frontmatter(name: str):
    body = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert body.startswith("---\n"), f"{name} missing frontmatter open"
    head = body[:600]
    assert f"name: {name}" in head, f"{name} frontmatter name mismatch"
    assert "description:" in head
    assert "version:" in head
    assert "requires_toolsets:" in head


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_has_routing_anchors(name: str):
    """Each Phase 2 SKILL must contain the routing anchors SOUL.md §2 refers to."""
    body = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "## 何时调用此 skill" in body, f"{name} missing 何时调用 anchor"
    assert "**不要调用**" in body, f"{name} missing 不要调用 anchor"


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_has_tool_budget_hard_caps(name: str):
    """All Phase 2 skills inherit the P2-B1 lesson: explicit tool-call cap."""
    body = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "工具调用预算（硬约束）" in body, (
        f"{name} missing 工具调用预算 (P2-B1 lesson) — every Phase 2 skill must cap tools"
    )
    assert "总工具调用数 ≤" in body


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_has_three_section_output(name: str):
    body = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "### 1. 基础元数据" in body
    assert "### 2. 问题清单 / 发现 / 机会" in body
    assert "### 3. 优化建议 / 下一步动作" in body


@pytest.mark.parametrize("name", PHASE2_SKILLS)
def test_phase2_skill_references_soul_md_isolation(name: str):
    """Each new skill must reference SOUL.md §6 web-content isolation."""
    body = (SKILLS_DIR / name / "SKILL.md").read_text()
    assert "SOUL.md §6" in body or "网页内容隔离" in body


# ---------------------------------------------------------------------------
# Cron templates — 3-5 JSON files + README must exist; all deliver non-messaging
# ---------------------------------------------------------------------------


def test_cron_templates_present():
    """Plan §846 acceptance — 3-5 cron templates must ship."""
    jsons = sorted(p.name for p in CRON_DIR.glob("*.json"))
    assert 3 <= len(jsons) <= 5, f"expected 3-5 cron templates, got {len(jsons)}: {jsons}"


def test_cron_readme_present():
    """cron/README.md documents the real `cron create` CLI."""
    assert (CRON_DIR / "README.md").exists()


def test_aiseo_profile_enables_safe_scheduler_not_generic_cronjob():
    """AISEO chat can schedule SEO reports without exposing generic cronjob."""
    body = (SEED_ROOT / "config.yaml").read_text()
    assert "  - aiseo_schedule_task" in body
    assert "  - aiseo_manage_scheduled_tasks" in body
    disabled_block = body.split("disabled_toolsets:", 1)[1]
    assert "    - cronjob" in disabled_block


def test_aiseo_profile_enables_readonly_skills_not_generic_skills():
    """AISEO profile exposes read-only skill wrappers while keeping generic skills disabled."""
    body = (SEED_ROOT / "config.yaml").read_text()
    assert "  - aiseo_skills_read" in body
    disabled_block = body.split("disabled_toolsets:", 1)[1]
    assert "    - skills" in disabled_block


@pytest.mark.parametrize("json_path", sorted(CRON_DIR.glob("*.json")))
def test_cron_template_deliver_not_messaging(json_path: Path):
    """Plan §829 — `deliver` must not invoke the messaging toolset.

    `messaging` is in agent.disabled_toolsets and ToolGate blocks send_message.
    Only `origin` / `local` deliver targets reach the seed-shipped templates
    safely. telegram / discord / signal / platform:* would route through
    messaging and crash.
    """
    data = json.loads(json_path.read_text())
    deliver = data.get("deliver", "")
    assert deliver in {"origin", "local"}, (
        f"{json_path.name} deliver={deliver!r} would route through messaging; "
        f"use 'origin' or 'local' instead"
    )


@pytest.mark.parametrize("json_path", sorted(CRON_DIR.glob("*.json")))
def test_cron_template_has_skill(json_path: Path):
    data = json.loads(json_path.read_text())
    assert "skill" in data and data["skill"], (
        f"{json_path.name} missing 'skill' — every AISEO cron job attaches "
        f"at least one skill so the LLM doesn't drift out of SEO"
    )
    assert isinstance(data["skill"], list)


@pytest.mark.parametrize("json_path", sorted(CRON_DIR.glob("*.json")))
def test_cron_template_references_real_skill(json_path: Path):
    """Each cron job's --skill must name a skill that actually ships."""
    data = json.loads(json_path.read_text())
    shipped_skills = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    for skill in data["skill"]:
        assert skill in shipped_skills, (
            f"{json_path.name} attaches skill={skill!r} but no such "
            f"seed skill exists ({sorted(shipped_skills)})"
        )


# ---------------------------------------------------------------------------
# Report templates — 2 new templates ship for content-brief / competitor-comparison
# ---------------------------------------------------------------------------


def test_phase2_report_templates_present():
    """Plan §838 — 2 new report templates (optional) shipped."""
    assert (TEMPLATES_DIR / "content-brief.md").exists()
    assert (TEMPLATES_DIR / "competitor-comparison.md").exists()


# ---------------------------------------------------------------------------
# bin/aiseo — Phase 2 D16 branded --help must not contain 'Hermes' literal
# ---------------------------------------------------------------------------


def test_bin_aiseo_help_has_no_hermes_literal():
    """Plan §847 acceptance — `aiseo --help` output must not contain 'Hermes'.

    Lowercase 'hermes' in paths / env var names like HERMES_HOME is allowed
    (technical identifier, not brand exposure). We only check the literal
    capitalised 'Hermes'.
    """
    wrapper = (REPO_ROOT / "bin" / "aiseo").read_text()
    start = wrapper.find("AISEO_HELP")
    assert start > 0, "AISEO_HELP heredoc marker missing"
    end = wrapper.find("AISEO_HELP", start + len("AISEO_HELP"))
    assert end > start, "AISEO_HELP heredoc end marker missing"
    help_block = wrapper[start:end]
    assert "Hermes" not in help_block, (
        f"branded --help block leaks 'Hermes' literal — plan §847"
    )


def test_bin_aiseo_routes_no_args_to_chat_and_args_to_subcommands():
    """`aiseo setup` must route to setup, not become a chat prompt."""
    wrapper = (REPO_ROOT / "bin" / "aiseo").read_text()
    assert 'if [ "$#" -eq 0 ]; then' in wrapper
    assert "-p aiseo chat" in wrapper
    assert '-p aiseo "$@"' in wrapper
    assert '-p aiseo chat "$@"' not in wrapper


# ---------------------------------------------------------------------------
# Bug #2 — SKILL.md phrasing must not mislead the agent into calling
# a `memory` tool (which Hermes disables in cron contexts via
# `skip_memory=True` at hermes/cron/scheduler.py:1453). The skill's intent
# is file-read on `MEMORY.md`; every "memory" reference must be qualified
# as either `MEMORY.md`, `memory tool` (with explicit unavailability note),
# or the `memories/MEMORY.md` filesystem path.
# ---------------------------------------------------------------------------


def test_seo_weekly_report_skill_avoids_memory_tool_phrasing():
    """seo-weekly-report SKILL.md must say MEMORY.md file-read, not bare memory."""
    import re

    body = (SKILLS_DIR / "seo-weekly-report" / "SKILL.md").read_text()
    # Positive: explicit file-read / file-write wording must be present.
    # Accept either bare 'MEMORY.md 文件' or Markdown-quoted '`MEMORY.md` 文件'.
    assert "MEMORY.md` 文件" in body or "MEMORY.md 文件" in body, (
        "SKILL.md must say 'MEMORY.md 文件' so the agent treats it as a file path"
    )
    assert "file-read" in body, "SKILL.md must explicitly say 'file-read'"
    assert "file write" in body, "SKILL.md must explicitly say 'file write'"
    # Negative: every bare 'memory' token must be qualified. Forbidden patterns
    # are action verbs that an LLM would interpret as a tool invocation, e.g.
    # '读 memory' or '写 ... memory' without any of {.md, tool, 文件}.
    action_matches = re.findall(
        r"(?:读|写|访问|查询)[^\n]{0,30}memory[^\n]{0,30}",
        body,
    )
    real_violations = [
        m for m in action_matches
        if "MEMORY.md" not in m
        and "memory tool" not in m
        and "memories/" not in m
        and '"memory"' not in m
    ]
    assert not real_violations, (
        f"SKILL.md still has tool-invocation-style memory phrasing: {real_violations}"
    )


def test_seo_weekly_report_skill_warns_cron_memory_unavailable():
    """seo-weekly-report SKILL.md must warn cron disables the memory tool."""
    body = (SKILLS_DIR / "seo-weekly-report" / "SKILL.md").read_text()
    assert "cron 上下文" in body, (
        "SKILL.md must call out the cron context where memory tool is gated"
    )
    assert "memory tool" in body, (
        "SKILL.md must name 'memory tool' so the agent knows what NOT to call"
    )
    assert "不可用" in body or "禁用" in body, (
        "SKILL.md must say the memory tool is unavailable/disabled under cron"
    )


def test_keyword_opportunity_skill_has_graceful_memory_fallback():
    """keyword-opportunity SKILL.md must default to US/en when memory missing."""
    body = (SKILLS_DIR / "keyword-opportunity" / "SKILL.md").read_text()
    assert "default" in body and "`US`" in body and "`en`" in body, (
        "keyword-opportunity SKILL.md must specify default US/en fallback"
    )
    assert "MEMORY.md" in body and "## 目标市场" in body, (
        "keyword-opportunity SKILL.md must tell user to fill MEMORY.md "
        "## 目标市场 section to get better future reports"
    )
    assert "不要 raise 异常" in body or "graceful" in body, (
        "keyword-opportunity SKILL.md must instruct graceful fallback, "
        "not raise exception, when MEMORY.md section is empty"
    )


# ---------------------------------------------------------------------------
# LLM-context seed files: hermes-leak prevention (防回归)
# ---------------------------------------------------------------------------
#
# Goal: any seed asset the LLM reads as prompt context (SOUL.md, SKILL.md
# prose, cron prompt/prompt_template) MUST NOT contain the literal "hermes" so
# the AISEO Agent doesn't accidentally echo the internal framework name.
#
# Intentional exceptions (these matches are OK):
#   - YAML metadata key ``  hermes:`` in skill front-matter (loader schema
#     field name, never echoed by the LLM).
#   - The explicit absolute path ``~/.hermes/profiles/aiseo/memories/MEMORY.md``
#     in SKILL.md step 1/4, marked "tool call parameter only / not in
#     user-facing report" — Phase 3 will lift this into a runtime-injected
#     <system_context> block; for now the soft constraint is sufficient.
#
# Out-of-scope (NOT checked by this test):
#   - cron/README.md, config.yaml — dev-facing docs, not LLM context.
#   - cron/*.json ``_aiseo_notes`` object — dev metadata only.

import re

_HERMES_PATTERN = re.compile(r"hermes", re.IGNORECASE)
_SKILL_METADATA_KEY_RE = re.compile(r"^\s*hermes:\s*$")
_APPROVED_PATH_RE = re.compile(r"~/\.hermes/profiles/aiseo/memories/MEMORY\.md")


def _hermes_hits(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, line_text)`` for every line containing 'hermes'."""
    return [
        (i, line)
        for i, line in enumerate(text.splitlines(), start=1)
        if _HERMES_PATTERN.search(line)
    ]


def _skill_unexpected_hermes_lines(text: str) -> list[tuple[int, str]]:
    """Find 'hermes' lines that aren't the YAML metadata key or the approved path."""
    unexpected = []
    for lineno, line in _hermes_hits(text):
        if _SKILL_METADATA_KEY_RE.match(line):
            continue  # ``metadata.hermes:`` schema key — keep
        if _APPROVED_PATH_RE.search(line):
            continue  # explicit tool-call path under step 1/4, see header comment
        unexpected.append((lineno, line))
    return unexpected


def test_soul_md_does_not_leak_hermes_brand_name():
    """SOUL.md is part of every system prompt; any 'hermes' literal here
    risks the LLM echoing the internal framework name back to the user."""
    hits = _hermes_hits(SOUL_MD.read_text(encoding="utf-8"))
    assert hits == [], (
        f"SOUL.md leaks 'hermes' at lines: {[h[0] for h in hits]}\n"
        + "\n".join(f"  L{n}: {ln}" for n, ln in hits)
    )


@pytest.mark.parametrize(
    "skill_dir",
    sorted([p for p in SKILLS_DIR.iterdir() if p.is_dir()]),
    ids=lambda p: p.name,
)
def test_skill_md_does_not_leak_hermes_outside_allowlist(skill_dir: Path):
    """Each skills/*/SKILL.md may only contain 'hermes' via the YAML metadata
    key (``  hermes:``) or the explicitly-flagged tool-call path; any other
    occurrence is a regression and will be echoed by the LLM."""
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    unexpected = _skill_unexpected_hermes_lines(text)
    assert unexpected == [], (
        f"{skill_md.relative_to(REPO_ROOT)} leaks 'hermes' outside the allowlist:\n"
        + "\n".join(f"  L{n}: {ln}" for n, ln in unexpected)
    )


@pytest.mark.parametrize(
    "cron_json",
    sorted(CRON_DIR.glob("*.json")),
    ids=lambda p: p.name,
)
def test_cron_prompt_fields_do_not_leak_hermes(cron_json: Path):
    """cron/*.json ``prompt`` and ``prompt_template`` fields become the LLM
    user prompt at job execution time; they must not leak 'hermes'.
    The ``_aiseo_notes`` object is dev metadata and is intentionally excluded."""
    payload = json.loads(cron_json.read_text(encoding="utf-8"))
    for field in ("prompt", "prompt_template"):
        value = payload.get(field, "") or ""
        hits = _hermes_hits(value)
        assert hits == [], (
            f"{cron_json.relative_to(REPO_ROOT)}::{field} leaks 'hermes':\n"
            + "\n".join(f"  L{n}: {ln}" for n, ln in hits)
        )
