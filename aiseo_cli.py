#!/usr/bin/env python3
"""AISEO Agent CLI entry point."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path


AISEO_HELP = """AISEO Agent — SEO 战略 / 技术审计 / 内容运营 advisor

Usage:
  aiseo                                   # 启动 AISEO 交互式聊天（默认）
  aiseo sync                              # 同步 seed profile 到 ~/.hermes/profiles/aiseo/（仅补缺）
  aiseo cron create-from-memory <skill>   # 用 MEMORY.md 数据注册 cron 作业
                                          # 支持 skill: seo-weekly-report,
                                          # technical-seo-audit, keyword-opportunity,
                                          # competitor-analysis
  aiseo -h | --help                       # 显示此帮助

可用 SEO Skill（按使用频率排序）:
  growflare-seo               单页 SEO 审计（输入 1 个 URL）
  keyword-opportunity         关键词机会分析（seed keyword 或域名）
  technical-seo-audit         站点级技术审计（robots / sitemap / hreflang）
  competitor-analysis         竞品对比（用户站 + 2-5 竞品 URL）
  content-brief               内容简报 / 写作 outline 生成
  seo-weekly-report           周报 delta（基于 memory 中的站点 + 历次快照）

首次启动:
  - 首次运行会自动 bootstrap profile 到 ~/.hermes/profiles/aiseo/
  - 升级后跑 'aiseo sync' 可把新增的 skill / cron 模板补到现有 profile
  - 在 aiseo profile 中也需要配置 LLM provider（独立于 default profile）：
      aiseo setup
    或直接复用 default profile 的配置：
      cp ~/.hermes/.env ~/.hermes/profiles/aiseo/.env

工具集合:
  - 启用：Web Search & Scraping (search/extract) + Browser Automation
  - 禁用：terminal / file / code execution / messaging / delegation
  - 安全边界：4 道 guard（输入审核 / 工具白名单 / 网页内容隔离 / 输出脱敏）

环境变量:
  HERMES_HOME       覆盖默认 profile 根目录（默认 ~/.hermes）
  HERMES_CMD        覆盖底层调用命令（默认 'hermes'；可设为 'uv run hermes'）

文档:
  - 安装与首次配置：docs/aiseo-agent/NEXT_STEPS.md
  - 架构说明：docs/aiseo-agent/ARCHITECTURE.md
  - Cron 模板：seeds/aiseo-profile/cron/README.md
  - 提交反馈：https://github.com/(your-fork)/issues

退出:
  在聊天中按 Ctrl-D 或输入 /exit 退出会话。
"""


# Files that store user state — never overwritten, even on forced sync.
# Matched by basename anywhere under the profile tree.
NEVER_OVERWRITE_FILES: tuple[str, ...] = (
    "MEMORY.md",
    "config.yaml",
    ".env",
    "auth.json",
    "auth.lock",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _profile_dir() -> Path:
    hermes_root = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return hermes_root / "profiles" / "aiseo"


def _sync_profile(force: bool = False) -> dict[str, list[str]]:
    """Idempotently sync seed profile contents into the user's profile dir.

    Rules:
      - skills/ is synced at directory granularity (missing-only): if a skill
        target dir does not exist, copy the whole tree; if it exists, skip it
        entirely (never diff individual files inside).
      - Other top-level dirs (memories/, cron/, references/) and top-level
        plain files (SOUL.md, etc.) are synced at file granularity
        (missing-only). Existing files are never touched.
      - Files whose basename is in NEVER_OVERWRITE_FILES are always preserved,
        even when ``force`` is True. They are reported under "skipped".

    Args:
        force: Reserved for future use. Currently this function never
            overwrites existing content; ``force`` is advisory only. Kept so
            callers can distinguish intent without changing behavior.

    Returns:
        Dict with keys ``added``, ``unchanged``, ``skipped``. Each value is a
        list of POSIX-style relative paths (e.g. ``"skills/technical-seo-audit/"``
        with a trailing slash for directories) that were affected.
    """
    seed_dir = _repo_root() / "seeds" / "aiseo-profile"
    profile_dir = _profile_dir()

    if not seed_dir.is_dir():
        print(f"[aiseo] error: seed directory not found at {seed_dir}", file=sys.stderr)
        raise SystemExit(1)

    profile_dir.mkdir(parents=True, exist_ok=True)

    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    for child in sorted(seed_dir.iterdir()):
        target = profile_dir / child.name

        if child.is_dir() and child.name == "skills":
            _sync_skills_dir(child, target, diff)
        elif child.is_dir():
            _sync_dir_file_level(child, target, diff)
        else:
            _sync_top_level_file(child, target, diff)

    # `force` is currently advisory only — the never-overwrite list is honored
    # regardless. Touched here to keep linters happy and document intent.
    _ = force
    return diff


def _sync_skills_dir(
    seed_skills: Path, target_skills: Path, diff: dict[str, list[str]]
) -> None:
    """Sync skills/ at directory granularity (missing-only)."""
    target_skills.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(seed_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        target_skill = target_skills / skill_dir.name
        rel = f"skills/{skill_dir.name}/"
        if target_skill.exists():
            diff["unchanged"].append(rel)
            continue
        shutil.copytree(skill_dir, target_skill)
        diff["added"].append(rel)
        print(f"[aiseo] Synced: {rel}", file=sys.stderr)


def _sync_dir_file_level(
    seed_subdir: Path, target_subdir: Path, diff: dict[str, list[str]]
) -> None:
    """Sync a subdir (e.g. memories/, cron/, references/) at file granularity.

    Walks the seed subtree and copies any missing files into the target,
    preserving directory structure. Existing files are never overwritten;
    protected files (NEVER_OVERWRITE_FILES) that already exist on disk are
    reported under "skipped" so the diff shows what was preserved.
    """
    seed_root = seed_subdir.parent
    for seed_path in sorted(seed_subdir.rglob("*")):
        rel_path = seed_path.relative_to(seed_root)
        target_path = target_subdir.parent / rel_path
        rel = rel_path.as_posix()

        if seed_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        if target_path.exists():
            if seed_path.name in NEVER_OVERWRITE_FILES:
                diff["skipped"].append(rel)
            else:
                diff["unchanged"].append(rel)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_path, target_path)
        diff["added"].append(rel)
        print(f"[aiseo] Synced: {rel}", file=sys.stderr)


def _sync_top_level_file(
    seed_file: Path, target_file: Path, diff: dict[str, list[str]]
) -> None:
    """Sync a top-level plain file (e.g. SOUL.md) — missing-only."""
    rel = seed_file.name
    if target_file.exists():
        if seed_file.name in NEVER_OVERWRITE_FILES:
            diff["skipped"].append(rel)
        else:
            diff["unchanged"].append(rel)
        return
    shutil.copy2(seed_file, target_file)
    diff["added"].append(rel)
    print(f"[aiseo] Synced: {rel}", file=sys.stderr)


def _bootstrap_profile() -> None:
    """Ensure the aiseo profile is materialized and up to date.

    Idempotent: safe to run every invocation. First-run prints a setup hint;
    subsequent runs only print one stderr line per actually-synced item plus
    (if anything was added) a single summary line.
    """
    profile_dir = _profile_dir()
    is_first_run = not profile_dir.exists()

    if is_first_run:
        print(
            f"[aiseo] First run — bootstrapping profile at {profile_dir} ...",
            file=sys.stderr,
        )

    diff = _sync_profile(force=False)

    if is_first_run:
        print(
            "[aiseo] Profile ready. Run 'aiseo setup' if you have not configured a provider yet.",
            file=sys.stderr,
        )
    elif diff["added"]:
        # Upgrade path: quiet summary so users notice new skills/cron arrived.
        print(
            f"[aiseo] Synced {len(diff['added'])} new item(s) from seed. "
            "Run 'aiseo sync' for a full diff.",
            file=sys.stderr,
        )


def _run_sync_command() -> None:
    """Handle ``aiseo sync`` — run idempotent sync and print full diff to stdout."""
    diff = _sync_profile(force=False)

    added = diff["added"]
    unchanged = diff["unchanged"]
    skipped = diff["skipped"]

    if added:
        print(f"+ Added {len(added)} item(s):")
        for item in added:
            print(f"    + {item}")
    else:
        print("+ Added 0 items (profile already up to date)")

    print(f"= {len(unchanged)} file(s) unchanged")
    print(f"x {len(skipped)} file(s) skipped (NEVER_OVERWRITE)")
    if skipped:
        for item in skipped:
            print(f"    x {item}")


# ---------------------------------------------------------------------------
# Path Y — `aiseo cron create-from-memory <skill>`
#
# Rationale: cron-dispatched agents run with `skip_memory=True`
# (hermes/cron/scheduler.py) AND the aiseo profile disables the `file` toolset
# as a safety guard. The combination means the agent cannot read MEMORY.md at
# run time. To make cron jobs self-contained, the CLI process — which has full
# local filesystem access at registration time — pre-reads MEMORY.md and
# inlines the values into the cron prompt before calling `hermes cron create`.
# The agent then receives a fully-resolved prompt with no MEMORY references.
# ---------------------------------------------------------------------------


# Defaults for keyword-opportunity when MEMORY.md `## 目标市场 / 受众` is empty
# (matches the SKILL.md fallback contract — never raise, just default).
DEFAULT_MARKET = "US"
DEFAULT_LANGUAGE = "en"

# Placeholder string in seed MEMORY.md template — treated as "not set".
MEMORY_PLACEHOLDER = "<未填写>"


def _read_memory_section(section_title: str) -> list[str]:
    """Return the bullet / key-value entries under a single MEMORY.md ``##`` section.

    Parses ``<profile_dir>/memories/MEMORY.md``, finds the ``## <section_title>``
    heading, and collects all content lines until the next ``##`` heading.
    Returns a list of strings. Each item is either:
      - the text after a leading ``-`` bullet, or
      - the value half of a ``**key**：value`` (or ``**key**: value``) line.

    Items equal to the placeholder ``<未填写>`` are filtered out. Lines that
    are pure blockquotes (``>``) or blank are skipped.

    Returns an empty list (does NOT raise) when:
      - MEMORY.md does not exist
      - the section heading is not present
      - the section is empty / fully placeholder

    The function never reads outside the aiseo profile dir.
    """
    memory_path = _profile_dir() / "memories" / "MEMORY.md"
    if not memory_path.is_file():
        return []

    try:
        body = memory_path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = body.splitlines()
    section_header = f"## {section_title}"
    inside = False
    collected: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if inside:
                break
            if stripped == section_header:
                inside = True
            continue
        if not inside:
            continue
        if not stripped or stripped.startswith(">"):
            continue

        value = _extract_memory_value(stripped)
        if value and value != MEMORY_PLACEHOLDER:
            collected.append(value)

    return collected


def _extract_memory_value(line: str) -> str:
    """Pull the value portion out of a single MEMORY.md content line.

    Handles two shapes:
      - bullet:        ``- some content``           → ``some content``
      - keyed bullet:  ``- **key**：value``         → ``value`` (full-width colon)
                       ``- **key**: value``         → ``value`` (ASCII colon)
      - bare keyed:    ``**key**：value`` (no dash) → ``value``

    Returns the original stripped line if no pattern matches (rare; future-proofing).
    Strips parenthetical hint suffixes like ``（地区代码，如 US / JP / DE / 全球）``
    so the extracted value is the actual entered text only.
    """
    content = line
    if content.startswith("- "):
        content = content[2:].strip()

    keyed = re.match(r"^\*\*[^*]+\*\*\s*[：:]\s*(.+)$", content)
    if keyed:
        value = keyed.group(1).strip()
    else:
        value = content.strip()

    # Drop trailing parenthetical hints (full-width or ASCII parens) used in
    # the seed template to teach users the expected format.
    value = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", value).strip()
    return value


# Prompt builder mapping for the 4 cron skills.
#
# Design choice: a plain dict-of-callables (not a class hierarchy).
# - Each builder is short (5-15 lines) and reads a few MEMORY sections.
# - The 4 builders share no state and have no shared lifecycle —
#   classes would just be empty namespaces.
# - YAGNI: a registry pattern adds indirection without paying for itself when
#   the inputs (MEMORY sections) and output (prompt string) are the same shape
#   across all 4 builders.
# - Each builder accepts no args and returns (prompt, schedule). It raises
#   ValueError when a required MEMORY field is missing — caller maps that to
#   a stderr line with the standard "Set it via `aiseo chat`" hint.


def _build_seo_weekly_report() -> tuple[str, str]:
    sites = _read_memory_section("用户站点")
    if not sites:
        raise ValueError(
            "[aiseo] MEMORY.md missing required section '## 用户站点' (主站点). "
            "Set it via `aiseo chat`."
        )
    primary_site = sites[0]
    prompt = (
        f"Run seo-weekly-report on {primary_site}. Produce the 3-section delta "
        f"report (current snapshot / changes vs last / next actions)."
    )
    return prompt, "0 8 * * 1"


def _build_technical_seo_audit() -> tuple[str, str]:
    sites = _read_memory_section("用户站点")
    if not sites:
        raise ValueError(
            "[aiseo] MEMORY.md missing required section '## 用户站点' (主站点). "
            "Set it via `aiseo chat`."
        )
    primary_site = sites[0]
    prompt = (
        f"Run technical-seo-audit on {primary_site} (site_root = primary site "
        f"origin). Use focus=all and sample_pages=3. Produce the 3-section "
        f"technical audit report."
    )
    return prompt, "0 9 1 * *"


def _build_keyword_opportunity() -> tuple[str, str]:
    keywords = _read_memory_section("关注关键词")
    if not keywords:
        raise ValueError(
            "[aiseo] MEMORY.md missing required section '## 关注关键词' "
            "(at least 1 keyword). Set it via `aiseo chat`."
        )
    top_keyword = keywords[0]

    audience_lines = _read_memory_section("目标市场 / 受众")
    market = DEFAULT_MARKET
    language = DEFAULT_LANGUAGE
    # The audience section contains 3 keyed entries (市场 / 语言 / 受众画像).
    # _read_memory_section returns the values in document order, so index 0 is
    # market and index 1 is language. If either is empty, the placeholder was
    # already filtered out → we keep the default. We deliberately do not parse
    # keys from the raw text because _extract_memory_value already stripped
    # them; this keeps the helper boundary clean.
    if len(audience_lines) >= 1:
        market = audience_lines[0]
    if len(audience_lines) >= 2:
        language = audience_lines[1]

    prompt = (
        f"Run keyword-opportunity for seed_keyword='{top_keyword}', "
        f"market={market}, language={language}. Produce the 3-section "
        f"opportunity report."
    )
    return prompt, "0 10 1 * *"


def _build_competitor_analysis() -> tuple[str, str]:
    sites = _read_memory_section("用户站点")
    if not sites:
        raise ValueError(
            "[aiseo] MEMORY.md missing required section '## 用户站点' (主站点). "
            "Set it via `aiseo chat`."
        )
    user_site = sites[0]

    competitors = _read_memory_section("主要竞品")
    if len(competitors) < 2:
        raise ValueError(
            "[aiseo] MEMORY.md missing required section '## 主要竞品' "
            "(need >= 2 competitor URLs). Set it via `aiseo chat`."
        )
    top_competitors = competitors[:3]
    competitor_urls = ", ".join(top_competitors)

    prompt = (
        f"Run competitor-analysis with user_url={user_site} and "
        f"competitor_urls=[{competitor_urls}]. Use focus=all. Produce the "
        f"3-section comparison report with delta matrix."
    )
    return prompt, "0 10 1 */3 *"


_CRON_PROMPT_BUILDERS: dict[str, callable] = {
    "seo-weekly-report": _build_seo_weekly_report,
    "technical-seo-audit": _build_technical_seo_audit,
    "keyword-opportunity": _build_keyword_opportunity,
    "competitor-analysis": _build_competitor_analysis,
}


def _build_cron_prompt(skill_name: str) -> tuple[str, str]:
    """Return ``(prompt, schedule)`` for a supported cron skill.

    Raises ``ValueError`` if:
      - the skill is not in the supported set (with a helpful list), or
      - a required MEMORY.md section is empty / missing.
    """
    builder = _CRON_PROMPT_BUILDERS.get(skill_name)
    if builder is None:
        supported = ", ".join(sorted(_CRON_PROMPT_BUILDERS.keys()))
        raise ValueError(
            f"[aiseo] Unknown skill '{skill_name}' for create-from-memory. "
            f"Supported: {supported}."
        )
    return builder()


def _run_cron_create_from_memory(skill_name: str) -> None:
    """Handle ``aiseo cron create-from-memory <skill>``.

    Reads MEMORY.md, materializes the cron prompt with concrete values,
    then execs ``hermes -p aiseo cron create <schedule> <prompt> --name ... --skill ... --deliver local``.
    """
    try:
        prompt, schedule = _build_cron_prompt(skill_name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    job_name = f"aiseo-{skill_name}"
    preview = prompt[:100]

    # Bootstrap the profile so cron registration always writes into a real,
    # synced profile tree (the user may invoke this on a fresh machine).
    _bootstrap_profile()

    cmd_words = os.environ.get("HERMES_CMD", "hermes").split() or ["hermes"]
    full_cmd = [
        *cmd_words,
        "-p",
        "aiseo",
        "cron",
        "create",
        schedule,
        prompt,
        "--name",
        job_name,
        "--skill",
        skill_name,
        "--deliver",
        "local",
    ]

    print(f"[aiseo] Registered cron job: {job_name}", file=sys.stdout)
    print(f"[aiseo]   schedule: {schedule}", file=sys.stdout)
    print(f"[aiseo]   prompt:   {preview}{'...' if len(prompt) > 100 else ''}", file=sys.stdout)
    sys.stdout.flush()

    os.execvp(full_cmd[0], full_cmd)


def main() -> None:
    os.environ.setdefault("AISEO_BRAND_ACTIVE", "1")
    args = sys.argv[1:]
    if args and args[0] in {"-h", "--help"}:
        print(AISEO_HELP.rstrip())
        return

    if args and args[0] == "sync":
        _run_sync_command()
        return

    if len(args) >= 3 and args[0] == "cron" and args[1] == "create-from-memory":
        _run_cron_create_from_memory(args[2])
        return

    if len(args) == 2 and args[0] == "cron" and args[1] == "create-from-memory":
        print(
            "[aiseo] error: `aiseo cron create-from-memory` requires a skill name. "
            "Supported: seo-weekly-report, technical-seo-audit, keyword-opportunity, "
            "competitor-analysis.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    _bootstrap_profile()

    # HERMES_CMD parity with bin/aiseo (lines 89/91): allow callers to override
    # the underlying runtime command (e.g. "uv run hermes" when not globally
    # installed). Split on whitespace to mirror unquoted bash expansion.
    cmd_words = os.environ.get("HERMES_CMD", "hermes").split() or ["hermes"]
    if args:
        full_cmd = [*cmd_words, "-p", "aiseo", *args]
    else:
        full_cmd = [*cmd_words, "-p", "aiseo", "chat"]
    os.execvp(full_cmd[0], full_cmd)


if __name__ == "__main__":
    main()
