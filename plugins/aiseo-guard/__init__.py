"""aiseo-guard plugin — AISEO Agent 4-hook guard skeleton (Phase 0).

Registers four noop hook handlers. Rule bodies land in Phase 1:
    - pre_user_message    -> InputGate (deterministic denylist; D6)
    - pre_tool_call       -> ToolGate (whitelist fallback)
    - transform_tool_result -> External Content Guard (wrap untrusted external content)
    - transform_llm_output  -> OutputGate (deterministic regex redaction)

Phase 0 handlers all return None (allow / passthrough). Their presence
proves V0 (plugin discovery and hook registration) before Phase 1 fills
the actual policy.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def register(ctx: Any) -> None:
    ctx.register_hook("pre_user_message", _input_gate)
    ctx.register_hook("pre_tool_call", _tool_gate)
    ctx.register_hook("transform_tool_result", _external_content_guard)
    ctx.register_hook("transform_llm_output", _output_gate)
    logger.debug("aiseo-guard: registered 4 hook handlers (Phase 0 skeleton)")


def _input_gate(user_message: str = "", **kwargs: Any) -> Optional[dict]:
    """InputGate — Phase 0 noop. Phase 1 fills deterministic denylist."""
    return None


def _tool_gate(tool_name: str = "", args: Optional[dict] = None, **kwargs: Any) -> Optional[dict]:
    """ToolGate — Phase 0 noop. Phase 1 fills tool whitelist fallback."""
    return None


def _external_content_guard(tool_name: str = "", result: Any = None, **kwargs: Any) -> Optional[str]:
    """External Content Guard — Phase 0 noop. Phase 1 wraps web_*/browser_* results."""
    return None


def _output_gate(text: str = "", **kwargs: Any) -> Optional[str]:
    """OutputGate — Phase 0 noop. Phase 1 fills deterministic regex redaction."""
    return None
