#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# AISEO Agent Gateway 重启脚本
# ============================================================
# 用途：重启 AISEO profile 的 Gateway，并验证 Feishu 连接
# 用法：bash /usr/local/lib/hermes-agent/scripts/restart.sh
#
# 跟原版的关键区别：
#   - 用 `aiseo gateway restart` 替代 `hermes gateway stop`
#     （只动 aiseo profile，不会误杀 default profile 的 gateway）
#   - 删掉 `pgrep -f "hermes.*gateway"` 那段兜底强杀
#     （那个正则会同时匹配所有 profile，可能误杀 aiseo 自己）
#   - 加 Feishu 连接健康检查（等到 Feishu 连接信号才算成功）
#   - 返回明确的退出码（0=成功 / 1=配置错 / 2=启动了但 Feishu 没连）
#
# 注意：
#   - 必须在外部终端运行，不能在 aiseo agent session 内执行
#     （会被自身重启 kill 掉）
#   - 不影响 default profile 或其他 profile 的 gateway
# ============================================================

AISEO_BIN="${AISEO_BIN:-/usr/local/bin/aiseo}"
LOG_PATH="${HOME:-/root}/.hermes/profiles/aiseo/logs/gateway.log"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-15}"

# === 前置检查 ===
if [ ! -x "$AISEO_BIN" ]; then
    echo "ERROR: aiseo binary not found: $AISEO_BIN" >&2
    echo "       Set AISEO_BIN env var to the correct path, or run pip install -e ." >&2
    exit 1
fi

# === 重启 ===
SERVICE_NAME="${AISEO_GATEWAY_SERVICE:-hermes-gateway-aiseo.service}"

echo ">>> Restarting AISEO Gateway..."
if systemctl --user list-unit-files "$SERVICE_NAME" >/dev/null 2>&1; then
    echo "    systemd user service: $SERVICE_NAME"
    systemctl --user restart "$SERVICE_NAME"
else
    echo "    wrapper: $AISEO_BIN"
    "$AISEO_BIN" gateway restart
fi

# === 健康检查：等 Feishu 连接信号 ===
echo
echo ">>> Waiting for Feishu to connect (max ${HEALTH_TIMEOUT}s)..."

deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ -f "$LOG_PATH" ] && tail -80 "$LOG_PATH" 2>/dev/null | grep -qiE "feishu.*connected|connecting to feishu"; then
        echo "OK: Gateway up, Feishu signaled in log"
        echo
        echo ">>> aiseo gateway status:"
        "$AISEO_BIN" gateway status 2>&1 | head -5
        exit 0
    fi
    sleep 1
done

# === 超时 — 启动了但 Feishu 没在窗口内连上 ===
echo "WARN: ${HEALTH_TIMEOUT}s elapsed without Feishu connection signal"
echo "      (but the gateway may already be functional; check the log below)"
echo
echo "  Possible causes:"
echo "    1. Feishu credentials missing (check FEISHU_APP_ID / FEISHU_APP_SECRET in .env)"
echo "    2. lark-oapi not installed (venv/bin/pip install lark-oapi)"
echo "    3. Another gateway is competing for the same FEISHU_APP_ID"
echo
echo ">>> Recent Feishu log entries:"
echo "----------------------------------------"
tail -80 "$LOG_PATH" 2>/dev/null | grep -iE "feishu" | tail -10 || echo "(none)"
echo "----------------------------------------"
exit 2
