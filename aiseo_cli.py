#!/usr/bin/env python3
"""AISEO Agent CLI entry point."""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import yaml

from utils import atomic_replace

logger = logging.getLogger(__name__)


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

# Seed-derived list fields that `_migrate_profile_config` will additively
# append to the user's profile config.yaml on every sync. The seed file is
# the single source of truth — when a new entry appears here in the seed,
# it propagates to old profiles automatically. Never deletes, never replaces.
#
# Add new dotted paths here when the seed introduces a new list-valued field
# that product changes (toolsets, plugins, disabled defenses) need to reach
# existing users through.
SEED_TRACKED_LIST_FIELDS: tuple[str, ...] = (
    "toolsets",
    "agent.disabled_toolsets",
    "plugins.enabled",
)

# Rolling backup retention for config.yaml mutations. Each successful write
# creates one timestamped .bak.<YYYYMMDD_HHMMSS> snapshot; older snapshots
# beyond this count are pruned.
MAX_CONFIG_BACKUPS = 5


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

    _migrate_profile_config(
        seed_dir / "config.yaml",
        profile_dir / "config.yaml",
        diff,
    )

    # `force` is currently advisory only — the never-overwrite list is honored
    # regardless. Touched here to keep linters happy and document intent.
    _ = force
    return diff


# Matches a YAML list item line at any indent: ``  - foo`` or ``- foo``.
# Used to detect end-of-list (first non-item line) and to extract item values.
# Tolerates trailing inline comments (``- foo  # note``).
_LIST_ITEM_LINE_RE = re.compile(r"^[ \t]*-[ \t]+(\S[^\n]*?)[ \t]*(?:#[^\n]*)?$", re.MULTILINE)

# Fallback indentation when a list block is empty (no existing items to mirror).
_FALLBACK_LIST_INDENT = "  "


def _find_list_block(text: str, dotted: str) -> "tuple[int, int, str] | None":
    """Locate the body of a YAML list at a dotted path.

    Supports up to one level of nesting:
      - ``"toolsets"``                — top-level list
      - ``"agent.disabled_toolsets"`` — list nested one level under ``agent:``
      - ``"plugins.enabled"``         — list nested one level under ``plugins:``

    Returns ``(items_start, items_end, item_indent)`` where:
      - ``items_start`` is the byte offset of the first character after the
        leaf key's header line (start of where items live).
      - ``items_end`` is the offset of the first non-blank/non-comment/non-item
        line (or end of text).
      - ``item_indent`` is the leading whitespace mirrored from the FIRST
        existing item in the block; falls back to leaf_key_indent + 2 spaces
        when the list is empty, then ``_FALLBACK_LIST_INDENT`` if nesting
        cannot be inferred.

    Returns ``None`` when:
      - the key (or its parent) is absent at the expected indent
      - the value is an inline scalar (``toolsets: web``) or inline array
        (``toolsets: [a, b]``) — neither is a parseable block list
      - YAML anchors / aliases (``&`` / ``*``) appear in the block body
    """
    parts = dotted.split(".")
    if len(parts) > 2:
        # Phase 1 only needs depth ≤ 2. Refuse silently to avoid wrong guesses.
        return None

    if "&" in text or "*" in text:
        # YAML anchors / aliases are rare in hand-edited configs but would
        # corrupt text-level edits. The check is intentionally broad — if any
        # anchor/alias char exists anywhere, we skip the whole migration for
        # this field. False positives are acceptable (warn + no-op).
        if _has_yaml_anchor(text):
            return None

    if len(parts) == 1:
        return _find_top_level_list(text, parts[0])

    # Nested (depth 2): find parent first, narrow window to its block, then
    # locate leaf inside the window.
    parent_key = parts[0]
    leaf_key = parts[1]
    parent_re = re.compile(
        rf"^{re.escape(parent_key)}:[ \t]*(?:#[^\n]*)?\n", re.MULTILINE
    )
    parent_match = parent_re.search(text)
    if parent_match is None:
        return None

    window_start = parent_match.end()
    window_end = _find_block_end(text, window_start, parent_indent=0)

    # Leaf key at ANY positive indent — don't pin to 2-space convention since
    # users may use tabs or 4-space indentation.
    leaf_re = re.compile(
        rf"^([ \t]+){re.escape(leaf_key)}:[ \t]*(?:#[^\n]*)?\n", re.MULTILINE
    )
    leaf_match = leaf_re.search(text, window_start, window_end)
    if leaf_match is None:
        return None

    leaf_indent = leaf_match.group(1)
    items_start = leaf_match.end()
    items_end = _scan_list_items_end(text, items_start, parent_indent=len(leaf_indent))
    item_indent = _detect_item_indent(text, items_start, items_end, leaf_indent)
    return items_start, items_end, item_indent


def _find_top_level_list(text: str, key: str) -> "tuple[int, int, str] | None":
    """Top-level (zero-indent) list block locator. Internal helper of `_find_list_block`."""
    header_re = re.compile(rf"^{re.escape(key)}:[ \t]*(?:#[^\n]*)?\n", re.MULTILINE)
    header = header_re.search(text)
    if header is None:
        return None
    items_start = header.end()
    items_end = _scan_list_items_end(text, items_start, parent_indent=0)
    item_indent = _detect_item_indent(text, items_start, items_end, leaf_indent="")
    return items_start, items_end, item_indent


def _scan_list_items_end(text: str, start: int, parent_indent: int) -> int:
    """Find offset where a list block ends.

    Walks forward from ``start``, tolerating blank lines and full-line comments,
    consuming list-item lines until the first line that is none of those AND
    has indent ≤ parent_indent (i.e. a sibling/parent key, end of this block).

    For top-level lists ``parent_indent`` is 0; any non-item line ends the block.
    """
    cursor = start
    while cursor < len(text):
        line_end = text.find("\n", cursor)
        if line_end == -1:
            line_end = len(text)
        line = text[cursor:line_end]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            cursor = line_end + 1
            continue

        # Is this a list item line?
        if re.match(r"^[ \t]*-[ \t\n]", line + "\n") or re.match(r"^[ \t]*-$", line):
            cursor = line_end + 1
            continue

        # Non-blank, non-comment, non-item: end of block.
        indent = len(line) - len(line.lstrip())
        if indent <= parent_indent:
            return cursor
        # Deeper indent of a non-list line shouldn't happen in valid YAML,
        # but be defensive — treat it as end-of-block to avoid swallowing
        # nested structures.
        return cursor
    return cursor


def _find_block_end(text: str, start: int, parent_indent: int) -> int:
    """Find offset where a *mapping* block ends — first sibling/parent key.

    Different from `_scan_list_items_end`: this is for the value-region under
    a mapping key (where children are key:value pairs, not list items).
    """
    cursor = start
    while cursor < len(text):
        line_end = text.find("\n", cursor)
        if line_end == -1:
            line_end = len(text)
        line = text[cursor:line_end]
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            indent = len(line) - len(line.lstrip())
            if indent <= parent_indent:
                return cursor
        cursor = line_end + 1
    return cursor


def _detect_item_indent(text: str, items_start: int, items_end: int, leaf_indent: str) -> str:
    """Pick the indent string for appending new items.

    Priority:
      1. First existing item's indent (preserve user style).
      2. ``leaf_indent`` + 2 spaces (typical YAML convention).
      3. ``_FALLBACK_LIST_INDENT``.
    """
    body = text[items_start:items_end]
    first = re.search(r"^([ \t]*)-", body, re.MULTILINE)
    if first:
        return first.group(1)
    if leaf_indent or leaf_indent == "":
        # Nested: indent two spaces deeper than the leaf key.
        # Top-level (leaf_indent=""): items typically flush-left or 2-indented;
        # default to 2-indent for consistency with the seed style.
        return leaf_indent + "  "
    return _FALLBACK_LIST_INDENT


def _parse_list_items(text: str, items_start: int, items_end: int) -> "list[str] | None":
    """Extract item values from a list block. Returns ``None`` on shape mismatch."""
    items: list[str] = []
    body = text[items_start:items_end]
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LIST_ITEM_LINE_RE.match(line + "\n")
        if match is None:
            # Lines that look like `-` with no value, or malformed — skip.
            # The block-locator already filtered the non-list-shape case; this
            # is just defensive.
            continue
        items.append(match.group(1).strip())
    return items


def _has_yaml_anchor(text: str) -> bool:
    """Return True if YAML anchor or alias syntax appears outside strings.

    Conservative scan: looks for ``&name`` or ``*name`` tokens at value
    positions. False positives are acceptable (caller treats as "skip").
    """
    return bool(
        re.search(r":\s+[&*][A-Za-z_]\w*", text)
        or re.search(r"^\s*-\s+[&*][A-Za-z_]\w*", text, re.MULTILINE)
    )


def _rolling_backup(target: Path, max_keep: int = MAX_CONFIG_BACKUPS) -> "Path | None":
    """Snapshot ``target`` to a timestamped ``.bak.<YYYYMMDD_HHMMSS>`` sibling.

    Prunes older backups beyond ``max_keep``. Also cleans up legacy
    single-slot ``config.yaml.bak`` files (no timestamp suffix) created by
    pre-Phase-1 versions. Returns the new backup path, or ``None`` on failure.
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    # `with_suffix` strips one extension — we want config.yaml → config.yaml.bak.<ts>.
    backup_path = target.parent / f"{target.name}.bak.{timestamp}"
    try:
        shutil.copy2(target, backup_path)
    except OSError as exc:
        logger.error(
            "AISEO config migration: backup to %s failed: %s", backup_path, exc
        )
        return None

    # Prune: glob matches both legacy single-slot bak and new timestamped baks.
    # Sort by FILENAME (not mtime): shutil.copy2 preserves the source's mtime,
    # so multiple backups taken in quick succession share an identical mtime
    # and the sort would be non-deterministic. Filename-based sort is reliable
    # because our naming convention encodes the timestamp in lexicographic order
    # — and the legacy `config.yaml.bak` (no suffix) sorts BEFORE any timestamped
    # sibling, so it gets pruned first when over capacity.
    siblings = sorted(
        target.parent.glob(f"{target.name}.bak*"),
        reverse=True,
    )
    for old in siblings[max_keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    return backup_path


def _migrate_profile_config(
    seed_cfg_path: Path,
    profile_cfg_path: Path,
    diff: dict[str, list[str]],
) -> bool:
    """Additively propagate seed list-field entries into the user's profile config.

    For each path in ``SEED_TRACKED_LIST_FIELDS``, compare the seed's list against
    the profile's; append any items the seed has but the profile is missing.
    Never deletes, never replaces scalars, never re-orders. The migration is
    **text-level** on the profile file — user comments, blank lines, and field
    order are preserved byte-for-byte.

    Strategy:
      1. Profile missing → fresh install, skip (the seed will be copied by
         ``_sync_top_level_file`` separately).
      2. Read seed via ``yaml.safe_load`` (read-only — we never write to seed).
      3. Read profile as UTF-8 text.
      4. For each tracked field, locate the list block in the profile text and
         compute the set-difference seed - profile.
      5. If anything is missing, append items with a ``# auto-added by aiseo
         sync <date>`` trailing comment so users can audit what changed.
      6. If changed: rolling timestamped backup + atomic write.

    Failure modes (each reported in ``diff["skipped"]``):
      - ``config.yaml:migration-non-utf8`` — profile not valid UTF-8
      - ``config.yaml:seed-unparseable`` — seed cannot be yaml-loaded
      - ``config.yaml:<field>:block-not-found`` — field absent in profile
      - ``config.yaml:backup-failed`` / ``:atomic-write-failed`` — IO failures
    """
    if not profile_cfg_path.exists():
        return False

    try:
        text = profile_cfg_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "AISEO config migration: %s is not valid UTF-8; skipping",
            profile_cfg_path,
        )
        diff["skipped"].append("config.yaml:migration-non-utf8")
        return False
    except OSError as exc:
        logger.error(
            "AISEO config migration: failed to read %s: %s", profile_cfg_path, exc
        )
        diff["skipped"].append("config.yaml:migration-unreadable")
        return False

    if not seed_cfg_path.exists():
        return False
    try:
        seed_data = yaml.safe_load(seed_cfg_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        logger.warning(
            "AISEO config migration: seed %s unparseable: %s",
            seed_cfg_path,
            exc,
        )
        diff["skipped"].append("config.yaml:seed-unparseable")
        return False

    today = time.strftime("%Y-%m-%d")
    new_text = text
    appended_records: list[tuple[str, str]] = []  # (dotted, item)

    for dotted in SEED_TRACKED_LIST_FIELDS:
        seed_items = _get_dotted(seed_data, dotted)
        if not isinstance(seed_items, list) or not seed_items:
            continue
        # Seed items must be strings to match the profile text-parser output.
        seed_items_str = [str(x) for x in seed_items if isinstance(x, (str, int, float))]

        block = _find_list_block(new_text, dotted)
        if block is None:
            diff["skipped"].append(f"config.yaml:{dotted}:block-not-found")
            continue

        items_start, items_end, item_indent = block
        profile_items = _parse_list_items(new_text, items_start, items_end)
        if profile_items is None:
            diff["skipped"].append(f"config.yaml:{dotted}:non-list-shape")
            continue

        missing = [x for x in seed_items_str if x not in profile_items]
        if not missing:
            continue

        # Build the appended text. Preserve a trailing newline guarantee:
        # `items_end` points to the start of the line AFTER the last item, so
        # we can safely insert right at items_end.
        addition = "".join(
            f"{item_indent}- {item}  # auto-added by aiseo sync {today}\n"
            for item in missing
        )
        new_text = new_text[:items_end] + addition + new_text[items_end:]

        for item in missing:
            appended_records.append((dotted, item))
            diff["added"].append(f"config.yaml:{dotted}/{item}")

    if not appended_records:
        return False

    backup = _rolling_backup(profile_cfg_path)
    if backup is None:
        # Backup failed — roll back diff bookkeeping so we don't pretend we wrote.
        for dotted, item in appended_records:
            try:
                diff["added"].remove(f"config.yaml:{dotted}/{item}")
            except ValueError:
                pass
        diff["skipped"].append("config.yaml:backup-failed")
        return False

    # Atomic write: tmp file + fsync + atomic_replace.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(profile_cfg_path.parent),
        prefix=f".{profile_cfg_path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace(tmp_path, profile_cfg_path)
    except BaseException as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        logger.error(
            "AISEO config migration: atomic write to %s failed: %s",
            profile_cfg_path,
            exc,
        )
        for dotted, item in appended_records:
            try:
                diff["added"].remove(f"config.yaml:{dotted}/{item}")
            except ValueError:
                pass
        diff["skipped"].append("config.yaml:atomic-write-failed")
        return False

    return True


def _get_dotted(data: dict, dotted: str) -> object:
    """Walk a dict by dotted path; return ``None`` if any segment is missing."""
    cursor: object = data
    for segment in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(segment)
    return cursor


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


def _refresh_soul_from_seed(
    profile_dir: Path,
    seed_dir: Path,
    interactive: bool = True,
) -> bool:
    """Back up and overwrite the profile's SOUL.md from the seed.

    SOUL.md drifts from seed when the seed gets new behavioral directives but
    sync's missing-only protection keeps the old profile copy in place. This is
    the explicit escape hatch — opt-in via ``aiseo sync --refresh-soul``.

    Backs up the current SOUL.md to ``SOUL.md.bak.<YYYYMMDD_HHMMSS>`` (so
    repeated calls don't clobber prior backups), then copies the seed version
    over. Returns ``True`` on success, ``False`` on user-cancel or IO failure.

    When ``interactive`` is True (default), prints a line-count diff summary
    and prompts ``Continue? [y/N]:``. ``-y / --yes`` flips ``interactive`` off.
    """
    source = seed_dir / "SOUL.md"
    target = profile_dir / "SOUL.md"

    if not source.exists():
        print(f"[aiseo] error: seed SOUL.md not found at {source}", file=sys.stderr)
        return False

    if target.exists():
        try:
            cur_lines = len(target.read_text(encoding="utf-8").splitlines())
            new_lines = len(source.read_text(encoding="utf-8").splitlines())
        except OSError as exc:
            print(f"[aiseo] error: cannot read SOUL.md: {exc}", file=sys.stderr)
            return False

        delta = new_lines - cur_lines
        sign = "+" if delta >= 0 else ""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = target.parent / f"SOUL.md.bak.{timestamp}"

        print(f"[aiseo] Current SOUL.md: {cur_lines} lines")
        print(f"[aiseo] Seed SOUL.md:    {new_lines} lines ({sign}{delta})")
        print("")
        print(f"This will:")
        print(f"  1. Back up to {backup_path.name}")
        print(f"  2. Overwrite with seed version")
        print("")

        if interactive:
            try:
                response = input("Continue? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                response = ""
            if response not in ("y", "yes"):
                print("[aiseo] Aborted; no changes made.")
                return False

        try:
            shutil.copy2(target, backup_path)
        except OSError as exc:
            print(f"[aiseo] error: backup to {backup_path.name} failed: {exc}", file=sys.stderr)
            return False
    else:
        # First-time creation — no backup needed.
        if interactive:
            print(f"[aiseo] Will create SOUL.md at {target}")

    try:
        shutil.copy2(source, target)
    except OSError as exc:
        print(f"[aiseo] error: failed to write SOUL.md: {exc}", file=sys.stderr)
        return False

    print("[aiseo] SOUL.md refreshed from seed.")
    return True


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Light-weight ``.env`` parser — KEY=VALUE per line, ``#`` comments, blank-line tolerant.

    Mirrors the subset of bash semantics that ``hermes_cli/config.py::load_env``
    handles for the AISEO profile. Strips surrounding single / double quotes
    but does NOT perform shell expansion (no ``$VAR`` interpolation).
    """
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    try:
        body = env_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return env
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"\'')
    return env


def _check_plugin_env_requirements(profile_dir: Path, repo_root: Path) -> None:
    """Warn (stderr) about env vars declared in enabled plugins' ``requires_env`` but missing.

    Resolution order for each var:
      1. profile's ``.env`` file
      2. process environment (``os.environ``)
    If neither has the var, it's reported. Plugins are read from the **profile's**
    ``config.yaml::plugins.enabled``, not the seed, so user disables propagate.

    Silent no-op when profile lacks a config or no plugins are enabled. Never
    blocks sync — pure advisory output.
    """
    config_path = profile_dir / "config.yaml"
    if not config_path.exists():
        return

    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return

    enabled = (cfg.get("plugins") or {}).get("enabled") or []
    if not enabled:
        return

    profile_env = _parse_env_file(profile_dir / ".env")

    missing: dict[str, list[str]] = {}
    for plugin_name in enabled:
        plugin_yaml = repo_root / "plugins" / str(plugin_name) / "plugin.yaml"
        if not plugin_yaml.exists():
            continue
        try:
            meta = yaml.safe_load(plugin_yaml.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, UnicodeDecodeError, OSError):
            continue
        for var in meta.get("requires_env") or []:
            var = str(var)
            if var not in profile_env and var not in os.environ:
                missing.setdefault(var, []).append(str(plugin_name))

    if not missing:
        return

    print("", file=sys.stderr)
    print("[aiseo] ⚠️  Missing env vars (required by enabled plugins):", file=sys.stderr)
    for var in sorted(missing):
        plugins_str = ", ".join(missing[var])
        print(f"          {var:25s}  required by: {plugins_str}", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"          Write to: {profile_dir / '.env'}", file=sys.stderr)
    print(f"          See:      docs/aiseo-agent/DEPLOYMENT.md (Known plugins credential list)", file=sys.stderr)


def _run_sync_command(sync_args: list[str]) -> None:
    """Handle ``aiseo sync`` — idempotent sync, full diff to stdout, env warnings.

    Flags:
      ``--refresh-soul``  Back up + overwrite profile SOUL.md from seed.
      ``-y`` / ``--yes``  Skip interactive confirmation for ``--refresh-soul``.
    """
    refresh_soul = False
    skip_confirm = False
    unknown: list[str] = []
    for arg in sync_args:
        if arg == "--refresh-soul":
            refresh_soul = True
        elif arg in ("-y", "--yes"):
            skip_confirm = True
        else:
            unknown.append(arg)
    if unknown:
        print(
            f"[aiseo] error: unknown sync flag(s): {' '.join(unknown)}\n"
            "Usage: aiseo sync [--refresh-soul] [-y|--yes]",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if refresh_soul:
        seed_dir = _repo_root() / "seeds" / "aiseo-profile"
        profile_dir = _profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        ok = _refresh_soul_from_seed(profile_dir, seed_dir, interactive=not skip_confirm)
        if not ok:
            raise SystemExit(1)
        return

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

    _check_plugin_env_requirements(_profile_dir(), _repo_root())


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
        _run_sync_command(args[1:])
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
