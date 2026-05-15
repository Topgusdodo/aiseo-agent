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
    (seed_dir / "config.yaml").write_text("seed: config\n", encoding="utf-8")

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
