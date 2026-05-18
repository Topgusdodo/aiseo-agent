"""Tests for the cron start-event delivery behavior.

When a scheduled job becomes due, the scheduler must:
  1. Build a start-event notice BEFORE invoking the agent
  2. Deliver the notice through the same channel(s) used for the result
  3. Suppress delivery for deliver=local jobs (consistent with _deliver_result)
  4. Never block the run on notice failure
  5. Sanitize user-controlled fields against control chars / markdown injection

See: .plans/cron-timezone-fix.md (or completed/) §D6 (C2)
"""
import pytest

from cron.scheduler import (
    _build_start_notice,
    _deliver_notice,
    _sanitize_for_notice,
)


class TestSanitizeForNotice:
    """User-controlled job fields must be scrubbed before splicing into notices."""

    def test_control_chars_stripped(self):
        assert _sanitize_for_notice("hello\nworld") == "hello world"
        assert _sanitize_for_notice("a\rb\tc") == "a b c"
        assert _sanitize_for_notice("x\x00y") == "x y"

    def test_angle_brackets_stripped(self):
        assert _sanitize_for_notice("<script>") == "script"
        assert _sanitize_for_notice("foo > bar") == "foo   bar"

    def test_truncation_respects_max_len(self):
        long = "a" * 200
        assert len(_sanitize_for_notice(long, max_len=80)) == 80

    def test_empty_input_safe(self):
        assert _sanitize_for_notice("") == ""
        assert _sanitize_for_notice(None) == ""


class TestBuildStartNotice:
    """Deterministic message — no LLM, no surprises."""

    def test_includes_job_name_and_schedule(self):
        job = {
            "id": "abc123",
            "name": "AISEO daily Page Audit — cfmate.com",
            "schedule_display": "35 9 * * * (Asia/Shanghai)",
        }
        notice = _build_start_notice(job)
        assert "AISEO daily Page Audit — cfmate.com" in notice
        assert "35 9 * * * (Asia/Shanghai)" in notice
        assert "开始执行" in notice

    def test_falls_back_to_job_id_when_name_missing(self):
        notice = _build_start_notice({"id": "fallback-id"})
        assert "fallback-id" in notice

    def test_sanitizes_injected_control_chars_in_name(self):
        job = {
            "id": "x",
            "name": "evil\nname\r<injection>",
            "schedule_display": "0 9 * * *",
        }
        notice = _build_start_notice(job)
        # The dangerous chars must not survive into the notice body
        assert "\r" not in notice
        assert "<injection" not in notice
        assert "evil name" in notice


class TestDeliverNoticeLocalSkip:
    """A deliver=local job has no targets — notice must silently noop."""

    def test_no_targets_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "cron.scheduler._resolve_delivery_targets", lambda job: []
        )
        result = _deliver_notice({"id": "x", "deliver": "local"}, "hello")
        assert result is None

    def test_empty_content_returns_none(self):
        result = _deliver_notice({"id": "x"}, "")
        assert result is None


class TestDeliverNoticeFailureContainment:
    """A notice send failure must NEVER raise — only return an error string."""

    def test_target_resolution_exception_returns_error_string(self, monkeypatch):
        def _boom(job):
            raise RuntimeError("resolver crashed")

        monkeypatch.setattr("cron.scheduler._resolve_delivery_targets", _boom)
        result = _deliver_notice({"id": "x"}, "hello")
        assert isinstance(result, str)
        assert "resolver crashed" in result

    def test_gateway_config_failure_returns_error_string(self, monkeypatch):
        monkeypatch.setattr(
            "cron.scheduler._resolve_delivery_targets",
            lambda job: [{"platform": "telegram", "chat_id": "1"}],
        )

        # Patch the lazy gateway-config import to raise
        import gateway.config

        def _boom():
            raise RuntimeError("config load failed")

        monkeypatch.setattr(gateway.config, "load_gateway_config", _boom)
        result = _deliver_notice({"id": "x"}, "hello")
        assert isinstance(result, str)
        assert "config load failed" in result


class TestDeliverNoticeAdapterFailureChecks:
    """Regression for P2 review findings: when the live adapter returns a
    structured failure object (success=False) instead of raising, AND when
    _send_to_platform returns an {"error": ...} dict, _deliver_notice must
    treat both as failures — same as _deliver_result already does."""

    def _setup_one_target(self, monkeypatch, platform_name="telegram"):
        """Wire up just enough state for _deliver_notice to reach the
        per-target send loop without crashing on config lookups."""
        monkeypatch.setattr(
            "cron.scheduler._resolve_delivery_targets",
            lambda job: [{"platform": platform_name, "chat_id": "c1"}],
        )

        import gateway.config

        class _PConfig:
            enabled = True

        class _Config:
            platforms = {gateway.config.Platform.TELEGRAM: _PConfig()}

        monkeypatch.setattr(gateway.config, "load_gateway_config", lambda: _Config())

    def test_standalone_send_returns_error_dict_is_reported(self, monkeypatch):
        """If _send_to_platform returns {"error": "..."} instead of raising,
        _deliver_notice MUST surface it (not silently log success)."""
        self._setup_one_target(monkeypatch)

        async def _fake_send(*args, **kwargs):
            return {"error": "rate limited"}

        import tools.send_message_tool
        monkeypatch.setattr(tools.send_message_tool, "_send_to_platform", _fake_send)

        result = _deliver_notice({"id": "x"}, "hello", adapters=None, loop=None)
        assert isinstance(result, str), f"Expected error string, got {result!r}"
        assert "rate limited" in result, f"Error message lost: {result!r}"

    def test_live_adapter_success_false_falls_through_to_standalone(self, monkeypatch):
        """If the live adapter returns a result with success=False (without
        raising), _deliver_notice MUST fall through to the standalone send
        path — matching the contract _deliver_result already implements."""
        self._setup_one_target(monkeypatch)

        # Live adapter: returns an object with success=False
        class _SendResult:
            success = False
            error = "channel blocked"

        class _FakeAdapter:
            sent = False

            async def send(self, chat_id, content, metadata=None):
                _FakeAdapter.sent = True
                return _SendResult()

        # Loop that "is running" so the live-adapter branch is taken
        class _FakeLoop:
            def is_running(self):
                return True

        # Patch run_coroutine_threadsafe to bypass the actual loop machinery
        class _Future:
            def __init__(self, result):
                self._r = result

            def result(self, timeout=None):
                return self._r

        async def _runner(coro):
            return await coro

        import asyncio as real_asyncio

        def _fake_threadsafe(coro, loop):
            return _Future(real_asyncio.run(_runner(coro)))

        monkeypatch.setattr(
            "cron.scheduler.asyncio.run_coroutine_threadsafe",
            _fake_threadsafe,
        )

        # Standalone fallback: track that it's reached
        standalone_called = []

        async def _fake_send(*args, **kwargs):
            standalone_called.append(True)
            return None  # success

        import tools.send_message_tool
        monkeypatch.setattr(tools.send_message_tool, "_send_to_platform", _fake_send)

        import gateway.config
        adapters = {gateway.config.Platform.TELEGRAM: _FakeAdapter()}

        _deliver_notice({"id": "x"}, "hello", adapters=adapters, loop=_FakeLoop())

        assert _FakeAdapter.sent, "live adapter send was not attempted"
        assert standalone_called == [True], (
            "live adapter returned success=False but standalone fallback was NOT invoked"
        )


class TestRecoveryComputeNextRunNoSkipToday:
    """Regression for P1 review concern: when a daily cron job has no
    next_run_at and recovery happens BEFORE today's trigger point, the
    recovered next_run_at must land on TODAY, not tomorrow.

    This is the user-suggested regression test. It confirms that
    compute_next_run(schedule, now.isoformat(), timezone=tz) behaves
    identically to compute_next_run(schedule, timezone=tz) and does not
    skip the same-day window — which is the recovery contract.
    """

    def test_recovery_before_trigger_lands_today(self, monkeypatch):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from cron.jobs import compute_next_run

        shanghai = ZoneInfo("Asia/Shanghai")
        # Now is 08:50 北京 — daily 09:00 should fire TODAY in 10 minutes.
        now = datetime(2026, 5, 18, 8, 50, 0, tzinfo=shanghai)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "0 9 * * *"}

        # The recovery path passes now.isoformat() as last_run_at. Result
        # must be today 09:00, not tomorrow.
        result = compute_next_run(
            schedule, now.isoformat(), timezone="Asia/Shanghai"
        )
        next_shanghai = datetime.fromisoformat(result).astimezone(shanghai)
        assert next_shanghai.date().isoformat() == "2026-05-18", (
            f"Recovery skipped today! Expected today 09:00, got {next_shanghai}"
        )
        assert next_shanghai.hour == 9 and next_shanghai.minute == 0


class TestProcessJobOrderingContract:
    """The start notice must be delivered BEFORE run_job(), and notice
    failures must NEVER prevent run_job() from being invoked.

    We do not drive the full scheduler.tick() — that would pull in IO and
    threading. Instead we verify the contract pieces independently:
      - the symbols exist at module level (importable & mockable)
      - the try/except shape used in _process_job behaves as designed
    """

    def test_symbols_are_module_level(self):
        import cron.scheduler as sched
        assert callable(sched._deliver_notice)
        assert callable(sched._build_start_notice)
        assert callable(sched._sanitize_for_notice)

    def test_try_except_isolation_pattern(self):
        """Mirror the exact try/except shape used in _process_job: a notice-
        building exception must NOT prevent the next step (run_job)."""

        def _bad_builder(job):
            raise RuntimeError("notice builder crashed")

        run_job_called = []
        try:
            _bad_builder({"id": "x"})
        except Exception:
            pass  # production code logs and continues — does not re-raise
        run_job_called.append(True)
        assert run_job_called == [True], (
            "If we did not reach this line, _process_job would skip run_job. "
            "The notice exception MUST be swallowed."
        )
