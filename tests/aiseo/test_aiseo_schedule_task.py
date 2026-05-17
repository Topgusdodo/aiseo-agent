from __future__ import annotations

import json

import pytest


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_schedule_task_creates_origin_delivered_technical_audit(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")
    monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "123")
    monkeypatch.setenv("HERMES_SESSION_CHAT_NAME", "SEO Room")
    monkeypatch.setenv("HERMES_SESSION_THREAD_ID", "456")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "technical_audit",
                "site_url": "https://lazseo.com/",
                "frequency": "weekly",
                "time": "09:30",
                "timezone": "Asia/Shanghai",
                "language": "zh-CN",
                "keywords": ["seo automation"],
                "competitors": ["example.com"],
            }
        )
    )

    assert result["success"] is True
    job = result["job"]
    assert job["task_type"] == "technical_audit"
    assert job["site_url"] == "https://lazseo.com/"
    assert job["schedule"] == "30 9 * * 1"
    assert job["deliver"] == "origin"
    assert job["origin"]["platform"] == "telegram"
    assert job["origin"]["chat_id"] == "123"
    assert job["origin"]["thread_id"] == "456"
    assert job["skills"] == ["technical-seo-audit"]
    assert job["enabled_toolsets"] == ["web", "search", "browser"]


def test_schedule_task_monthly_uses_monthly_cron(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "seo_delta_report",
                "site_url": "https://example.com",
                "frequency": "monthly",
                "time": "08:00",
            }
        )
    )

    assert result["success"] is True
    assert result["job"]["schedule"] == "0 8 1 * *"
    assert result["job"]["deliver"] == "local"
    assert result["job"]["skills"] == ["seo-weekly-report"]


def test_schedule_task_unwraps_model_argument_wrappers(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    value_wrapped = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "string": False,
                "value": json.dumps(
                    {
                        "task_type": "page_audit",
                        "page_url": "https://example.com",
                        "frequency": "daily",
                        "time": "23:00",
                    }
                ),
            }
        )
    )
    params_wrapped = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "params": {
                    "task_type": "page_audit",
                    "page_url": "https://example.org",
                    "frequency": "daily",
                    "time": "23:30",
                }
            }
        )
    )

    assert value_wrapped["success"] is True, value_wrapped
    assert value_wrapped["job"]["task_type"] == "page_audit"
    assert value_wrapped["job"]["time"] == "23:00"
    assert params_wrapped["success"] is True, params_wrapped
    assert params_wrapped["job"]["task_type"] == "page_audit"
    assert params_wrapped["job"]["time"] == "23:30"


def test_schedule_task_supports_all_seo_task_types(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    cases = [
        ("site_health_check", {"site_url": "https://example.com"}, ["technical-seo-audit"]),
        ("technical_audit", {"site_url": "https://example.com"}, ["technical-seo-audit"]),
        ("page_audit", {"page_url": "https://example.com/blog/post"}, ["growflare-seo"]),
        ("keyword_opportunity", {"target_keyword": "seo automation"}, ["keyword-opportunity"]),
        ("competitor_monitoring", {
            "site_url": "https://example.com",
            "competitors": ["https://example.org", "https://example.net"],
        }, ["competitor-analysis"]),
        ("content_brief", {"target_keyword": "ai seo tools"}, ["content-brief"]),
        ("seo_delta_report", {"site_url": "https://example.com"}, ["seo-weekly-report"]),
    ]

    for task_type, extra_args, skills in cases:
        result = _payload(
            aiseo_guard._aiseo_schedule_task({"task_type": task_type, **extra_args})
        )
        assert result["success"] is True, result
        assert result["job"]["task_type"] == task_type
        assert result["job"]["skills"] == skills
        assert result["job"]["enabled_toolsets"] == ["web", "search", "browser"]


def test_schedule_task_rejects_private_targets(aiseo_guard):
    for site_url in (
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://site.internal/",
        "file:///tmp/site.html",
    ):
        result = _payload(
            aiseo_guard._aiseo_schedule_task(
                {"task_type": "technical_audit", "site_url": site_url}
            )
        )
        assert result["success"] is False, site_url


def test_schedule_task_rejects_invalid_time_frequency_and_task_type(aiseo_guard):
    bad_time = _payload(
        aiseo_guard._aiseo_schedule_task(
            {"task_type": "technical_audit", "site_url": "https://example.com", "time": "9am"}
        )
    )
    assert bad_time["success"] is False
    assert "HH:MM" in bad_time["error"]

    bad_frequency = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "technical_audit",
                "site_url": "https://example.com",
                "frequency": "every_5min",
            }
        )
    )
    assert bad_frequency["success"] is False
    assert "frequency must be one of" in bad_frequency["error"]
    assert "every_5min" not in bad_frequency["error"]

    bad_task = _payload(
        aiseo_guard._aiseo_schedule_task(
            {"task_type": "backup_database", "site_url": "https://example.com"}
        )
    )
    assert bad_task["success"] is False
    assert "task_type must be one of" in bad_task["error"]


def test_schedule_task_rejects_competitor_private_target(aiseo_guard):
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "competitor_monitoring",
                "site_url": "https://example.com",
                "competitors": ["localhost", "https://example.org"],
            }
        )
    )
    assert result["success"] is False
    assert "competitors" in result["error"]


def test_schedule_task_rejects_forbidden_generic_cron_fields(aiseo_guard):
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "technical_audit",
                "site_url": "https://example.com",
                "script": "cat /etc/passwd",
                "deliver": "all",
                "workdir": "/tmp",
            }
        )
    )
    assert result["success"] is False
    assert "Unsupported field" in result["error"]


def test_schedule_report_alias_still_creates_delta_report(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_report({"site_url": "https://example.com"})
    )

    assert result["success"] is True
    assert result["job"]["task_type"] == "seo_delta_report"
    assert result["job"]["skills"] == ["seo-weekly-report"]


def test_aiseo_schedule_task_hourly_cron_expr(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "hourly",
                "time": "09:30",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    assert job["frequency"] == "hourly"
    # Sub-daily cadence: cron only carries MM; the displayed HH:MM stays in the
    # job's prompt for human readability.
    assert job["schedule"] == "30 * * * *"
    assert job["time"] == "09:30"


def test_aiseo_schedule_task_every_6h_cron_expr(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "every_6h",
                "time": "09:15",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    assert job["frequency"] == "every_6h"
    # every_6h fires every 6 hours anchored to the submitted HH:MM.
    assert job["schedule"] == "15 3,9,15,21 * * *"
    assert job["time"] == "09:15"


def test_aiseo_schedule_task_every_12h_cron_expr(aiseo_guard, tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "every_12h",
                "time": "09:45",
            }
        )
    )

    assert result["success"] is True, result
    job = result["job"]
    assert job["frequency"] == "every_12h"
    assert job["schedule"] == "45 9,21 * * *"
    assert job["time"] == "09:45"


def test_aiseo_schedule_task_rejects_minute_level_frequency(aiseo_guard):
    """Anti-slippage guard: hourly is the floor, anything sub-hourly must reject."""
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "every_5min",
                "time": "09:00",
            }
        )
    )
    assert result["success"] is False
    assert "frequency must be one of" in result["error"]


def test_aiseo_schedule_task_rejects_arbitrary_cron_expression(aiseo_guard):
    """Anti-slippage guard: raw cron strings must never reach the schedule expr."""
    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "*/5 * * * *",
                "time": "09:00",
            }
        )
    )
    assert result["success"] is False
    assert "frequency must be one of" in result["error"]


def test_aiseo_schedule_task_subdaily_cadence_prompt_carries_full_time(
    aiseo_guard, tmp_path, monkeypatch
):
    """Schedule label in the prompt keeps the HH:MM the customer specified
    even when the hourly cron expression only uses MM."""
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    from cron.jobs import get_job

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": "hourly",
                "time": "14:42",
            }
        )
    )
    assert result["success"] is True, result
    stored = get_job(result["job"]["id"])
    assert "Schedule label: hourly at 14:42 (Asia/Shanghai)." in stored["prompt"]
    # Plugin must classify its own newly created sub-daily job as AISEO-owned.
    assert aiseo_guard._is_aiseo_created_job(stored)


@pytest.mark.parametrize(
    "frequency,expected_expr",
    [
        ("daily", "0 9 * * *"),
        ("weekly", "0 9 * * 1"),
        ("monthly", "0 9 1 * *"),
        ("hourly", "0 * * * *"),
        ("every_6h", "0 3,9,15,21 * * *"),
        ("every_12h", "0 9,21 * * *"),
    ],
)
def test_aiseo_schedule_task_all_frequencies_produce_canonical_cron(
    aiseo_guard, tmp_path, monkeypatch, frequency, expected_expr
):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")

    result = _payload(
        aiseo_guard._aiseo_schedule_task(
            {
                "task_type": "page_audit",
                "page_url": "https://example.com",
                "frequency": frequency,
                "time": "09:00",
            }
        )
    )

    assert result["success"] is True, result
    assert result["job"]["frequency"] == frequency
    assert result["job"]["schedule"] == expected_expr
