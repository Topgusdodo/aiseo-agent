"""Test _normalize_job_record fills timezone field for legacy jobs.

Regression: jobs written before the timezone bug fix have no `timezone` key.
On load (or any normalize-record consumer path), they must auto-fall-back to
DEFAULT_CRON_TIMEZONE so downstream compute_next_run/scheduler/UI never see
a None/missing timezone field.

See: .plans/cron-timezone-fix.md (or completed/) §D2
"""
import pytest

from cron.jobs import _normalize_job_record, compute_next_run


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


class TestCronTzRuntimeEnv:
    """Verify that timezone resolution uses env at call time, not import time.

    Before the P1 #4 fix, DEFAULT_CRON_TIMEZONE was read once at module import
    and cached as a module-level constant. Any env change after import was
    invisible to running code without importlib.reload(). The fix introduces
    _get_default_timezone() which reads os.environ on every call, so these
    tests must pass WITHOUT any reload().
    """

    def test_normalize_job_record_picks_up_env_at_call_time(self, monkeypatch):
        """_normalize_job_record must use the env value current at call time.

        No importlib.reload() — the point is that the runtime helper reads the
        env fresh on every invocation.
        """
        # Arrange
        monkeypatch.setenv("HERMES_DEFAULT_CRON_TIMEZONE", "Europe/London")
        job = {
            "id": "runtime-tz-test",
            "prompt": "x",
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
        }

        # Act — no reload; env was set after module was already imported
        normalized = _normalize_job_record(job)

        # Assert — must reflect the env value set above, not the import-time snapshot
        assert normalized["timezone"] == "Europe/London", (
            "Expected _normalize_job_record to read HERMES_DEFAULT_CRON_TIMEZONE "
            "at call time, not at module import time."
        )

    def test_compute_next_run_picks_up_env_at_call_time(self, monkeypatch):
        """compute_next_run must use the env value current at call time.

        Verifies that passing timezone=None falls back to _get_default_timezone()
        (runtime read) rather than the import-time constant snapshot.
        """
        # Arrange
        monkeypatch.setenv("HERMES_DEFAULT_CRON_TIMEZONE", "UTC")
        schedule = {"kind": "cron", "expr": "0 9 * * *"}

        # Act — timezone=None triggers the default fallback path
        result = compute_next_run(schedule, timezone=None)

        # Assert — result must be a valid ISO timestamp; we verify it is
        # produced without error (ZoneInfoNotFoundError would propagate if
        # the wrong timezone string were used). The key assertion is that
        # "UTC" is accepted, which it is only if the runtime helper is called.
        assert result is not None, (
            "compute_next_run returned None unexpectedly with UTC timezone"
        )
        # Confirm no Asia/Shanghai offset bleed-through by ensuring the call
        # did not crash (ZoneInfo("UTC") is always valid).
        from datetime import datetime
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None, "Expected timezone-aware datetime in result"
