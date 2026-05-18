"""Deterministic tests for the Python ``uv run aiseo`` entry point."""

from __future__ import annotations

import os
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
        "  - aiseo_manage_scheduled_tasks\n",
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

    assert "model: user-model" in body
    assert "aiseo_skills_read" in body
    assert body.count("aiseo_skills_read") == 1
    assert "config.yaml:toolsets/aiseo_skills_read" in diff["added"]

    second = aiseo_cli._sync_profile(force=False)
    assert config_path.read_text(encoding="utf-8").count("aiseo_skills_read") == 1
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
    assert "config.yaml:toolsets-not-list" in diff["skipped"]


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
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

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
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    def _boom(tmp, target):  # pragma: no cover - failure path
        raise OSError("simulated disk full")

    monkeypatch.setattr(aiseo_cli, "atomic_replace", _boom)

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

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
    """M_new1: .yaml.bak must exist after migration and equal the pre-migration content."""
    original = (
        "# user-owned config\n"
        "toolsets:\n"
        "  - web\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)
    assert changed is True

    backup_path = config_path.with_suffix(".yaml.bak")
    assert backup_path.is_file(), "expected .yaml.bak after successful migration"
    assert backup_path.read_text(encoding="utf-8") == original, (
        ".yaml.bak should be a byte-identical snapshot of the pre-migration file"
    )

    # Idempotent no-op runs do NOT need to rewrite the backup — they don't write at all.
    pre_bak_mtime = backup_path.stat().st_mtime
    second_diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}
    second_changed = aiseo_cli._migrate_profile_config(config_path, second_diff)
    assert second_changed is False
    assert backup_path.stat().st_mtime == pre_bak_mtime


def test_migrate_config_non_utf8_silent_skip_no_destruction(tmp_path):
    """Non-UTF-8 body: logger.warning + skip, original bytes preserved."""
    profile_dir = tmp_path / ".hermes" / "profiles" / "aiseo"
    profile_dir.mkdir(parents=True)
    config_path = profile_dir / "config.yaml"
    raw_bytes = b"\xff\xfe\x00\x00not utf-8 at all"
    config_path.write_bytes(raw_bytes)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

    assert changed is False
    # File still exists and bytes are unchanged.
    assert config_path.is_file()
    assert config_path.read_bytes() == raw_bytes
    assert "config.yaml:migration-non-utf8" in diff["skipped"]
    # No phantom adds, no backup churn.
    assert diff["added"] == []
    assert not (profile_dir / "config.yaml.bak").exists()


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
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

    assert changed is True, (
        "0-indent toolsets list was not recognized — see diff: " + repr(diff)
    )
    result = config_path.read_text(encoding="utf-8")

    # All original lines preserved.
    for line in original.splitlines():
        assert line in result, f"missing original line: {line!r}"

    # Appended item must use SAME indent (0) as existing items, not the
    # hardcoded 2-space default — keeps the file visually consistent.
    assert "\n- aiseo_skills_read\n" in result, (
        "Appended item should use 0-indent matching existing items; got:\n" + result
    )
    assert "  - aiseo_skills_read" not in result, (
        "Should NOT use 2-indent when user's existing list is 0-indent"
    )
    # And only appended once.
    assert result.count("- aiseo_skills_read") == 1

    # Diff bookkeeping correct.
    assert "config.yaml:toolsets/aiseo_skills_read" in diff["added"]
    assert not any(s.startswith("config.yaml:toolsets-not-list") for s in diff["skipped"])


def test_migrate_config_idempotent_under_zero_indent(tmp_path):
    """Running migration twice on a 0-indent config must be a no-op the
    second time — does not re-append aiseo_skills_read."""
    original = (
        "toolsets:\n"
        "- web\n"
        "- aiseo_skills_read\n"
        "- search\n"
    )
    config_path = _make_profile_with_config(tmp_path, original)
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

    assert changed is False, (
        "Migration should be a no-op when aiseo_skills_read already present"
    )
    result = config_path.read_text(encoding="utf-8")
    assert result.count("- aiseo_skills_read") == 1


def test_migrate_config_toolsets_key_completely_missing_is_skip(tmp_path):
    """Top-level `toolsets:` absent: migration must NOT invent the structure."""
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
    diff: dict[str, list[str]] = {"added": [], "unchanged": [], "skipped": []}

    changed = aiseo_cli._migrate_profile_config(config_path, diff)

    assert changed is False
    # Bytes preserved exactly — no auto-generated `toolsets:` block.
    assert config_path.read_text(encoding="utf-8") == original
    assert "config.yaml:toolsets-not-list" in diff["skipped"]
    assert "aiseo_skills_read" not in config_path.read_text(encoding="utf-8")
    # No backup created for a skip path.
    assert not (config_path.parent / "config.yaml.bak").exists()
