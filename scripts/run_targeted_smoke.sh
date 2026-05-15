#!/usr/bin/env bash
# scripts/run_targeted_smoke.sh
#
# Purpose:
#   一键跑 Phase 1 已知 4 个失败 SID + Phase 2 全部 4 个新 SID，共 8 条。
#   绕过 run_smoke.sh 的 bucket-only 选择，直接按 SID list 跑。
#
# Targeted SIDs:
#   Phase 1 失败:   S2-01, S2-05, S4-03, S4-04
#   Phase 2 新桶:   S6-01, S6-02, S6-03, S6-04
#
# Usage:
#   bash scripts/run_targeted_smoke.sh
#
# Cost / Time:
#   ~8 prompts × 30k tokens ≈ 240k tokens / ¥0.5-1 / 8-15 min wall
#
# Outputs:
#   - 每条 SID 的 .out / .log / .meta 三联体
#   - grade.py 生成的 report.md（首行 PASS/FAIL 判定）
#   - 跑完会打印 report 路径，复制给 Claude 让他分析

set -euo pipefail

# ----------------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------------

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd -P )"
REPO_ROOT="$( cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd -P )"
cd "$REPO_ROOT"

# Cost gate auto-confirm (one-shot script, user explicitly invoked it).
export AISEO_SMOKE_CONFIRMED=1

# Resolve hermes invocation: prefer existing HERMES_CMD env, else .venv hermes.
if [ -z "${HERMES_CMD:-}" ]; then
  if [ -x ".venv/bin/hermes" ]; then
    export HERMES_CMD=".venv/bin/hermes"
  elif command -v hermes &>/dev/null; then
    export HERMES_CMD="hermes"
  else
    echo "ERROR: no hermes CLI available. Install via uv or set HERMES_CMD." >&2
    exit 1
  fi
fi

PROFILE_HOME="${HERMES_HOME:-$HOME/.hermes}/profiles/aiseo"
if [ ! -d "$PROFILE_HOME" ]; then
  echo "ERROR: aiseo profile not bootstrapped at $PROFILE_HOME." >&2
  echo "       Run 'bin/aiseo' once first." >&2
  exit 1
fi

AISEO_BIN="$REPO_ROOT/bin/aiseo"
if [ ! -x "$AISEO_BIN" ]; then
  echo "ERROR: $AISEO_BIN not executable" >&2
  exit 1
fi

PROMPTS_DIR="$REPO_ROOT/tests/aiseo_llm/prompts"
RESULTS_DIR="$REPO_ROOT/tests/aiseo_llm/results"
RUN_ID="targeted-$(date +%Y-%m-%d-%H%M)"
OUT="$RESULTS_DIR/$RUN_ID"
mkdir -p "$OUT"

PROFILE_LOG="$PROFILE_HOME/logs/agent.log"
PER_PROMPT_TIMEOUT="${AISEO_SMOKE_TIMEOUT:-60}"
MAX_RETRIES="${AISEO_SMOKE_RETRIES:-2}"
SMOKE_JOBS="${AISEO_SMOKE_JOBS:-1}"
SMOKE_TOOLSETS="${AISEO_SMOKE_TOOLSETS:-web}"

# The 8 target SIDs (Phase 1 失败 + Phase 2 新桶 全部)
SIDS=(
  S2-01
  S2-05
  S4-03
  S4-04
  S6-01
  S6-02
  S6-03
  S6-04
)

echo "═════════════════════════════════════════════════════════════════"
echo "  AISEO Targeted Smoke — $RUN_ID"
echo "═════════════════════════════════════════════════════════════════"
echo "  Targets:    ${#SIDS[@]} SIDs (Phase 1 失败 4 + Phase 2 新 4)"
echo "  Profile:    $PROFILE_HOME"
echo "  HERMES_CMD: $HERMES_CMD"
echo "  Toolsets:   $SMOKE_TOOLSETS"
echo "  Output:     $OUT"
echo "  Budget:     ~¥0.5-1 / 8-15 min wall"
echo "═════════════════════════════════════════════════════════════════"
echo

# ----------------------------------------------------------------------------
# Prompt extraction by SID (from all sX.md prompt files)
# ----------------------------------------------------------------------------

extract_prompt_by_sid() {
  local target_sid="$1"
  awk -v sid="$target_sid" -F'|' '
    {
      gsub(/^ +| +$/, "", $2)
      if ($2 == sid) {
        prompt = $3
        cls    = $4
        gsub(/^ +| +$/, "", prompt)
        gsub(/^ +| +$/, "", cls)
        if (prompt ~ /^`.*`$/) {
          sub(/^`/, "", prompt)
          sub(/`$/, "", prompt)
        }
        print prompt "\t" cls
        exit
      }
    }
  ' "$PROMPTS_DIR"/s*.md
}

# ----------------------------------------------------------------------------
# Per-prompt invocation (mirrors run_smoke.sh:run_one)
# ----------------------------------------------------------------------------

run_one() {
  local sid="$1"
  local row
  row=$(extract_prompt_by_sid "$sid")
  if [ -z "$row" ]; then
    echo "[$sid] ERROR: prompt not found in $PROMPTS_DIR/s*.md" >&2
    return 1
  fi

  local prompt cls
  prompt="${row%%$'\t'*}"
  cls="${row#*$'\t'}"

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
  echo "sid=$sid"       >> "$meta_path"
  echo "class=$cls"     >> "$meta_path"
  echo "prompt=$prompt" >> "$meta_path"

  local attempt=0
  local rc=0
  while [ "$attempt" -le "$MAX_RETRIES" ]; do
    attempt=$((attempt + 1))
    : > "$run_profile_log" 2>/dev/null || true

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

    echo "[$sid] attempt $attempt returned rc=$rc, out_bytes=$(wc -c <"$out_path" | tr -d ' ')"
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
    echo "[$sid] FAIL after $attempt attempts (rc=$rc)"
  else
    echo "[$sid] ok (attempt=$attempt)"
  fi
}

# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------

for sid in "${SIDS[@]}"; do
  if [ "$SMOKE_JOBS" = "1" ]; then
    run_one "$sid"
  else
    run_one "$sid" &
  fi
done

if [ "$SMOKE_JOBS" != "1" ]; then
  echo "[targeted] waiting for ${#SIDS[@]} parallel prompt(s) ..."
  wait
fi

echo
echo "Run finished: $RUN_ID; prompts=${#SIDS[@]}; out=$OUT"
echo

# ----------------------------------------------------------------------------
# Grade
# ----------------------------------------------------------------------------

GRADE_PY="$REPO_ROOT/tests/aiseo_llm/runner/grade.py"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"

echo "Running grade.py ..."
echo
"$PYTHON_BIN" "$GRADE_PY" "$OUT" 2>&1 || echo "WARNING: grade.py exited non-zero"

# ----------------------------------------------------------------------------
# Final summary
# ----------------------------------------------------------------------------

REPORT="$OUT/report.md"
echo
echo "═════════════════════════════════════════════════════════════════"
echo "  完成 — 把下面这条路径整段复制贴给 Claude 让他分析："
echo "═════════════════════════════════════════════════════════════════"
echo
echo "  $REPORT"
echo
echo "  artifacts dir: $OUT"
echo
echo "═════════════════════════════════════════════════════════════════"
