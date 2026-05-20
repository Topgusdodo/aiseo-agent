"""Confirm aiseo profile pins two cost / safety tunings on top of upstream defaults.

- prompt_caching.cache_ttl: cron tasks reuse the same system prompt + skill
  files repeatedly. 1h Anthropic cache TTL gives much higher hit rate than the
  5m default, slashing input token cost. The cache layer is outside the 4-hook
  defence chain (InputGate/ToolGate/external-content/OutputGate), so this is
  pure cost optimisation with no safety trade-off.

- tool_loop_guardrails.hard_stop_enabled: AISEO cron jobs run unattended under
  skip_memory=True. Without a hard stop on same_tool_failure repetition, a
  runaway loop bills overnight. The hook layer does not cover semantic
  repetition, so this is the only cost-runaway brake.

These contracts are critical because they harden the cron path that
plugins/aiseo-guard/__init__.py::aiseo_schedule_task creates. Regressing either
value silently exposes users to cost runaway or worse cache miss bills.
"""

from pathlib import Path

import yaml

_SEED_CONFIG = Path(__file__).resolve().parents[2] / "seeds" / "aiseo-profile" / "config.yaml"


def _load_seed_config() -> dict:
    return yaml.safe_load(_SEED_CONFIG.read_text())


def test_aiseo_seed_pins_prompt_cache_ttl_to_1h() -> None:
    config = _load_seed_config()
    section = config.get("prompt_caching")
    assert section is not None, (
        "aiseo seed config must declare a `prompt_caching` block "
        "(default 5m wastes input tokens on repeated cron prompts)"
    )
    assert section.get("cache_ttl") == "1h", (
        f"aiseo profile must pin Anthropic cache TTL to '1h'; got "
        f"{section.get('cache_ttl')!r}. cron tasks reuse the same system "
        f"prompt + skill files on a daily/weekly cadence, so 1h has a much "
        f"higher hit rate than the 5m upstream default."
    )


def test_aiseo_seed_enables_tool_loop_hard_stop() -> None:
    config = _load_seed_config()
    section = config.get("tool_loop_guardrails")
    assert section is not None, (
        "aiseo seed config must declare a `tool_loop_guardrails` block "
        "(hard_stop is the only brake on unattended cron cost runaway)"
    )
    assert section.get("hard_stop_enabled") is True, (
        f"aiseo profile must set tool_loop_guardrails.hard_stop_enabled=True; "
        f"got {section.get('hard_stop_enabled')!r}. AISEO cron runs "
        f"unattended under skip_memory=True; the hook chain "
        f"(InputGate/ToolGate/OutputGate) does not cover semantic tool-call "
        f"repetition, so hard_stop is the only thing between a runaway loop "
        f"and an overnight bill."
    )
