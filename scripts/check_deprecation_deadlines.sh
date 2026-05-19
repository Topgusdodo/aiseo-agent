#!/usr/bin/env bash
# Scan the repo for `# AISEO_DEPRECATION_DEADLINE: YYYY-MM-DD` markers and
# fail CI if any deadline has passed or is malformed.
#
# Marker contract (see .plans/upstream-reuse-audit.md §P2-C):
#   * Comment-only — must appear as `# AISEO_DEPRECATION_DEADLINE: <date>`
#     in .py or .sh files. Never assigned to a Python variable.
#   * Date must be ISO `YYYY-MM-DD`. Lexicographic comparison is correct.
#   * Once today >= deadline, this script exits non-zero and CI blocks merge.
#
# Bash gotcha worth documenting (one-line summary, longer rationale in
# .plans/upstream-reuse-audit.md): `grep | while ...; exit 1; done` runs the
# loop body in a subshell, so `exit 1` only kills the subshell and the
# enclosing script keeps going. Use process substitution
# `while ... done < <(grep ...)` so the loop runs in the parent shell and the
# accumulated FAILURES counter survives.

set -euo pipefail

TODAY=$(date +%Y-%m-%d)
DATE_RE='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
FAILURES=0

while IFS= read -r line; do
    raw=$(echo "$line" | sed -E 's/.*AISEO_DEPRECATION_DEADLINE:[[:space:]]*//' | awk '{print $1}')
    if ! [[ "$raw" =~ $DATE_RE ]]; then
        echo "[FORMAT-ERROR] $line  (deadline='$raw' not matching YYYY-MM-DD)" >&2
        FAILURES=$((FAILURES + 1))
        continue
    fi
    if [[ "$raw" < "$TODAY" ]]; then
        echo "[EXPIRED] $line" >&2
        FAILURES=$((FAILURES + 1))
    fi
done < <(grep -rn "AISEO_DEPRECATION_DEADLINE:" \
    --include="*.py" --include="*.sh" \
    --exclude="check_deprecation_deadlines.sh" \
    . 2>/dev/null || true)

if [[ "$FAILURES" -gt 0 ]]; then
    echo "" >&2
    echo "Found $FAILURES expired or malformed AISEO_DEPRECATION_DEADLINE marker(s)." >&2
    echo "Action required: review .plans/upstream-push-ledger.md for each expired marker." >&2
    echo "  Option 1 (preferred): graduate upstream + delete deprecated code + delete marker." >&2
    echo "  Option 2 (delete-only): if the deprecated code is no longer used, delete it + marker." >&2
    echo "  Option 3 (defer): bump the date ONLY after team decision — do NOT bump silently to dodge CI." >&2
    exit 1
fi
