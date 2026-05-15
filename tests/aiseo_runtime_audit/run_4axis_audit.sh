#!/usr/bin/env bash
# tests/aiseo_runtime_audit/run_4axis_audit.sh
#
# 一键批量跑 4 维度 AISEO Agent runtime audit，输出三联体 + manifest.md。
# 跑完打印 manifest 路径，把路径发回给 Claude 分析。
#
# 4 个 axis:
#   axis1_anti_mining       — 反提示词挖掘 / 后台信息防泄漏     (10 prompts, default model)
#   axis2_model_compare     — 同一组 SEO 任务 × default + Claude (10 prompts = 5 task × 2 model)
#   axis3_claude_reports    — Claude 跑深推理 SEO 报告           (5 prompts, Claude only)
#   axis4_schedule          — day/week/month 定时任务 CRUD       (10 prompts, default, 必须串行 + 共享 HOME)
#
# 总规模: 35 prompts。 默认 JOBS=2 并发，axis4 强制串行。
# 预估: ~25-50 min wall, ~¥3-8 (Claude prompts 占大头)
#
# 用法:
#   bash tests/aiseo_runtime_audit/run_4axis_audit.sh
#
# 可调环境变量:
#   AISEO_AUDIT_JOBS         并发数 (default 2)
#   AISEO_AUDIT_TIMEOUT      每条 prompt 超时秒 (default 120 — 比 smoke 60s 大，因为 axis3 长)
#   AISEO_AUDIT_RETRIES      失败重试次数 (default 1)
#   AISEO_AUDIT_AXES         只跑指定 axis (空格分隔，如 "axis1 axis2")；默认全跑
#   AISEO_AUDIT_TOOLSETS     工具集 (default: "web,search,aiseo_schedule_task,aiseo_manage_scheduled_tasks")
#   AISEO_AUDIT_CONFIRMED=1  跳过费用确认 prompt
#   HERMES_CMD               底层 hermes 调用 (default 自动探测 .venv/bin/hermes 或 PATH)
#
# 输出:
#   tests/aiseo_runtime_audit/results/<RUN_ID>/
#       axis1_anti_mining/{SID.out, SID.log, SID.meta}
#       axis2_model_compare/...
#       axis3_claude_reports/...
#       axis4_schedule/...
#       manifest.md           ← 把这个路径发给 Claude

set -euo pipefail

# ----------------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------------

SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd -P )"
REPO_ROOT="$( cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd -P )"
cd "$REPO_ROOT"

PROMPTS_DIR="$SCRIPT_DIR/prompts"
RESULTS_DIR="$SCRIPT_DIR/results"
RUN_ID="audit-$(date +%Y-%m-%d-%H%M%S)"
OUT="$RESULTS_DIR/$RUN_ID"
mkdir -p "$OUT"

JOBS="${AISEO_AUDIT_JOBS:-2}"
PER_PROMPT_TIMEOUT="${AISEO_AUDIT_TIMEOUT:-120}"
MAX_RETRIES="${AISEO_AUDIT_RETRIES:-1}"
TOOLSETS="${AISEO_AUDIT_TOOLSETS:-web,search,aiseo_schedule_task,aiseo_manage_scheduled_tasks}"
AXES="${AISEO_AUDIT_AXES:-axis1 axis2 axis3 axis4}"

# Resolve hermes invocation
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
  echo "       Run 'bin/aiseo' once first to bootstrap." >&2
  exit 1
fi

AISEO_BIN="$REPO_ROOT/bin/aiseo"
if [ ! -x "$AISEO_BIN" ]; then
  echo "ERROR: $AISEO_BIN not executable" >&2
  exit 1
fi

PROFILE_LOG="$PROFILE_HOME/logs/agent.log"

# ----------------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------------

echo "═════════════════════════════════════════════════════════════════"
echo "  AISEO 4-Axis Runtime Audit — $RUN_ID"
echo "═════════════════════════════════════════════════════════════════"
echo "  Repo:        $REPO_ROOT"
echo "  Profile:     $PROFILE_HOME"
echo "  HERMES_CMD:  $HERMES_CMD"
echo "  Toolsets:    $TOOLSETS"
echo "  Axes:        $AXES"
echo "  Jobs:        $JOBS (axis4 forced to 1)"
echo "  Timeout:     ${PER_PROMPT_TIMEOUT}s per prompt"
echo "  Output:      $OUT"
echo
echo "  ⚠ AXIS-2 + AXIS-3 will call --model anthropic/claude-sonnet-4-6."
echo "    Ensure your aiseo profile's .env has a working ANTHROPIC_API_KEY."
echo "    Missing key → those rows will fail and grade as infra_error."
echo "═════════════════════════════════════════════════════════════════"
echo

if [ "${AISEO_AUDIT_CONFIRMED:-0}" != "1" ]; then
  echo "Estimated cost: ~¥3-8 (Claude rows occupy majority of token spend)."
  echo "Estimated wall: ~25-50 min."
  read -r -p "Proceed? [y/N] " confirm
  case "$confirm" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Aborted."; exit 1 ;;
  esac
fi

# ----------------------------------------------------------------------------
# Per-prompt runner (mirrors run_targeted_smoke.sh:run_one)
# ----------------------------------------------------------------------------

# run_one <axis> <sid> <mode> <prompt> <expected> <isolate_home: 0|1>
run_one() {
  local axis="$1"; local sid="$2"; local mode="$3"
  local prompt="$4"; local expected="$5"; local isolate_home="$6"

  local axis_dir="$OUT/$axis"
  mkdir -p "$axis_dir"

  local out_path="$axis_dir/${sid}.out"
  local log_path="$axis_dir/${sid}.log"
  local meta_path="$axis_dir/${sid}.meta"

  local run_hermes_home="${HERMES_HOME:-$HOME/.hermes}"
  local run_profile_log="$PROFILE_LOG"
  if [ "$isolate_home" = "1" ]; then
    run_hermes_home="$OUT/.homes/$sid"
    mkdir -p "$run_hermes_home/profiles"
    cp -R "$PROFILE_HOME" "$run_hermes_home/profiles/aiseo"
    mkdir -p "$run_hermes_home/profiles/aiseo/logs"
    run_profile_log="$run_hermes_home/profiles/aiseo/logs/agent.log"
  fi

  : > "$out_path"; : > "$log_path"; : > "$meta_path"
  echo "sid=$sid"             >> "$meta_path"
  echo "axis=$axis"           >> "$meta_path"
  echo "mode=$mode"           >> "$meta_path"
  echo "isolate_home=$isolate_home" >> "$meta_path"
  echo "expected=$expected"   >> "$meta_path"
  echo "prompt=$prompt"       >> "$meta_path"

  # Build aiseo args. If mode != default, prepend --model <mode>.
  local model_args=()
  if [ "$mode" != "default" ]; then
    model_args=(--model "$mode")
  fi

  local attempt=0 rc=0
  local t_start t_end
  t_start=$(date +%s)
  while [ "$attempt" -le "$MAX_RETRIES" ]; do
    attempt=$((attempt + 1))
    : > "$run_profile_log" 2>/dev/null || true

    set +e
    HERMES_HOME="$run_hermes_home" perl -e '
      use strict; use warnings;
      my $secs = shift;
      my $pid = fork();
      if ($pid == 0) { exec @ARGV; exit 127; }
      eval {
        local $SIG{ALRM} = sub { die "timeout\n"; };
        alarm $secs;
        waitpid($pid, 0);
        alarm 0;
        exit($? >> 8);
      };
      if ($@ =~ /timeout/) {
        kill "TERM", $pid; sleep 1; kill "KILL", $pid; exit 124;
      }
    ' "$PER_PROMPT_TIMEOUT" \
      "$AISEO_BIN" chat --toolsets "$TOOLSETS" ${model_args[@]+"${model_args[@]}"} -q "$prompt" --quiet \
      >"$out_path" 2>>"$log_path"
    rc=$?
    set -e

    if [ -s "$run_profile_log" ]; then
      cat "$run_profile_log" >> "$log_path" 2>/dev/null || true
    fi

    if [ "$rc" -eq 0 ] && [ -s "$out_path" ]; then
      break
    fi
    [ "$attempt" -gt "$MAX_RETRIES" ] && break
    sleep 2
  done
  t_end=$(date +%s)

  echo "rc=$rc"                                   >> "$meta_path"
  echo "wall_s=$(( t_end - t_start ))"            >> "$meta_path"
  echo "attempts=$attempt"                        >> "$meta_path"
  echo "out_bytes=$(wc -c <"$out_path" | tr -d ' ')" >> "$meta_path"
  echo "out_lines=$(wc -l <"$out_path" | tr -d ' ')" >> "$meta_path"

  printf "  [%s/%s] rc=%s wall=%ss bytes=%s\n" \
    "$axis" "$sid" "$rc" "$(( t_end - t_start ))" \
    "$(wc -c <"$out_path" | tr -d ' ')"
}

# ----------------------------------------------------------------------------
# Axis runner
# ----------------------------------------------------------------------------

# Parse a TSV file (skipping # comments and blank lines) and emit
# "SID<TAB>MODE<TAB>PROMPT<TAB>EXPECTED" lines.
emit_tsv_rows() {
  local file="$1"
  awk -F'\t' '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/  { next }
    NF >= 4 { print $1 "\t" $2 "\t" $3 "\t" $4 }
  ' "$file"
}

# Drain a list of PIDs (bash 3.2 compatible — no `wait -n`).
# Args: PIDs to wait on. Errors are ignored (we read rc from .meta).
drain_pids() {
  local p
  for p in "$@"; do
    wait "$p" 2>/dev/null || true
  done
}

# run_axis_parallel <axis_name> <tsv_path>
# Runs all prompts in batches of $JOBS (barrier mode), with HOME isolation.
# Bash 3.2 compatible: no `wait -n`; barrier waits for the whole batch before
# starting the next. Worst-case loss per batch = max(wall) - min(wall) of that
# batch, which is acceptable for our 25-50 min run.
run_axis_parallel() {
  local axis="$1"; local tsv="$2"
  echo
  echo "── $axis  (parallel JOBS=$JOBS, barrier mode) ──"

  local pids=()
  while IFS=$'\t' read -r sid mode prompt expected; do
    [ -z "$sid" ] && continue
    run_one "$axis" "$sid" "$mode" "$prompt" "$expected" 1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$JOBS" ]; then
      drain_pids "${pids[@]}"
      pids=()
    fi
  done < <(emit_tsv_rows "$tsv")
  if [ "${#pids[@]}" -gt 0 ]; then
    drain_pids "${pids[@]}"
  fi
}

# run_axis_sequential <axis_name> <tsv_path>
# Runs all prompts strictly sequential, sharing the main HERMES_HOME.
run_axis_sequential() {
  local axis="$1"; local tsv="$2"
  echo
  echo "── $axis  (SERIAL — shared HOME for state persistence) ──"

  while IFS=$'\t' read -r sid mode prompt expected; do
    [ -z "$sid" ] && continue
    run_one "$axis" "$sid" "$mode" "$prompt" "$expected" 0
  done < <(emit_tsv_rows "$tsv")
}

# ----------------------------------------------------------------------------
# Dispatch by axis
# ----------------------------------------------------------------------------

declare -a TSV_axis1=("$PROMPTS_DIR/axis1_anti_mining.tsv")
declare -a TSV_axis2=("$PROMPTS_DIR/axis2_model_compare.tsv")
declare -a TSV_axis3=("$PROMPTS_DIR/axis3_claude_reports.tsv")
declare -a TSV_axis4=("$PROMPTS_DIR/axis4_schedule.tsv")

OVERALL_START=$(date +%s)

for axis in $AXES; do
  case "$axis" in
    axis1) run_axis_parallel   "axis1_anti_mining"    "${TSV_axis1[0]}" ;;
    axis2) run_axis_parallel   "axis2_model_compare"  "${TSV_axis2[0]}" ;;
    axis3) run_axis_parallel   "axis3_claude_reports" "${TSV_axis3[0]}" ;;
    axis4) run_axis_sequential "axis4_schedule"       "${TSV_axis4[0]}" ;;
    *) echo "WARN: unknown axis '$axis' — skipped" >&2 ;;
  esac
done

OVERALL_END=$(date +%s)
OVERALL_WALL=$(( OVERALL_END - OVERALL_START ))

# ----------------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------------

MANIFEST="$OUT/manifest.md"

axis_stats() {
  local axis_dir="$1"
  if [ ! -d "$axis_dir" ]; then
    echo "0 0 0 0"
    return
  fi
  local total ok timeouts empty
  total=$(ls "$axis_dir"/*.meta 2>/dev/null | wc -l | tr -d ' ')
  ok=$(grep -l "^rc=0$" "$axis_dir"/*.meta 2>/dev/null | wc -l | tr -d ' ')
  timeouts=$(grep -l "^rc=124$" "$axis_dir"/*.meta 2>/dev/null | wc -l | tr -d ' ')
  empty=$(awk -F= '/^out_bytes=/ { if ($2 == 0) c++ } END { print c+0 }' "$axis_dir"/*.meta 2>/dev/null || echo 0)
  echo "$total $ok $timeouts $empty"
}

{
  echo "# AISEO 4-Axis Runtime Audit — $RUN_ID"
  echo
  echo "- **Run timestamp**: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "- **Wall time**:     ${OVERALL_WALL}s"
  echo "- **Jobs**:          $JOBS (axis4 forced to 1)"
  echo "- **Timeout**:       ${PER_PROMPT_TIMEOUT}s per prompt"
  echo "- **Toolsets**:      $TOOLSETS"
  echo "- **Axes run**:      $AXES"
  echo "- **Output root**:   $OUT"
  echo
  echo "## Per-axis summary"
  echo
  echo "| Axis | Total | rc=0 | timeouts | empty out |"
  echo "|---|---|---|---|---|"
  for a in axis1_anti_mining axis2_model_compare axis3_claude_reports axis4_schedule; do
    read -r t ok to empty < <(axis_stats "$OUT/$a")
    echo "| $a | $t | $ok | $to | $empty |"
  done
  echo
  echo "## Files produced"
  echo
  echo "Each prompt produces 3 sibling files:"
  echo
  echo "- \`<axis>/<SID>.out\`  — stdout (the actual model reply)"
  echo "- \`<axis>/<SID>.log\`  — stderr + agent.log (tool dispatch, errors)"
  echo "- \`<axis>/<SID>.meta\` — sid, mode, expected, rc, wall_s, attempts, out_bytes, out_lines"
  echo
  echo "## What to send back to Claude"
  echo
  echo "After this run, send this single path to Claude:"
  echo
  echo '```'
  echo "$OUT"
  echo '```'
  echo
  echo "Claude will then:"
  echo
  echo "1. Read all 4 axes' .meta + .out + .log triplets"
  echo "2. Per-axis grade against the EXPECTED signals in the TSV"
  echo "3. Diff axis2 default vs claude (length / structure / leak / fabrication)"
  echo "4. Output a problem-list grouped by severity (CRITICAL / HIGH / MEDIUM / LOW)"
} > "$MANIFEST"

echo
echo "═════════════════════════════════════════════════════════════════"
echo "  Audit complete in ${OVERALL_WALL}s."
echo "  Manifest: $MANIFEST"
echo
echo "  → 把下面这条路径发回给 Claude 分析："
echo
echo "      $OUT"
echo
echo "═════════════════════════════════════════════════════════════════"
