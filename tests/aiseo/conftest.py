"""Shared fixtures for Phase 1 adversarial smoke tests.

The smoke tests import the four aiseo-guard hook functions directly from
plugins/aiseo-guard/__init__.py and exercise their deterministic rules in
isolation (no Hermes runtime needed). This keeps each smoke test fast
and isolates regressions to the guard's policy code, while Phase 0
already covers the orchestration layer (run_agent / plugin loader)
end-to-end.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def aiseo_guard():
    """Load plugins/aiseo-guard/__init__.py as a module.

    Plugin lives at <repo>/plugins/aiseo-guard/ — its directory name
    contains a hyphen so a direct ``import`` won't work; load it via
    importlib.util under a synthetic module name.
    """
    repo_root = Path(__file__).resolve().parents[2]
    plugin_init = repo_root / "plugins" / "aiseo-guard" / "__init__.py"
    spec = importlib.util.spec_from_file_location("aiseo_guard_plugin", plugin_init)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to locate aiseo-guard plugin at {plugin_init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["aiseo_guard_plugin"] = module
    spec.loader.exec_module(module)
    return module
