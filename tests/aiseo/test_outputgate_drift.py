"""OutputGate drift gate — pinned-copy pattern.

Design decisions:
- Positive drift (upstream adds a prefix that pinned copy lacks): CI RED,
  forces a human to decide whether to mirror the new prefix into
  AISEO_REDACT_PINNED_COPY and OUTPUT_REDACT_PATTERNS.
- Reverse drift (upstream removes a prefix that pinned copy still has):
  CI does NOT alert — redacting more is the safe side. Zombie patterns
  should be pruned during quarterly reviews.
- Behaviour test: verifies that two recently-added upstream prefixes
  (brv_ and mem0_) are actually intercepted by the live OutputGate, not
  just present in the pinned list.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Drift gate
# ---------------------------------------------------------------------------


def test_no_upstream_prefix_missing_from_pinned_copy(aiseo_guard):
    """Positive drift gate: every prefix in agent/redact._PREFIX_PATTERNS must
    appear in AISEO_REDACT_PINNED_COPY.

    Failure means the upstream vendor list has grown and the OutputGate has a
    coverage gap.  A human must decide whether to adopt the new prefix.
    """
    from agent.redact import _PREFIX_PATTERNS

    pinned: list[str] = aiseo_guard.AISEO_REDACT_PINNED_COPY
    missing = set(_PREFIX_PATTERNS) - set(pinned)
    assert not missing, (
        f"upstream agent/redact._PREFIX_PATTERNS has {len(missing)} prefix(es) "
        f"not in AISEO_REDACT_PINNED_COPY: {sorted(missing)}\n"
        "Action: add them to AISEO_REDACT_PINNED_COPY and OUTPUT_REDACT_PATTERNS "
        "in plugins/aiseo-guard/__init__.py, or document the intentional exclusion."
    )


# ---------------------------------------------------------------------------
# Behaviour test
# ---------------------------------------------------------------------------


def test_outputgate_actually_redacts_recent_upstream_prefixes(aiseo_guard):
    """Behaviour test: OUTPUT_REDACT_PATTERNS must redact brv_ and mem0_ tokens.

    These two prefixes were among the most recently added to the upstream
    agent/redact._PREFIX_PATTERNS list.  Confirming redaction here ensures that
    keeping the pinned copy in sync translates into real protection, not just a
    passing CI badge.
    """
    compiled_patterns: list[tuple[re.Pattern[str], str]] = (
        aiseo_guard.OUTPUT_REDACT_PATTERNS
    )

    # Tokens that should be redacted — realistic-length fake secrets.
    test_cases = [
        ("brv_ABCDEF1234567890", "brv_ prefix (Brevo API key)"),
        ("mem0_ABCDEF1234567890", "mem0_ prefix (Mem0 API key)"),
    ]

    for token, description in test_cases:
        payload = f"Here is the secret: {token} — please keep it safe."
        redacted = payload
        for pat, repl in compiled_patterns:
            redacted = pat.sub(repl, redacted)

        assert token not in redacted, (
            f"OutputGate failed to redact {description}.\n"
            f"  Input   : {payload!r}\n"
            f"  Redacted: {redacted!r}\n"
            "Ensure OUTPUT_REDACT_PATTERNS contains a matching compiled pattern."
        )
        assert "[REDACTED_API_KEY]" in redacted, (
            f"OutputGate replaced {description} but not with '[REDACTED_API_KEY]'.\n"
            f"  Redacted: {redacted!r}"
        )
