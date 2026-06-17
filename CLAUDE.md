# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo identity

This is the **AISEO Agent** — a fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent)
that adds an SEO-specialized brand layer (wrapper CLI + Hermes profile + guard plugin + one new
core hook). All upstream Hermes code is still present and unchanged in spirit.

**Read `AGENTS.md` first.** It is the authoritative Hermes-side developer guide
(1000 lines: AIAgent loop, plugin/toolset/skill systems, slash-command registry,
profile rules, prompt-cache invariants, test policy, known pitfalls). This file
only documents the AISEO **fork delta** that AGENTS.md does not cover.

Two more sources sit alongside this file and supersede it on their specific topics:

- `docs/aiseo-agent/ARCHITECTURE.md` — full design rationale for the 4-guard model,
  the `pre_user_message` hook contract, and the thin-wrapper-vs-real-cli decision.
- `.plans/` — in-flight design docs (currently: `dataforseo-plugin.md`,
  `streaming-support.md`, `openai-api-server.md`, `multi-tenant-saas.md`).

## Entry points and brand switch

There are two parallel `aiseo` entry points; both bootstrap the seed profile and
then `exec hermes -p aiseo <args...>`. Keep them in lockstep when changing one.

| Entry point | File | Where it's exposed |
|---|---|---|
| Python | `aiseo_cli.py` (`main()`) | `pyproject.toml::[project.scripts] aiseo = "aiseo_cli:main"` — installed by `pip install -e .` / `uv pip install -e .` |
| Bash | `bin/aiseo` | Repo-local wrapper for fresh clones (`./bin/aiseo`) |

Both set `AISEO_BRAND_ACTIVE=1` before invoking Hermes. That env var is read in
two specific places to swap the user-visible brand:

- `hermes_cli/banner.py::format_banner_version_label` — startup banner text
- `agent/prompt_builder.py::DEFAULT_AGENT_IDENTITY` — system-prompt agent name

Running `hermes -p aiseo` directly (without the wrapper) **intentionally**
preserves upstream Hermes branding. Contract tests:
`tests/agent/test_prompt_builder.py::TestPromptBuilderBrandSwitch` and
`tests/hermes_cli/test_banner.py::test_format_banner_version_label_*`.

`aiseo_cli.py` also implements two extra subcommands the bash wrapper does not:
- `aiseo sync [--refresh-soul] [-y|--yes]` — re-run seed→profile sync.
  Default is missing-only + additive list migration (see "Profile bootstrap
  pattern" below). `--refresh-soul` backs up + overwrites the profile SOUL.md
  from seed; `-y` skips the interactive prompt. On every run, prints a warning
  block listing env vars declared by enabled plugins' `requires_env` but
  missing from both the profile `.env` and the process environment.
- `aiseo cron create-from-memory <skill>` — pre-reads `MEMORY.md` and registers a
  cron job with a fully resolved prompt. Required because cron sessions run with
  `skip_memory=True` AND the aiseo profile disables the `file` toolset, so the
  cron agent cannot read `MEMORY.md` at run time.

## Profile bootstrap pattern

```
seeds/aiseo-profile/   (repo)  ──first-run sync──▶   ~/.hermes/profiles/aiseo/   (user state)
```

The seed dir contains `SOUL.md`, `config.yaml`, `cron/`, `memories/`, `references/`,
`skills/{growflare-seo,keyword-opportunity,technical-seo-audit,competitor-analysis,content-brief,seo-weekly-report}`.

Sync is **missing-only and idempotent**:
- `skills/` is copied at directory granularity — once a skill dir exists in the
  user's profile, the seed never touches its contents.
- Other dirs (`memories/`, `cron/`, `references/`) and top-level files (`SOUL.md`)
  are copied at file granularity, again missing-only.
- `NEVER_OVERWRITE_FILES = ("MEMORY.md", "config.yaml", ".env", "auth.json", "auth.lock")`
  are protected regardless — they hold user state.

`config.yaml` has one **narrow exception** to "never overwrite": seed-derived
**additive list migration**. `_migrate_profile_config` reads the seed config
on every sync and diffs the items in `SEED_TRACKED_LIST_FIELDS` (currently
`toolsets`, `agent.disabled_toolsets`, `plugins.enabled`) against the profile.
Items present in seed but missing from profile are appended at the user's
existing indent style, with an `# auto-added by aiseo sync <date>` audit
comment. Never deletes, never replaces, never re-orders. Before any write,
a rolling timestamped backup `config.yaml.bak.<YYYYMMDD_HHMMSS>` is taken
(keep newest `MAX_CONFIG_BACKUPS` = 5; older pruned). Failure modes (corrupt
seed YAML, missing block, inline scalar, YAML anchors) are reported under
`diff["skipped"]` rather than crashing.

**To extend additive migration**: add a dotted path to `SEED_TRACKED_LIST_FIELDS`
in `aiseo_cli.py`. Only list-valued fields up to one level of nesting are
supported. Scalars (model, max_turns) are intentionally NOT auto-migrated.

For non-list seed drift (SOUL.md regression, new plugin `requires_env`),
use `aiseo sync --refresh-soul` or follow the env warning block. Skills/
internal file updates are NOT propagated; iterate skills directly in
`~/.hermes/profiles/aiseo/skills/<name>/`.

**Profile sync is a permanent AISEO fork-only asset** — it does NOT delegate
to `hermes_cli/profile_distribution.py`. The two implementations have
opposing semantics (full-replace vs missing-only; `yaml.safe_dump` vs
text-level merge; bare `shutil.copy2` vs atomic write + fsync + rolling
backup). Do not "refactor" `aiseo_cli.py` sync to call into the upstream
distribution module; it would silently destroy user state. See
`docs/aiseo-agent/ARCHITECTURE.md` ADR-001 (and `.plans/profile-sync-upstream-spike.md`
for the full 13-point gap matrix and re-evaluation triggers).

## The aiseo-guard plugin

`plugins/aiseo-guard/` registers four hooks (declared in `plugin.yaml`):

| Hook | Role | Where it blocks |
|---|---|---|
| `pre_user_message` | InputGate — deterministic denylist (prompt mining, secrets, jailbreak, forbidden capabilities) | **New hook added to Hermes core** for this fork — see ARCHITECTURE.md §5 |
| `pre_tool_call` | ToolGate — whitelist fallback for tools not blocked by `agent.disabled_toolsets` | Returns `{"action":"block","message":...}` |
| `transform_tool_result` | External Content Guard — wraps `web_search` / `web_extract` / `browser_*` results in `<untrusted_external_content>` | Indirect prompt injection defense |
| `transform_llm_output` | OutputGate — regex redaction layered on top of `agent/redact.py` | Path/traceback/secret leaks the built-in redactor misses |

The plugin also provides two **narrow** scheduling tools (`aiseo_schedule_task`,
`aiseo_manage_scheduled_tasks`) that replace the disabled generic `cronjob`
toolset. `aiseo_schedule_task` supports two mutually-exclusive modes:
(a) **free-form SEO prompt** — pass `prompt` (≤ 2000 chars) and the cron
agent auto-loads matching SKILL.md at runtime via `aiseo_skills_read`,
giving scheduled tasks the same expressivity as interactive tasks;
(b) **structured shortcut** — pass `task_type` from a 7-value enum plus
its required structured fields. Both modes hard-reject `script / workdir /
deliver / model / provider / base_url / toolsets / enabled_toolsets / skills /
no_agent / context_from` (see `_AISEO_SCHEDULE_FORBIDDEN_FIELDS`).

Profile-level defense in depth lives in `seeds/aiseo-profile/config.yaml`:
`agent.disabled_toolsets` boots without `terminal`, `code_execution`, `delegation`,
`messaging`, `file`, `skills` (management), `cronjob`, `image_gen`. ToolGate is the
backstop if a future toolset slips through.

## The dataforseo plugin

`plugins/dataforseo/` is a standalone, opt-in plugin that exposes 5 structured
SEO data tools backed by the DataForSEO API (SERP, keyword search volume,
keyword ideas, on-page audit, backlinks summary).

| Aspect | Value | Notes |
|---|---|---|
| Path | `plugins/dataforseo/` | `plugin.yaml` declares `provides_tools` (5 tools) and `requires_env: [DATAFORSEO_BASE64]` |
| Enabled by | `seeds/aiseo-profile/config.yaml` `plugins.enabled` (includes `- dataforseo`) | Default on, but every tool's `check_fn=_check_dataforseo_available` greys it out until env is set |
| Credentials | `DATAFORSEO_BASE64` in `~/.hermes/profiles/aiseo/.env` | Precomputed `base64(login:password)`; optional `DATAFORSEO_SANDBOX=1` flips to the sandbox base URL |

Tool runtime behavior covers four DataForSEO call patterns: Basic Auth POST for
Live endpoints (fast path), `tasks_post` + `tasks_ready` polling for SERP, on-page
`task_post` + `crawl_progress` polling, and direct Live calls for keyword/backlinks
summaries. Credentials are masked via `_mask_auth_header` in all logged request
metadata. HTTP 429 triggers exponential backoff (5s / 10s / 20s, max 3 retries).

Design reference: `.plans/dataforseo-plugin.md` is the original design doc — its
older variable names (`DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`) have since been
merged into the single `DATAFORSEO_BASE64`. The current source of truth is
`.claude/PRPs/reports/dataforseo-plugin-report.md`. Server-side credential
provisioning SOP lives in `docs/aiseo-agent/DEPLOYMENT.md`.

## Common commands

```bash
# Dev install
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[all,dev]"

# Run the AISEO CLI from source
uv run aiseo                          # chat in the aiseo profile
uv run aiseo sync                     # re-sync seed→profile
uv run aiseo setup                    # configure provider for the aiseo profile

# Tests — ALWAYS use the wrapper (see AGENTS.md "Testing" for why)
scripts/run_tests.sh tests/aiseo/                         # AISEO deterministic suite (mocked LLMs)
scripts/run_tests.sh tests/aiseo/test_input_gate_*.py     # InputGate buckets only
scripts/run_tests.sh tests/aiseo_runtime_audit/           # 4-axis runtime audit harness
scripts/run_tests.sh                                       # full Hermes + AISEO suite
```

LLM-end smoke tests (cost-bearing, manual trigger only):

```bash
# Full 32-prompt regression — ~200k tokens, ¥1-3, 30 min
AISEO_SMOKE_CONFIRMED=1 bash tests/aiseo_llm/runner/run_smoke.sh

# Single bucket (S1..S6)
AISEO_SMOKE_CONFIRMED=1 bash tests/aiseo_llm/runner/run_smoke.sh s3

# Targeted 8-SID re-run (Phase 1 failures + Phase 2 new bucket)
bash scripts/run_targeted_smoke.sh

# Report-style eval harness (provider/model matrix)
bash scripts/run_aiseo_report_eval.sh
```

`tests/aiseo_llm/` is **not** collected by pytest — it has no `__init__.py` and
runner refuses to start without `AISEO_SMOKE_CONFIRMED=1`. Results land under
`tests/aiseo_llm/results/<run-id>/` (gitignored).

## When editing AISEO code

- **Two CLI entry points must stay in parity.** If `aiseo_cli.py::main` and
  `bin/aiseo` diverge on flag handling, brand switch, or bootstrap behavior,
  users invoking the same flag from different shells get different results.
- **Don't put rules in soft prompts.** AISEO ships a deterministic-first defense
  posture. `plugins/aiseo-guard/__init__.py` regex patterns are the primary line;
  `seeds/aiseo-profile/SOUL.md` is the soft fallback, not the contract.
- **Profile boot config is order-sensitive.** `seeds/aiseo-profile/config.yaml`
  pins `agent.disabled_toolsets` and `plugins.enabled: [aiseo-guard]`. Hermes
  loaders apply surface-specific filtering on top — re-verify on CLI/TUI/Gateway
  after a config change. (See ARCHITECTURE.md §4 for the caveat.)
- **Prompt-cache safety from AGENTS.md still applies.** Don't mutate toolsets /
  system prompt / memory mid-conversation. The `transform_*` hooks are safe
  because they touch tool results / LLM output, not the system prompt.
- **Skills under `seeds/aiseo-profile/skills/` are seed copies, not the active set.**
  Edits propagate to users only via `aiseo sync` on a missing skill dir or a fresh
  install. To iterate on a skill in your own profile, edit
  `~/.hermes/profiles/aiseo/skills/<name>/` directly.
