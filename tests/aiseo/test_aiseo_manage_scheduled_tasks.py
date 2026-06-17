from __future__ import annotations

import json

import pytest

from cron.jobs import create_job, get_job


def _payload(raw: str) -> dict:
    return json.loads(raw)


def _isolate_cron(tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")


def _set_origin(monkeypatch, chat_id: str = "123", thread_id: str = "456"):
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", chat_id)
    monkeypatch.setenv("HERMES_SESSION_THREAD_ID", thread_id)


def _create_aiseo_task(aiseo_guard, **overrides) -> dict:
    args = {
        "task_type": "technical_audit",
        "site_url": "https://example.com",
        **overrides,
    }
    result = _payload(aiseo_guard._aiseo_schedule_task(args))
    assert result["success"] is True, result
    return result["job"]


def test_manage_scheduled_tasks_lists_only_current_origin_aiseo_jobs(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch, chat_id="123")
    own = _create_aiseo_task(aiseo_guard)

    _set_origin(monkeypatch, chat_id="999")
    _create_aiseo_task(aiseo_guard)

    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "123")
    create_job(prompt="generic job", schedule="0 9 * * *", name="Generic job")

    listed = _payload(aiseo_guard._aiseo_manage_scheduled_tasks({"action": "list"}))

    assert listed["success"] is True
    assert [task["id"] for task in listed["tasks"]] == [own["id"]]
    assert "prompt" not in listed["tasks"][0]


def test_manage_scheduled_tasks_allows_custom_named_aiseo_jobs(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard, report_name="官网周报")

    listed = _payload(aiseo_guard._aiseo_manage_scheduled_tasks({"action": "list"}))
    viewed = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "view", "job_id": job["id"]}
        )
    )

    assert listed["success"] is True
    assert [task["id"] for task in listed["tasks"]] == [job["id"]]
    assert viewed["success"] is True
    assert viewed["task"]["name"] == "官网周报"


def test_manage_scheduled_tasks_view_does_not_return_prompt(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "view", "job_id": job["id"]}
        )
    )

    assert result["success"] is True
    assert result["task"]["id"] == job["id"]
    assert result["task"]["task_type"] == "technical_audit"
    assert "prompt" not in result["task"]


def test_manage_scheduled_tasks_pause_and_resume(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    paused = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": job["id"]}
        )
    )
    assert paused["success"] is True
    assert paused["task"]["enabled"] is False
    assert paused["task"]["state"] == "paused"
    assert get_job(job["id"])["state"] == "paused"

    resumed = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "resume", "job_id": job["id"]}
        )
    )
    assert resumed["success"] is True
    assert resumed["task"]["enabled"] is True
    assert resumed["task"]["state"] == "scheduled"


def test_manage_scheduled_tasks_resolves_exact_task_name(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard, report_name="daily-py-health")

    paused = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": "daily-py-health"}
        )
    )
    resumed = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "resume", "job_id": "daily-py-health"}
        )
    )

    assert paused["success"] is True, paused
    assert resumed["success"] is True, resumed
    assert resumed["task"]["id"] == job["id"]
    assert get_job(job["id"])["state"] == "scheduled"


def test_manage_scheduled_tasks_defaults_missing_action_to_safe_list(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    listed = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks({"include_paused": True})
    )

    assert listed["success"] is True
    assert [task["id"] for task in listed["tasks"]] == [job["id"]]


def test_manage_scheduled_tasks_delete_requires_confirmation(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    rejected = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "delete", "job_id": job["id"]}
        )
    )
    assert rejected["success"] is False
    assert get_job(job["id"]) is not None

    deleted = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "delete", "job_id": job["id"], "confirm": True}
        )
    )
    assert deleted["success"] is True
    assert deleted["deleted_job_id"] == job["id"]
    assert get_job(job["id"]) is None


def test_manage_scheduled_tasks_reschedule_time_preserves_frequency_and_timezone(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": job["id"], "time": "15:42"}
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["frequency"] == "weekly"
    assert result["reschedule"]["time"] == "15:42"
    assert result["reschedule"]["timezone"] == "Asia/Shanghai"
    assert result["reschedule"]["schedule"].startswith("42 15 * * 1")
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "42 15 * * 1"
    assert stored["schedule_display"].startswith("42 15 * * 1")
    assert "(Asia/Shanghai)" in stored["schedule_display"]
    assert stored["timezone"] == "Asia/Shanghai"
    assert "Schedule label: weekly at 15:42 (Asia/Shanghai)." in stored["prompt"]
    assert "Schedule label: weekly at 09:00 (Asia/Shanghai)." not in stored["prompt"]
    assert aiseo_guard._is_aiseo_created_job(stored)
    assert "prompt" not in result["task"]


def test_manage_scheduled_tasks_reschedule_unwraps_params_wrapper(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "params": {
                    "action": "reschedule",
                    "job_id": job["id"],
                    "time": "16:30",
                }
            }
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["time"] == "16:30"
    assert get_job(job["id"])["schedule"]["expr"] == "30 16 * * 1"


def test_manage_scheduled_tasks_reschedule_frequency_and_time(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "monthly",
                "time": "08:15",
            }
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["frequency"] == "monthly"
    assert result["reschedule"]["time"] == "08:15"
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "15 8 1 * *"
    assert "Schedule label: monthly at 08:15 (Asia/Shanghai)." in stored["prompt"]


def test_manage_scheduled_tasks_reschedule_timezone_updates_prompt_only(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": job["id"], "timezone": "UTC"}
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["timezone"] == "UTC"
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "0 9 * * 1"
    assert "Schedule label: weekly at 09:00 (UTC)." in stored["prompt"]
    assert "Schedule label: weekly at 09:00 (Asia/Shanghai)." not in stored["prompt"]


@pytest.mark.parametrize("field", ["task_type", "site_url", "page_url"])
def test_manage_scheduled_tasks_reschedule_rejects_task_identity_fields(
    aiseo_guard, tmp_path, monkeypatch, field
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": job["id"], "time": "10:00", field: "x"}
        )
    )

    assert result["success"] is False
    assert "Unsupported field" in result["error"]


def test_manage_scheduled_tasks_reschedule_rejects_other_origin_and_generic_jobs(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch, chat_id="999")
    other = _create_aiseo_task(aiseo_guard)

    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "123")
    blocked_other = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": other["id"], "time": "10:00"}
        )
    )
    assert blocked_other["success"] is False
    assert "not found or not accessible" in blocked_other["error"]

    generic = create_job(prompt="Run something", schedule="0 9 * * *", name="Generic")
    blocked_generic = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": generic["id"], "time": "10:00"}
        )
    )
    assert blocked_generic["success"] is False
    assert "not found or not accessible" in blocked_generic["error"]


def test_manage_scheduled_tasks_reschedule_paused_job_stays_paused(
    aiseo_guard, tmp_path, monkeypatch
):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)
    paused = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": job["id"]}
        )
    )
    assert paused["success"] is True

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": job["id"], "time": "11:45"}
        )
    )

    assert result["success"] is True, result
    stored = get_job(job["id"])
    assert stored["state"] == "paused"
    assert stored["enabled"] is False
    assert stored["schedule"]["expr"] == "45 11 * * 1"


def test_manage_scheduled_tasks_reschedule_missing_job_id_returns_error(aiseo_guard):
    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "reschedule", "job_id": "does-not-exist", "time": "10:00"}
        )
    )

    assert result["success"] is False
    assert "not found or not accessible" in result["error"]


def test_manage_scheduled_tasks_rejects_other_origin_and_generic_jobs(aiseo_guard, tmp_path, monkeypatch):
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch, chat_id="999")
    other = _create_aiseo_task(aiseo_guard)

    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "123")
    blocked_other = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": other["id"]}
        )
    )
    assert blocked_other["success"] is False
    assert "not found or not accessible" in blocked_other["error"]

    generic = create_job(prompt="Run something", schedule="0 9 * * *", name="Generic")
    blocked_generic = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": generic["id"]}
        )
    )
    assert blocked_generic["success"] is False
    assert "not found or not accessible" in blocked_generic["error"]


def test_manage_scheduled_tasks_validates_action_and_job_id(aiseo_guard):
    bad_action = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks({"action": "run"})
    )
    assert bad_action["success"] is False
    assert "action must be one of" in bad_action["error"]

    missing_job = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks({"action": "pause"})
    )
    assert missing_job["success"] is False
    assert "job_id is required" in missing_job["error"]


def test_manage_scheduled_tasks_reschedule_daily_to_hourly(aiseo_guard, tmp_path, monkeypatch):
    """daily → hourly swaps the cron expression from ``MM HH * * *`` to
    ``MM * * * *`` and rewrites the Schedule label inside the prompt."""
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(
        aiseo_guard,
        task_type="page_audit",
        page_url="https://example.com",
        frequency="daily",
        time="08:00",
    )

    # Sanity: starting from a daily cron expression.
    assert get_job(job["id"])["schedule"]["expr"] == "0 8 * * *"

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "hourly",
                "time": "09:30",
            }
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["frequency"] == "hourly"
    assert result["reschedule"]["time"] == "09:30"
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "30 * * * *"
    assert "Schedule label: hourly at 09:30 (Asia/Shanghai)." in stored["prompt"]
    assert "Schedule label: daily" not in stored["prompt"]
    assert aiseo_guard._is_aiseo_created_job(stored)


def test_manage_scheduled_tasks_reschedule_hourly_to_every_6h(aiseo_guard, tmp_path, monkeypatch):
    """hourly → every_6h rewrites the hour field from ``*`` to an anchored set."""
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(
        aiseo_guard,
        task_type="page_audit",
        page_url="https://example.com",
        frequency="hourly",
        time="09:15",
    )
    assert get_job(job["id"])["schedule"]["expr"] == "15 * * * *"

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "every_6h",
                "time": "10:20",
            }
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["frequency"] == "every_6h"
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "20 4,10,16,22 * * *"
    assert "Schedule label: every_6h at 10:20 (Asia/Shanghai)." in stored["prompt"]
    assert aiseo_guard._is_aiseo_created_job(stored)


def test_manage_scheduled_tasks_reschedule_every_12h_to_daily(aiseo_guard, tmp_path, monkeypatch):
    """every_12h → daily restores a full ``MM HH * * *`` form."""
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(
        aiseo_guard,
        task_type="page_audit",
        page_url="https://example.com",
        frequency="every_12h",
        time="07:45",
    )
    assert get_job(job["id"])["schedule"]["expr"] == "45 7,19 * * *"

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "daily",
                "time": "09:00",
            }
        )
    )

    assert result["success"] is True, result
    assert result["reschedule"]["frequency"] == "daily"
    stored = get_job(job["id"])
    assert stored["schedule"]["expr"] == "0 9 * * *"
    assert "Schedule label: daily at 09:00 (Asia/Shanghai)." in stored["prompt"]
    assert aiseo_guard._is_aiseo_created_job(stored)


def test_manage_scheduled_tasks_reschedule_paused_hourly_stays_paused(
    aiseo_guard, tmp_path, monkeypatch
):
    """Pause state must survive a sub-daily reschedule, mirroring the existing
    daily/weekly invariant for the new frequencies."""
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(
        aiseo_guard,
        task_type="page_audit",
        page_url="https://example.com",
        frequency="hourly",
        time="09:00",
    )
    paused = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {"action": "pause", "job_id": job["id"]}
        )
    )
    assert paused["success"] is True

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "every_12h",
                "time": "11:30",
            }
        )
    )

    assert result["success"] is True, result
    stored = get_job(job["id"])
    assert stored["state"] == "paused"
    assert stored["enabled"] is False
    assert stored["schedule"]["expr"] == "30 11,23 * * *"


def test_manage_scheduled_tasks_reschedule_rejects_minute_level_frequency(
    aiseo_guard, tmp_path, monkeypatch
):
    """Defense-in-depth: reschedule must reject sub-hourly cadences too."""
    _isolate_cron(tmp_path, monkeypatch)
    _set_origin(monkeypatch)
    job = _create_aiseo_task(aiseo_guard)

    result = _payload(
        aiseo_guard._aiseo_manage_scheduled_tasks(
            {
                "action": "reschedule",
                "job_id": job["id"],
                "frequency": "every_5min",
            }
        )
    )

    assert result["success"] is False
    assert "frequency must be one of" in result["error"]
