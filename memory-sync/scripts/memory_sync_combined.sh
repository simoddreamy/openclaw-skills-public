#!/bin/bash
# Memory Sync + Session Cleanup Combined Script v6
# 功能：
#   1. 先执行记忆同步（提取 Agent 会话到数据库）
#   2. 再执行会话清理（运行 cleanup Python 脚本）
# 位置：/root/.openclaw/workspace/agent-756cc864/memory-sync/scripts/memory_sync_combined.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MEMORY_SYNC_SCRIPT="$SCRIPT_DIR/memory_sync.py"
CLEANUP_SCRIPT="/root/.openclaw/workspace/agent-756cc864/scripts/cleanup_cron_sessions_v5.py"
STATE_FILE="/root/.openclaw/workspace/agent-756cc864/scripts/fixed_sessions/cleanup/state.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
log_step() { echo -e "${YELLOW}[STEP]${NC} $1" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

echo "=============================================="
echo "  合并任务开始: 记忆同步 + 会话清理"
echo "=============================================="
echo ""

# ===== 步骤 1: 记忆同步（使用 Python 版本）=====
log_step ">>> 步骤 1/2: 执行记忆同步任务"
echo ""

python3 "$SCRIPT_DIR/memory_sync.py"
memory_sync_exit=$?

if [ $memory_sync_exit -ne 0 ]; then
    log_error "记忆同步任务失败，退出码: $memory_sync_exit"
fi

echo ""
echo ""

# ===== 步骤 2: 会话清理 =====
log_step ">>> 步骤 2/2: 执行会话清理任务"
echo ""

if [ ! -f "$CLEANUP_SCRIPT" ]; then
    log_error "清理脚本不存在: $CLEANUP_SCRIPT"
    exit 1
fi

# 运行清理脚本
cd /root/.openclaw/workspace/agent-756cc864
python3 "$CLEANUP_SCRIPT" --max-cleanup 50
cleanup_exit=$?

if [ $cleanup_exit -ne 0 ]; then
    log_error "会话清理任务失败，退出码: $cleanup_exit"
fi

echo ""
echo "=============================================="
echo "  合并任务完成"
echo "=============================================="
echo ""
echo "各步骤退出码: 记忆同步=$memory_sync_exit, 会话清理=$cleanup_exit"