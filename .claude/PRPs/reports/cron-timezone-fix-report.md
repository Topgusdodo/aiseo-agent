# Implementation Report: Cron Timezone Fix + Start Event

## Summary

Fixed two independent classes of cron job bugs in aiseo-agent:

1. **Job-level timezone** (problems 1 & 3 from user report): cron jobs created via the AISEO plugin stored only a naive cron expression (e.g. `35 9 * * *`) without timezone metadata. On non-Asia/Shanghai host containers, croniter interpreted `09:35` as UTC — so "北京时间 09:35" tasks would fire at 17:35 (北京) instead. Also caused next_run_at to jump to "tomorrow" when a same-day window of a few minutes should have been honored.

2. **Start-event notice** (problem 2 from user report): the scheduler only delivered a result message to messaging channels **after** `run_job()` completed, causing a multi-minute silent gap from trigger to first user-visible signal. Added a deterministic, sanitized "task starting" notice delivered before `run_job()`.

## Assessment vs Reality

| Metric | Predicted (Plan v2) | Actual |
|---|---|---|
| Commits planned | 2 (+1 optional docs) | 2 distinct logical changes (timezone bundle + start event) |
| Files touched | 3 source + 4+ test | 3 source + 5 test |
| New module-level symbols | DEFAULT_CRON_TIMEZONE, _format_display_with_tz, _deliver_notice, _build_start_notice, _sanitize_for_notice | 5 — exactly as planned |
| compute_next_run callsites updated | 8 internal | 8 internal in cron/jobs.py (scheduler.py had 0 direct callsites — plan was overly cautious) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | RED test: compute_next_run timezone matrix | [done] | 7 cases (host UTC × job Asia/Shanghai / UTC / default) |
| 2 | Implement cron/jobs.py timezone schema | [done] | DEFAULT_CRON_TIMEZONE + _normalize_job_record extension + _format_display_with_tz + compute_next_run/create_job/update_job timezone-aware |
| 3 | Update cron/scheduler.py compute_next_run callsites | [done] | scheduler.py has **no direct callsites** — plan was overly cautious; indirect callers in cron/jobs.py already updated in task 2 |
| 4 | AISEO plugin timezone passthrough | [done] | schedule_task (line 773) + manage_scheduled_tasks reschedule update_job + rollback (lines 1099-1117) |
| 5 | RED test: _normalize_job_record timezone fallback | [done] | 5 cases including env override + non-mutation contract |
| 6 | Extend tests/aiseo/ for timezone persistence | [done] | 10 schedule_display assertions updated to tolerate `(tz)` suffix |
| 7 | C1 GREEN verification (cron+aiseo+runtime audit) | [done] | 385/385 green |
| 8 | Implement C2 start event delivery | [done] | _build_start_notice + _deliver_notice + _sanitize_for_notice + _process_job try/except wrapper |
| 9 | C2 tests: start event behavior | [done] | 13 tests across sanitize/build/local-skip/failure-containment/ordering |
| 10 | Full suite validation + report + archive | [done] | 762 tests in changed-files scope GREEN |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Type Check | N/A | Python project, no separate type-check step |
| Lint | N/A | Project does not run lint pre-test |
| Unit Tests (scope) | [done] | 762/762 passed in cron + aiseo + runtime audit + cronjob_tools + cron CLI + timezone module |
| Build | N/A | Pure Python — no build step |
| Integration | [done] | tests/aiseo_runtime_audit (4-axis harness) green |
| Edge Cases | [done] | host TZ != job TZ matrix (UTC host, Asia/Shanghai job); legacy job without `timezone` field; control-char injection in job name; deliver=local silent skip; notice exception isolation |

**Full-suite note**: a `scripts/run_tests.sh tests/` run (~20 minutes) reports 2083 failures + 18 errors, but all are pre-existing in modules I did not touch (MCP/OAuth/TTS/Kanban plugin ImportErrors, SSE OAuth transport tests, etc.). My change blast radius is `cron/jobs.py`, `cron/scheduler.py`, `plugins/aiseo-guard/__init__.py`, and tests under `tests/cron/` + `tests/aiseo/` — and that entire scope passes.

## Files Changed

| File | Action | Notes |
|---|---|---|
| `cron/jobs.py` | UPDATED | DEFAULT_CRON_TIMEZONE constant; ZoneInfo import; _normalize_job_record extended; _format_display_with_tz added; compute_next_run signature + timezone-aware body; create_job + update_job timezone handling; 8 internal compute_next_run callsites transfer timezone |
| `cron/scheduler.py` | UPDATED | `re` module imported; _CONTROL_CHARS_RE + _sanitize_for_notice + _build_start_notice + _deliver_notice added; _process_job calls start notice via try/except before run_job |
| `plugins/aiseo-guard/__init__.py` | UPDATED | _aiseo_schedule_task passes timezone to create_job (line 773); _aiseo_manage_scheduled_tasks reschedule + rollback paths persist timezone (lines 1099-1117) |
| `tests/cron/test_compute_next_run_timezone.py` | CREATED | 7 tests covering full timezone matrix |
| `tests/cron/test_normalize_job_record_timezone.py` | CREATED | 5 tests covering normalize + env override + non-mutation |
| `tests/cron/test_process_job_start_event.py` | CREATED | 13 tests covering sanitize/build/local-skip/failure-containment/ordering |
| `tests/cron/test_compute_next_run_last_run_at.py` | UPDATED | 2 tests: explicit `timezone="Africa/Casablanca"` to preserve original intent under new explicit-timezone contract |
| `tests/aiseo/test_aiseo_schedule_task.py` | UPDATED | 6 schedule_display assertions converted to `startswith` + `(Asia/Shanghai)` substring checks |
| `tests/aiseo/test_aiseo_manage_scheduled_tasks.py` | UPDATED | reschedule dict-equality assertion converted to field-level + timezone persistence check |

## Deviations from Plan

| What | Why |
|---|---|
| `create_job()` signature: added `timezone` as the **last** positional-keyword param rather than introducing `*,` kw-only boundary | Plan §D3 proposed `*, timezone: Optional[str] = None`, which would have been a stricter signature shape change. All 5 external callers already use keyword form, so adding a keyword default at the end is both backward-compatible **and** achieves the same call-site discipline. Net safety identical, smaller blast radius. |
| Task 3 (scheduler.py compute_next_run callsites) was a no-op | `cron/scheduler.py` has **zero** direct calls to `compute_next_run`; it relies on `cron/jobs.py` internal functions (`advance_next_run`, `mark_job_run`) which were already updated in task 2. Kept task as completed for audit trail. |
| Legacy `tests/cron/test_compute_next_run_last_run_at.py` needed two assertions updated | Exactly the trade-off plan §D4b warned about: the new contract decouples base_time's tz from cron-interpretation tz. Fix: explicitly pass `timezone="Africa/Casablanca"` so the test's original intent is preserved under the new explicit-timezone contract. |
| Plan §D5c suggested `schedule_display` rewriting at plugin level too | Implemented entirely in `cron/jobs.py::create_job` and `update_job` — when plugin passes timezone, jobs.py handles the display rewrite. Plugin-level rewrite would have been redundant. |

## Issues Encountered

| Issue | Resolution |
|---|---|
| `cron/scheduler.py` lacked `import re` — `_CONTROL_CHARS_RE` module-level pattern failed at import time | Added `import re` to top-of-file imports |
| `scripts/run_tests.sh` with no args triggers `ARGS[@]: unbound variable` on this bash | Used explicit `tests/` arg for full-suite run; not a regression introduced by this change |
| `test_aiseo_schedule_task_all_frequencies_produce_canonical_cron` failed exact-string match after `(Asia/Shanghai)` suffix added | Converted to `startswith` + `assert "(Asia/Shanghai)" in ...` to assert the new contract precisely |
| `test_compute_next_run_last_run_at` failures from implicit-timezone removal | Explicit `timezone="Africa/Casablanca"` kwarg + inline docstring noting the contract change |

## Tests Written

| Test File | Tests | Coverage Area |
|---|---|---|
| `tests/cron/test_compute_next_run_timezone.py` | 7 | host TZ × job TZ matrix; today-vs-tomorrow boundary at 09:14/09:25/09:34; ISO offset presence |
| `tests/cron/test_normalize_job_record_timezone.py` | 5 | legacy job timezone fallback; env override; non-mutation contract |
| `tests/cron/test_process_job_start_event.py` | 13 | sanitize control chars / angle brackets / truncation; deterministic notice body; deliver=local silent skip; gateway failure containment; ordering contract |

## Next Steps

- [ ] Code review via `/code-review` (or `everything-claude-code:code-reviewer` agent on the diff)
- [ ] Real-machine validation in a UTC container (see plan §验收): create "每天北京时间 09:35 ..." task, confirm jobs.json has `timezone: "Asia/Shanghai"`, `schedule_display` carries `(Asia/Shanghai)` suffix, `next_run_at` carries `+08:00` offset, 09:14 creation of 09:20 task lands on today not tomorrow
- [ ] Real-machine validation of start event: trigger a cron task and confirm 飞书 receives "⏳ 开始执行..." BEFORE the "Cronjob Response: ..." finish message
- [ ] Commit via `/prp-commit` (suggest two commits per the plan: `feat(cron): job-level timezone` then `feat(cron): start event delivery before run_job`)
- [ ] Optional docs commit: update `CLAUDE.md` fork-delta section to mention `timezone` field in cron job schema
