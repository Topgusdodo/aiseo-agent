"""Unit tests for plugins.dataforseo — client, handlers, and registration.

Mirrors the shape of tests/tools/test_spotify_client.py: fake httpx.request,
fake response objects, and per-test monkeypatched env vars. Covers:

* 401 -> DataForSEOAuthRequiredError
* 402 -> DataForSEOAPIError with status_code preserved
* 429 -> exponential backoff (5/10/20s), then success / give up
* sandbox host switch via DATAFORSEO_SANDBOX
* 3-step task lifecycle (task_post -> tasks_ready filter by task_id -> task_get)
* crawl_progress polling (finished / timeout)
* credential masking — Basic auth never appears in error strings
* env-missing -> handler returns tool_error(..., code=401)
* plugin registration — 5 tools land in the registry; check_fn behavior
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

import pytest

from plugins.dataforseo import client as dfs_client
from plugins.dataforseo import tools as dfs_tools


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        text: str = "",
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {"content-type": "application/json"}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def _install_fake_request(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., _FakeResponse],
) -> list[tuple[str, str, dict, Any]]:
    """Replace httpx.request with a recording fake driven by ``handler``."""
    calls: list[tuple[str, str, dict, Any]] = []

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        calls.append((method, url, dict(headers or {}), json))
        return handler(method, url, dict(headers or {}), json)

    monkeypatch.setattr(dfs_client.httpx, "request", fake_request)
    return calls


_FAKE_AUTH_B64 = "dGVzdEBleGFtcGxlLmNvbTphcGlrZXlfdGVzdA=="  # test@example.com:apikey_test


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to credentials set; tests can override or pop."""
    monkeypatch.setenv("DATAFORSEO_BASE64", _FAKE_AUTH_B64)
    monkeypatch.delenv("DATAFORSEO_SANDBOX", raising=False)
    # Avoid real sleeps inside 429 / poll branches.
    monkeypatch.setattr(dfs_client.time, "sleep", lambda *_a, **_kw: None)


# ---------------------------------------------------------------------------
# __init__ / sandbox / credential masking
# ---------------------------------------------------------------------------


def test_client_init_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)
    with pytest.raises(dfs_client.DataForSEOAuthRequiredError):
        dfs_client.DataForSEOClient()


def test_client_uses_explicit_auth_b64_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)
    client = dfs_client.DataForSEOClient(auth_b64="ZXhwbGljaXQ6dG9rZW4=")
    assert client._auth_header == "Basic ZXhwbGljaXQ6dG9rZW4="


def test_client_uses_sandbox_host_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAFORSEO_SANDBOX", "1")
    client = dfs_client.DataForSEOClient()
    assert client._host == dfs_client.SANDBOX_HOST


def test_client_uses_prod_host_by_default() -> None:
    client = dfs_client.DataForSEOClient()
    assert client._host == dfs_client.PROD_HOST


def test_mask_auth_header_redacts_basic_auth() -> None:
    raw = "Authorization: Basic dGVzdEBleGFtcGxlLmNvbTphcGlrZXlfdGVzdA== was sent"
    masked = dfs_client._mask_auth_header(raw)
    assert "Basic ***" in masked
    assert "dGVzdEBleGFtcGxlLmNvbTph" not in masked


def test_mask_auth_header_handles_empty_input() -> None:
    assert dfs_client._mask_auth_header("") == ""


# ---------------------------------------------------------------------------
# 401 / 402 / 429 paths
# ---------------------------------------------------------------------------


def test_client_raises_auth_required_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_request(
        monkeypatch,
        lambda *_: _FakeResponse(401, {"status_code": 40100, "status_message": "Auth failed"}),
    )
    client = dfs_client.DataForSEOClient()
    with pytest.raises(dfs_client.DataForSEOAuthRequiredError):
        client.backlinks_summary(target="example.com", mode="live")


def test_client_raises_api_error_with_status_code_on_402(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_request(
        monkeypatch,
        lambda *_: _FakeResponse(402, text="402 Payment Required"),
    )
    client = dfs_client.DataForSEOClient()
    with pytest.raises(dfs_client.DataForSEOAPIError) as ei:
        client.backlinks_summary(target="example.com", mode="live")
    assert ei.value.status_code == 402


def test_client_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = {"n": 0}

    def handler(*_a):
        counter["n"] += 1
        if counter["n"] < 3:
            return _FakeResponse(429, text="rate limited")
        return _FakeResponse(200, {"status_code": 20000, "tasks": []})

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    payload = client.backlinks_summary(target="example.com", mode="live")
    assert counter["n"] == 3
    assert payload["status_code"] == 20000


def test_client_gives_up_after_429_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = {"n": 0}

    def handler(*_a):
        counter["n"] += 1
        return _FakeResponse(429, text="rate limited")

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    with pytest.raises(dfs_client.DataForSEOAPIError) as ei:
        client.backlinks_summary(target="example.com", mode="live")
    # 1 initial + 3 retries
    assert counter["n"] == len(dfs_client.RATE_LIMIT_BACKOFFS) + 1
    assert ei.value.status_code == 429


# ---------------------------------------------------------------------------
# Standard 3-step task lifecycle — task_post / tasks_ready filter / task_get
# ---------------------------------------------------------------------------


def test_serp_google_standard_polls_by_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standard SERP flow must filter tasks_ready by the just-posted id."""
    target_id = "11220304-0000-0000-0000-abcdef"
    other_id = "99999999-1111-2222-3333-cccccc"
    state = {"posted": False, "ready_hits": 0}

    def handler(method, url, *_):
        if method == "POST" and url.endswith("/v3/serp/google/organic/task_post"):
            state["posted"] = True
            return _FakeResponse(200, {
                "status_code": 20000,
                "tasks": [{"id": target_id, "status_code": 20000}],
            })
        if method == "GET" and url.endswith("/v3/serp/google/organic/tasks_ready"):
            state["ready_hits"] += 1
            # First poll returns only an unrelated id; second poll returns ours.
            if state["ready_hits"] < 2:
                return _FakeResponse(200, {
                    "status_code": 20000,
                    "tasks": [{"result": [{"id": other_id}]}],
                })
            return _FakeResponse(200, {
                "status_code": 20000,
                "tasks": [{"result": [{"id": other_id}, {"id": target_id}]}],
            })
        if method == "GET" and url.endswith(f"/v3/serp/google/organic/task_get/advanced/{target_id}"):
            return _FakeResponse(200, {
                "status_code": 20000,
                "tasks": [{"id": target_id, "result": [{"items": []}]}],
            })
        raise AssertionError(f"unexpected call {method} {url}")

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    payload = client.serp_google(
        keyword="vegan protein",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=10,
        mode="standard",
    )
    assert state["posted"] is True
    assert state["ready_hits"] == 2
    assert payload["tasks"][0]["id"] == target_id


def test_keyword_volume_standard_uses_task_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = "kw-task-1"

    def handler(method, url, *_):
        if "task_post" in url:
            return _FakeResponse(200, {"tasks": [{"id": target_id}]})
        if "tasks_ready" in url:
            return _FakeResponse(200, {"tasks": [{"result": [{"id": target_id}]}]})
        if f"/task_get/{target_id}" in url:
            return _FakeResponse(200, {"tasks": [{"id": target_id, "result": [{"keyword": "kindle"}]}]})
        raise AssertionError(f"unexpected {method} {url}")

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    payload = client.keyword_volume(
        keywords=["kindle"],
        location_code=2840,
        language_code="en",
        mode="standard",
    )
    assert payload["tasks"][0]["id"] == target_id


def test_live_mode_skips_task_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live mode must hit exactly one /live endpoint, no polling."""
    seen_paths: list[str] = []

    def handler(_method, url, *_):
        seen_paths.append(url)
        return _FakeResponse(200, {"status_code": 20000, "tasks": []})

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    client.serp_google(
        keyword="x",
        location_code=2840,
        language_code="en",
        device="desktop",
        depth=10,
        mode="live",
    )
    assert len(seen_paths) == 1
    assert "/live/advanced" in seen_paths[0]


# ---------------------------------------------------------------------------
# crawl_progress polling (OnPage)
# ---------------------------------------------------------------------------


def test_crawl_progress_returns_when_finished(monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = "onpage-1"
    state = {"posts": 0, "polls": 0}

    def handler(method, url, *_):
        if method == "POST" and url.endswith("/v3/on_page/task_post"):
            state["posts"] += 1
            return _FakeResponse(200, {"tasks": [{"id": task_id}]})
        if method == "GET" and f"/v3/on_page/summary/{task_id}" in url:
            state["polls"] += 1
            # Mark finished on the second poll; first one is in-progress.
            crawl_progress = "finished" if state["polls"] >= 2 else "in_progress"
            return _FakeResponse(200, {"tasks": [{"result": [{"crawl_progress": crawl_progress, "id": task_id}]}]})
        raise AssertionError(f"unexpected {method} {url}")

    _install_fake_request(monkeypatch, handler)
    monkeypatch.setattr(dfs_client, "ONPAGE_POLL_INTERVAL", 0.0)
    client = dfs_client.DataForSEOClient()
    payload = client.onpage_summary(
        target="https://example.com",
        max_crawl_pages=10,
        mode="standard",
    )
    assert state["posts"] == 1
    assert state["polls"] >= 3  # 2 worker polls + 1 final summary fetch
    assert payload["tasks"][0]["result"][0]["crawl_progress"] == "finished"


def test_crawl_progress_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = "onpage-slow"

    def handler(method, url, *_):
        if method == "POST" and url.endswith("/v3/on_page/task_post"):
            return _FakeResponse(200, {"tasks": [{"id": task_id}]})
        if method == "GET" and f"/v3/on_page/summary/{task_id}" in url:
            return _FakeResponse(200, {"tasks": [{"result": [{"crawl_progress": "in_progress"}]}]})
        raise AssertionError(f"unexpected {method} {url}")

    _install_fake_request(monkeypatch, handler)
    monkeypatch.setattr(dfs_client, "ONPAGE_POLL_INTERVAL", 0.0)
    monkeypatch.setattr(dfs_client, "ONPAGE_POLL_TIMEOUT", 0.05)
    client = dfs_client.DataForSEOClient()
    with pytest.raises(dfs_client.DataForSEOAPIError) as ei:
        client.onpage_summary(target="https://example.com", max_crawl_pages=10, mode="standard")
    assert ei.value.status_code == 408


# ---------------------------------------------------------------------------
# Credential leakage
# ---------------------------------------------------------------------------


def test_credentials_not_in_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """If DataForSEO returns 500 with body echoing auth, it must not leak."""

    def handler(*_a):
        # Simulate a server echoing the auth header in its response body.
        return _FakeResponse(
            500,
            text=f"upstream failure — Authorization: Basic {_FAKE_AUTH_B64}",
        )

    _install_fake_request(monkeypatch, handler)
    client = dfs_client.DataForSEOClient()
    with pytest.raises(dfs_client.DataForSEOAPIError) as ei:
        client.backlinks_summary(target="example.com", mode="live")
    message = str(ei.value)
    assert "Basic ***" in message
    assert _FAKE_AUTH_B64 not in message


# ---------------------------------------------------------------------------
# Handler env gating
# ---------------------------------------------------------------------------


def test_handler_returns_tool_error_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)
    payload = json.loads(dfs_tools._handle_dataforseo_serp_google({"keyword": "test"}))
    assert payload.get("code") == 401
    assert "credentials" in payload["error"].lower()
    assert "DATAFORSEO_BASE64" in payload["error"]


def test_handler_validation_error_is_400() -> None:
    payload = json.loads(dfs_tools._handle_dataforseo_serp_google({}))
    assert payload.get("code") == 400


def test_check_dataforseo_available_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert dfs_tools._check_dataforseo_available() is True
    monkeypatch.delenv("DATAFORSEO_BASE64", raising=False)
    assert dfs_tools._check_dataforseo_available() is False


# ---------------------------------------------------------------------------
# Plugin registration — 5 tools land + check_fn wired
# ---------------------------------------------------------------------------


class _FakeCtx:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def register_tool(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_register_publishes_all_five_tools_with_check_fn() -> None:
    import plugins.dataforseo as plugin
    ctx = _FakeCtx()
    plugin.register(ctx)
    names = [c["name"] for c in ctx.calls]
    assert sorted(names) == sorted([
        "dataforseo_serp_google",
        "dataforseo_onpage_summary",
        "dataforseo_keyword_volume",
        "dataforseo_labs_keyword_ideas",
        "dataforseo_backlinks_summary",
    ])
    for call in ctx.calls:
        assert call["toolset"] == "dataforseo"
        assert call["check_fn"] is dfs_tools._check_dataforseo_available
        assert call["requires_env"] == ["DATAFORSEO_BASE64"]
        assert call.get("emoji"), f"tool {call['name']} missing emoji"
        # onpage_summary must stay sync — see plan rationale on registry.py:384-387
        assert call.get("is_async") in (None, False)


def test_crawl_progress_thread_is_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """The polling worker thread must not block process shutdown."""
    captured: dict[str, threading.Thread] = {}
    real_thread = threading.Thread

    class _RecordingThread(real_thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["thread"] = self

    monkeypatch.setattr(dfs_client.threading, "Thread", _RecordingThread)

    def handler(method, url, *_):
        if method == "POST" and url.endswith("/v3/on_page/task_post"):
            return _FakeResponse(200, {"tasks": [{"id": "t"}]})
        return _FakeResponse(200, {"tasks": [{"result": [{"crawl_progress": "finished"}]}]})

    _install_fake_request(monkeypatch, handler)
    monkeypatch.setattr(dfs_client, "ONPAGE_POLL_INTERVAL", 0.0)
    dfs_client.DataForSEOClient().onpage_summary(
        target="https://example.com",
        max_crawl_pages=1,
        mode="standard",
    )
    assert captured["thread"].daemon is True
