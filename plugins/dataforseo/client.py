"""DataForSEO API client — sync httpx, Basic Auth, 4 polling modes, sandbox.

Five public endpoint methods power the 5 LLM-exposed tools registered by
``plugins.dataforseo``:

    serp_google           — /v3/serp/google/organic/{task_post|live/advanced}
    onpage_summary        — /v3/on_page/task_post + /v3/on_page/summary/{id}
    keyword_volume        — /v3/keywords_data/google_ads/search_volume/{task_post|live}
    labs_keyword_ideas    — /v3/dataforseo_labs/google/keyword_ideas/live (Live only)
    backlinks_summary     — /v3/backlinks/summary/live (Live only)

Four call modes:

    1. Basic-Auth + ``{tasks: [...]}`` envelope (most endpoints)
    2. ``tasks_ready`` poll for Standard-async (SERP / keyword_volume).
       MUST filter by current task_id to avoid concurrent task crosstalk.
    3. ``crawl_progress`` poll for OnPage (special-case, not tasks_ready)
    4. Live-only fast path (Labs / Backlinks summary)

Credentials never appear in logs, errors, or LLM-visible output. The
``_mask_auth_header()`` helper rewrites the ``Authorization: Basic ...``
header line before any text is surfaced. The ``DATAFORSEO_BASE64`` env
var holds a precomputed ``base64(login:password)`` token (matches the
sibling aiseo-api/probe convention) — never decoded inside this process.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

PROD_HOST = "api.dataforseo.com"
SANDBOX_HOST = "sandbox.dataforseo.com"

DEFAULT_REQUEST_TIMEOUT = 60.0
ONPAGE_POLL_TIMEOUT = 300.0
ONPAGE_POLL_INTERVAL = 5.0
TASKS_READY_POLL_INTERVAL = 3.0
TASKS_READY_POLL_TIMEOUT = 60.0
RATE_LIMIT_BACKOFFS = (5.0, 10.0, 20.0)

_AUTH_HEADER_RE = re.compile(
    r"(Authorization\s*:\s*Basic\s+)[A-Za-z0-9+/=_-]+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Exceptions (Appendix §1 in plan)
# ---------------------------------------------------------------------------


class DataForSEOError(Exception):
    """Base class for all DataForSEO client errors."""


class DataForSEOAuthRequiredError(DataForSEOError):
    """Credentials missing or rejected (401)."""


class DataForSEOAPIError(DataForSEOError):
    """API returned a non-2xx status; carries ``status_code``."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_auth_header(text: str) -> str:
    """Replace Basic-Auth header values with ``***`` in any text blob.

    Defensive belt-and-suspenders alongside the registry-level scrubbing —
    keeps the raw Authorization base64 out of any string we ever return,
    raise, or log.
    """
    if not text:
        return text
    return _AUTH_HEADER_RE.sub(r"\1***", text)


def _env_truthy(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class DataForSEOClient:
    """Sync DataForSEO API client (httpx)."""

    def __init__(
        self,
        auth_b64: Optional[str] = None,
        sandbox: Optional[bool] = None,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        token = auth_b64 if auth_b64 is not None else os.getenv("DATAFORSEO_BASE64")
        if not token:
            raise DataForSEOAuthRequiredError(
                "DataForSEO credentials missing. Set DATAFORSEO_BASE64 to "
                "base64(login:password) from app.dataforseo.com/api-access "
                "(generate with: `echo -n \"login:password\" | base64`)."
            )
        self._sandbox = bool(sandbox) if sandbox is not None else _env_truthy("DATAFORSEO_SANDBOX")
        self._host = SANDBOX_HOST if self._sandbox else PROD_HOST
        self._timeout = float(timeout)
        self._auth_header = f"Basic {token.strip()}"

    # ------------------------------------------------------------------
    # Public endpoint methods
    # ------------------------------------------------------------------

    def serp_google(
        self,
        *,
        keyword: str,
        location_code: int,
        language_code: str,
        device: str,
        depth: int,
        mode: str,
    ) -> Dict[str, Any]:
        payload = [{
            "keyword": keyword,
            "location_code": location_code,
            "language_code": language_code,
            "device": device,
            "depth": depth,
        }]
        if mode == "live":
            return self._live_call("/v3/serp/google/organic/live/advanced", payload)
        task_id = self._task_post("/v3/serp/google/organic/task_post", payload)
        self._tasks_ready("/v3/serp/google/organic/tasks_ready", task_id)
        return self._task_get("/v3/serp/google/organic/task_get/advanced", task_id)

    def onpage_summary(
        self,
        *,
        target: str,
        max_crawl_pages: int,
        mode: str,
    ) -> Dict[str, Any]:
        payload = [{
            "target": target,
            "max_crawl_pages": max_crawl_pages,
        }]
        task_id = self._task_post("/v3/on_page/task_post", payload)
        self._crawl_progress_poll(task_id, timeout=ONPAGE_POLL_TIMEOUT)
        return self._get(f"/v3/on_page/summary/{task_id}")

    def keyword_volume(
        self,
        *,
        keywords: List[str],
        location_code: int,
        language_code: str,
        mode: str,
    ) -> Dict[str, Any]:
        payload = [{
            "keywords": list(keywords),
            "location_code": location_code,
            "language_code": language_code,
        }]
        if mode == "live":
            return self._live_call(
                "/v3/keywords_data/google_ads/search_volume/live",
                payload,
            )
        task_id = self._task_post(
            "/v3/keywords_data/google_ads/search_volume/task_post",
            payload,
        )
        self._tasks_ready(
            "/v3/keywords_data/google_ads/search_volume/tasks_ready",
            task_id,
        )
        return self._task_get(
            "/v3/keywords_data/google_ads/search_volume/task_get",
            task_id,
        )

    def labs_keyword_ideas(
        self,
        *,
        keywords: List[str],
        location_code: int,
        language_code: str,
        limit: int,
        mode: str,
    ) -> Dict[str, Any]:
        payload = [{
            "keywords": list(keywords),
            "location_code": location_code,
            "language_code": language_code,
            "limit": limit,
        }]
        return self._live_call(
            "/v3/dataforseo_labs/google/keyword_ideas/live",
            payload,
        )

    def backlinks_summary(
        self,
        *,
        target: str,
        mode: str,
    ) -> Dict[str, Any]:
        payload = [{"target": target}]
        return self._live_call("/v3/backlinks/summary/live", payload)

    # ------------------------------------------------------------------
    # HTTP primitives — POST / GET with credential-masked error reporting
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"https://{self._host}{path}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: Any) -> Dict[str, Any]:
        return self._request_with_retry("POST", path, json_body=payload)

    def _get(self, path: str) -> Dict[str, Any]:
        return self._request_with_retry("GET", path)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
    ) -> Dict[str, Any]:
        for attempt in range(len(RATE_LIMIT_BACKOFFS) + 1):
            try:
                response = httpx.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_body,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                raise DataForSEOAPIError(
                    _mask_auth_header(f"HTTP error calling {path}: {exc}"),
                    status_code=0,
                ) from None
            if response.status_code == 401:
                raise DataForSEOAuthRequiredError(
                    "DataForSEO credentials invalid — check app.dataforseo.com/api-access"
                )
            if response.status_code == 429 and attempt < len(RATE_LIMIT_BACKOFFS):
                time.sleep(RATE_LIMIT_BACKOFFS[attempt])
                continue
            if response.status_code >= 400:
                detail = _mask_auth_header((response.text or "")[:500])
                raise DataForSEOAPIError(
                    f"DataForSEO {method} {path} failed (HTTP {response.status_code}): {detail}",
                    status_code=response.status_code,
                )
            try:
                return response.json()
            except ValueError as exc:
                raise DataForSEOAPIError(
                    _mask_auth_header(f"DataForSEO returned non-JSON: {exc}"),
                    status_code=response.status_code,
                ) from None
        raise DataForSEOAPIError(
            f"DataForSEO {method} {path} exhausted retries",
            status_code=429,
        )

    # ------------------------------------------------------------------
    # Polling helpers (3 of 4 lifecycle modes — live has no polling)
    # ------------------------------------------------------------------

    def _task_post(self, path: str, payload: List[Dict[str, Any]]) -> str:
        envelope = self._post(path, payload)
        tasks = envelope.get("tasks") or []
        if not tasks:
            raise DataForSEOAPIError(
                f"DataForSEO {path} returned no task entries",
                status_code=envelope.get("status_code") or 0,
            )
        first = tasks[0]
        task_id = first.get("id")
        if not task_id:
            raise DataForSEOAPIError(
                f"DataForSEO {path} returned task without id: {first.get('status_message')}",
                status_code=first.get("status_code") or 0,
            )
        return str(task_id)

    def _tasks_ready(
        self,
        path: str,
        task_id: str,
        *,
        timeout: float = TASKS_READY_POLL_TIMEOUT,
        interval: float = TASKS_READY_POLL_INTERVAL,
    ) -> None:
        deadline = time.monotonic() + timeout
        while True:
            envelope = self._get(path)
            tasks = envelope.get("tasks") or []
            for task in tasks:
                ready_results = task.get("result") or []
                for entry in ready_results:
                    if str(entry.get("id")) == task_id:
                        return
            if time.monotonic() >= deadline:
                raise DataForSEOAPIError(
                    f"DataForSEO tasks_ready timed out waiting for {task_id}",
                    status_code=408,
                )
            time.sleep(interval)

    def _task_get(self, path: str, task_id: str) -> Dict[str, Any]:
        return self._get(f"{path}/{task_id}")

    def _live_call(self, path: str, payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._post(path, payload)

    def _crawl_progress_poll(
        self,
        task_id: str,
        *,
        timeout: float = ONPAGE_POLL_TIMEOUT,
        interval: float = ONPAGE_POLL_INTERVAL,
    ) -> None:
        """Block until ``crawl_progress == 'finished'`` or hard timeout.

        Runs the inner polling loop on a worker thread so we can enforce a
        hard wall-clock cap with ``thread.join(timeout=...)``. The dispatch
        thread still waits synchronously — this only guarantees the worker
        cannot exceed the budget if the HTTP call itself gets stuck.
        """
        outcome: Dict[str, Any] = {}

        def _worker() -> None:
            try:
                deadline = time.monotonic() + timeout
                while True:
                    envelope = self._get(f"/v3/on_page/summary/{task_id}")
                    tasks = envelope.get("tasks") or []
                    for task in tasks:
                        result = task.get("result") or []
                        for entry in result:
                            if entry.get("crawl_progress") == "finished":
                                outcome["done"] = True
                                return
                    if time.monotonic() >= deadline:
                        outcome["error"] = DataForSEOAPIError(
                            f"DataForSEO crawl_progress timed out for {task_id}",
                            status_code=408,
                        )
                        return
                    time.sleep(interval)
            except Exception as exc:
                outcome["error"] = exc

        worker = threading.Thread(target=_worker, name=f"dfs-crawl-{task_id}", daemon=True)
        worker.start()
        worker.join(timeout + 5.0)
        if worker.is_alive():
            raise DataForSEOAPIError(
                f"DataForSEO crawl_progress polling exceeded hard timeout for {task_id}",
                status_code=408,
            )
        if "error" in outcome:
            raise outcome["error"]
