# `seeds/aiseo-profile/` — AISEO Hermes seed profile

This directory is the **seed source** for the AISEO Hermes profile. On first
run (or `aiseo sync`), the contents here are copied into
`~/.hermes/profiles/aiseo/` by the **AISEO fork-only** sync implementation
in `aiseo_cli.py` (functions `_bootstrap_profile`, `_sync_profile`,
`_sync_skills_dir`, `_migrate_profile_config`).

## CODEOWNERS — DO NOT TOUCH WITHOUT READING ADR-001

> **Maintainer scope**: AISEO fork only. Upstream Hermes does not consume
> this directory. Changes here ship to every existing AISEO user via the
> next `aiseo sync` run, but **only for missing files / additive list fields**.

### Hard rules

1. **Do NOT add `distribution.yaml` to this directory.** If you do, anyone
   who runs `hermes profile install <git-url>` or `hermes profile update aiseo`
   will trigger upstream `hermes_cli/profile_distribution.py:update_distribution`,
   which uses `shutil.rmtree(dest) + shutil.copytree(entry, dest)` semantics
   (`_copy_dist_payload`, l.554-563) and will **silently delete every user
   modification** under `skills/`, `cron/`, `references/`, etc. AISEO's
   `_sync_skills_dir` missing-only protection only runs when `aiseo sync`
   is the entry point; it cannot block the upstream distribution path.

2. **Do NOT try to "consolidate" sync logic into `hermes_cli/profile_distribution.py`.**
   The two implementations have opposing design philosophies:

   | Aspect | AISEO `aiseo_cli.py` sync | Upstream `profile_distribution.py` |
   |---|---|---|
   | Default semantics | Additive / missing-only | Full replace (`rmtree` + `copytree`) |
   | `config.yaml` updates | Text-level merge (preserves comments, anchors, indent) | `preserve_config=True` (skip) or `yaml.safe_dump` (lose all comments) |
   | Write durability | `mkstemp` + `fsync` + `atomic_replace` + rolling backup (5 slots) | Bare `shutil.copy2` / `write_text`, no backup, no fsync |
   | Skills protection | Directory-granular `target.exists() → skip` | Forced `rmtree` then `copytree` |

   See `docs/aiseo-agent/ARCHITECTURE.md` **ADR-001** for the full decision
   record and the gap matrix in `.plans/profile-sync-upstream-spike.md` §2.

3. **Do NOT edit files here as a way to push hotfixes to existing users'
   `skills/<name>/SKILL.md`.** Skill directory updates are seed-side only
   — once a skill dir exists in `~/.hermes/profiles/aiseo/skills/<name>/`,
   `_sync_skills_dir` will never re-touch it. To iterate on a skill in your
   own profile, edit `~/.hermes/profiles/aiseo/skills/<name>/` directly.
   To roll an update out to new installs only, edit here.

### Files in this seed tree

| Path | Bootstrap behavior | User state? |
|---|---|---|
| `SOUL.md` | Copied if missing; force-overwrite via `aiseo sync --refresh-soul` | No |
| `config.yaml` | Copied if missing; on each sync, `_migrate_profile_config` text-appends new items from `SEED_TRACKED_LIST_FIELDS` (`toolsets`, `agent.disabled_toolsets`, `plugins.enabled`) — never replaces, never re-orders | Yes (after first sync) |
| `skills/<name>/` | Directory-granular missing-only via `_sync_skills_dir` | Yes (after first sync) |
| `cron/`, `memories/`, `references/` | File-granular missing-only | Yes (after first sync) |
| `memories/MEMORY.md` | Protected by `NEVER_OVERWRITE_FILES` (basename match) | Yes |

### When to touch this directory

- Adding a new SEO skill → drop a new `skills/<name>/SKILL.md` here; next
  `aiseo sync` on existing installs will copy the directory if absent.
- Adding a new toolset / plugin → append to `config.yaml` and add the dotted
  path to `SEED_TRACKED_LIST_FIELDS` in `aiseo_cli.py:87-91` so existing
  users receive the addition on next sync.
- Updating SOUL.md content → edit here; existing users will only see the
  change after running `aiseo sync --refresh-soul -y` (gated by interactive
  confirmation otherwise).

### When NOT to touch this directory

- Iterating on a skill for your own profile (use `~/.hermes/profiles/aiseo/skills/<name>/`).
- Adding `distribution.yaml` to expose this profile to `hermes profile install` (rule #1).
- Trying to ship a `MEMORY.md` template (it's user state, protected by `NEVER_OVERWRITE_FILES`).

### Re-evaluation cadence

The "AISEO sync stays fork-only" decision is reviewed quarterly. If upstream
Hermes introduces per-path policy, text-level config merge hooks, atomic
writes, or backup machinery in `profile_distribution.py`, re-run the gap
matrix in `.plans/profile-sync-upstream-spike.md` §6 within 1 week and
update ADR-001's `Status` if the answer changes.
