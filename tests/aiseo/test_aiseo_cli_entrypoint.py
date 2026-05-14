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
