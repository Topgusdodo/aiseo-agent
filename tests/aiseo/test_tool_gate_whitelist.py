"""Bucket 4 — Tool whitelist bypass + OutputGate redaction smoke tests
(plan §Phase 1 Tasks 12 #17-#24).

All B-class variants: ≥1 LLM call is fine (the model is allowed to
try); what we assert here is:
    - dispatch-time veto via _tool_gate for any blocklisted tool name
    - OutputGate regex redaction on LLM output text

L3 (agent.disabled_toolsets at boot) is the primary defense — verified
end-to-end in Phase 0 V0/V2. This file covers L6 (ToolGate hook
fallback) + L8 (OutputGate) in isolation.
"""

from __future__ import annotations


def _is_block(result):
    return isinstance(result, dict) and result.get("action") == "block"


# ---------------------------------------------------------------------------
# ToolGate veto — blocklisted tool names
# ---------------------------------------------------------------------------

def test_tg_17_terminal(aiseo_guard):
    """Plan §Phase 1 #17 — LLM tries to call terminal toolset."""
    result = aiseo_guard._tool_gate("terminal", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_18_send_message(aiseo_guard):
    """Plan §Phase 1 #18 — LLM tries to call send_message (messaging)."""
    result = aiseo_guard._tool_gate("send_message", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_19_write_file(aiseo_guard):
    """Plan §Phase 1 #19 — LLM tries to call write_file (file)."""
    result = aiseo_guard._tool_gate("write_file", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_20_execute_code(aiseo_guard):
    """Plan §Phase 1 #20 — LLM tries to call execute_code."""
    result = aiseo_guard._tool_gate("execute_code", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_21_delegate_task(aiseo_guard):
    """Plan §Phase 1 #21 — LLM tries to call delegate_task."""
    result = aiseo_guard._tool_gate("delegate_task", {})
    assert _is_block(result), f"expected block, got {result!r}"


# ---------------------------------------------------------------------------
# ToolGate passthrough — whitelisted tool names MUST NOT be blocked
# ---------------------------------------------------------------------------

def test_tg_passthrough_web_extract(aiseo_guard):
    """Whitelist tool web_extract must pass through (return None)."""
    result = aiseo_guard._tool_gate("web_extract", {"url": "https://example.com"})
    assert result is None, f"web_extract must passthrough, got {result!r}"


def test_tg_passthrough_web_search(aiseo_guard):
    """Whitelist tool web_search must pass through (return None)."""
    result = aiseo_guard._tool_gate("web_search", {"query": "best running shoes"})
    assert result is None, f"web_search must passthrough, got {result!r}"


def test_tg_passthrough_browser_navigate(aiseo_guard):
    """Whitelist tool browser_navigate must pass through (return None)."""
    result = aiseo_guard._tool_gate("browser_navigate", {"url": "https://example.com"})
    assert result is None, f"browser_navigate must passthrough, got {result!r}"


# ---------------------------------------------------------------------------
# OutputGate — deterministic regex redaction (plan §Phase 1 #22-#24)
# ---------------------------------------------------------------------------

def test_og_22_redact_api_key(aiseo_guard):
    """Plan §Phase 1 #22 — synthetic sk-* key in LLM output."""
    out = aiseo_guard._output_gate("Use sk-abc1234567890ABCDEFGHIJ to access provider X")
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "sk-abc1234567890ABCDEFGHIJ" not in out
    assert "[REDACTED_API_KEY]" in out


def test_og_23_redact_users_home_path(aiseo_guard):
    """Plan §Phase 1 #23 — absolute home path in LLM output.

    Test username "topgus" is synthetic (matches the dev env coincidentally);
    the OutputGate redacts the username component regardless.
    """
    out = aiseo_guard._output_gate("config is at /Users/topgus/.hermes/config.yaml")
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "/Users/topgus" not in out
    assert "[REDACTED" in out  # [REDACTED] or [REDACTED_CONFIG_PATH]


def test_og_24_redact_traceback(aiseo_guard):
    """Plan §Phase 1 #24 — Python traceback block in LLM output."""
    tb = (
        "Traceback (most recent call last):\n"
        "  File \"/x.py\", line 1, in <module>\n"
        "    foo()\n"
        "ValueError: synthetic"
    )
    out = aiseo_guard._output_gate(tb)
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "Traceback (most recent call last):" not in out
    assert "[REDACTED_TRACEBACK]" in out


# ---------------------------------------------------------------------------
# OutputGate passthrough — clean text MUST NOT be modified
# ---------------------------------------------------------------------------

def test_og_passthrough_clean_text(aiseo_guard):
    """Clean SEO report text must pass through unchanged."""
    text = (
        "## SEO Audit Report\n\n"
        "URL: https://example.com/blog/post-1\n"
        "P0 finding: canonical points to old slug.\n"
    )
    out = aiseo_guard._output_gate(text)
    assert out is None, f"clean text must passthrough, got {out!r}"


# ---------------------------------------------------------------------------
# C1 increment — newly-blocklisted tools must be vetoed
# ---------------------------------------------------------------------------

def test_tg_25_vision_analyze(aiseo_guard):
    """C1 — vision_analyze (image analysis) is out of SEO scope; must block."""
    result = aiseo_guard._tool_gate("vision_analyze", {"image_url": "x"})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_26_ha_call_service(aiseo_guard):
    """C1 — Home Assistant service calls must block."""
    result = aiseo_guard._tool_gate("ha_call_service", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_27_kanban_create(aiseo_guard):
    """C1 — Kanban multi-agent coordination must block."""
    result = aiseo_guard._tool_gate("kanban_create", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_28_computer_use(aiseo_guard):
    """C1 — Full desktop control via computer_use must block."""
    result = aiseo_guard._tool_gate("computer_use", {})
    assert _is_block(result), f"expected block, got {result!r}"


# ---------------------------------------------------------------------------
# C7 — MCP-namespace tool names must still be caught by the ToolGate
# ---------------------------------------------------------------------------

def test_tg_29_mcp_namespace_terminal(aiseo_guard):
    """C7 — `mcp__foo__terminal` must be blocked (namespace-aware suffix match)."""
    result = aiseo_guard._tool_gate("mcp__foo__terminal", {})
    assert _is_block(result), f"expected block, got {result!r}"


def test_tg_30_endswith_false_positive(aiseo_guard):
    """C7 — `web_extract_html` MUST NOT trip the namespace match.

    The namespace check uses last-segment / ``__`` suffix, not naive
    substring/`endswith`, so legitimate tools whose names happen to contain
    a blocklist token are not falsely caught.
    """
    result = aiseo_guard._tool_gate("web_extract_html", {})
    assert result is None, f"endswith false-positive must passthrough, got {result!r}"


def test_tg_passthrough_clarify(aiseo_guard):
    """`clarify` is an agent-self-management tool and must pass through.

    Phase 0 Test 9 already exercises this tool; ToolGate should leave it alone.
    """
    result = aiseo_guard._tool_gate("clarify", {})
    assert result is None, f"clarify must passthrough, got {result!r}"


# ---------------------------------------------------------------------------
# A4 / C3 — OutputGate must mirror agent/redact.py vendor PAT prefixes
# ---------------------------------------------------------------------------

def test_og_25_redact_github_pat(aiseo_guard):
    """A4 — GitHub personal access token (ghp_) prefix must be redacted."""
    out = aiseo_guard._output_gate(
        "credentials: ghp_ABCDEFGHIJKLMNOPQRST in the logs"
    )
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "ghp_ABCDEFGHIJKLMNOPQRST" not in out
    assert "[REDACTED_API_KEY]" in out


def test_og_26_redact_slack(aiseo_guard):
    """A4 — Slack bot token (xoxb-) must be redacted."""
    out = aiseo_guard._output_gate(
        "slack webhook uses xoxb-1234567890-fake-token-value"
    )
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "xoxb-1234567890-fake-token-value" not in out
    assert "[REDACTED_API_KEY]" in out


def test_og_27_redact_aws(aiseo_guard):
    """A4 — AWS Access Key ID (AKIA*) must be redacted."""
    out = aiseo_guard._output_gate(
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE in .env"
    )
    assert isinstance(out, str), f"expected redacted str, got {out!r}"
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED_API_KEY]" in out
