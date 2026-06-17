"""P2-B: Double-defense parity — seed config disabled_toolsets ↔ plugin TOOL_BLOCKLIST.

Ensures that every tool belonging to a boot-time disabled toolset (from
seeds/aiseo-profile/config.yaml ``agent.disabled_toolsets``) is also
intercepted at dispatch time by the aiseo-guard plugin's
``_is_blocked_tool_name`` function.

Design rationale:
  - config.disabled_toolsets is coarse-grained (entire toolset, at boot).
  - TOOL_BLOCKLIST is fine-grained (individual tool name, at dispatch).
  - Both layers must cover the same tools: if a toolset slips through boot-time
    filtering (e.g., future loader change), the plugin is the backstop.
  - This test makes the double-defense contract machine-checkable so any
    future addition to disabled_toolsets that is not mirrored in TOOL_BLOCKLIST
    will fail CI immediately.

Uses:
  - ``aiseo_guard`` session fixture from conftest.py (module-level load of
    plugins/aiseo-guard/__init__.py via importlib, no Hermes runtime needed).
  - ``resolve_toolset(name)`` from toolsets.py to expand toolset names to tool
    name lists (handles composition / includes recursively).
  - ``yaml`` to load the seed config as a plain dict (read-only, no mutation).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from toolsets import resolve_toolset

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CONFIG = REPO_ROOT / "seeds" / "aiseo-profile" / "config.yaml"


def _load_seed_disabled_toolsets() -> list[str]:
    """Read agent.disabled_toolsets from the seed config (read-only)."""
    config = yaml.safe_load(SEED_CONFIG.read_text())
    return config["agent"]["disabled_toolsets"]


# ---------------------------------------------------------------------------
# Structural sanity tests (no aiseo_guard needed)
# ---------------------------------------------------------------------------

class TestSeedConfigStructure:
    """Verify the seed config has the expected shape before parity checks."""

    def test_seed_config_exists(self):
        assert SEED_CONFIG.exists(), f"seed config not found at {SEED_CONFIG}"

    def test_disabled_toolsets_is_nonempty_list(self):
        disabled = _load_seed_disabled_toolsets()
        assert isinstance(disabled, list)
        assert len(disabled) > 0, "agent.disabled_toolsets must not be empty"

    def test_known_security_toolsets_present(self):
        """Core security-relevant toolsets must always be in disabled list."""
        disabled = _load_seed_disabled_toolsets()
        required = {"terminal", "code_execution", "delegation", "messaging", "file"}
        missing = required - set(disabled)
        assert not missing, (
            f"Security-critical toolsets missing from disabled_toolsets: {missing}"
        )

    def test_each_disabled_toolset_resolves_to_nonempty_tool_list(self):
        """Every toolset name in disabled_toolsets must expand to at least one tool.

        An empty expansion means the toolset name is misspelled or the toolset
        was renamed in the upstream registry — the parity check below would
        be silently vacuous.
        """
        disabled = _load_seed_disabled_toolsets()
        for toolset_name in disabled:
            tool_names = resolve_toolset(toolset_name)
            assert tool_names, (
                f"Toolset '{toolset_name}' in config.disabled_toolsets resolves to "
                f"zero tools — name may be misspelled or the toolset was renamed. "
                f"Double-defense check would be vacuous."
            )


# ---------------------------------------------------------------------------
# Double-defense parity: disabled toolsets → TOOL_BLOCKLIST
# ---------------------------------------------------------------------------

class TestDisabledToolsetsBlocklistParity:
    """Every tool from a disabled toolset must be intercepted by _is_blocked_tool_name."""

    def test_disabled_toolsets_all_tools_actually_blocked(self, aiseo_guard):
        """Parametric parity check across all disabled toolsets and their tools.

        For each toolset in config.disabled_toolsets, resolve it to its tool
        names and assert every tool name is blocked by the plugin guard.
        A failure here means double-defense has a gap: the toolset is disabled
        at boot time, but a tool within it could slip through at dispatch time
        if the boot-time filter is bypassed.
        """
        _is_blocked_tool_name = aiseo_guard._is_blocked_tool_name
        config_disabled = _load_seed_disabled_toolsets()

        failures: list[str] = []
        for toolset_name in config_disabled:
            tool_names = resolve_toolset(toolset_name)
            assert tool_names, (
                f"toolset '{toolset_name}' 在 config 禁用,但 resolve_toolset 返回空列表 — "
                f"检查 config.yaml 中的 toolset 名是否拼写正确"
            )
            for tool_name in tool_names:
                if not _is_blocked_tool_name(tool_name):
                    failures.append(
                        f"toolset='{toolset_name}' tool='{tool_name}' "
                        f"未被 _is_blocked_tool_name 拦截,双层防御失效"
                    )

        assert not failures, (
            "Double-defense gap(s) detected — toolset disabled in config but "
            "tool NOT intercepted by _is_blocked_tool_name:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )

    def test_terminal_toolset_tools_blocked(self, aiseo_guard):
        """Spot-check: all terminal toolset tools must be individually blocked."""
        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("terminal")
        assert tools, "terminal toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"terminal toolset tool '{tool}' is not blocked by _is_blocked_tool_name"
            )

    def test_code_execution_toolset_tools_blocked(self, aiseo_guard):
        """Spot-check: all code_execution toolset tools must be individually blocked."""
        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("code_execution")
        assert tools, "code_execution toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"code_execution toolset tool '{tool}' is not blocked by _is_blocked_tool_name"
            )

    def test_file_toolset_tools_blocked(self, aiseo_guard):
        """Spot-check: all file toolset tools must be individually blocked."""
        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("file")
        assert tools, "file toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"file toolset tool '{tool}' is not blocked by _is_blocked_tool_name"
            )

    def test_cronjob_toolset_covered_by_both_layers(self, aiseo_guard):
        """cronjob appears in both disabled_toolsets and TOOL_BLOCKLIST — verify both."""
        disabled = _load_seed_disabled_toolsets()
        assert "cronjob" in disabled, "cronjob must remain in config.disabled_toolsets"

        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("cronjob")
        assert tools, "cronjob toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"cronjob toolset tool '{tool}' is not blocked — "
                f"both defense layers must cover it"
            )

    def test_delegation_toolset_tools_blocked(self, aiseo_guard):
        """Spot-check: all delegation toolset tools must be individually blocked."""
        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("delegation")
        assert tools, "delegation toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"delegation toolset tool '{tool}' is not blocked by _is_blocked_tool_name"
            )

    def test_messaging_toolset_tools_blocked(self, aiseo_guard):
        """Spot-check: all messaging toolset tools must be individually blocked."""
        _is_blocked = aiseo_guard._is_blocked_tool_name
        tools = resolve_toolset("messaging")
        assert tools, "messaging toolset resolved to empty list"
        for tool in tools:
            assert _is_blocked(tool), (
                f"messaging toolset tool '{tool}' is not blocked by _is_blocked_tool_name"
            )


# ---------------------------------------------------------------------------
# Coverage count sanity
# ---------------------------------------------------------------------------

class TestBlocklistCoverageCount:
    """Verify the total number of tools covered by the parity check is meaningful."""

    def test_total_tool_count_across_disabled_toolsets(self):
        """At least 10 tools must be covered by the double-defense check.

        This prevents the test suite from becoming vacuous if toolsets are
        restructured to be empty.
        """
        disabled = _load_seed_disabled_toolsets()
        total_tools = sum(len(resolve_toolset(ts)) for ts in disabled)
        assert total_tools >= 10, (
            f"Only {total_tools} tools across all disabled toolsets — "
            f"check for toolset resolution regression"
        )

    def test_disabled_toolset_count_baseline(self):
        """At least 8 toolsets must be in disabled_toolsets (current baseline is 8)."""
        disabled = _load_seed_disabled_toolsets()
        assert len(disabled) >= 8, (
            f"Expected >= 8 disabled toolsets, got {len(disabled)}: {disabled}"
        )
