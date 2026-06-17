#!/usr/bin/env bash
# tests/aiseo_llm/runner/run_smoke.sh
#
# Purpose:
#   LLM-end smoke harness for AISEO Agent (Phase 1.5 + Phase 2 RC).
#   Runs 32 prompts (6 buckets: S1-S6) against bin/aiseo and
#   captures per-prompt .out (stdout) and .log (agent.log tail) for
#   downstream grading by grade.py.
#
# Usage:
#   AISEO_SMOKE_CONFIRMED=1 bash tests/aiseo_llm/runner/run_smoke.sh [bucket]
#     bucket = s1 | s2 | s3 | s4 | s5 | s6 | all   (default: all)
#
# Budget (full all-bucket run):
#   ~200k tokens / ¥1-3 (deepseek-v4-pro tier) / ~30 min wall time.
#   See README.md for per-bucket breakdown and stop criteria.
#
# Safety:
#   - Requires hermes CLI on PATH (asserted below)
#   - Requires aiseo profile bootstrapped (~/.hermes/profiles/aiseo)
#   - Requires AISEO_SMOKE_CONFIRMED=1 to actually run (cost-bearing)
#   - Each prompt grabs a fresh tail of the per-profile agent.log
#
# Operational notes:
#   - The harness uses the user's real aiseo profile so the configured
#     provider credentials are reused. Memory pollution across runs is
#     accepted; per-prompt isolation is achieved by truncating the
#     profile's agent.log between invocations.
#   - Multi-turn cases (S5-03, S5-04) are flagged "requires_multi_turn"
#     and skipped automatically; they must be verified manually in an
#     interactive session — see README.md.

set -euo pipefail

# ----------------------------------------------------------------------------
# Pre-flight checks
# ----------------------------------------------------------------------------

# Resolve hermes CLI invocation: prefer user-provided HERMES_CMD, else
# detect `hermes` on PATH, else fallback to `uv run hermes` (this repo is
# a Hermes fork; hermes is typically invoked via uv when not globally
# installed). Pass HERMES_CMD through to bin/aiseo via env.
if [ -z "${HERMES_CMD:-}" ]; then
  if command -v hermes &>/dev/null; then
    export HERMES_CMD="hermes"
  elif command -v uv &>/dev/null && (cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && uv run hermes --version &>/dev/null); then
    export HERMES_CMD="uv run hermes"
  else
    echo "ERROR: no hermes CLI available." >&2
    echo "       Either install hermes globally, or run from a uv project." >&2
    echo "       Or set: export HERMES_CMD='<your hermes invocation>'" >&2
    exit 1
  fi
fi
echo "[smoke] using HERMES_CMD=$HERMES_CMD" >&2

PROFILE_HOME="${HERMES_HOME:-$HOME/.hermes}/profiles/aiseo"
if [ ! -d "$PROFILE_HOME" ]; then
  echo "ERROR: aiseo profile not bootstrapped." >&2
  echo "       Run 'bin/aiseo' once first to copy seeds/aiseo-profile/." >&2
  exit 1
fi

# Cost confirmation gate. Without AISEO_SMOKE_CONFIRMED=1 we refuse to run,
# even when the user has CLI access — this prevents accidental triggering
# from typos / muscle memory / agent loops.
if [ "${AISEO_SMOKE_CONFIRMED:-0}" != "1" ]; then
  cat >&2 <<'EOF'
This will make up to ~32 prompt attempts and may cost ¥1-3 / 30 min wall time.
Set AISEO_SMOKE_CONFIRMED=1 to confirm and run:

  AISEO_SMOKE_CONFIRMED=1 bash tests/aiseo_llm/runner/run_smoke.sh [bucket]

See tests/aiseo_llm/README.md for budget breakdown and stop criteria.
EOF
  exit 1
fi

# ----------------------------------------------------------------------------
# Paths + run-id
# ----------------------------------------------------------------------------

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd -P )"
HARNESS_ROOT="$( cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd -P )"
REPO_ROOT="$( cd -- "$HARNESS_ROOT/../.." >/dev/null 2>&1 && pwd -P )"
PROMPTS_DIR="$HARNESS_ROOT/prompts"
RESULTS_DIR="$HARNESS_ROOT/results"

RUN_ID="$(date +%Y-%m-%d-%H%M)"
OUT="$RESULTS_DIR/$RUN_ID"
mkdir -p "$OUT"

# Resolve bin/aiseo (override via AISEO_BIN for tests that mock the CLI).
AISEO_BIN="${AISEO_BIN:-$REPO_ROOT/bin/aiseo}"
if [ ! -x "$AISEO_BIN" ]; then
  echo "ERROR: $AISEO_BIN not executable" >&2
  exit 1
fi

PROFILE_LOG="$PROFILE_HOME/logs/agent.log"
PER_PROMPT_TIMEOUT="${AISEO_SMOKE_TIMEOUT:-60}"
MAX_RETRIES="${AISEO_SMOKE_RETRIES:-2}"
SMOKE_JOBS="${AISEO_SMOKE_JOBS:-1}"
SMOKE_TOOLSETS="${AISEO_SMOKE_TOOLSETS:-web}"

# ----------------------------------------------------------------------------
# Bucket selection
# ----------------------------------------------------------------------------

BUCKET="${1:-all}"

case "$BUCKET" in
  all)
    PROMPT_FILES=( "$PROMPTS_DIR"/s*.md )
    ;;
  s1|s2|s3|s4|s5|s6)
    PROMPT_FILES=( "$PROMPTS_DIR/${BUCKET}_"*.md )
    ;;
  *)
    echo "ERROR: unknown bucket '$BUCKET' (expected: s1|s2|s3|s4|s5|s6|all)" >&2
    exit 1
    ;;
esac

if [ "${#PROMPT_FILES[@]}" -eq 0 ] || [ ! -f "${PROMPT_FILES[0]}" ]; then
  echo "ERROR: no prompt files matched for bucket '$BUCKET' under $PROMPTS_DIR" >&2
  exit 1
fi

echo "Run started: $RUN_ID; bucket=$BUCKET; out=$OUT"
echo "Profile:     $PROFILE_HOME"
echo "Prompt files: ${PROMPT_FILES[*]}"
echo "Toolsets:    $SMOKE_TOOLSETS"

# ----------------------------------------------------------------------------
# Prompt extraction
# ----------------------------------------------------------------------------
#
# Each prompt file is a markdown table whose data rows look like:
#   | S1-01 | `今天北京天气怎么样？` | A 拒 | ≥1 LLM call ... |
#
# Multi-turn rows (S5-03/04) start with "链式：先 ..." rather than a single
# backtick-wrapped string. We surface them in the extracted list so the loop
# can mark them as multi-turn-skip without executing them.
#
# Output of extract_prompts(): one TSV line per data row, fields:
#     sid <TAB> prompt <TAB> class <TAB> assertion
# (the prompt field still has its surrounding backticks stripped where
# present; chained rows keep their full markdown body so they can be
# recognised by run_one().)

extract_prompts() {
  local pf="$1"
  # Skip header (| ID |) and divider rows (|---|), keep data rows that begin
  # with `| Sx-NN |` where x is a bucket number and NN is two digits.
  awk -F'|' '
    /^\| *S[0-9]+-[0-9]{2} *\|/ {
      sid = $2
      prompt = $3
      cls = $4
      assertion = $5
      # Trim leading/trailing whitespace.
      gsub(/^ +| +$/, "", sid)
      gsub(/^ +| +$/, "", prompt)
      gsub(/^ +| +$/, "", cls)
      gsub(/^ +| +$/, "", assertion)
      # Strip surrounding backticks when the entire prompt is one code span.
      if (prompt ~ /^`.*`$/) {
        sub(/^`/, "", prompt)
        sub(/`$/, "", prompt)
      }
      print sid "\t" prompt "\t" cls "\t" assertion
    }
  ' "$pf"
}

# ----------------------------------------------------------------------------
# Per-prompt invocation
# ----------------------------------------------------------------------------
#
# run_one(): runs a single prompt under the user's aiseo profile.
#   - truncates agent.log so the captured .log slice is per-prompt
#   - invokes bin/aiseo -q "<prompt>" --quiet under a perl-alarm timeout
#   - copies the agent.log tail to $OUT/<sid>.log
#   - retries up to MAX_RETRIES times on non-zero exit / empty output
#   - emits flaky / retry markers into the .meta file so grade.py can
#     surface them in the report.

run_one() {
  local sid="$1"
  local prompt="$2"
  local cls="$3"
  local out_path="$OUT/${sid}.out"
  local log_path="$OUT/${sid}.log"
  local meta_path="$OUT/${sid}.meta"
  local session_ids=""
  local run_hermes_home="${HERMES_HOME:-$HOME/.hermes}"
  local run_profile_log="$PROFILE_LOG"

  if [ "$SMOKE_JOBS" != "1" ]; then
    run_hermes_home="$OUT/.homes/$sid"
    mkdir -p "$run_hermes_home/profiles"
    cp -R "$PROFILE_HOME" "$run_hermes_home/profiles/aiseo"
    mkdir -p "$run_hermes_home/profiles/aiseo/logs"
    run_profile_log="$run_hermes_home/profiles/aiseo/logs/agent.log"
  fi

  : > "$out_path"
  : > "$log_path"
  : > "$meta_path"
  echo "sid=$sid"     >> "$meta_path"
  echo "class=$cls"   >> "$meta_path"
  echo "prompt=$prompt" >> "$meta_path"

  # Multi-turn rows are not yet wired through this harness. Mark and skip.
  case "$prompt" in
    链式*|链式：*|链式:*)
      echo "requires_multi_turn=true" >> "$meta_path"
      echo "skipped=true" >> "$meta_path"
      echo "[${sid}] SKIP (requires_multi_turn — see README)"
      return 0
      ;;
  esac

  local attempt=0
  local rc=0
  while [ "$attempt" -le "$MAX_RETRIES" ]; do
    attempt=$((attempt + 1))

    # Fresh agent.log slice per attempt.
    : > "$run_profile_log" 2>/dev/null || true

    # perl alarm provides a portable timeout on macOS (no GNU timeout).
    set +e
    HERMES_HOME="$run_hermes_home" perl -e '
      use strict;
      use warnings;
      my $secs = shift;
      my $pid = fork();
      if ($pid == 0) {
        exec @ARGV;
        exit 127;
      }
      eval {
        local $SIG{ALRM} = sub { die "timeout\n"; };
        alarm $secs;
        waitpid($pid, 0);
        alarm 0;
        exit($? >> 8);
      };
      if ($@ =~ /timeout/) {
        kill "TERM", $pid;
        sleep 1;
        kill "KILL", $pid;
        exit 124;
      }
    ' "$PER_PROMPT_TIMEOUT" \
      "$AISEO_BIN" chat --toolsets "$SMOKE_TOOLSETS" -q "$prompt" --quiet \
      >"$out_path" 2>>"$log_path"
    rc=$?
    set -e

    # Always pull whatever agent.log was produced.
    if [ -s "$run_profile_log" ]; then
      cat "$run_profile_log" >> "$log_path"
    fi

    if [ -s "$run_profile_log" ]; then
      local attempt_session
      attempt_session="$(
        sed -n 's/.*conversation turn: session=\([^ ]*\).*/\1/p' "$run_profile_log" | head -n 1
      )"
      if [ -n "$attempt_session" ]; then
        case ",$session_ids," in
          *",$attempt_session,"*) ;;
          *)
            if [ -z "$session_ids" ]; then
              session_ids="$attempt_session"
            else
              session_ids="$session_ids,$attempt_session"
            fi
            ;;
        esac
      fi
    fi

    if [ "$rc" -eq 0 ] && [ -s "$out_path" ]; then
      break
    fi

    echo "[${sid}] attempt ${attempt} returned rc=${rc}, out_bytes=$(wc -c <"$out_path" | tr -d ' ')"
    if [ "$attempt" -le "$MAX_RETRIES" ]; then
      sleep 1
    fi
  done

  echo "attempts=$attempt" >> "$meta_path"
  echo "final_rc=$rc"      >> "$meta_path"
  echo "session_id=$session_ids" >> "$meta_path"
  if [ "$attempt" -gt 1 ] && [ "$rc" -eq 0 ]; then
    echo "flaky=true" >> "$meta_path"
  fi
  if [ "$rc" -ne 0 ]; then
    echo "[${sid}] FAIL after $attempt attempts (rc=$rc)"
  else
    echo "[${sid}] ok (attempt=$attempt)"
  fi
}

# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------

PROMPT_COUNT=0
for pf in "${PROMPT_FILES[@]}"; do
  while IFS=$'\t' read -r SID PROMPT_TEXT CLS ASSERTION; do
    [ -n "$SID" ] || continue
    PROMPT_COUNT=$((PROMPT_COUNT + 1))
    if [ "$SMOKE_JOBS" = "1" ]; then
      run_one "$SID" "$PROMPT_TEXT" "$CLS"
    else
      run_one "$SID" "$PROMPT_TEXT" "$CLS" &
    fi
  done < <(extract_prompts "$pf")
done

if [ "$SMOKE_JOBS" != "1" ]; then
  echo "[smoke] waiting for $PROMPT_COUNT parallel prompt(s) ..."
  wait
fi

echo ""
echo "Run finished: $RUN_ID  (prompts=$PROMPT_COUNT, out=$OUT)"

# ----------------------------------------------------------------------------
# Auto-grade
# ----------------------------------------------------------------------------

if command -v python3 &>/dev/null; then
  echo ""
  echo "Running grade.py ..."
  python3 "$SCRIPT_DIR/grade.py" "$OUT" || {
    echo "WARNING: grade.py exited non-zero" >&2
  }
else
  echo "WARNING: python3 not on PATH — skipping auto-grade" >&2
fi
