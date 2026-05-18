from __future__ import annotations

import json


class _CaptureCtx:
    def __init__(self):
        self.tools = {}
        self.hooks = []

    def register_hook(self, name, handler):
        self.hooks.append((name, handler))

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_aiseo_guard_registers_readonly_skill_wrappers(aiseo_guard):
    ctx = _CaptureCtx()

    aiseo_guard.register(ctx)

    assert ctx.tools["aiseo_skills_list"]["toolset"] == "aiseo_skills_read"
    assert ctx.tools["aiseo_skill_view"]["toolset"] == "aiseo_skills_read"
    assert "skill_manage" not in ctx.tools
    assert "skill_view" not in ctx.tools
    assert "skills_list" not in ctx.tools


def test_aiseo_skill_wrappers_delegate_to_readonly_skill_functions(aiseo_guard, monkeypatch):
    calls = []

    def fake_skills_list(category=None, task_id=None):
        calls.append(("list", category, task_id))
        return json.dumps({"success": True, "skills": []})

    def fake_skill_view_with_bump(args, **kwargs):
        calls.append(("view", args, kwargs.get("task_id")))
        return json.dumps({"success": True, "name": args["name"], "content": "ok"})

    monkeypatch.setattr("tools.skills_tool.skills_list", fake_skills_list)
    monkeypatch.setattr("tools.skills_tool._skill_view_with_bump", fake_skill_view_with_bump)

    ctx = _CaptureCtx()
    aiseo_guard.register(ctx)

    listed = _payload(ctx.tools["aiseo_skills_list"]["handler"]({"category": "seo"}, task_id="task-1"))
    viewed = _payload(
        ctx.tools["aiseo_skill_view"]["handler"](
            {"name": "growflare-seo", "file_path": "references/x.md"},
            task_id="task-2",
        )
    )

    assert listed["success"] is True
    assert viewed["success"] is True
    assert calls == [
        ("list", "seo", "task-1"),
        ("view", {"name": "growflare-seo", "file_path": "references/x.md"}, "task-2"),
    ]


def test_aiseo_skill_view_triggers_curator_bump(aiseo_guard, monkeypatch):
    """Regression: aiseo_skill_view MUST route through _skill_view_with_bump,
    not the bare skill_view, so curator's view_count / last_used_at telemetry
    keeps updating for skills loaded via the AISEO wrapper.

    This test lets the real _skill_view_with_bump run (no monkeypatch on the
    wrapper itself) and only patches its leaf dependencies:
      - skill_view (the bare function it delegates to for I/O)
      - bump_view / bump_use (the telemetry calls it makes on success)
    so we can verify bumps actually fire."""
    bump_view_calls: list[str] = []
    bump_use_calls: list[str] = []

    def fake_skill_view(name, file_path=None, task_id=None):
        return json.dumps({"success": True, "name": name, "content": "ok"})

    def fake_bump_view(name):
        bump_view_calls.append(name)

    def fake_bump_use(name):
        bump_use_calls.append(name)

    monkeypatch.setattr("tools.skills_tool.skill_view", fake_skill_view)
    monkeypatch.setattr("tools.skill_usage.bump_view", fake_bump_view)
    monkeypatch.setattr("tools.skill_usage.bump_use", fake_bump_use)

    ctx = _CaptureCtx()
    aiseo_guard.register(ctx)

    result = _payload(
        ctx.tools["aiseo_skill_view"]["handler"](
            {"name": "technical-seo-audit"},
            task_id="task-bump",
        )
    )

    assert result["success"] is True
    assert bump_view_calls == ["technical-seo-audit"], (
        f"bump_view was not called — curator telemetry is broken. Got: {bump_view_calls!r}"
    )
    assert bump_use_calls == ["technical-seo-audit"], (
        f"bump_use was not called — curator stale-skill detection will misfire. Got: {bump_use_calls!r}"
    )
