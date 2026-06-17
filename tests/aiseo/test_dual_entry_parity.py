"""P2-A: Parity tests between bin/aiseo (bash wrapper) and python aiseo_cli.py.

Both entry points must produce identical stdout, stderr, and exit codes for
every subcommand. The bash wrapper now delegates entirely to aiseo_cli.py, so
divergence can only arise from path/env differences caught here.

Strategy:
  - Run each subcommand via subprocess for both entry points.
  - Compare stdout + stderr text and exit code.
  - Use PYTHON env var to pin the interpreter across both invocations.
  - No real hermes exec happens: the subcommands exercised here all return
    before reaching the os.execvp() call in aiseo_cli.py::main().
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_BIN_ENTRY = str(REPO_ROOT / "aiseo_cli.py")
BASH_BIN_ENTRY = str(REPO_ROOT / "bin" / "aiseo")


def _base_env() -> dict[str, str]:
    """Return os.environ copy without AISEO_BRAND_ACTIVE so tests are independent."""
    env = dict(os.environ)
    env.pop("AISEO_BRAND_ACTIVE", None)
    return env


def _run_python(args: list[str]) -> subprocess.CompletedProcess:
    """Invoke aiseo_cli.py directly via the current Python interpreter."""
    return subprocess.run(
        [sys.executable, PYTHON_BIN_ENTRY, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_base_env(),
    )


def _run_bash(args: list[str]) -> subprocess.CompletedProcess:
    """Invoke bin/aiseo (bash wrapper) with PYTHON pinned to the current interpreter."""
    return subprocess.run(
        ["bash", BASH_BIN_ENTRY, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**_base_env(), "PYTHON": sys.executable},
    )


# ---------------------------------------------------------------------------
# aiseo --help parity
# ---------------------------------------------------------------------------

class TestHelpParity:
    """aiseo --help / aiseo -h must be identical across both entry points."""

    def test_help_long_stdout_identical(self):
        # Arrange
        args = ["--help"]

        # Act
        py_result = _run_python(args)
        bash_result = _run_bash(args)

        # Assert
        assert py_result.stdout == bash_result.stdout, (
            f"--help stdout mismatch.\nPython:\n{py_result.stdout}\n"
            f"Bash:\n{bash_result.stdout}"
        )

    def test_help_long_exit_code_zero(self):
        args = ["--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == 0
        assert bash_result.returncode == 0

    def test_help_long_exit_code_identical(self):
        args = ["--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == bash_result.returncode

    def test_help_short_stdout_identical(self):
        args = ["-h"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.stdout == bash_result.stdout

    def test_help_short_exit_code_identical(self):
        args = ["-h"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == bash_result.returncode

    def test_help_contains_sync_subcommand(self):
        """Both help outputs must mention the sync subcommand."""
        args = ["--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert "sync" in py_result.stdout
        assert "sync" in bash_result.stdout

    def test_help_contains_cron_subcommand(self):
        """Both help outputs must mention cron create-from-memory."""
        args = ["--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert "cron" in py_result.stdout
        assert "cron" in bash_result.stdout

    def test_help_short_long_outputs_match(self):
        """-h and --help must produce identical output within each entry point."""
        py_short = _run_python(["-h"])
        py_long = _run_python(["--help"])
        assert py_short.stdout == py_long.stdout

        bash_short = _run_bash(["-h"])
        bash_long = _run_bash(["--help"])
        assert bash_short.stdout == bash_long.stdout


# ---------------------------------------------------------------------------
# aiseo sync --help parity
# ---------------------------------------------------------------------------

class TestSyncHelpParity:
    """aiseo sync --help must behave identically (error path, non-zero exit)."""

    def test_sync_unknown_flag_stderr_identical(self):
        # Arrange
        args = ["sync", "--help"]

        # Act
        py_result = _run_python(args)
        bash_result = _run_bash(args)

        # Assert
        assert py_result.stderr == bash_result.stderr, (
            f"sync --help stderr mismatch.\nPython:\n{py_result.stderr}\n"
            f"Bash:\n{bash_result.stderr}"
        )

    def test_sync_unknown_flag_exit_code_identical(self):
        args = ["sync", "--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == bash_result.returncode

    def test_sync_unknown_flag_exits_nonzero(self):
        args = ["sync", "--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode != 0
        assert bash_result.returncode != 0

    def test_sync_unknown_flag_stdout_identical(self):
        args = ["sync", "--help"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.stdout == bash_result.stdout


# ---------------------------------------------------------------------------
# aiseo cron create-from-memory parity
# ---------------------------------------------------------------------------

class TestCronCreateFromMemoryParity:
    """aiseo cron create-from-memory must behave identically in both entry points."""

    def test_missing_skill_stderr_identical(self):
        # Arrange — no skill arg triggers the missing-skill error path
        args = ["cron", "create-from-memory"]

        # Act
        py_result = _run_python(args)
        bash_result = _run_bash(args)

        # Assert
        assert py_result.stderr == bash_result.stderr, (
            f"cron create-from-memory stderr mismatch.\n"
            f"Python:\n{py_result.stderr}\nBash:\n{bash_result.stderr}"
        )

    def test_missing_skill_exit_code_identical(self):
        args = ["cron", "create-from-memory"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == bash_result.returncode

    def test_missing_skill_exits_one(self):
        args = ["cron", "create-from-memory"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == 1
        assert bash_result.returncode == 1

    def test_missing_skill_stdout_identical(self):
        args = ["cron", "create-from-memory"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.stdout == bash_result.stdout

    def test_unknown_skill_stderr_identical(self):
        """Unknown skill name must produce the same error in both entry points."""
        args = ["cron", "create-from-memory", "nonexistent-skill"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.stderr == bash_result.stderr

    def test_unknown_skill_exit_code_identical(self):
        args = ["cron", "create-from-memory", "nonexistent-skill"]
        py_result = _run_python(args)
        bash_result = _run_bash(args)
        assert py_result.returncode == bash_result.returncode


# ---------------------------------------------------------------------------
# AISEO_BRAND_ACTIVE env var parity
# ---------------------------------------------------------------------------

class TestBrandActiveParity:
    """Both entry points must produce branded output (AISEO_BRAND_ACTIVE=1 in effect)."""

    def test_bash_help_contains_aiseo_brand(self):
        """bin/aiseo sets AISEO_BRAND_ACTIVE=1; --help output must contain brand name."""
        result = _run_bash(["--help"])
        assert result.returncode == 0
        assert "AISEO" in result.stdout

    def test_python_help_contains_aiseo_brand(self):
        """aiseo_cli.py --help must also produce brand text."""
        result = _run_python(["--help"])
        assert result.returncode == 0
        assert "AISEO" in result.stdout

    def test_brand_text_identical_across_entry_points(self):
        """Ensure brand name appears the same number of times in both help outputs."""
        py_result = _run_python(["--help"])
        bash_result = _run_bash(["--help"])
        py_count = py_result.stdout.count("AISEO")
        bash_count = bash_result.stdout.count("AISEO")
        assert py_count == bash_count, (
            f"AISEO brand count differs: python={py_count}, bash={bash_count}"
        )
