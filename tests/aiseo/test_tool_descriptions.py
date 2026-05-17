from __future__ import annotations

from pathlib import Path


def test_schedule_task_description_does_not_require_preconfirmation(aiseo_guard):
    description = aiseo_guard.AISEO_SCHEDULE_TASK_SCHEMA["description"].lower()

    assert "confirms" not in description
    assert "pre-confirm" in description
    assert "safe defaults" in description


def test_manage_scheduled_tasks_reschedule_schema_is_time_only(aiseo_guard):
    schema = aiseo_guard.AISEO_MANAGE_SCHEDULED_TASKS_SCHEMA
    props = schema["parameters"]["properties"]

    assert "reschedule" in props["action"]["enum"]
    for field in ("frequency", "time", "timezone"):
        assert "reschedule only" in props[field]["description"].lower()
        assert "task identity" in props[field]["description"].lower()


def test_aiseo_soul_does_not_encourage_raw_cron_examples():
    repo_root = Path(__file__).resolve().parents[2]
    soul = (repo_root / "seeds" / "aiseo-profile" / "SOUL.md").read_text(
        encoding="utf-8"
    )

    assert "* * * * *" not in soul
    # Frequency enum advertised in SOUL must include the narrow daily/weekly/monthly
    # plus the new sub-daily cadences (hourly / 6h / 12h) but NOT raw cron expressions.
    assert "每天 / 每周 / 每月 / 每小时 / 每 6 小时 / 每 12 小时 + HH:MM" in soul
    # Sub-hourly cadences must remain explicitly rejected to keep the narrow
    # enum and prevent slipping into arbitrary minute-level schedules.
    assert "短于每小时的频率" in soul
    assert "reschedule" in soul
