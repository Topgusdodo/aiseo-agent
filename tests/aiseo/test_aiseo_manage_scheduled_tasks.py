from __future__ import annotations

import json

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
