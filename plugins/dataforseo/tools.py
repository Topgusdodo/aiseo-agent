"""5 LLM-exposed DataForSEO tools — schemas, pydantic validators, handlers.

Each tool is built by :func:`_make_handler` which threads pydantic
validation, environment-credential checking, and exception aggregation
through a shared shell. Handlers always return JSON strings via
``tools.registry.tool_result`` / ``tool_error`` (handler contract from
``tools/registry.py:537-563``; mirrored from ``plugins/spotify/tools.py:17``).

The 5 schemas registered with the host are plain JSON-schema dicts —
that is what ``PluginContext.register_tool(schema=dict)`` expects
(``hermes_cli/plugins.py:332-359``). The pydantic models are *internal*
validators consumed only by ``_make_handler``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Literal

from pydantic import BaseModel, Field, ValidationError

from plugins.dataforseo.client import (
    DataForSEOAPIError,
    DataForSEOAuthRequiredError,
    DataForSEOClient,
    DataForSEOError,
)
from tools.registry import tool_error, tool_result

DEFAULT_LOCATION_CODE = 2840  # United States
DEFAULT_LANGUAGE_CODE = "en"


def _check_dataforseo_available() -> bool:
    """Layer-1 gate — registry consults this before exposing tools."""
    return bool(os.getenv("DATAFORSEO_BASE64"))


# ---------------------------------------------------------------------------
# Pydantic input schemas (Appendix §2)
# ---------------------------------------------------------------------------


class SerpGoogleArgs(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=700)
    location_code: int = DEFAULT_LOCATION_CODE
    language_code: str = DEFAULT_LANGUAGE_CODE
    device: Literal["desktop", "mobile"] = "desktop"
    depth: int = Field(10, ge=1, le=100)
    mode: Literal["standard", "live"] = "standard"


class OnPageSummaryArgs(BaseModel):
    target: str = Field(..., min_length=1, description="Target URL or domain")
    max_crawl_pages: int = Field(100, ge=1, le=1000)
    mode: Literal["standard"] = "standard"


class KeywordVolumeArgs(BaseModel):
    keywords: List[str] = Field(..., min_length=1, max_length=1000)
    location_code: int = DEFAULT_LOCATION_CODE
    language_code: str = DEFAULT_LANGUAGE_CODE
    mode: Literal["standard", "live"] = "standard"


class LabsKeywordIdeasArgs(BaseModel):
    keywords: List[str] = Field(..., min_length=1, max_length=200)
    location_code: int = DEFAULT_LOCATION_CODE
    language_code: str = DEFAULT_LANGUAGE_CODE
    limit: int = Field(100, ge=1, le=1000)
    mode: Literal["live"] = "live"


class BacklinksSummaryArgs(BaseModel):
    target: str = Field(..., min_length=1, description="Target domain")
    mode: Literal["live"] = "live"


# ---------------------------------------------------------------------------
# JSON schemas exposed to the LLM via the tool registry
# ---------------------------------------------------------------------------


SERP_GOOGLE_SCHEMA = {
    "description": (
        "Run a Google organic SERP query and return structured top-N results "
        "(titles, URLs, snippets, SERP features). Default mode is 'standard' "
        "(task-post + poll); pass mode='live' for a synchronous answer at "
        "higher per-call cost."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "minLength": 1, "maxLength": 700},
            "location_code": {
                "type": "integer",
                "description": "Geo target (default 2840=US).",
            },
            "language_code": {
                "type": "string",
                "description": "ISO language code (default 'en').",
            },
            "device": {"type": "string", "enum": ["desktop", "mobile"]},
            "depth": {"type": "integer", "minimum": 1, "maximum": 100},
            "mode": {"type": "string", "enum": ["standard", "live"]},
        },
        "required": ["keyword"],
    },
}

ONPAGE_SUMMARY_SCHEMA = {
    "description": (
        "Crawl a website (or single page) and return an on-page audit summary "
        "(indexability, on-page tags, page-level errors). Long-running: polls "
        "crawl_progress with a 300s hard ceiling."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "minLength": 1,
                "description": "Target URL or root domain to crawl.",
            },
            "max_crawl_pages": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": "Hard cap on pages crawled (default 100).",
            },
            "mode": {"type": "string", "enum": ["standard"]},
        },
        "required": ["target"],
    },
}

KEYWORD_VOLUME_SCHEMA = {
    "description": (
        "Look up Google Ads monthly search volume + CPC + competition for "
        "a batch of keywords (up to 1000). Default mode is 'standard' "
        "(task-post + poll); pass mode='live' for a synchronous result."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 1000,
            },
            "location_code": {
                "type": "integer",
                "description": "Geo target (default 2840=US).",
            },
            "language_code": {
                "type": "string",
                "description": "ISO language code (default 'en').",
            },
            "mode": {"type": "string", "enum": ["standard", "live"]},
        },
        "required": ["keywords"],
    },
}

LABS_KEYWORD_IDEAS_SCHEMA = {
    "description": (
        "Expand a seed set into related keyword ideas with difficulty signals "
        "(max 200 seeds in, up to 1000 ideas out). Live-only endpoint."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 200,
            },
            "location_code": {
                "type": "integer",
                "description": "Geo target (default 2840=US).",
            },
            "language_code": {
                "type": "string",
                "description": "ISO language code (default 'en').",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": "Max ideas returned (default 100).",
            },
            "mode": {"type": "string", "enum": ["live"]},
        },
        "required": ["keywords"],
    },
}

BACKLINKS_SUMMARY_SCHEMA = {
    "description": (
        "Return a backlink-profile summary for a domain (referring domains, "
        "rank metrics, anchor diversity). Live-only endpoint."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "minLength": 1,
                "description": "Target domain (e.g. example.com).",
            },
            "mode": {"type": "string", "enum": ["live"]},
        },
        "required": ["target"],
    },
}


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def _aggregate_tool_error(exc: Exception) -> str:
    """Mirror plugins/spotify/tools.py:31-36 — coalesce 3 error types."""
    if isinstance(exc, DataForSEOAuthRequiredError):
        return tool_error(str(exc), code=401)
    if isinstance(exc, DataForSEOAPIError):
        return tool_error(str(exc), code=exc.status_code)
    if isinstance(exc, DataForSEOError):
        return tool_error(str(exc))
    return tool_error(f"DataForSEO tool failed: {type(exc).__name__}: {exc}")


def _make_handler(
    client_method_name: str,
    schema_validator: type[BaseModel],
    mode_default: str = "standard",
) -> Callable[..., str]:
    """Build a handler that validates, dispatches, and uniformly errors."""

    def _handler(args: dict, **_kw: Any) -> str:
        # Layer-2 defensive env check (layer-1 is the registry check_fn).
        if not os.getenv("DATAFORSEO_BASE64"):
            return tool_error(
                "DataForSEO credentials missing. Set DATAFORSEO_BASE64 to "
                "base64(login:password) from app.dataforseo.com/api-access.",
                code=401,
            )
        try:
            validated = schema_validator(**(args or {})).model_dump()
        except ValidationError as exc:
            return tool_error(f"invalid args: {exc.errors()}", code=400)
        # Defensive defaults — pydantic defaults already fill these, but
        # ``setdefault`` keeps the contract stable if a future validator drops
        # the field or passes through arbitrary kwargs.
        if "location_code" in schema_validator.model_fields:
            validated.setdefault("location_code", DEFAULT_LOCATION_CODE)
        if "language_code" in schema_validator.model_fields:
            validated.setdefault("language_code", DEFAULT_LANGUAGE_CODE)
        validated.setdefault("mode", mode_default)
        try:
            client = DataForSEOClient()
            method = getattr(client, client_method_name)
            payload = method(**validated)
            return tool_result(payload)
        except Exception as exc:
            return _aggregate_tool_error(exc)

    _handler.__name__ = f"_handle_dataforseo_{client_method_name}"
    return _handler


_handle_dataforseo_serp_google = _make_handler("serp_google", SerpGoogleArgs, "standard")
_handle_dataforseo_onpage_summary = _make_handler("onpage_summary", OnPageSummaryArgs, "standard")
_handle_dataforseo_keyword_volume = _make_handler("keyword_volume", KeywordVolumeArgs, "standard")
_handle_dataforseo_labs_keyword_ideas = _make_handler(
    "labs_keyword_ideas", LabsKeywordIdeasArgs, "live"
)
_handle_dataforseo_backlinks_summary = _make_handler(
    "backlinks_summary", BacklinksSummaryArgs, "live"
)
