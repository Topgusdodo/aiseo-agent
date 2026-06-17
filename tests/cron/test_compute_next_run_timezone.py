"""Test compute_next_run respects job-level timezone.

Regression test for the cron timezone bug:
- User says "北京时间 09:35", scheduler stores cron "35 9 * * *" without
  timezone metadata. Default croniter interprets "09:35" as host-process-
  timezone (UTC on production containers), causing tasks to fire 8 hours
  late (北京 17:35) instead of 北京 09:35.
- Also: 09:14 创建 09:20 任务时, next_run_at 跳到明天而不是今天.

All test cases run under TZ=UTC host (enforced by scripts/run_tests.sh) — this
is essential because the bug is masked when host TZ == job TZ == Asia/Shanghai
(developer machine), but exposed in production UTC containers.

See: .plans/cron-timezone-fix.md (or completed/)
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

pytest.importorskip("croniter")

from cron.jobs import compute_next_run


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


class TestComputeNextRunTimezone:
    """compute_next_run MUST use job-level timezone to interpret cron
    expressions, not the host process timezone."""

    def test_case1_shanghai_job_at_09_14_fires_today_not_tomorrow(self, monkeypatch):
        """Case 1 (problem 3 repro): host UTC, job Asia/Shanghai, now 北京 09:14.
        cron "20 9 * * *" must fire today at 北京 09:20 — currently jumps to tomorrow."""
        now = datetime(2026, 5, 18, 9, 14, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        result = compute_next_run(schedule, timezone="Asia/Shanghai")

        assert result is not None
        next_shanghai = datetime.fromisoformat(result).astimezone(SHANGHAI)
        assert next_shanghai.date().isoformat() == "2026-05-18", (
            f"Expected today (2026-05-18 北京), got {next_shanghai}"
        )
        assert next_shanghai.hour == 9
        assert next_shanghai.minute == 20

    def test_case2_shanghai_job_at_09_25_fires_tomorrow(self, monkeypatch):
        """Case 2 (regression guard): already past 09:20, must roll to tomorrow."""
        now = datetime(2026, 5, 18, 9, 25, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        result = compute_next_run(schedule, timezone="Asia/Shanghai")

        next_shanghai = datetime.fromisoformat(result).astimezone(SHANGHAI)
        assert next_shanghai.date().isoformat() == "2026-05-19"
        assert next_shanghai.hour == 9
        assert next_shanghai.minute == 20

    def test_case3_user_actual_report_09_35(self, monkeypatch):
        """Case 3 (problem 1 repro): user's exact report — "北京时间 09:35".
        At 北京 09:34 must fire at today 09:35 (not delayed to 17:35 which
        is what UTC-interpreted "09:35" would mean)."""
        now = datetime(2026, 5, 18, 9, 34, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "35 9 * * *"}
        result = compute_next_run(schedule, timezone="Asia/Shanghai")

        next_shanghai = datetime.fromisoformat(result).astimezone(SHANGHAI)
        assert next_shanghai.hour == 9 and next_shanghai.minute == 35, (
            f"Expected 北京 09:35, got 北京 {next_shanghai.strftime('%H:%M')} "
            f"(this is the 17:35 bug if hour != 9)"
        )
        assert next_shanghai.date().isoformat() == "2026-05-18"

    def test_case4_host_tz_matches_job_tz_no_regression(self, monkeypatch):
        """Case 4 (legacy good case): host TZ == job TZ == Asia/Shanghai.
        Must still produce correct today 09:20. This case masks the bug
        on developer machines — must not regress when fixing."""
        now = datetime(2026, 5, 18, 9, 14, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        result = compute_next_run(schedule, timezone="Asia/Shanghai")

        next_shanghai = datetime.fromisoformat(result).astimezone(SHANGHAI)
        assert next_shanghai.date().isoformat() == "2026-05-18"
        assert next_shanghai.hour == 9 and next_shanghai.minute == 20

    def test_case5_utc_job_under_utc_host_baseline(self, monkeypatch):
        """Case 5 (baseline): both host and job are UTC. Identity case —
        no timezone conversion happens. Guards against fix introducing
        regression in the simple path."""
        now = datetime(2026, 5, 18, 9, 14, 0, tzinfo=UTC)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        result = compute_next_run(schedule, timezone="UTC")

        next_utc = datetime.fromisoformat(result).astimezone(UTC)
        assert next_utc.date().isoformat() == "2026-05-18"
        assert next_utc.hour == 9 and next_utc.minute == 20

    def test_case6_no_timezone_falls_back_to_default(self, monkeypatch):
        """Case 6 (backward compat): legacy job without timezone field —
        compute_next_run must fall back to DEFAULT_CRON_TIMEZONE
        (Asia/Shanghai by default). Required so that loading legacy
        jobs.json (no `timezone` key) does not silently break."""
        now = datetime(2026, 5, 18, 9, 14, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        # NO timezone kwarg → falls back to DEFAULT_CRON_TIMEZONE
        result = compute_next_run(schedule)

        next_shanghai = datetime.fromisoformat(result).astimezone(SHANGHAI)
        assert next_shanghai.date().isoformat() == "2026-05-18"
        assert next_shanghai.hour == 9 and next_shanghai.minute == 20

    def test_next_run_at_iso_string_carries_offset(self, monkeypatch):
        """The returned ISO string MUST be timezone-aware (carry offset like
        +08:00), not naive — so downstream consumers do not have to guess."""
        now = datetime(2026, 5, 18, 9, 14, 0, tzinfo=SHANGHAI)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "20 9 * * *"}
        result = compute_next_run(schedule, timezone="Asia/Shanghai")

        # +08:00 or +0800 — anything offset-aware
        assert "+" in result or "Z" in result, (
            f"Expected timezone-aware ISO with offset, got naive: {result}"
        )
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
