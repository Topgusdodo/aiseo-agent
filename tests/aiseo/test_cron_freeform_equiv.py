# TODO: delete this file when create-from-memory subcommand is removed
"""Cron equivalence tests: freeform vs legacy create-from-memory paths.

Design note on assertion form (DoD b):
  The two paths produce structurally different prompts — _build_* emits direct
  skill-invocation strings (e.g. "Run seo-weekly-report on site.com ...") while
  the freeform path wraps in <AISEO_FREEFORM_TASK> infrastructure. sha256
  equality is therefore impossible and intentionally not attempted.

  Instead each test asserts the weaker but meaningful equivalences that matter
  for operational correctness:
    - schedule cron expression matches the _build_* default for that skill
    - prompt contains the key identifying token(s) from the user's input
    - deliver mode defaults to local when no gateway origin is active

DoD (f) and (g) are also housed here as they test _is_aiseo_created_job
behaviour introduced in the same P1-A change.
"""
from __future__ import annotations

import json
import uuid

import pytest


def _payload(raw: str) -> dict:
    return json.loads(raw)


# ---------------------------------------------------------------------------
# DoD (b): Freeform equivalence — one test per _build_* builder
# ---------------------------------------------------------------------------


def test_equiv_seo_weekly_report(aiseo_guard, isolate_cron):
    """Freeform prompt covering the seo-weekly-report use case produces a cron
    job with a weekly schedule and the site URL preserved in the prompt.

    Equivalent _build_*: _build_seo_weekly_report -> schedule "0 8 * * 1"
    """
    site = "https://example.com"
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "prompt": (
                    f"Run seo-weekly-report on {site}. "
                    "Produce the 3-section delta report (current snapshot / changes vs last / next actions)."
                ),
                "frequency": "weekly",
                "time": "08:00",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    # Schedule must be weekly (day-of-week = 1, Monday) — matches _build_seo_weekly_report.
    assert job["schedule"].startswith("0 8 * * 1"), job["schedule"]
    # Deliver defaults to local when no gateway origin is active.
    assert job["deliver"] == "local"
    # The site URL must survive into the stored cron prompt.
    from cron.jobs import list_jobs
    stored_prompt = list_jobs(include_disabled=True)[0]["prompt"]
    assert site in stored_prompt


def test_equiv_technical_seo_audit(aiseo_guard, isolate_cron):
    """Freeform path for technical-seo-audit: monthly schedule, site URL preserved.

    Equivalent _build_*: _build_technical_seo_audit -> schedule "0 9 1 * *"
    """
    site = "https://example.com"
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "prompt": (
                    f"Run technical-seo-audit on {site} (site_root = primary site origin). "
                    "Use focus=all and sample_pages=3. Produce the 3-section technical audit report."
                ),
                "frequency": "monthly",
                "time": "09:00",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    # Schedule must be monthly (1st of month) — matches _build_technical_seo_audit.
    assert job["schedule"].startswith("0 9 1 * *"), job["schedule"]
    assert job["deliver"] == "local"
    from cron.jobs import list_jobs
    stored_prompt = list_jobs(include_disabled=True)[0]["prompt"]
    assert site in stored_prompt


def test_equiv_keyword_opportunity(aiseo_guard, isolate_cron):
    """Freeform path for keyword-opportunity: monthly schedule, keyword preserved.

    Equivalent _build_*: _build_keyword_opportunity -> schedule "0 10 1 * *"
    """
    keyword = "seo automation"
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "prompt": (
                    f"Run keyword-opportunity for seed_keyword='{keyword}', "
                    "market=Global, language=en. Produce the 3-section opportunity report."
                ),
                "frequency": "monthly",
                "time": "10:00",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    # Schedule must be monthly — matches _build_keyword_opportunity.
    assert job["schedule"].startswith("0 10 1 * *"), job["schedule"]
    assert job["deliver"] == "local"
    from cron.jobs import list_jobs
    stored_prompt = list_jobs(include_disabled=True)[0]["prompt"]
    assert keyword in stored_prompt


def test_equiv_competitor_analysis(aiseo_guard, isolate_cron):
    """Freeform path for competitor-analysis: quarterly-ish monthly schedule,
    user_url and competitor URLs preserved in the prompt.

    Equivalent _build_*: _build_competitor_analysis -> schedule "0 10 1 */3 *"
    Freeform uses monthly (closest supported cadence) — schedule prefix is the
    same 5-field structure, differing only in the month step field.
    """
    user_site = "https://example.com"
    competitor = "https://competitor.com"
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "prompt": (
                    f"Run competitor-analysis with user_url={user_site} and "
                    f"competitor_urls=[{competitor}]. Use focus=all. "
                    "Produce the 3-section comparison report with delta matrix."
                ),
                "frequency": "monthly",
                "time": "10:00",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    # Monthly schedule — nearest supported cadence to the quarterly _build_* default.
    assert job["schedule"].startswith("0 10 1 * *"), job["schedule"]
    assert job["deliver"] == "local"
    from cron.jobs import list_jobs
    stored_prompt = list_jobs(include_disabled=True)[0]["prompt"]
    assert user_site in stored_prompt
    assert competitor in stored_prompt


# ---------------------------------------------------------------------------
# DoD (f): End-to-end visibility — legacy create-from-memory job is listable
# ---------------------------------------------------------------------------


def test_legacy_job_visible_via_manage_list(aiseo_guard, isolate_cron):
    """A job created by the old `aiseo cron create-from-memory` subcommand
    (no enabled_toolsets, prompt starts with a _LEGACY_FROM_MEMORY_PREFIXES
    prefix, name starts with aiseo-) must appear in aiseo_manage_scheduled_tasks
    action=list output after the _is_aiseo_created_job multi-dim fix."""
    from cron.jobs import create_job, list_jobs

    # Mirror what `hermes cron create` produces when called by
    # _run_cron_create_from_memory.  The key invariant under test:
    #   enabled_toolsets=None  (hermes cron create does not set this field)
    legacy_job = create_job(
        prompt=(
            "Run seo-weekly-report on https://legacy-site.com. "
            "Produce the 3-section delta report (current snapshot / changes vs last / next actions)."
        ),
        schedule="0 8 * * 1",
        timezone="Asia/Shanghai",
        name="aiseo-seo-weekly-report",
        deliver="local",
        origin=None,
        skills=["seo-weekly-report"],
        enabled_toolsets=None,
    )

    # Sanity: the raw store must contain the job.
    all_jobs = list_jobs(include_disabled=True)
    assert any(j["id"] == legacy_job["id"] for j in all_jobs)

    # _is_aiseo_created_job must recognise it via the secondary (legacy) path.
    assert aiseo_guard._is_aiseo_created_job(legacy_job) is True

    # The manage list action must surface it (no gateway origin = local session,
    # origin=None on the job also matches the local session).
    listed = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks({"action": "list"})
    )
    assert listed["success"] is True
    visible_ids = {t["id"] for t in listed["tasks"]}
    assert legacy_job["id"] in visible_ids, (
        f"Legacy job {legacy_job['id']} not found in manage list; "
        f"visible ids: {visible_ids}"
    )


# ---------------------------------------------------------------------------
# DoD (g): False-positive guard — user-built job must NOT be classified as AISEO
# ---------------------------------------------------------------------------


def test_user_built_job_not_classified_as_aiseo(aiseo_guard):
    """A user-constructed cron job with:
      - natural-language prompt (not matching any _LEGACY_FROM_MEMORY_PREFIXES)
      - name that does NOT start with 'aiseo-'
      - no enabled_toolsets
    must return False from _is_aiseo_created_job so the guard never leaks
    it into the AISEO manage view or blocks user operations on it."""
    user_job: dict = {
        "id": str(uuid.uuid4()),
        "name": "my-custom-weekly-report",
        "prompt": (
            "use the keyword-opportunity tool to find ranking gaps for my site. "
            "Run every Monday and send me the results."
        ),
        "schedule": "0 9 * * 1",
        "timezone": "UTC",
        "skills": ["keyword-opportunity"],
        "enabled_toolsets": None,
        "script": None,
        "no_agent": None,
        "workdir": None,
        "context_from": None,
        "deliver": "local",
        "enabled": True,
    }

    assert aiseo_guard._is_aiseo_created_job(user_job) is False, (
        "User-built job with natural-language prompt and non-aiseo- name "
        "must not be classified as an AISEO-created job."
    )


def test_user_job_with_aiseo_prompt_prefix_not_classified(aiseo_guard):
    """GPT-review false-positive: a user-built cron job whose prompt happens to
    start with one of the _LEGACY_FROM_MEMORY_PREFIXES strings (e.g. "Run
    keyword-opportunity for ...") but has no 'aiseo-' name and empty skills must
    NOT be classified as an AISEO-created job.

    True _run_cron_create_from_memory jobs always set name=aiseo-{skill} AND
    skills=[skill] (aiseo_cli.py:994-1110).  Prompt prefix alone is not a
    sufficient signal — requiring at least one structural corroborator
    (aiseo- name OR known skills) prevents misclassification.
    """
    user_job: dict = {
        "id": "test-fp-prefix-only",
        "name": "user-job",          # does NOT start with "aiseo-"
        "prompt": "Run keyword-opportunity for some-task and report results",
        "skills": [],                 # empty — no known AISEO skills
        "enabled_toolsets": None,
        "script": None,
        "no_agent": None,
        "workdir": None,
        "context_from": None,
    }
    assert aiseo_guard._is_aiseo_created_job(user_job) is False, (
        "User job whose prompt prefix matches _LEGACY_FROM_MEMORY_PREFIXES "
        "but lacks aiseo- name and known skills must not be classified as AISEO."
    )
