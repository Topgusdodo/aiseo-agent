#!/usr/bin/env python3
"""AISEO Agent CLI entry point."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _profile_dir() -> Path:
    hermes_root = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return hermes_root / "profiles" / "aiseo"


def _bootstrap_profile() -> None:
    seed_dir = _repo_root() / "seeds" / "aiseo-profile"
    profile_dir = _profile_dir()

    if profile_dir.exists():
        return

    if not seed_dir.is_dir():
        print(f"[aiseo] error: seed directory not found at {seed_dir}", file=sys.stderr)
        raise SystemExit(1)

    print(f"[aiseo] First run — bootstrapping profile at {profile_dir} ...", file=sys.stderr)
    profile_dir.mkdir(parents=True, exist_ok=True)
    for child in seed_dir.iterdir():
        target = profile_dir / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    print(
        "[aiseo] Profile ready. Run 'hermes setup' if you have not configured a provider yet.",
        file=sys.stderr,
    )


def main() -> None:
    _bootstrap_profile()
    sys.argv = ["hermes", "-p", "aiseo", "chat", *sys.argv[1:]]
    from hermes_cli.main import main as hermes_main

    hermes_main()


if __name__ == "__main__":
    main()
