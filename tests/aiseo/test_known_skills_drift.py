"""Drift gate: pin `_KNOWN_AISEO_SKILLS` to the seed skills/ directory.

The `_KNOWN_AISEO_SKILLS` frozenset in plugins/aiseo-guard/__init__.py is one
half of the legacy-job recognition path in `_is_aiseo_created_job` (the other
half being `_LEGACY_FROM_MEMORY_PREFIXES`). If the seed skills directory
grows or shrinks but the constant is not updated, legacy cron jobs created
via `aiseo cron create-from-memory <new_skill>` will silently become orphans
(visible to the cron daemon, invisible to `aiseo_manage_scheduled_tasks`).

This test fails loud when the two drift, forcing a manual sync.

Symmetric in intent to `tests/aiseo/test_outputgate_drift.py`, which pins
the OutputGate redact prefixes against the upstream `agent.redact` list.
"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "seeds" / "aiseo-profile" / "skills"


def test_known_aiseo_skills_matches_seed_directory(aiseo_guard):
    """`_KNOWN_AISEO_SKILLS` must equal the set of directory names under
    `seeds/aiseo-profile/skills/`.

    Uses the session-scoped `aiseo_guard` fixture (see tests/aiseo/conftest.py)
    to reach the constant, since the plugin directory's hyphen makes a
    plain Python import impossible.
    """
    seed_skills = {
        child.name for child in _SKILLS_DIR.iterdir() if child.is_dir()
    }
    pinned = aiseo_guard._KNOWN_AISEO_SKILLS

    assert seed_skills == pinned, (
        "_KNOWN_AISEO_SKILLS drifted from seeds/aiseo-profile/skills/: "
        f"extra in pinned={sorted(pinned - seed_skills)}, "
        f"missing from pinned={sorted(seed_skills - pinned)}"
    )
