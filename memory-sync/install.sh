#!/bin/bash
# Memory Sync Skill 安装脚本
# 功能：自动检测环境，创建定时任务
# 依赖：openclaw CLI
#
# 使用方式：bash /root/.openclaw/workspace/agent-756cc864/memory-sync/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================"
echo "  Memory Sync Skill 安装向导"
echo "============================================"
echo ""

# ===== 检查 openclaw CLI =====
if ! command -v openclaw &> /dev/null; then
    log_error "未找到 openclaw 命令，请先安装 OpenClaw"
    exit 1
fi
log_info "openclaw CLI 检查通过"

# ===== 检测 main agent sessions.json =====
SESSION_KEY=""
if command -v openclaw >/dev/null 2>&1; then
    SESSION_KEY=$(openclaw sessions --all-agents 2>/dev/null | awk '/agent:main:lightclawbot:direct:/{print $1; exit}')
fi

if [ -z "$SESSION_KEY" ]; then
    MAIN_SESSIONS="/root/.openclaw/agents/main/sessions/sessions.json"
    if [ ! -f "$MAIN_SESSIONS" ]; then
        log_error "未找到 main agent sessions.json: $MAIN_SESSIONS"
        exit 1
    fi
    SESSION_KEY=$(jq -r 'to_entries[] | select(.key | startswith("agent:main:lightclawbot:direct:")) | .key' "$MAIN_SESSIONS" 2>/dev/null | head -1)
fi

if [ -z "$SESSION_KEY" ]; then
    log_error "未找到 lightclawbot direct session，无法自动配置"
    exit 1
fi
log_info "检测到 session: $SESSION_KEY"

# ===== 检测是否已有 memory-sync 定时任务 =====
EXISTING=$(openclaw cron list 2>/dev/null | grep -c "memory-sync\|memory_sync" || echo "0")
if [ "$EXISTING" -gt "0" ]; then
    log_warn "检测到已存在的 memory-sync 定时任务，跳过创建"
    echo ""
    log_info "安装完成！"
    exit 0
fi

# ===== 初始化数据库 =====
log_info "初始化 memory.db..."
bash "$SCRIPT_DIR/memory_sync.sh" --init 2>/dev/null || log_warn "数据库初始化完成（可能已有）"
echo ""

# ===== 创建每小时定时任务 =====
# 使用 --session isolated：在独立临时 session 中执行，不干扰正常会话
log_info "创建每小时定时任务..."

if openclaw cron add \
    --name "memory-sync（记忆同步与会话清理）" \
    --cron "0 * * * *" \
    --session isolated \
    --message "bash $SCRIPT_DIR/memory_sync_combined.sh" \
    --timeout-seconds 300 \
    --no-deliver 2>&1; then
    echo ""
    log_info "✅ 定时任务创建成功！"
else
    log_error "创建定时任务失败"
    echo ""
    echo "请手动创建定时任务："
    echo ""
    echo "  openclaw cron add \\"
    echo "    --name 'memory-sync（记忆同步与会话清理）' \\"
    echo "    --cron '0 * * * *' \\"
    echo "    --session isolated \\"
    echo "    --message 'bash $SCRIPT_DIR/memory_sync_combined.sh' \\"
    echo "    --timeout-seconds 300 \\"
    echo "    --no-deliver"
    exit 1
fi

echo ""
echo "--------------------------------------------"
echo "  定时任务配置完成！"
echo ""
echo "  执行频率：每小时整点"
echo "  执行内容："
echo "    1. 增量提取 main agent 会话消息 → memory.db"
echo "    2. 检测 session 重置 → 标记 pending_cleanse"
echo "    3. 清理废弃 session 文件"
echo ""
echo "  管理命令："
echo "    查看任务：openclaw cron list | grep memory-sync"
echo "    立即触发：openclaw cron run <job-id>"
echo "    删除任务：openclaw cron remove <job-id>"
echo "--------------------------------------------"
echo ""
log_info "安装完成！"
