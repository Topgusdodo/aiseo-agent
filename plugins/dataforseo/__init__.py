"""DataForSEO plugin — registers 5 structured SEO data tools.

Profile-level opt-in: ``seeds/aiseo-profile/config.yaml`` must list
``dataforseo`` under ``plugins.enabled`` for the plugin loader to call
:func:`register`. After that, the registry consults
:func:`_check_dataforseo_available` to grey-out tools when
``DATAFORSEO_BASE64`` is unset.

Both layers are defended in depth:

    layer 1 (registry) — check_fn gates every dispatch
    layer 2 (handler)  — defensive env check in ``_make_handler``
                         returns ``tool_error(..., code=401)``
"""

from __future__ import annotations

from plugins.dataforseo.tools import (
    BACKLINKS_SUMMARY_SCHEMA,
    KEYWORD_VOLUME_SCHEMA,
    LABS_KEYWORD_IDEAS_SCHEMA,
    ONPAGE_SUMMARY_SCHEMA,
    SERP_GOOGLE_SCHEMA,
    _check_dataforseo_available,
    _handle_dataforseo_backlinks_summary,
    _handle_dataforseo_keyword_volume,
    _handle_dataforseo_labs_keyword_ideas,
    _handle_dataforseo_onpage_summary,
    _handle_dataforseo_serp_google,
)

_TOOLS = (
    ("dataforseo_serp_google",        SERP_GOOGLE_SCHEMA,        _handle_dataforseo_serp_google,        "🔍"),
    ("dataforseo_onpage_summary",     ONPAGE_SUMMARY_SCHEMA,     _handle_dataforseo_onpage_summary,     "📋"),
    ("dataforseo_keyword_volume",     KEYWORD_VOLUME_SCHEMA,     _handle_dataforseo_keyword_volume,     "📊"),
    ("dataforseo_labs_keyword_ideas", LABS_KEYWORD_IDEAS_SCHEMA, _handle_dataforseo_labs_keyword_ideas, "💡"),
    ("dataforseo_backlinks_summary",  BACKLINKS_SUMMARY_SCHEMA,  _handle_dataforseo_backlinks_summary,  "🔗"),
)

_REQUIRES_ENV = ["DATAFORSEO_BASE64"]


def register(ctx) -> None:
    """Register all 5 DataForSEO tools. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="dataforseo",
            schema=schema,
            handler=handler,
            check_fn=_check_dataforseo_available,
            requires_env=_REQUIRES_ENV,
            emoji=emoji,
        )
