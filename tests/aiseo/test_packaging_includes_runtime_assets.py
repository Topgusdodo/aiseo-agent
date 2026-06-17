"""Packaging contract: aiseo runtime assets must be declared in MANIFEST.in / pyproject.toml.

Why this exists
---------------
The aiseo CLI bootstraps a user profile by copying ``seeds/aiseo-profile/`` and
loads two non-Python plugin manifests at runtime
(``plugins/aiseo-guard/plugin.yaml`` and ``plugins/dataforseo/plugin.yaml``).

If those assets are not declared for packaging, a downstream
``pip install <wheel>`` or ``pip install <sdist.tar.gz>`` ships a broken
``aiseo`` entry point: the bootstrap call in
``aiseo_cli._sync_profile`` cannot find the seed directory, and the plugin
loader cannot read the plugin manifests.

This test is a fast, static guard. The "real" verification — actually
running ``python -m build`` and inspecting the artifacts — is too slow for
the per-PR loop, so we lock the declarations themselves so a future edit
to MANIFEST.in or pyproject.toml that drops these lines fails CI.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_manifest_grafts_seeds_and_plugins() -> None:
    """sdist must contain seeds/ and plugin non-Python assets (graft directives)."""
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    # `seeds/` is not a Python package (no __init__.py), so it can ONLY ship in
    # the sdist via a MANIFEST.in graft directive. Without this line the
    # `aiseo` CLI seed→profile sync breaks on a fresh sdist install.
    assert "graft seeds" in manifest, (
        "MANIFEST.in must `graft seeds` so seeds/aiseo-profile/ ships in the sdist; "
        "aiseo_cli._sync_profile reads it at runtime."
    )

    # plugin .py files are covered by `[tool.setuptools.packages.find]`, but
    # the plugin manifest YAML files and other non-Python assets need either
    # graft or package-data. `graft plugins` covers them in the sdist.
    assert "graft plugins" in manifest, (
        "MANIFEST.in must `graft plugins` so plugin non-Python assets "
        "(plugin.yaml, READMEs) ship in the sdist."
    )


def test_pyproject_bundles_aiseo_plugin_manifests_in_wheel() -> None:
    """Wheel must contain plugin.yaml for aiseo-guard and dataforseo plugins."""
    data = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = data["tool"]["setuptools"]["package-data"]

    # These two plugins are loaded by the aiseo profile on every boot. Their
    # plugin.yaml manifests are read by the plugin loader to discover hooks
    # and tools. Without these entries, `pip install <wheel>` ships only the
    # .py files and the plugin loader silently skips both plugins.
    assert "plugins.aiseo-guard" in package_data, (
        "pyproject.toml must declare package-data for plugins.aiseo-guard "
        "so plugin.yaml ships in the wheel."
    )
    assert "plugin.yaml" in package_data["plugins.aiseo-guard"], (
        "plugins.aiseo-guard package-data must include 'plugin.yaml'."
    )

    assert "plugins.dataforseo" in package_data, (
        "pyproject.toml must declare package-data for plugins.dataforseo "
        "so plugin.yaml ships in the wheel."
    )
    assert "plugin.yaml" in package_data["plugins.dataforseo"], (
        "plugins.dataforseo package-data must include 'plugin.yaml'."
    )


def test_seed_aiseo_profile_soul_exists_in_source_tree() -> None:
    """Sanity check: the file we claim to ship actually exists in the repo.

    If this fails, either seeds/aiseo-profile/SOUL.md was moved/renamed and
    aiseo_cli._sync_profile is broken, or the test is running from the wrong
    repo root.
    """
    soul = REPO_ROOT / "seeds" / "aiseo-profile" / "SOUL.md"
    assert soul.is_file(), (
        f"Expected seed file {soul} to exist — required by aiseo_cli._sync_profile."
    )
