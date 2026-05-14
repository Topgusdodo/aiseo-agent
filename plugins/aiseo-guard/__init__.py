"""aiseo-guard plugin — AISEO Agent 4-hook guard (Phase 1).

Implements the four guard hooks defined in D6 of the AISEO master plan:

    - pre_user_message      -> InputGate
                               Deterministic denylist across 5 buckets:
                               prompt mining / secrets / verb+sensitive-path /
                               jailbreak / explicit forbidden capabilities.

    - pre_tool_call         -> ToolGate
                               Whitelist fallback for tools not blocked by
                               agent.disabled_toolsets at boot time. Canonical
                               return shape: {"action":"block","message":...}.

    - transform_tool_result -> External Content Guard
                               Wraps web_search / web_extract / browser_*
                               string results as <untrusted_external_content>
                               so the LLM treats them as data, not instructions.

    - transform_llm_output  -> OutputGate
                               Deterministic regex redaction on LLM output.
                               Operates as a deterministic extra layer on top
                               of agent/redact.py (Hermes built-in secret
                               redaction), targeting paths / tracebacks the
                               built-in redactor does not cover.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)


_REFUSAL_DOMAIN = (
    "我是 AISEO Agent，专注 SEO 战略 / 技术审计 / 内容运营，"
    "该请求不在受理范围内。"
)


# ---------------------------------------------------------------------------
# InputGate — D6, deterministic denylist only; no semantic classification.
# Patterns intentionally conservative to keep false positives on legitimate
# SEO input low. Coverage tested in tests/aiseo/test_input_gate_*.py.
# ---------------------------------------------------------------------------

INPUT_DENYLIST_PATTERNS: List[Pattern[str]] = [
    # Bucket 1 — Prompt mining / system prompt extraction
    re.compile(r"(?i)show\s+me\s+your\s+(system\s+)?prompt"),
    re.compile(r"(?i)print\s+your\s+instructions\s+verbatim"),
    re.compile(r"(?i)what\s+is\s+your\s+SOUL\.?\s*md"),
    re.compile(r"(?i)reveal\s+your\s+(model\s+name|system\s+prompt|instructions)"),
    # Paraphrase cluster: verb cluster × sensitive-target cluster. Catches
    # "recite verbatim ...", "repeat your preamble", "dump the system message".
    re.compile(
        r"(?i)\b(recite|repeat|echo|reproduce|dump|leak|disclose)\b"
        r"[\s\S]{0,80}?"
        r"\b(system\s+(prompt|message)|preamble|context|instructions|SOUL"
        r"|text\s+you\s+were\s+given|session\s+startup|initial\s+(?:prompt|message|text))\b"
    ),
    # Verb cluster × adverb "verbatim" — covers prompt-mining phrasings
    # like "Recite verbatim ..." where the noun is generic ("text"/"content"
    # /"message") and the give-away tell is the adverb itself.
    re.compile(
        r"(?i)\b(recite|repeat|echo|reproduce|read|print)\b\s+verbatim\b"
    ),

    # Bucket 2 — Secrets / credential exfiltration
    re.compile(r"(?i)what\s+is\s+your\s+API\s*[_-]?key"),
    re.compile(r"(?i)tell\s+me\s+your\s+(API\s*[_-]?key|secret\s+token|provider'?s?\s+secret)"),
    re.compile(r"(?i)\b(api[_\s-]?key|secret|token|password|credential)\s*[:=]\s*\S"),

    # Bucket 3 — Verb + sensitive path/credential keyword combo. Deliberately
    # NOT a bare path-prefix match so legitimate SEO discussion like
    # "report stored at /Users/alice/report.md" does not false-positive.
    # Filler is ``[\s\S]{0,30}?`` (not ``\S*?``) so the verb and target can
    # be separated by spaces / Chinese particles like "一下", "的", "里的".
    # LLM smoke S2/S3 surfaced "复述一下你的 .env 文件内容" missing because
    # ``\S*?`` cannot cross spaces.
    re.compile(
        r"(?i)\b(read|open|cat|show|view|access|fetch|dump|exfiltrate)\b"
        r"[\s\S]{0,30}?"
        r"(\.\./|/etc/|/var/|/tmp/|/private/|/proc/|~/\.|\.ssh|id_rsa|\.env"
        r"|\$HOME\b|\$\{HOME\}|%USERPROFILE%|\.aws/credentials|kubeconfig"
        r"|password|token|api[_-]?key|secret|credential)"
    ),
    # Bucket 3b — Chinese verb cluster × sensitive target. Mirrors the
    # English variant above. Verbs intentionally do NOT include generic
    # words like "看看 / 帮我看" so legit SEO questions ("帮我看 robots.txt")
    # fall through.
    re.compile(
        r"(?:复述|读取|打印|输出|展示|告诉我|查看|显示|泄露|导出|外泄|抓取|下载|读出|读一下|读出来|读取一下)"
        r"[\s\S]{0,30}?"
        r"(\.env|/etc/|\.ssh|id_rsa|api[_\-]?key|password|secret|credential"
        r"|私钥|密钥|令牌|凭证|口令|access[_\-]?token|/Users/|/home/|~/\.|"
        r"\$HOME\b|\$\{HOME\}|%USERPROFILE%|\.aws/credentials|kubeconfig)"
    ),

    # Bucket 4 — Jailbreak / role override
    re.compile(r"(?i)ignore\s+(all\s+|the\s+)?previous\s+instructions"),
    re.compile(r"(?i)disregard\s+(your\s+|the\s+)?(system|safety)\s+(prompt|guidelines|instructions)"),
    # Modern jailbreak persona cluster (DAN/STAN/AIM/developer mode/etc.)
    re.compile(
        r"(?i)you\s+are\s+now\s+"
        r"(DAN|STAN|AIM|developer\s+mode|unfiltered|uncensored|unrestricted|jailbroken)\b"
    ),
    # "switch/enter/activate developer mode unfiltered" style phrasings.
    re.compile(
        r"(?i)\b(switch|enter|activate|enable|turn\s+on)\s+(to\s+)?"
        r"(developer\s+mode|jailbroken\s+mode|unfiltered\s+mode|uncensored\s+mode)"
    ),
    re.compile(r"(?i)act\s+as\s+if\s+you\s+(have\s+no|were\s+without)\s+(restrictions|guidelines|safety)"),

    # Bucket 5 — Explicit forbidden capabilities
    re.compile(r"(?i)(write|execute|run)\s+(shell|bash|python|terminal)\s+(code|command)"),
    re.compile(r"(?i)send\s+(an?\s+)?(email|message|sms)\s+to"),
]


def _input_gate(user_message: str = "", **kwargs: Any) -> Optional[dict]:
    """InputGate: deterministic denylist check on incoming user text.

    Returns ``{"action": "block", "message": ...}`` on first matching
    pattern; otherwise ``None`` so SOUL.md / model can handle the
    request (including soft-refusal of out-of-domain prompts).
    """
    text = user_message or ""
    if not isinstance(text, str) or not text:
        return None
    for pat in INPUT_DENYLIST_PATTERNS:
        if pat.search(text):
            logger.debug("aiseo-guard InputGate blocked: %s", pat.pattern[:60])
            return {"action": "block", "message": _REFUSAL_DOMAIN}
    return None


# ---------------------------------------------------------------------------
# ToolGate — D6, dispatch-time fallback. agent.disabled_toolsets at boot is
# the primary defense; this hook is the second layer.
#
# Tool names sourced from toolsets.py (lines 33-60):
#   web              -> web_search, web_extract                     (ALLOWED)
#   terminal         -> terminal, process
#   file             -> read_file, write_file, patch, search_files
#   skills (mgmt)    -> skills_list, skill_view, skill_manage
#   browser          -> browser_navigate, browser_snapshot,         (ALLOWED)
#                       browser_click, browser_type,
#                       browser_scroll, browser_back
#   code_execution   -> execute_code
#   delegation       -> delegate_task
#   messaging        -> send_message
# ---------------------------------------------------------------------------

TOOL_BLOCKLIST: frozenset = frozenset({
    "terminal", "process",
    "execute_code",
    "delegate_task",
    "send_message",
    "read_file", "write_file", "patch", "search_files",
    "skills_list", "skill_view", "skill_manage",
    "cronjob",
    "image_gen",
    "shell",
    # Vision / image / TTS / video — out of SEO scope.
    "vision_analyze", "image_generate", "text_to_speech", "video_analyze",
    # Home Assistant smart-home control — out of scope.
    "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
    # Kanban multi-agent coordination — agent runs solo for SEO.
    "kanban_show", "kanban_list", "kanban_complete", "kanban_block",
    "kanban_heartbeat", "kanban_comment", "kanban_create", "kanban_link",
    "kanban_unblock",
    # Computer use (full desktop control) — out of scope.
    "computer_use",
    # High-risk browser surfaces (LLM smoke S2/S4 exposed). Basic
    # navigation/snapshot/click/type/scroll/back/press stay in the
    # EXTERNAL_TOOLS whitelist (legit SEO needs them). Anything that
    # executes script, reads console output, opens dev-protocol, takes
    # screenshots, or scrapes raw images is blocked — out of SEO scope
    # and a common indirect-injection escape hatch.
    "browser_console", "browser_console_messages",
    "browser_evaluate", "browser_run_code",
    "browser_vision", "browser_get_images",
    "browser_cdp", "browser_dialog", "browser_handle_dialog",
    "browser_take_screenshot",
    "browser_file_upload", "browser_network_requests",
})


def _is_blocked_tool_name(tool_name: str) -> bool:
    """Match either the exact tool name or a namespaced suffix (`mcp__pkg__terminal`).

    MCP-style namespaced tools use ``__`` segment separators. Take the final
    segment as the bare tool name and also check the full suffix join, so
    ``mcp__foo__terminal`` is blocked when ``terminal`` is blocklisted, while
    legitimate tools whose names happen to contain a blocklist token as a
    substring (e.g. ``web_extract_html``) are not falsely caught — only the
    last ``__`` segment is consulted, never a substring match.
    """
    if tool_name in TOOL_BLOCKLIST:
        return True
    if "__" in tool_name:
        last_segment = tool_name.rsplit("__", 1)[-1]
        if last_segment in TOOL_BLOCKLIST:
            return True
        for blocked in TOOL_BLOCKLIST:
            if tool_name.endswith("__" + blocked):
                return True
    return False


def _tool_gate(tool_name: str = "", args: Optional[dict] = None, **kwargs: Any) -> Optional[dict]:
    """ToolGate: veto dispatch of any blocklisted tool name."""
    if not tool_name:
        return None
    if _is_blocked_tool_name(tool_name):
        logger.debug("aiseo-guard ToolGate blocked tool=%s", tool_name)
        return {
            "action": "block",
            "message": f"Tool {tool_name} disabled by AISEO guard",
        }
    return None


# ---------------------------------------------------------------------------
# External Content Guard — D6, wraps untrusted external tool output. SOUL.md
# §7 instructs the model on the wrapper tag's semantics.
# ---------------------------------------------------------------------------

EXTERNAL_TOOLS: frozenset = frozenset({
    "web_search",
    "web_extract",
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_scroll",
    "browser_back",
    "browser_press",
    "browser_press_key",
    "browser_navigate_back",
    "browser_wait_for",
})


def _external_content_guard(
    tool_name: str = "",
    result: Any = None,
    **kwargs: Any,
) -> Optional[str]:
    """External Content Guard: wrap web_*/browser_* tool results.

    Returns a wrapped string when applicable; ``None`` otherwise so
    Hermes' transform_tool_result first-non-empty chain proceeds.

    Handles ``str``, ``dict``, and ``list`` payloads (JSON-serializes the
    structured ones so SERP / page-content shapes do not silently
    bypass the wrapper). Any literal ``</untrusted_external_content>``
    inside the payload is HTML-escaped so a hostile page cannot close
    the wrapper early and inject instructions into the trusted band.
    """
    if tool_name not in EXTERNAL_TOOLS:
        return None
    if isinstance(result, str):
        body = result
    elif isinstance(result, (dict, list)):
        body = json.dumps(result, ensure_ascii=False, default=str)
    else:
        return None
    body = body.replace(
        "</untrusted_external_content>",
        "&lt;/untrusted_external_content&gt;",
    )
    return (
        f"<untrusted_external_content tool=\"{tool_name}\">\n"
        f"{body}\n"
        f"</untrusted_external_content>"
    )


# ---------------------------------------------------------------------------
# OutputGate — D6, deterministic regex redaction.
#
# Layered relationship with agent/redact.py:
#   - agent/redact.py already covers vendor-prefix API keys (sk-, ghp_, …)
#     and structured query/body keys; we keep "sk-" here as belt-and-
#     suspenders per plan §Patterns to Mirror.
#   - Absolute home paths, traceback blocks, .hermes config paths are NOT
#     covered by agent/redact.py and are this gate's primary contribution.
#
# Anchors stay tight (sk- prefix, /Users/<name>/, /home/<name>/) so legit
# SEO output (URLs, domain names, marketing copy) is not over-redacted.
# Traceback pattern runs BEFORE absolute-path patterns so the entire block
# collapses to a single token instead of a slurry of nested replacements.
# ---------------------------------------------------------------------------

OUTPUT_REDACT_PATTERNS: List[Tuple[Pattern[str], str]] = [
    # Original sk- prefix — kept as belt-and-suspenders.
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "[REDACTED_API_KEY]"),
    # Mirror agent/redact.py:70-106 vendor PAT prefixes so the LLM output
    # path is covered even if the upstream redactor is bypassed or absent.
    # Patterns copied (not imported) to keep the plugin self-contained and
    # avoid runtime circular dependencies on agent.redact internals.
    (re.compile(r"ghp_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gho_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghu_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghs_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"ghr_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"AIza[A-Za-z0-9_-]{30,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"pplx-[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"fal_[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"fc-[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"bb_live_[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gAAAA[A-Za-z0-9_=-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "[REDACTED_API_KEY]"),
    (re.compile(r"sk_live_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"sk_test_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"rk_live_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"SG\.[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"hf_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"r8_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"npm_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"pypi-[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"dop_v1_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"doo_v1_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"am_[A-Za-z0-9_-]{10,}"), "[REDACTED_API_KEY]"),
    # ElevenLabs sk_ prefix — note: underscore, not dash; distinct from sk-.
    (re.compile(r"sk_[A-Za-z0-9_]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"tvly-[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"exa_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gsk_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"syt_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"retaindb_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"hsk-[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"mem0_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"brv_[A-Za-z0-9]{10,}"), "[REDACTED_API_KEY]"),
    # Generic "api_key: <value>" / "token = <value>" assignments.
    (
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret)\s*[:=]\s*"
            r"['\"]?[A-Za-z0-9_\-]{16,}['\"]?"
        ),
        "[REDACTED_API_KEY]",
    ),
    # Traceback MUST collapse before path patterns rewrite the inner lines.
    (
        re.compile(
            r"(?ms)^\s*Traceback \(most recent call last\):.*?"
            r"(?=\n\S|\n\s*\n|\Z)"
        ),
        "[REDACTED_TRACEBACK]",
    ),
    (
        re.compile(r"\.hermes/\S*?\.(?:yaml|yml|json|db|sqlite)\b"),
        "[REDACTED_CONFIG_PATH]",
    ),
    (re.compile(r"/Users/[^/\s\"']+"), "/Users/[REDACTED]"),
    (re.compile(r"/home/[^/\s\"']+"), "/home/[REDACTED]"),
    # Belt-and-suspenders: strip any <untrusted_external_content ...>
    # wrapper tags if the LLM echoes them verbatim back to the user.
    # External Content Guard wraps tool results so the LLM sees them as
    # data; SOUL.md §7 tells the model not to repeat the wrapper, but
    # LLM smoke S5-01 shows it can still leak. Stripping the tags here
    # is purely cosmetic (the *body* is already trusted data the LLM
    # summarized) and MUST run last so the inner tracebacks / paths
    # were rewritten first under their original context.
    (re.compile(r"</?untrusted_external_content[^>]*>"), ""),
]


def _output_gate(
    text: str = "",
    response_text: Optional[str] = None,
    **kwargs: Any,
) -> Optional[str]:
    """OutputGate: regex redact LLM output before it reaches the user.

    Accepts both ``text`` (positional, used by unit tests) and
    ``response_text`` (the kwarg name Hermes actually passes from
    ``invoke_hook("transform_llm_output", response_text=final_response, ...)``
    at ``run_agent.py:15443``). The original signature only had
    ``text=""`` so when called from real Hermes the payload landed in
    ``**kwargs`` and the gate silently no-op'd — LLM smoke S5 surfaced
    this. ``response_text`` wins when both are given so the real Hermes
    call path takes precedence over any legacy positional caller.
    """
    payload = response_text if isinstance(response_text, str) and response_text else text
    if not isinstance(payload, str) or not payload:
        return None
    redacted = payload
    for pat, repl in OUTPUT_REDACT_PATTERNS:
        redacted = pat.sub(repl, redacted)
    if redacted != payload:
        return redacted
    return None


def register(ctx: Any) -> None:
    """Register the four aiseo-guard handlers with Hermes plugin context."""
    ctx.register_hook("pre_user_message", _input_gate)
    ctx.register_hook("pre_tool_call", _tool_gate)
    ctx.register_hook("transform_tool_result", _external_content_guard)
    ctx.register_hook("transform_llm_output", _output_gate)
    logger.debug("aiseo-guard: registered 4 hook handlers (Phase 1)")
