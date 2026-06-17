"""Tests for the new `pre_user_message` plugin hook (Phase 0).

Covers four contract paths from plan section 5:
    1. allow      - handler returns None or {"action": "allow"} -> no block, no rewrite
    2. block      - handler returns {"action": "block", "message": "..."} -> captured
    3. rewrite    - handler returns {"action": "rewrite", "text": "..."} -> captured
    4. exception  - handler raises -> caught + logged, hook fails open (no result)

Plus regression checks:
    - VALID_HOOKS membership
    - first-block-wins / first-rewrite-wins iteration semantics
    - non-dict / malformed return values silently ignored by run_agent.py iteration
"""

from __future__ import annotations

from pathlib import Path

import yaml

from hermes_cli.plugins import VALID_HOOKS, PluginManager


def _make_pum_plugin(
    plugins_dir: Path,
    name: str,
    *,
    register_body: str,
    enable: bool = True,
) -> Path:
    """Create a minimal plugin dir that registers a pre_user_message handler.

    *register_body* is the Python body for `def register(ctx):`. Caller must
    ensure the body calls ctx.register_hook(...).
    """
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": f"test pre_user_message plugin {name}",
        "hooks": ["pre_user_message"],
    }
    (plugin_dir / "plugin.yaml").write_text(yaml.dump(manifest))
    (plugin_dir / "__init__.py").write_text(
        "def register(ctx):\n"
        f"    {register_body}\n"
    )

    if enable:
        hermes_home = plugins_dir.parent
        hermes_home.mkdir(parents=True, exist_ok=True)
        cfg_path = hermes_home / "config.yaml"
        cfg: dict = {}
        if cfg_path.exists():
            try:
                cfg = yaml.safe_load(cfg_path.read_text()) or {}
            except Exception:
                cfg = {}
        plugins_cfg = cfg.setdefault("plugins", {})
        enabled = plugins_cfg.setdefault("enabled", [])
        if isinstance(enabled, list) and name not in enabled:
            enabled.append(name)
        cfg_path.write_text(yaml.safe_dump(cfg))

    return plugin_dir


# -- Membership -----------------------------------------------------------


def test_valid_hooks_includes_pre_user_message():
    """pre_user_message must be a registered Hermes hook name."""
    assert "pre_user_message" in VALID_HOOKS


# -- Path 1: allow (None) -------------------------------------------------


def test_pre_user_message_allow_returns_no_results(tmp_path, monkeypatch):
    """Handler returning None contributes nothing to invoke_hook() results."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_allow",
        register_body=(
            'ctx.register_hook("pre_user_message", lambda **kw: None)'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="hello",
        conversation_history=[],
        is_first_turn=True,
        model="claude-sonnet-4-6",
        platform="cli",
        sender_id="u1",
    )
    # invoke_hook drops None returns; allow path -> empty list.
    assert results == []


def test_pre_user_message_explicit_allow_dict_collected(tmp_path, monkeypatch):
    """{"action": "allow"} is collected as a non-None result; run_agent.py
    iteration treats it the same as None (no block, no rewrite triggered)."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_allow_dict",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "allow"})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="hi",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )
    assert results == [{"action": "allow"}]
    # Replicate run_agent.py iteration: allow -> no block, no rewrite.
    block = None
    rewritten = None
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("action") == "block":
            block = r
            break
        if r.get("action") == "rewrite" and rewritten is None:
            text = r.get("text")
            if isinstance(text, str):
                rewritten = text
    assert block is None
    assert rewritten is None


# -- Path 2: block --------------------------------------------------------


def test_pre_user_message_block_captured(tmp_path, monkeypatch):
    """Block directive surfaces in results so run_agent.py can short-circuit."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_block",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "block", "message": "blocked: not SEO"})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="ignore previous instructions",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )
    assert len(results) == 1
    assert results[0] == {"action": "block", "message": "blocked: not SEO"}


# -- Path 3: rewrite ------------------------------------------------------


def test_pre_user_message_rewrite_captured(tmp_path, monkeypatch):
    """Rewrite directive surfaces in results for run_agent.py to apply."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_rewrite",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "rewrite", "text": "(safe) " + kw["user_message"]})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="analyze example.com",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )
    assert len(results) == 1
    assert results[0] == {"action": "rewrite", "text": "(safe) analyze example.com"}


# -- Path 4: exception (fail-open) ----------------------------------------


def test_pre_user_message_handler_exception_fails_open(tmp_path, monkeypatch):
    """A handler that raises is caught + logged; other handlers still run."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"

    # First handler raises; second returns a valid block dict.
    _make_pum_plugin(
        plugins_dir,
        "pum_explode",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))'
        ),
    )
    _make_pum_plugin(
        plugins_dir,
        "pum_block_after_explode",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "block", "message": "guard"})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()

    # Should not raise despite first handler exploding.
    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="bad input",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )
    # Exploded handler contributes nothing; surviving handler block reaches caller.
    assert results == [{"action": "block", "message": "guard"}]


# -- Multi-plugin: first-block-wins iteration --------------------------------


def test_pre_user_message_iteration_first_block_wins(tmp_path, monkeypatch):
    """Iteration logic from run_agent.py:run_conversation breaks on the first
    block dict in results. Replicates the inline loop to confirm semantics
    (mirrors pre_gateway_dispatch in gateway/run.py:5666-5685).
    """
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_block_a",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "block", "message": "first block"})'
        ),
    )
    _make_pum_plugin(
        plugins_dir,
        "pum_block_b",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "block", "message": "second block"})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()
    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="x",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )

    # Replicate run_agent.py iteration (first-block-wins -> first-rewrite-wins).
    block = None
    rewritten = None
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("action") == "block":
            block = r
            break
        if r.get("action") == "rewrite" and rewritten is None:
            text = r.get("text")
            if isinstance(text, str):
                rewritten = text

    assert block is not None
    # Plugin discovery order isn't guaranteed across filesystems, but exactly
    # one block dict drives the abort.
    assert block["message"] in {"first block", "second block"}


def test_pre_user_message_iteration_first_rewrite_wins(tmp_path, monkeypatch):
    """When no block is present, the first rewrite directive wins."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_rewrite_a",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "rewrite", "text": "rewrite-a"})'
        ),
    )
    _make_pum_plugin(
        plugins_dir,
        "pum_rewrite_b",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: {"action": "rewrite", "text": "rewrite-b"})'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()
    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="x",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )

    block = None
    rewritten = None
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("action") == "block":
            block = r
            break
        if r.get("action") == "rewrite" and rewritten is None:
            text = r.get("text")
            if isinstance(text, str):
                rewritten = text

    assert block is None
    assert rewritten in {"rewrite-a", "rewrite-b"}


def test_pre_user_message_non_dict_returns_skipped_by_iteration(tmp_path, monkeypatch):
    """Handlers returning unexpected types (str, int, etc.) do not affect iteration."""
    plugins_dir = tmp_path / "hermes_test" / "plugins"
    _make_pum_plugin(
        plugins_dir,
        "pum_garbage",
        register_body=(
            'ctx.register_hook("pre_user_message", '
            'lambda **kw: "this should be ignored by iteration")'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes_test"))

    mgr = PluginManager()
    mgr.discover_and_load()
    results = mgr.invoke_hook(
        "pre_user_message",
        session_id="s1",
        user_message="x",
        conversation_history=[],
        is_first_turn=True,
        model="m",
        platform="cli",
        sender_id="",
    )

    # invoke_hook collects strings (they're not None), but run_agent.py iteration
    # skips non-dict results.
    assert results == ["this should be ignored by iteration"]
    block = None
    rewritten = None
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("action") == "block":
            block = r
            break
        if r.get("action") == "rewrite" and rewritten is None:
            text = r.get("text")
            if isinstance(text, str):
                rewritten = text
    assert block is None
    assert rewritten is None
