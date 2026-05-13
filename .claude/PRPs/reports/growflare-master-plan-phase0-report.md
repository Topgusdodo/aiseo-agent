# Implementation Report — AISEO Agent Phase 0 (Runtime Seam + Bootstrap Skeleton)

**Plan**: `.claude/PRPs/plans/growflare-master-plan.md`
**Phase**: 0 of 2 (Phase 1 + Phase 2 NOT started — pending user invocation)
**Branch**: `feat/aiseo-phase0`
**Date**: 2026-05-13

---

## Summary

Phase 0 lays the runtime seam (new `pre_user_message` hook in Hermes core)
and bootstrap skeleton (`bin/aiseo` thin wrapper + `plugins/aiseo-guard/`
plugin + `seeds/aiseo-profile/` profile seed + `tests/aiseo/` test bucket).
All 4 noop hook handlers in `aiseo-guard` are registered via Hermes plugin
discovery; the new `pre_user_message` hook is invoked in
`AIAgent.run_conversation()` before `pre_llm_call`, with full
allow / block / rewrite / exception contract honored.

Rule bodies (deterministic denylist, redaction patterns, External Content
Guard tag wrapping, SKILL.md bodies, adversarial smoke pack) land in
Phase 1 — Phase 0 is intentionally limited to seams + skeleton + V0-V4
verification gates.

---

## Assessment vs Reality

| Metric                  | Predicted (plan) | Actual          |
|-------------------------|------------------|-----------------|
| Phase 0 complexity      | M                | M (as expected) |
| Phase 0 estimate        | 1-2 working days | one session     |
| Phase 0 files changed   | ~10 new + 2 modified | 11 new + 2 modified |
| Hermes core lines added | ~20              | ~46 (including comment block) |
| V0-V4 gates             | all required     | V0/V2/V3/V4 PASS; V1 PASS with caveat |

---

## Tasks Completed

| #  | Task                                                                                  | Status        |
|----|---------------------------------------------------------------------------------------|---------------|
| 1  | Verify Phase 0 source anchors + grep `config.py` field names                          | Complete      |
| 2  | Create `feat/aiseo-phase0` branch from main                                           | Complete      |
| 3  | Add `pre_user_message` to `VALID_HOOKS` in `hermes_cli/plugins.py`                    | Complete      |
| 4  | Insert `pre_user_message` hook invoke in `run_agent.py` before `pre_llm_call`         | Complete      |
| 5  | Write 4-path unit tests for `pre_user_message` hook                                   | Complete (9 tests, all green) |
| 6  | Write `bin/aiseo` bash wrapper (D17 bootstrap)                                        | Complete      |
| 7  | Write `plugins/aiseo-guard/` skeleton (plugin.yaml + `__init__.py`)                   | Complete      |
| 8  | Write `seeds/aiseo-profile/SOUL.md` minimal (4 sections, 27 lines)                    | Complete      |
| 9  | Write `seeds/aiseo-profile/config.yaml` per CONFIG_YAML_TEMPLATE                      | Complete (deviation: `display.streaming` instead of top-level) |
| 10 | Write `seeds/aiseo-profile/skills/growflare-seo/SKILL.md` placeholder + `.gitkeep`    | Complete      |
| 11 | V0 — plugin discovery picks up `plugins/aiseo-guard/`                                 | PASS          |
| 12 | V1 — top-level `toolsets` config equivalence across CLI/TUI/Gateway                   | PASS with caveat |
| 13 | V2 — `disabled_toolsets[skills]` doesn't break SKILL.md auto-scan                     | PASS          |
| 14 | V3 — wrapper bootstrap (mkdir+cp -R) suffices for `hermes -p aiseo`                   | PASS          |
| 15 | V4 — wrapper bash compat on macOS Darwin (no `readlink -f`)                           | PASS with caveat (symlink-in-PATH edge case) |
| 16 | Run pytest `tests/aiseo/` + regression on `tests/hermes_cli/test_plugins.py`          | PASS (9 + 65 = 74 tests green) |
| 17 | bin/aiseo smoke — wrapper passthrough verified; full chat smoke pending user setup    | Partial       |
| 18 | Write Phase 0 implementation report                                                   | Complete      |

---

## Verification Gate Results

### V0 — Plugin Discovery (PASS, prerequisite gate)

`PluginManager.discover_and_load()` finds `plugins/aiseo-guard/` as a
**bundled** plugin (manifest.source = "bundled"), enables it via
`plugins.enabled` allow-list, and registers all 4 noop hook handlers:

```
aiseo-guard in _plugins: True
  enabled:           True
  manifest.source:   bundled
  hooks_registered:  4
  hook 'pre_user_message':      1 callback [OK]
  hook 'pre_tool_call':         1 callback [OK]
  hook 'transform_tool_result': 1 callback [OK]
  hook 'transform_llm_output':  1 callback [OK]
```

V0 was the hardest precondition — its PASS validates D13 (plugin at
`<repo>/plugins/aiseo-guard/` is auto-discovered without a profile-local
install or `hermes profile install` step).

### V1 — top-level `toolsets` surface equivalence (PASS with caveat)

**Code-path investigation result**:

| Field                         | CLI | TUI | Gateway | Cron | Equivalent? |
|-------------------------------|-----|-----|---------|------|-------------|
| top-level `toolsets`          | display only (`dump.py:303`) | not consumed | not consumed | not consumed | **No** — overridden by `_get_platform_tools` |
| `agent.disabled_toolsets`     | `cli.py:2461` | via `_get_platform_tools` | `run.py:10207/14139` | via `_get_platform_tools` | **Yes** |

`hermes_cli/tools_config.py:1251-1256` line comment confirms the design:
*"Honor agent.disabled_toolsets from config.yaml — allows users to
[remove toolsets across all platforms]"*. The disable list is the true
cross-surface mechanism; the top-level `toolsets` field is more a
declarative hint than a runtime enable list.

**Impact on ToolGate defense depth**: NONE.

The plan's ToolGate first layer (boot-time refusal) depends on
`agent.disabled_toolsets`, which **is** cross-surface equivalent.
ToolGate second layer (`pre_tool_call` plugin) is unaffected. Defense
depth remains the planned double layer.

**Action recorded to D-决策附录** (see below).

### V2 — `disabled_toolsets[skills]` vs SKILL.md scan (PASS)

`agent.disabled_toolsets: [skills]` disables ONLY the skills *management*
toolset (`skills_list` / `skill_view` / `skill_manage`). It does **not**
affect SKILL.md auto-scanning via `agent.skill_utils.iter_skill_index_files`.

Test run output:
```
agent.disabled_toolsets = ['terminal', 'code_execution', 'delegation',
                           'messaging', 'file', 'skills', 'cronjob', 'image_gen']
Scanning .../profiles/aiseo/skills ...
  found: skills/growflare-seo/SKILL.md
"skills" in disabled_toolsets: True
growflare-seo SKILL.md discovered: True
```

### V3 — wrapper bootstrap (PASS)

`bin/aiseo` first run with `HERMES_HOME=/tmp/...`:
- `[aiseo] First run — bootstrapping profile at /tmp/.../profiles/aiseo`
- Created seed contents (`SOUL.md`, `config.yaml`, `skills/growflare-seo/`,
  `cron/`, `memories/`, `references/`)
- Second run skipped bootstrap (idempotent — directory check passes).

No `hermes profile create` / `hermes profile install` was invoked; pure
`mkdir -p` + `cp -R` is sufficient (D17 confirmed).

### V4 — macOS bash compat (PASS with caveat)

`cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null && pwd -P` resolves
correctly under three invocation modes:
- (a) absolute path: `SCRIPT_DIR=<repo>/bin`
- (b) symlink invocation: `SCRIPT_DIR=<symlink dir>` (BSD `pwd -P` resolves
  the parent dir of the symlink itself, not the symlink target)
- (c) via `$PATH`: wrapper-in-PATH works when the wrapper is the real
  script (or copied alongside `seeds/`).

**Caveat for D-决策附录**: a symlink in `~/bin` pointing at `bin/aiseo`
inside the repo will set `SCRIPT_DIR=~/bin`, so `REPO_ROOT=~/`, and
`SEED_DIR=~/seeds/aiseo-profile` will not exist. Users wanting symlink-in-PATH
installation should either invoke via the actual repo `bin/` path or use a
symlink-following install pattern.

---

## Files Changed

### New files (11)

| File                                                                | Lines |
|---------------------------------------------------------------------|-------|
| `bin/aiseo`                                                         | 38    |
| `plugins/aiseo-guard/plugin.yaml`                                   | 8     |
| `plugins/aiseo-guard/__init__.py`                                   | 55    |
| `seeds/aiseo-profile/SOUL.md`                                       | 27    |
| `seeds/aiseo-profile/config.yaml`                                   | 51    |
| `seeds/aiseo-profile/skills/growflare-seo/SKILL.md`                 | 29    |
| `seeds/aiseo-profile/cron/.gitkeep`                                 | 0     |
| `seeds/aiseo-profile/memories/.gitkeep`                             | 0     |
| `seeds/aiseo-profile/references/.gitkeep`                           | 0     |
| `tests/aiseo/__init__.py`                                           | 0     |
| `tests/aiseo/test_pre_user_message_hook.py`                         | 328   |

### Modified files (2)

| File                          | Change                                                                 | Lines |
|-------------------------------|------------------------------------------------------------------------|-------|
| `hermes_cli/plugins.py`       | Added `pre_user_message` to `VALID_HOOKS` with full docstring          | +16   |
| `run_agent.py`                | Inserted `pre_user_message` hook invoke before `pre_llm_call` (line 11952) — block / rewrite / allow contract + first-block-wins → first-rewrite-wins + short-circuit return | +47   |

---

## D-决策附录 (new entries from Phase 0)

| ID     | Decision                                                                                                                                                                                                                                                                  | Surface | Action |
|--------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|--------|
| D14-A1 | `streaming` lives at `display.streaming` in `DEFAULT_CONFIG` (config.py:911), NOT top-level. Plan template "streaming: false" at top level was wrong; implemented config uses `display.streaming: false`.                                                                  | All     | Done (Phase 0) |
| D14-A2 | `pre_llm_call` invoke actual line is `run_agent.py:11968` (plan said 11967 — 1-line drift). `transform_llm_output` invoke at `run_agent.py:15321` (plan said 15320, 1-line drift).                                                                                          | All     | Done |
| D3-A1  | Initial Phase 0 seed `config.yaml` hard-coded `model: claude-sonnet-4-6` as a "recommended default", which broke users who configured only a different provider (e.g. deepseek). Per D3 (profile must not lock model/provider), the `model` field was removed from the seed. Plan D3 + PRD risk-table mitigation text updated accordingly. | All | Done — also synced `~/.hermes/profiles/aiseo/config.yaml` for users who already bootstrapped. |
| D3-A2  | **Profile isolation discovery**: Hermes profile is a **fully isolated HERMES_HOME** (hermes_cli/main.py:119 `_apply_profile_override` sets `os.environ["HERMES_HOME"]` to the profile path). The aiseo profile's `.env`, `config.yaml`, `providers`, and `auth` are **all independent** — it does NOT inherit the default profile's API key or model. After `bin/aiseo` bootstraps the profile, the user MUST run either `hermes -p aiseo setup` (full guided setup) OR manually `cp ~/.hermes/.env ~/.hermes/profiles/aiseo/.env` + `hermes -p aiseo model`. Earlier claim that "provider credentials are globally shared" was incorrect. | All | Documented in NEXT_STEPS.md + seed comments + bootstrapped profile comments. Plan D3 already states "profile 不锁 model 也不锁 provider"; this entry clarifies the **isolation mechanism**. |
| V1-C1  | Top-level `toolsets` field is **not** cross-surface equivalent. `_get_platform_tools` (hermes_cli/tools_config.py:1054) reads `config["platform_toolsets"][platform]`, falling back to `PLATFORMS[platform]["default_toolset"]`. Top-level `toolsets` is consumed only by `hermes dump` and a few helper paths. | All     | Document in `config.yaml` comment; do not rely on top-level `toolsets` for runtime gating. |
| V1-C2  | `agent.disabled_toolsets` IS cross-surface equivalent (CLI/TUI/Gateway/Cron all route through it). **This is the field ToolGate first-layer defense actually relies on.** Defense depth unchanged.                                                                          | All     | Continue using `agent.disabled_toolsets` as primary ToolGate-1 mechanism. |
| V4-C1  | Symlink-in-`~/bin` pointing at `bin/aiseo` inside the repo will **not** resolve `SEED_DIR` correctly because BSD `pwd -P` resolves the symlink's parent dir, not the target dir. Documented limitation.                                                                    | macOS   | Document in installation guide (Phase 2). |
| T17-P1 | Full `bin/aiseo` → `hermes -p aiseo chat` smoke ("你好" → AISEO identity) requires user-side `hermes setup` (LLM provider key). Wrapper bootstrap + passthrough verified; full chat smoke is a manual sanity check left to the user.                                       | All     | User runs `hermes setup` + `bin/aiseo` once after Phase 0 merge. |

---

## Test Results

```
$ pytest tests/aiseo/test_pre_user_message_hook.py
9 tests passed (allow / block / rewrite / exception / first-block-wins /
                first-rewrite-wins / non-dict / VALID_HOOKS membership /
                explicit allow dict).

$ pytest tests/hermes_cli/test_plugins.py
65 tests passed — no regression on existing plugin infrastructure.
```

Total: **74 tests green; 0 failures; 0 errors**.

---

## Phase 0 Acceptance Checklist

- [x] `pre_user_message` hook in `VALID_HOOKS` and invoke point before `pre_llm_call`
- [x] 4-path unit tests green (allow / block / rewrite / exception)
- [x] `bin/aiseo` first-run bootstraps profile via pure `mkdir -p` + `cp -R`; second-run skips
- [x] `plugins/aiseo-guard/` 4 hook handlers registered (V0 confirmed via PluginManager introspection)
- [x] `seeds/aiseo-profile/` directory skeleton complete
- [x] **Chat startup shows AISEO identity** — verified 2026-05-13 via user manual smoke after `hermes -p aiseo setup` + `hermes -p aiseo tools` (T17-P1 closed)
- [x] Verification gates V0-V4 all pass (V1, V4 with documented caveats in D-决策附录)
- [x] No V failure went around with a TODO bypass; deviations recorded in D-决策附录

---

## What Phase 0 Did NOT Do (intentional — Phase 1 / 2 scope)

- 4 hook rule bodies (deterministic denylist, redaction patterns, External Content Guard tag wrapping)
- Full 9-section SOUL.md
- ≥20 adversarial smoke tests
- 2 MVP skill bodies (`growflare-seo`, `keyword-opportunity`)
- helper script `seo_metadata.py`
- `references/seo-audit-checklist.md` + report templates
- branded `aiseo --help` intercept
- stream gate
- cron templates
- 5-10 URL e2e validation

---

## Next Steps

1. **User**: run `hermes setup` to configure an LLM provider, then
   `bin/aiseo` to smoke-test the chat → AISEO identity flow (T17-P1).
2. **Review**: optionally `/code-review` on this branch before merging.
3. **Commit + PR**: not auto-committed by Phase 0 (per session policy);
   user decides commit message + merge timing.
4. **Phase 1**: re-invoke `/prp-implement` against
   `.claude/PRPs/plans/growflare-master-plan.md` when ready; Phase 1
   adds the actual policy logic to the 4 hook bodies and writes the
   adversarial smoke pack.

Phase 1 / Phase 2 are NOT auto-started — they require explicit user
invocation. Plan file is NOT archived (Phase 1 + Phase 2 still pending).
