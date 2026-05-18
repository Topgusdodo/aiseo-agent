"""Test _normalize_job_record fills timezone field for legacy jobs.

Regression: jobs written before the timezone bug fix have no `timezone` key.
On load (or any normalize-record consumer path), they must auto-fall-back to
DEFAULT_CRON_TIMEZONE so downstream compute_next_run/scheduler/UI never see
a None/missing timezone field.

See: .plans/cron-timezone-fix.md (or completed/) §D2
"""
import pytest

from cron.jobs import _normalize_job_record


class TestNormalizeJobRecordTimezone:
    """_normalize_job_record() MUST fill missing timezone with the
    process-default; never mutate the caller's dict (pure function)."""

    def test_legacy_job_without_timezone_gets_default_shanghai(self, monkeypatch):
        """A job dict missing the `timezone` key (legacy ~/.hermes/cron/jobs.json
        from before the fix) should be normalized to Asia/Shanghai by default."""
        monkeypatch.delenv("HERMES_DEFAULT_CRON_TIMEZONE", raising=False)
        legacy = {
            "id": "legacy-abc",
            "prompt": "test prompt",
            "schedule": {"kind": "cron", "expr": "35 9 * * *", "display": "35 9 * * *"},
            "enabled": True,
        }

        normalized = _normalize_job_record(legacy)

        assert normalized["timezone"] == "Asia/Shanghai"

    def test_explicit_timezone_is_preserved(self):
        """If the job already has a timezone, normalize must not overwrite it."""
        job = {
            "id": "job-with-tz",
            "prompt": "test",
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "timezone": "America/New_York",
        }

        normalized = _normalize_job_record(job)

        assert normalized["timezone"] == "America/New_York"

    def test_empty_string_timezone_treated_as_missing(self):
        """An empty string in `timezone` should be treated as missing
        (defensive against bad migrations / hand edits)."""
        job = {
            "id": "job-empty-tz",
            "prompt": "test",
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "timezone": "",
        }

        normalized = _normalize_job_record(job)

        assert normalized["timezone"] == "Asia/Shanghai"

    def test_env_override_changes_default(self, monkeypatch):
        """HERMES_DEFAULT_CRON_TIMEZONE env var lets upstream Hermes
        users opt out of the aiseo-favored default."""
        monkeypatch.setenv("HERMES_DEFAULT_CRON_TIMEZONE", "UTC")
        # Reimport to pick up env at module-load time
        import importlib
        import cron.jobs
        importlib.reload(cron.jobs)
        try:
            job = {
                "id": "no-tz",
                "prompt": "x",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            }
            normalized = cron.jobs._normalize_job_record(job)
            assert normalized["timezone"] == "UTC"
        finally:
            monkeypatch.delenv("HERMES_DEFAULT_CRON_TIMEZONE", raising=False)
            importlib.reload(cron.jobs)

    def test_normalize_does_not_mutate_input(self):
        """Pure function contract: caller's dict must not be touched."""
        job = {
            "id": "test-no-mutate",
            "prompt": "x",
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
        }
        snapshot = dict(job)

        _normalize_job_record(job)

        # `timezone` must NOT have been written to the input dict
        assert "timezone" not in job
        assert job == snapshot
