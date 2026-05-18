"""Deterministic tests for the Python ``uv run aiseo`` entry point."""

from __future__ import annotations

import os
import re
import sys

import pytest

import aiseo_cli


def _run_entrypoint(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> tuple[str, list[str]]:
    """Run ``aiseo_cli.main`` with a fake ``os.execvp`` and return (file, argv)."""
    captured: list[tuple[str, list[str]]] = []

    def _fake_execvp(file: str, argv: list[str]) -> None:
        captured.append((file, list(argv)))

    monkeypatch.setattr(aiseo_cli.os, "execvp", _fake_execvp)
    monkeypatch.setattr(aiseo_cli, "_bootstrap_profile", lambda: None)
    monkeypatch.setattr(sys, "argv", ["aiseo", *argv])

    aiseo_cli.main()

    assert captured, "os.execvp was not called"
    return captured[0]


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        ([], ["hermes", "-p", "aiseo", "chat"]),
        (["setup"], ["hermes", "-p", "aiseo", "setup"]),
        (["tools"], ["hermes", "-p", "aiseo", "tools"]),
        (["cron", "list"], ["hermes", "-p", "aiseo", "cron", "list"]),
        (["setup", "--help"], ["hermes", "-p", "aiseo", "setup", "--help"]),
    ),
)
def test_aiseo_cli_route_b_parity(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected: list[str],
):
    """No args enter chat; explicit args passthrough as profile-scoped subcommands."""
    monkeypatch.delenv("HERMES_CMD", raising=False)
    file, full = _run_entrypoint(monkeypatch, argv)
    assert file == "hermes"
    assert full == expected


@pytest.mark.parametrize("help_arg", ["-h", "--help"])
def test_aiseo_cli_branded_help_short_circuits_bootstrap_and_runtime(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    help_arg: str,
):
    """Top-level help must be branded and must not bootstrap or exec the runtime."""
    bootstrap_called = False

    def _bootstrap() -> None:
        nonlocal bootstrap_called
        bootstrap_called = True

    def _fake_execvp(file: str, argv: list[str]) -> None:
        raise AssertionError("help path should not call os.execvp")

    monkeypatch.setattr(aiseo_cli.os, "execvp", _fake_execvp)
    monkeypatch.setattr(aiseo_cli, "_bootstrap_profile", _bootstrap)
    monkeypatch.setattr(sys, "argv", ["aiseo", help_arg])

    aiseo_cli.main()

    out = capsys.readouterr().out
    assert "AISEO Agent" in out
    assert "aiseo setup" in out
    assert "Hermes" not in out
    assert not bootstrap_called


def test_aiseo_cli_bootstrap_message_points_to_aiseo_setup(tmp_path, monkeypatch, capsys):
    """First-run guidance must match Route B user-facing setup command."""
    seed_dir = tmp_path / "seeds" / "aiseo-profile"
    seed_dir.mkdir(parents=True)
    (seed_dir / "SOUL.md").write_text("AISEO", encoding="utf-8")

    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    aiseo_cli._bootstrap_profile()

    err = capsys.readouterr().err
    assert "Run 'aiseo setup'" in err
    assert "Run 'hermes setup'" not in err


@pytest.mark.parametrize(
    ("hermes_cmd", "argv", "expected_file", "expected_argv"),
    (
        # Single-word override: still execs that binary directly.
        ("hermes-dev", [], "hermes-dev", ["hermes-dev", "-p", "aiseo", "chat"]),
        # Multi-word override (the documented "uv run hermes" case): split on
        # whitespace so HERMES_CMD env actually takes effect at the Python entry
        # point, matching bin/aiseo bash semantics.
        (
            "uv run hermes",
            ["setup"],
            "uv",
            ["uv", "run", "hermes", "-p", "aiseo", "setup"],
        ),
    ),
)
def test_aiseo_cli_hermes_cmd_env_override(
    monkeypatch: pytest.MonkeyPatch,
    hermes_cmd: str,
    argv: list[str],
    expected_file: str,
    expected_argv: list[str],
):
    """HERMES_CMD env must override the underlying runtime command (parity with bin/aiseo)."""
    monkeypatch.setenv("HERMES_CMD", hermes_cmd)
    file, full = _run_entrypoint(monkeypatch, argv)
    assert file == expected_file
    assert full == expected_argv


def test_aiseo_cli_hermes_cmd_empty_falls_back_to_hermes(monkeypatch: pytest.MonkeyPatch):
    """Empty HERMES_CMD must not crash; fall back to the default 'hermes' binary."""
    monkeypatch.setenv("HERMES_CMD", "   ")
    file, full = _run_entrypoint(monkeypatch, [])
    assert file == "hermes"
    assert full == ["hermes", "-p", "aiseo", "chat"]


# ---------------------------------------------------------------------------
# Profile sync tests (Bug #1: aiseo_cli.py profile skill sync gap)
# ---------------------------------------------------------------------------

# Skills shipped in seeds/aiseo-profile/skills/ as of Phase 2 — used by the
# sync tests to assert that all six are materialized into a fresh profile.
SEED_SKILL_NAMES = (
    "growflare-seo",
    "keyword-opportunity",
    "technical-seo-audit",
    "competitor-analysis",
    "content-brief",
    "seo-weekly-report",
)


def _build_fake_seed(tmp_path):
    """Materialize a synthetic seed tree mirroring seeds/aiseo-profile/ shape.

    Returns the repo-root path that ``_repo_root`` should be monkey-patched to.
    """
    seed_dir = tmp_path / "seeds" / "aiseo-profile"
    (seed_dir / "skills").mkdir(parents=True)
    for skill in SEED_SKILL_NAMES:
        skill_dir = seed_dir / "skills" / skill
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"# {skill}\nseed default content\n", encoding="utf-8"
        )

    (seed_dir / "memories").mkdir()
    (seed_dir / "memories" / "MEMORY.md").write_text(
        "seed memory placeholder\n", encoding="utf-8"
    )
    (seed_dir / "memories" / "USER.md").write_text(
        "seed user placeholder\n", encoding="utf-8"
    )

    (seed_dir / "cron").mkdir()
    (seed_dir / "cron" / "weekly-audit.json").write_text(
        '{"name": "weekly-audit"}\n', encoding="utf-8"
    )

    (seed_dir / "references").mkdir()
    (seed_dir / "references" / "seo-audit-checklist.md").write_text(
        "seed checklist\n", encoding="utf-8"
    )

    (seed_dir / "SOUL.md").write_text("seed SOUL\n", encoding="utf-8")
    (seed_dir / "config.yaml").write_text(
        "toolsets:\n"
        "  - web\n"
        "  - search\n"
        "  - browser\n"
        "  - aiseo_skills_read\n"
        "  - aiseo_schedule_task\n"
        "  - aiseo_manage_scheduled_tasks\n"
        "agent:\n"
        "  disabled_toolsets:\n"
        "    - terminal\n"
        "    - code_execution\n"
        "    - delegation\n"
        "    - cronjob\n"
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n"
        "    - dataforseo\n",
        encoding="utf-8",
    )

    return tmp_path


def test_sync_fresh_install_copies_all_skills(tmp_path, monkeypatch):
    """Fresh install: profile dir does not exist; bootstrap materializes all 6 skills."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    aiseo_cli._bootstrap_profile()

    profile_skills = tmp_path / ".hermes" / "profiles" / "aiseo" / "skills"
    assert profile_skills.is_dir()
    for skill in SEED_SKILL_NAMES:
        assert (profile_skills / skill / "SKILL.md").is_file(), (
            f"expected skill '{skill}' to be materialized"
        )

    # Top-level plain files also land.
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    assert (profile_dir / "SOUL.md").is_file()
    assert (profile_dir / "config.yaml").is_file()


def test_sync_upgrade_only_adds_missing_skills(tmp_path, monkeypatch):
    """Upgrade path: profile pre-exists with one skill; sync adds the other five
    and never overwrites the user's customized growflare-seo/SKILL.md."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    # Pre-create the profile with ONLY growflare-seo, holding user-modified content.
    profile_skills = tmp_path / ".hermes" / "profiles" / "aiseo" / "skills"
    profile_skills.mkdir(parents=True)
    user_skill_dir = profile_skills / "growflare-seo"
    user_skill_dir.mkdir()
    user_content = "# growflare-seo (USER EDITED)\ncustom workflow notes\n"
    (user_skill_dir / "SKILL.md").write_text(user_content, encoding="utf-8")

    diff = aiseo_cli._sync_profile(force=False)

    # Five new skills got copied in; growflare-seo stayed unchanged.
    new_skills = set(SEED_SKILL_NAMES) - {"growflare-seo"}
    added_skills = {
        item.rstrip("/").split("/")[-1]
        for item in diff["added"]
        if item.startswith("skills/")
    }
    assert added_skills == new_skills, (
        f"expected added skills {new_skills}, got {added_skills}"
    )
    assert "skills/growflare-seo/" in diff["unchanged"]

    # The user's customized content survived.
    assert (user_skill_dir / "SKILL.md").read_text(encoding="utf-8") == user_content


def test_sync_never_overwrite_protected_files(tmp_path, monkeypatch):
    """Protected files (MEMORY.md, .env) with user content must survive sync."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    (profile_dir / "memories").mkdir(parents=True)
    user_memory = "## user-specific notes\nsite=example.com\n"
    (profile_dir / "memories" / "MEMORY.md").write_text(user_memory, encoding="utf-8")
    user_env = "OPENAI_API_KEY=sk-redacted\n"
    (profile_dir / ".env").write_text(user_env, encoding="utf-8")

    diff = aiseo_cli._sync_profile(force=False)

    # Files preserved on disk verbatim.
    assert (profile_dir / "memories" / "MEMORY.md").read_text(encoding="utf-8") == user_memory
    assert (profile_dir / ".env").read_text(encoding="utf-8") == user_env

    # .env is not shipped in the fake seed, so it never enters the diff —
    # protection means "don't overwrite if present". MEMORY.md is in the seed,
    # so it appears under skipped.
    assert "memories/MEMORY.md" in diff["skipped"]


def test_sync_migrates_existing_config_with_aiseo_skills_read(tmp_path, monkeypatch):
    """Existing AISEO profile config is user state, but safe toolset additions are merged."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    config_path = profile_dir / "config.yaml"
    config_path.write_text(
        "model: user-model\n"
        "toolsets:\n"
        "  - web\n"
        "  - browser\n"
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n",
        encoding="utf-8",
    )

    diff = aiseo_cli._sync_profile(force=False)
    body = config_path.read_text(encoding="utf-8")

    # User-set scalar field preserved verbatim.
    assert "model: user-model" in body
    # Seed-tracked list field: missing items appended without dups.
    assert "- aiseo_skills_read" in body
    assert "- aiseo_schedule_task" in body
    assert "- aiseo_manage_scheduled_tasks" in body
    assert "- search" in body
    assert body.count("- aiseo_skills_read") == 1
    # Items already present (web, browser) not duplicated.
    assert body.count("- web") == 1
    assert body.count("- browser") == 1
    # Auto-added-by comment so users can audit propagation.
    assert "# auto-added by aiseo sync" in body
    # Diff bookkeeping reflects each appended item.
    assert "config.yaml:toolsets/aiseo_skills_read" in diff["added"]
    assert "config.yaml:toolsets/aiseo_schedule_task" in diff["added"]
    # plugins.enabled in profile has aiseo-guard; seed adds dataforseo too.
    assert "config.yaml:plugins.enabled/dataforseo" in diff["added"]

    # Idempotent: re-running sync does not re-append.
    second = aiseo_cli._sync_profile(force=False)
    body2 = config_path.read_text(encoding="utf-8")
    assert body2.count("- aiseo_skills_read") == 1
    assert "config.yaml:toolsets/aiseo_skills_read" not in second["added"]


def test_sync_config_migration_skips_non_list_toolsets(tmp_path, monkeypatch):
    """Malformed/custom toolsets shapes are preserved instead of rewritten."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    config_path = profile_dir / "config.yaml"
    original = "toolsets: web\ncustom: keep\n"
    config_path.write_text(original, encoding="utf-8")

    diff = aiseo_cli._sync_profile(force=False)

    assert config_path.read_text(encoding="utf-8") == original
    # Phase 1: skip reason is now per-field "<dotted>:block-not-found" since
    # multiple fields are tracked. Inline scalar `toolsets: web` fails the
    # header regex which requires no value after the colon.
    assert "config.yaml:toolsets:block-not-found" in diff["skipped"]


def test_sync_command_prints_diff(tmp_path, monkeypatch):
    """_sync_profile returns a dict with added/unchanged/skipped keys of correct type."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    diff = aiseo_cli._sync_profile(force=False)

    assert set(diff.keys()) == {"added", "unchanged", "skipped"}
    for key, value in diff.items():
        assert isinstance(value, list), f"diff['{key}'] should be a list, got {type(value)}"
        for item in value:
            assert isinstance(item, str), (
                f"diff['{key}'] entries should be str, got {type(item)}"
            )

    # Fresh install: every seed item appears in "added"; nothing pre-existed.
    assert len(diff["added"]) > 0
    assert len(diff["skipped"]) == 0


# ---------------------------------------------------------------------------
# _migrate_profile_config — text-level, atomic, backed-up migration
#
# These tests target the H_new1 / H_new2 / M_new1 fixes:
#   - H_new1: regex-based append must preserve user comments, blank lines,
#             field order, and not parse YAML.
#   - H_new2: atomic write must leave the original file untouched on failure.
#   - M_new1: .bak snapshot must be created before each destructive write.
# ---------------------------------------------------------------------------


def _make_profile_with_config(tmp_path, body: str):
    """Materialize ~/.hermes/profiles/aiseo/config.yaml with ``body`` content."""
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True, exist_ok=True)
    config_path = profile_dir / "config.yaml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _make_seed_config(tmp_path, body: str | None = None):
    """Materialize seeds/aiseo-profile/config.yaml with ``body`` (default: a
    minimal seed exposing all three SEED_TRACKED_LIST_FIELDS for migration tests).
    """
    seed_dir = tmp_path / "seeds" / "aiseo-profile"
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_cfg = seed_dir / "config.yaml"
    if body is None:
        body = (
            "toolsets:\n"
            "  - web\n"
            "  - search\n"
            "  - browser\n"
            "  - aiseo_skills_read\n"
            "agent:\n"
            "  disabled_toolsets:\n"
            "    - terminal\n"
            "plugins:\n"
            "  enabled:\n"
            "    - aiseo-guard\n"
        )
    seed_cfg.write_text(body, encoding="utf-8")
    return seed_cfg


def _backup_files(config_path):
    """Return all rolling-backup paths for ``config_path`` (.bak.<ts> siblings)."""
    return sorted(config_path.parent.glob(f"{config_path.name}.bak*"))


def test_migrate_config_preserves_comments_and_blank_lines(tmp_path):
    """H_new1: comment + blank-line + field-order preservation, byte-for-byte."""
    original = (
        "# my custom model setup\n"
        "model: gpt-4.1                # locked for cost\n"
        "\n"
        "# === toolsets section ===\n"
        "toolsets:\n"
        "  - web                       # search backend\n"
        "  - browser\n"
        "  # explanatory mid-list note\n"
        "  - search\n"
        "\n"
        "agent:\n"
        "  disabled_toolsets:\n"
        "    - terminal\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is True
    result = config_path.read_text(encoding="utf-8")

    # All original lines survive in order with byte-identical comments.
    for line in original.splitlines():
        assert line in result, f"missing original line: {line!r}"

    # The required toolset was appended exactly once, at the END of the
    # toolsets block (before `agent:`), with the expected two-space indent.
    assert result.count("- aiseo_skills_read") == 1
    toolsets_idx = result.index("toolsets:")
    appended_idx = result.index("  - aiseo_skills_read")
    agent_idx = result.index("agent:")
    assert toolsets_idx < appended_idx < agent_idx

    # Header comment block preserved verbatim at the top.
    assert result.startswith("# my custom model setup\n")
    # Inline comment on the model line preserved.
    assert "model: gpt-4.1                # locked for cost" in result
    # Blank lines preserved (no YAML re-serialization collapsed them).
    assert "\n\n# === toolsets section ===\n" in result
    # Mid-list explanatory comment preserved.
    assert "  # explanatory mid-list note\n" in result


def test_migrate_config_atomic_write_safety_on_replace_failure(tmp_path, monkeypatch):
    """H_new2: when atomic_replace raises mid-migration, the original file is untouched."""
    original = "toolsets:\n  - web\n  - browser\n"
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    def _boom(tmp, target):  # pragma: no cover - failure path
        raise OSError("simulated disk full")

    monkeypatch.setattr(aiseo_cli, "atomic_replace", _boom)

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is False
    # CRITICAL invariant: original file content is byte-identical.
    assert config_path.read_text(encoding="utf-8") == original
    # No phantom "added" bookkeeping should leak when the write failed.
    assert "config.yaml:toolsets/aiseo_skills_read" not in diff["added"]
    assert "config.yaml:atomic-write-failed" in diff["skipped"]
    # No tmp file should be left behind in the profile dir.
    leftovers = [p for p in config_path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == [], f"tmp files leaked on failure path: {leftovers}"


def test_migrate_config_creates_backup_before_write(tmp_path):
    """Phase 1: a timestamped .bak.<ts> snapshot is created on successful write."""
    original = (
        "# user-owned config\n"
        "toolsets:\n"
        "  - web\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    assert changed is True

    backups = _backup_files(config_path)
    assert len(backups) == 1, f"expected exactly one rolling backup, got {backups}"
    assert backups[0].name.startswith("config.yaml.bak."), (
        f"backup should use timestamped pattern; got {backups[0].name}"
    )
    assert backups[0].read_text(encoding="utf-8") == original, (
        "rolling backup must be a byte-identical snapshot of the pre-migration file"
    )

    # Idempotent no-op runs do NOT create additional backups.
    second_diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}
    second_changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, second_diff)
    assert second_changed is False
    assert _backup_files(config_path) == backups


def test_migrate_config_non_utf8_silent_skip_no_destruction(tmp_path):
    """Non-UTF-8 body: logger.warning + skip, original bytes preserved."""
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    config_path = profile_dir / "config.yaml"
    raw_bytes = b"\xff\xfe\x00\x00not utf-8 at all"
    config_path.write_bytes(raw_bytes)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is False
    # File still exists and bytes are unchanged.
    assert config_path.is_file()
    assert config_path.read_bytes() == raw_bytes
    assert "config.yaml:migration-non-utf8" in diff["skipped"]
    # No phantom adds, no backup churn (legacy single-slot OR timestamped).
    assert diff["added"] == []
    assert _backup_files(config_path) == []


def test_migrate_config_handles_zero_indent_toolsets_list(tmp_path):
    """Regression: real user configs (e.g. inherited from hermes default profile)
    use 0-indent block-list syntax (``- web`` flush left) under the ``toolsets:``
    key. The migration must recognize this as a list AND preserve the indent
    style when appending — not silently skip or force a 2-indent rewrite.

    See: real user report 2026-05-18 — `aiseo sync` reported "top-level
    toolsets list not found" on a config that had a perfectly valid 0-indent
    toolsets block.
    """
    original = (
        "# user config inherited from hermes default profile\n"
        "model:\n"
        "toolsets:\n"
        "- web\n"
        "- search\n"
        "- browser\n"
        "agent:\n"
        "  max_turns: 90\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is True, (
        "0-indent toolsets list was not recognized — see diff: " + repr(diff)
    )
    result = config_path.read_text(encoding="utf-8")

    # All original lines preserved.
    for line in original.splitlines():
        assert line in result, f"missing original line: {line!r}"

    # Appended item must use SAME indent (0) as existing items, not the
    # hardcoded 2-space default — keeps the file visually consistent.
    # Phase 1: appended items now carry an `# auto-added by ...` trailing
    # comment, so match on the leading prefix not the trailing newline.
    assert re.search(r"^- aiseo_skills_read\s+#", result, re.MULTILINE), (
        "Appended item should use 0-indent matching existing items; got:\n" + result
    )
    assert "  - aiseo_skills_read" not in result, (
        "Should NOT use 2-indent when user's existing list is 0-indent"
    )
    # And only appended once.
    assert result.count("- aiseo_skills_read") == 1

    # Diff bookkeeping correct.
    assert "config.yaml:toolsets/aiseo_skills_read" in diff["added"]
    assert not any(s.startswith("config.yaml:toolsets:block-not-found") for s in diff["skipped"])


def test_migrate_config_idempotent_under_zero_indent(tmp_path):
    """Running migration twice on a 0-indent config must be a no-op the
    second time — does not re-append aiseo_skills_read."""
    original = (
        "toolsets:\n"
        "- web\n"
        "- aiseo_skills_read\n"
        "- search\n"
        "- browser\n"
        "agent:\n"
        "  disabled_toolsets:\n"
        "    - terminal\n"
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    # Seed exactly matches what the profile already has — so nothing missing.
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is False, (
        "Migration should be a no-op when all seed items already present"
    )
    result = config_path.read_text(encoding="utf-8")
    assert result.count("- aiseo_skills_read") == 1


def test_migrate_config_toolsets_key_completely_missing_is_skip(tmp_path):
    """Top-level `toolsets:` absent: migration must NOT invent the structure
    (for that field), but other tracked fields with matching profile blocks
    can still be migrated independently.
    """
    original = (
        "model: claude-sonnet-4-5\n"
        "agent:\n"
        "  toolsets:                  # nested, not top-level — must be ignored\n"
        "    - file\n"
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    # Top-level `toolsets:` field is genuinely missing in the profile, so the
    # migration reports `block-not-found` for it. `agent.disabled_toolsets`
    # is also missing as a sibling of `agent.toolsets`, so it skips too.
    # `plugins.enabled` is present and unchanged (seed and profile match).
    assert "config.yaml:toolsets:block-not-found" in diff["skipped"]
    assert "aiseo_skills_read" not in config_path.read_text(encoding="utf-8")
    # The `agent.toolsets:` nested block (under agent:) must not have been
    # interpreted as a top-level toolsets target.
    assert "    - file" in config_path.read_text(encoding="utf-8")
    # No legacy single-slot backup file.
    assert not (config_path.parent / "config.yaml.bak").exists()


# ---------------------------------------------------------------------------
# Phase 1 — Seed-derived additive migration for nested fields
# ---------------------------------------------------------------------------


def test_migrate_config_nested_disabled_toolsets_additive(tmp_path):
    """agent.disabled_toolsets: seed has [terminal, delegation, cronjob];
    profile has [terminal] → migration appends the other two preserving the
    user's 4-space child indent."""
    original = (
        "agent:\n"
        "  max_turns: 90\n"
        "  disabled_toolsets:\n"
        "    - terminal\n"
        "  other_setting: keep_me\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(
        tmp_path,
        body=(
            "agent:\n"
            "  disabled_toolsets:\n"
            "    - terminal\n"
            "    - delegation\n"
            "    - cronjob\n"
        ),
    )
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    assert changed is True

    result = config_path.read_text(encoding="utf-8")
    # User's sibling setting must survive.
    assert "  other_setting: keep_me\n" in result
    # Appended items use the SAME 4-space indent as existing items.
    assert re.search(r"^    - delegation\s+#", result, re.MULTILINE)
    assert re.search(r"^    - cronjob\s+#", result, re.MULTILINE)
    # Inserted into the list block, NOT below other_setting.
    delegation_idx = result.index("- delegation")
    other_idx = result.index("other_setting")
    assert delegation_idx < other_idx
    # Diff reflects each addition.
    assert "config.yaml:agent.disabled_toolsets/delegation" in diff["added"]
    assert "config.yaml:agent.disabled_toolsets/cronjob" in diff["added"]


def test_migrate_config_nested_plugins_enabled_additive(tmp_path):
    """plugins.enabled: seed adds dataforseo; profile has only aiseo-guard."""
    original = (
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(
        tmp_path,
        body=(
            "plugins:\n"
            "  enabled:\n"
            "    - aiseo-guard\n"
            "    - dataforseo\n"
        ),
    )
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    result = config_path.read_text(encoding="utf-8")

    assert "- dataforseo" in result
    assert result.count("- aiseo-guard") == 1
    assert "config.yaml:plugins.enabled/dataforseo" in diff["added"]


def test_migrate_config_multiple_fields_in_one_pass(tmp_path):
    """A single migration call covers all SEED_TRACKED_LIST_FIELDS at once."""
    original = (
        "toolsets:\n"
        "  - web\n"
        "agent:\n"
        "  disabled_toolsets:\n"
        "    - terminal\n"
        "plugins:\n"
        "  enabled:\n"
        "    - aiseo-guard\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(
        tmp_path,
        body=(
            "toolsets:\n"
            "  - web\n"
            "  - aiseo_skills_read\n"
            "agent:\n"
            "  disabled_toolsets:\n"
            "    - terminal\n"
            "    - cronjob\n"
            "plugins:\n"
            "  enabled:\n"
            "    - aiseo-guard\n"
            "    - dataforseo\n"
        ),
    )
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    assert changed is True

    result = config_path.read_text(encoding="utf-8")
    assert "- aiseo_skills_read" in result
    assert "- cronjob" in result
    assert "- dataforseo" in result
    # One write → one backup, regardless of how many fields got items added.
    assert len(_backup_files(config_path)) == 1


def test_migrate_config_inline_array_in_profile_is_skipped(tmp_path):
    """Profile using `toolsets: [a, b]` flow-style array fails the header
    regex (which requires no value after the colon) and is reported skipped
    rather than normalized — conservative choice to avoid changing the user's
    chosen style."""
    original = "toolsets: [web, search]\nagent:\n  max_turns: 90\n"
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is False
    assert config_path.read_text(encoding="utf-8") == original
    assert "config.yaml:toolsets:block-not-found" in diff["skipped"]


def test_migrate_config_yaml_anchor_in_profile_is_skipped(tmp_path):
    """Conservative guard: anchors/aliases (`&` / `*`) anywhere in the file
    skip the migration entirely — text-level edits could corrupt the document."""
    original = (
        "defaults: &defaults\n"
        "  timeout: 30\n"
        "toolsets:\n"
        "  - web\n"
        "settings: *defaults\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)

    assert changed is False
    # File untouched.
    assert config_path.read_text(encoding="utf-8") == original


def test_migrate_config_appended_items_carry_audit_comment(tmp_path):
    """Each auto-appended item gets a `# auto-added by aiseo sync <YYYY-MM-DD>`
    inline comment so users can audit propagation later."""
    config_path = _make_profile_with_config(
        tmp_path,
        "toolsets:\n  - web\n",
    )
    seed_cfg = _make_seed_config(
        tmp_path,
        body="toolsets:\n  - web\n  - search\n",
    )
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    result = config_path.read_text(encoding="utf-8")

    assert re.search(
        r"- search\s+# auto-added by aiseo sync \d{4}-\d{2}-\d{2}\b",
        result,
    ), f"audit comment missing or malformed:\n{result}"


def test_migrate_config_seed_unparseable_skips_gracefully(tmp_path):
    """Corrupt seed YAML → skip + diff entry, profile untouched."""
    original = "toolsets:\n  - web\n"
    config_path = _make_profile_with_config(tmp_path, original)
    seed_cfg = _make_seed_config(tmp_path, body="toolsets: [unclosed\n")
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(seed_cfg, config_path, diff)
    assert changed is False
    assert config_path.read_text(encoding="utf-8") == original
    assert "config.yaml:seed-unparseable" in diff["skipped"]


def test_rolling_backup_prunes_beyond_max_keep(tmp_path, monkeypatch):
    """After MAX_CONFIG_BACKUPS + 2 writes, only MAX newest backups remain."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("initial\n", encoding="utf-8")

    timestamps = iter(
        f"20260101_{i:02d}0000" for i in range(1, 99)
    )

    def _fake_strftime(_fmt):
        return next(timestamps)

    monkeypatch.setattr(aiseo_cli.time, "strftime", _fake_strftime)

    for _ in range(aiseo_cli.MAX_CONFIG_BACKUPS + 2):
        result = aiseo_cli._rolling_backup(config_path)
        assert result is not None and result.exists()

    backups = sorted(config_path.parent.glob(f"{config_path.name}.bak*"))
    assert len(backups) == aiseo_cli.MAX_CONFIG_BACKUPS, (
        f"expected {aiseo_cli.MAX_CONFIG_BACKUPS} backups, got {len(backups)}: {backups}"
    )


def test_rolling_backup_cleans_up_legacy_single_slot(tmp_path, monkeypatch):
    """Pre-Phase-1 `config.yaml.bak` (no timestamp) must be picked up by
    the rolling glob and pruned once MAX is exceeded."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("body\n", encoding="utf-8")
    legacy = config_path.parent / "config.yaml.bak"
    legacy.write_text("old single-slot snapshot\n", encoding="utf-8")
    # Force the legacy file to be the OLDEST so it gets pruned first.
    very_old = 1.0
    os.utime(legacy, (very_old, very_old))

    timestamps = iter(f"20260101_{i:02d}0000" for i in range(1, 99))
    monkeypatch.setattr(aiseo_cli.time, "strftime", lambda _f: next(timestamps))

    # Create exactly MAX new timestamped backups → total = MAX + 1 (with legacy);
    # the legacy slot should be pruned to bring count back to MAX.
    for _ in range(aiseo_cli.MAX_CONFIG_BACKUPS):
        aiseo_cli._rolling_backup(config_path)

    survivors = sorted(config_path.parent.glob("config.yaml.bak*"))
    assert legacy not in survivors, "legacy single-slot bak should have been pruned"
    assert len(survivors) == aiseo_cli.MAX_CONFIG_BACKUPS


# ---------------------------------------------------------------------------
# Phase 1 — `aiseo sync --refresh-soul`
# ---------------------------------------------------------------------------


def _make_profile_and_seed_souls(tmp_path, profile_body: str, seed_body: str):
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "SOUL.md").write_text(profile_body, encoding="utf-8")
    seed_dir = tmp_path / "seeds" / "aiseo-profile"
    seed_dir.mkdir(parents=True, exist_ok=True)
    (seed_dir / "SOUL.md").write_text(seed_body, encoding="utf-8")
    return profile_dir, seed_dir


def test_refresh_soul_non_interactive_overwrites_and_backs_up(tmp_path, monkeypatch):
    """`-y` skips the prompt, backup is created, file content == seed."""
    profile_dir, seed_dir = _make_profile_and_seed_souls(
        tmp_path,
        profile_body="profile soul old\n",
        seed_body="seed soul new and longer\n",
    )
    # Freeze timestamp for deterministic backup name.
    monkeypatch.setattr(aiseo_cli.time, "strftime", lambda _f: "20260518_120000")

    ok = aiseo_cli._refresh_soul_from_seed(profile_dir, seed_dir, interactive=False)
    assert ok is True

    soul = (profile_dir / "SOUL.md").read_text(encoding="utf-8")
    assert soul == "seed soul new and longer\n"

    backup = profile_dir / "SOUL.md.bak.20260518_120000"
    assert backup.is_file()
    assert backup.read_text(encoding="utf-8") == "profile soul old\n"


def test_refresh_soul_interactive_y_proceeds(tmp_path, monkeypatch):
    profile_dir, seed_dir = _make_profile_and_seed_souls(
        tmp_path,
        profile_body="old\n",
        seed_body="new\n",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    ok = aiseo_cli._refresh_soul_from_seed(profile_dir, seed_dir, interactive=True)
    assert ok is True
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "new\n"


def test_refresh_soul_interactive_n_aborts(tmp_path, monkeypatch):
    profile_dir, seed_dir = _make_profile_and_seed_souls(
        tmp_path,
        profile_body="old\n",
        seed_body="new\n",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    ok = aiseo_cli._refresh_soul_from_seed(profile_dir, seed_dir, interactive=True)
    assert ok is False
    # Profile untouched; no backup written.
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "old\n"
    assert list(profile_dir.glob("SOUL.md.bak*")) == []


def test_refresh_soul_eof_treated_as_no(tmp_path, monkeypatch):
    """Ctrl-D / piped stdin EOF must abort, not proceed."""
    profile_dir, seed_dir = _make_profile_and_seed_souls(
        tmp_path,
        profile_body="old\n",
        seed_body="new\n",
    )

    def _raise_eof(_prompt):
        raise EOFError()

    monkeypatch.setattr("builtins.input", _raise_eof)
    ok = aiseo_cli._refresh_soul_from_seed(profile_dir, seed_dir, interactive=True)
    assert ok is False
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "old\n"


def test_refresh_soul_seed_missing_errors(tmp_path):
    """No seed SOUL.md → error + return False, no profile change."""
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    (profile_dir / "SOUL.md").write_text("intact\n", encoding="utf-8")
    seed_dir = tmp_path / "seeds" / "aiseo-profile"
    seed_dir.mkdir(parents=True)
    # NO seed SOUL.md written.

    ok = aiseo_cli._refresh_soul_from_seed(profile_dir, seed_dir, interactive=False)
    assert ok is False
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "intact\n"


# ---------------------------------------------------------------------------
# Phase 1 — Plugin env requirement detection
# ---------------------------------------------------------------------------


def _make_profile_for_env_check(tmp_path, *, plugin_names, env_body=""):
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    enabled_lines = "\n".join(f"    - {name}" for name in plugin_names)
    (profile_dir / "config.yaml").write_text(
        f"plugins:\n  enabled:\n{enabled_lines}\n",
        encoding="utf-8",
    )
    if env_body:
        (profile_dir / ".env").write_text(env_body, encoding="utf-8")
    return profile_dir


def _make_plugin(tmp_path, name, requires_env):
    plugin_dir = tmp_path / "plugins" / name
    plugin_dir.mkdir(parents=True)
    req_lines = "\n".join(f"  - {v}" for v in requires_env)
    body = f"name: {name}\nversion: 0.1.0\n"
    if requires_env:
        body += f"requires_env:\n{req_lines}\n"
    (plugin_dir / "plugin.yaml").write_text(body, encoding="utf-8")


def test_env_check_reports_missing_var(tmp_path, monkeypatch, capsys):
    profile_dir = _make_profile_for_env_check(tmp_path, plugin_names=["dataforseo"])
    _make_plugin(tmp_path, "dataforseo", ["DATAFORSEO_BASE64"])
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)

    aiseo_cli._check_plugin_env_requirements(profile_dir, tmp_path)
    err = capsys.readouterr().err
    assert "DATAFORSEO_BASE64" in err
    assert "dataforseo" in err
    assert "Missing env vars" in err


def test_env_check_silent_when_all_present_in_dotenv(tmp_path, monkeypatch, capsys):
    profile_dir = _make_profile_for_env_check(
        tmp_path,
        plugin_names=["dataforseo"],
        env_body="DATAFORSEO_BASE64=abc==\n",
    )
    _make_plugin(tmp_path, "dataforseo", ["DATAFORSEO_BASE64"])
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)

    aiseo_cli._check_plugin_env_requirements(profile_dir, tmp_path)
    assert capsys.readouterr().err == ""


def test_env_check_reads_os_environ_as_fallback(tmp_path, monkeypatch, capsys):
    """When the var is set in the process env but not in .env, no warning."""
    profile_dir = _make_profile_for_env_check(tmp_path, plugin_names=["dataforseo"])
    _make_plugin(tmp_path, "dataforseo", ["DATAFORSEO_BASE64"])
    monkeypatch.setenv("DATAFORSEO_BASE64", "from-process-env")

    aiseo_cli._check_plugin_env_requirements(profile_dir, tmp_path)
    assert capsys.readouterr().err == ""


def test_env_check_groups_shared_var_across_plugins(tmp_path, monkeypatch, capsys):
    profile_dir = _make_profile_for_env_check(
        tmp_path, plugin_names=["plugin_a", "plugin_b"],
    )
    _make_plugin(tmp_path, "plugin_a", ["SHARED_TOKEN"])
    _make_plugin(tmp_path, "plugin_b", ["SHARED_TOKEN"])
    monkeypatch.delenv("SHARED_TOKEN", raising=False)

    aiseo_cli._check_plugin_env_requirements(profile_dir, tmp_path)
    err = capsys.readouterr().err
    assert "SHARED_TOKEN" in err
    # Both plugins listed for the same missing var (order-insensitive).
    assert "plugin_a" in err and "plugin_b" in err


def test_env_check_silent_when_no_plugins_enabled(tmp_path, capsys):
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text("plugins:\n  enabled: []\n", encoding="utf-8")
    aiseo_cli._check_plugin_env_requirements(profile_dir, tmp_path)
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Phase 1 — `aiseo sync` flag parsing
# ---------------------------------------------------------------------------


def test_run_sync_command_rejects_unknown_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    with pytest.raises(SystemExit) as exc:
        aiseo_cli._run_sync_command(["--bogus-flag"])
    assert exc.value.code == 2
    assert "--bogus-flag" in capsys.readouterr().err


def test_run_sync_command_refresh_soul_routes_to_helper(tmp_path, monkeypatch, capsys):
    """`aiseo sync --refresh-soul -y` invokes _refresh_soul_from_seed with
    interactive=False and short-circuits the regular sync."""
    _build_fake_seed(tmp_path)
    monkeypatch.setattr(aiseo_cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

    called: list[bool] = []

    def _fake(profile_dir, seed_dir, interactive):
        called.append(interactive)
        return True

    monkeypatch.setattr(aiseo_cli, "_refresh_soul_from_seed", _fake)
    # Also prevent the regular sync path from running.
    monkeypatch.setattr(
        aiseo_cli, "_sync_profile",
        lambda force=False: (_ for _ in ()).throw(  # pragma: no cover
            AssertionError("regular sync should be skipped on --refresh-soul")
        ),
    )

    aiseo_cli._run_sync_command(["--refresh-soul", "-y"])
    assert called == [False], "interactive flag should be False with -y"
