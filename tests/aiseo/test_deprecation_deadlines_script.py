"""Tests for ``scripts/check_deprecation_deadlines.sh``.

Three-branch coverage matching the P2-C DoD:

* **format-error** — a marker whose date doesn't match ``YYYY-MM-DD`` must
  trip ``[FORMAT-ERROR]`` and exit non-zero.
* **expired** — a marker whose date is in the past must trip ``[EXPIRED]``
  and exit non-zero.
* **clean** — a marker dated in the far future must exit zero with no
  alert lines on stderr.

Isolation strategy: we invoke the script with ``cwd=tmp_path`` so its
``grep -rn ... .`` recurses inside a throwaway fixture tree rather than
walking the real repo. The script is called by absolute path so the
working-directory swap doesn't break the invocation itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_deprecation_deadlines.sh"

# Build the marker token at runtime so the literal phrase does not appear in
# this source file. Otherwise the deadline-checker itself would scan this
# test module, see the marker comment baked into the fixture strings, and
# trip on what are really test-only sentinels.
#
# IMPORTANT: Do NOT simplify to a single string literal. The grep-based
# deadline checker scans all .py files; a literal AISEO_DEPRECATION_DEADLINE
# string (without split) would be found and treated as a malformed marker,
# producing confusing CI failures pointing at this test file.
_MARKER = "AISEO_" + "DEPRECATION_" + "DEADLINE"


def _marker_line(date_value: str) -> str:
    """Return a one-line marker comment with ``date_value`` as the date."""
    return f"# {_MARKER}: {date_value}\n"


def _run_script(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the deadline-check script with ``cwd`` and capture output."""
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.fixture(autouse=True)
def _require_script_present():
    """Fail loudly if the script is missing — a SKIP would hide a real regression."""
    if not SCRIPT_PATH.exists():
        pytest.fail(
            f"deadline-check script not found at {SCRIPT_PATH} — was it deleted?"
        )


def test_format_error_branch_fails(tmp_path: Path) -> None:
    """A marker with a non-ISO date string must trip [FORMAT-ERROR]."""
    # Arrange — drop a single .py file with a malformed deadline marker.
    fixture = tmp_path / "bad_format.py"
    fixture.write_text(_marker_line("TBD"), encoding="utf-8")

    # Act
    result = _run_script(tmp_path)

    # Assert
    assert result.returncode == 1, (
        f"expected non-zero exit on format error; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "FORMAT-ERROR" in result.stderr


def test_expired_branch_fails(tmp_path: Path) -> None:
    """A marker dated in the past must trip [EXPIRED]."""
    # Arrange — past date well before any plausible 'today'.
    fixture = tmp_path / "expired.py"
    fixture.write_text(_marker_line("2020-01-01"), encoding="utf-8")

    # Act
    result = _run_script(tmp_path)

    # Assert
    assert result.returncode == 1, (
        f"expected non-zero exit on expired marker; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "EXPIRED" in result.stderr


def test_clean_future_deadline_passes(tmp_path: Path) -> None:
    """A marker dated in the far future must exit 0 silently."""
    # Arrange — 2099-01-01 is far enough out to outlast any reasonable
    # test-suite lifetime without baking in 'today'.
    fixture = tmp_path / "future.py"
    fixture.write_text(_marker_line("2099-01-01"), encoding="utf-8")

    # Act
    result = _run_script(tmp_path)

    # Assert
    assert result.returncode == 0, (
        f"expected zero exit on future marker; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "FORMAT-ERROR" not in result.stderr
    assert "EXPIRED" not in result.stderr
