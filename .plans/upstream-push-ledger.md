# Upstream Push Ledger

Tracks AISEO-specific changes that are candidates for upstream contribution or
scheduled for removal. See `.plans/upstream-reuse-audit.md` for full context.

Column semantics (per `.plans/upstream-reuse-audit.md` P2-C):
- `Deadline` = upstream PR accept/reject due date (6 weeks / 2 releases); only "push-upstream" rows fill this.
- `Delete-by` = local code planned removal date (end of deprecation window); only "delete-local" rows fill this.
- Two columns are mutually exclusive by default (`N/A` fills the unused side); the rare exception (local deprecation + upstream push simultaneously) must be explained in `Decision-if-expired`.
- `Upstream Health`: `active` / `stale` / `closed-to-external` / `N/A` (for delete-local rows).
- `Status` allowed values: `not-started` / `spike` / `pr-open` / `pr-merged` / `rejected` / `graduated` / `degraded-to-refactor` / `deprecating`.

| Topic | Started | PR URL | Deadline | Delete-by | Owner | Status | Upstream Health | Decision-if-expired |
|-------|---------|--------|----------|-----------|-------|--------|-----------------|---------------------|
| cron-create-from-memory deprecation | 2026-05-19 | N/A | N/A | 2026-08-15 | yujian | deprecating | N/A | hard-delete subcommand; users migrate to `aiseo_schedule_task` freeform prompt |
