#!/bin/bash
# Memory Sync Script v7
# 功能：增量提取 Agent 会话消息，检测重置并触发 AI 记忆清洗
# 变更：
#   - v7: 增加 main agent 处理，仅处理 direct 类型的会话

set -e

# ===== 配置 =====
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/memory_schema.sql"
AGENTS_DIR="/root/.openclaw/agents"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }

# ===== 初始化数据库 =====
init_db() {
    local db_path="$1"
    if [ ! -f "$db_path" ]; then
        log_info "初始化数据库: $db_path"
        sqlite3 "$db_path" < "$SCHEMA_FILE"
    fi
}

# ===== 获取 Agent 目录的会话信息 =====
get_sessions_info() {
    local agent_dir="$1"
    local sessions_file="$agent_dir/sessions/sessions.json"
    
    if [ ! -f "$sessions_file" ]; then
        echo ""
        return
    fi
    
    # 输出所有 session 的 sessionId 和 chatType
    jq -r 'to_entries[] | "\(.key)|\(.value.sessionId)|\(.value.chatType // "unknown")"' "$sessions_file" 2>/dev/null
}

# ===== 获取当前活跃 session ID（用于判断重置）=====
get_active_session_id() {
    local agent_dir="$1"
    local agent_id=$(basename "$agent_dir")
    
    # 最高优先级：直接从 openclaw sessions --all-agents 读取最新 direct session
    if command -v openclaw &> /dev/null; then
        local sessions_out
        sessions_out=$(openclaw sessions --all-agents 2>/dev/null || true)
        if [ -n "$sessions_out" ]; then
            # 取第一条匹配（输出通常按最新优先），避免 tail 选到旧记录
            local matched
            matched=$(printf '%s
' "$sessions_out" | awk -v agent="$agent_id" '
                $1 == agent && $2 == "direct" {
                    if ($NF ~ /^id:/) {
                        sub(/^id:/, "", $NF)
                        print $NF
                    } else if ($NF ~ /^system$/ && $(NF-1) ~ /^id:/) {
                        sub(/^id:/, "", $(NF-1))
                        print $(NF-1)
                    }
                    exit
                }
            ')
            if [ -n "$matched" ]; then
                echo "$matched"
                return
            fi
        fi
    fi
    
    # 兜底：从 sessions.json 中按前缀选择 direct/lightclawbot
    local sessions_file="$agent_dir/sessions/sessions.json"
    if [ ! -f "$sessions_file" ]; then
        echo ""
        return
    fi
    
    if command -v jq &> /dev/null; then
        if [ "$agent_id" = "main" ]; then
            jq -r '
                to_entries[]
                | select(.key | startswith("agent:main:lightclawbot:direct:"))
                | .value.sessionId
            ' "$sessions_file" 2>/dev/null | head -1
        else
            jq -r --arg aid "$agent_id" '
                to_entries[]
                | select(.key | startswith("agent:" + $aid + ":direct:"))
                | .value.sessionId
            ' "$sessions_file" 2>/dev/null | head -1
        fi
    fi
}

# ===== 获取 session 文件路径 =====
get_session_file_path() {
    local agent_dir="$1"
    local session_id="$2"
    echo "$agent_dir/sessions/${session_id}.jsonl"
}

# ===== 检测会话重置 =====
detect_session_reset() {
    local agent_id="$1"
    local current_session_id="$2"
    local db_path="$AGENTS_DIR/$agent_id/memory.db"
    
    local last_session_id=$(sqlite3 "$db_path" "SELECT session_id FROM extraction_state WHERE agent_id='$agent_id';" 2>/dev/null)
    
    if [ -z "$last_session_id" ]; then
        echo "first_run"
        return
    fi
    
    if [ "$current_session_id" != "$last_session_id" ]; then
        echo "reset"
    else
        echo "normal"
    fi
}

# ===== 解析 JSONL 并提取消息（用 jq）=====
parse_jsonl_messages() {
    local jsonl_file="$1"
    local from_line="$2"
    
    if [ ! -f "$jsonl_file" ]; then
        echo ""
        return
    fi
    
    local total_lines=$(wc -l < "$jsonl_file")
    local new_lines=$((total_lines - from_line))
    
    if [ "$new_lines" -le 0 ]; then
        echo ""
        return
    fi
    
    tail -n +$((from_line + 1)) "$jsonl_file" | jq -r 'select(.type=="message") | .message.role + "|" + (.message.content | if type=="array" then map(select(.type=="text")) | map(.text) | join("") elif type=="string" then . else empty end)' 2>/dev/null
}

# ===== 提取消息并存储到数据库 =====
extract_messages() {
    local session_file="$1"
    local from_line="$2"
    local agent_id="$3"
    local session_id="$4"
    local db_path="$AGENTS_DIR/$agent_id/memory.db"
    
    log_info "提取消息: 从第 $((from_line + 1)) 行开始"
    
    local messages=$(parse_jsonl_messages "$session_file" "$from_line")
    local count=0
    
    while IFS='|' read -r role content; do
        if [ -z "$role" ] || [ -z "$content" ]; then
            continue
        fi
        
        content=$(printf '%s' "$content" | sed "s/'/''/g")
        local timestamp=$(date -Iseconds | sed "s/+00:00/Z/")
        
        sqlite3 "$db_path" "INSERT INTO messages (agent_id, session_id, created_at, role, content) VALUES ('$agent_id', '$session_id', '$timestamp', '$role', '$content');"
        count=$((count + 1))
    done <<< "$messages"
    
    echo "$count"
}

# ===== 处理普通 Agent（agent-*）=====
process_normal_agent() {
    local agent_dir="$1"
    local agent_id=$(basename "$agent_dir")
    
    log_info "=== 处理 Agent: $agent_id ==="
    
    local current_session_id=$(get_active_session_id "$agent_dir")
    if [ -z "$current_session_id" ]; then
        log_warn "无法获取 session_id，跳过"
        return
    fi
    log_info "当前 session: $current_session_id"
    
    local db_path="$agent_dir/memory.db"
    init_db "$db_path"
    
    local status=$(detect_session_reset "$agent_id" "$current_session_id")
    log_info "状态: $status"
    
    case "$status" in
        "first_run"|"reset")
            if [ "$status" == "reset" ]; then
                log_warn "检测到会话重置: $agent_id"
            else
                log_info "首次运行: $agent_id"
            fi
            
            local session_file=$(get_session_file_path "$agent_dir" "$current_session_id")
            if [ -f "$session_file" ]; then
                local count=$(extract_messages "$session_file" 0 "$agent_id" "$current_session_id")
                now=$(date -Iseconds | sed "s/+00:00/Z/" | sed "s/'/''/g")
                sqlite3 "$db_path" "INSERT OR REPLACE INTO extraction_state (agent_id, session_id, last_line_processed, last_extracted_at, pending_cleanse) VALUES ('$agent_id', '$current_session_id', 0, '$now', 1);"
                log_info "已设置 pending_cleanse=1，新增 $count 条消息"
            fi
            ;;
        "normal")
            local state=$(sqlite3 "$db_path" "SELECT session_id, last_line_processed FROM extraction_state WHERE agent_id='$agent_id';" 2>/dev/null)
            [ -z "$state" ] && log_warn "无状态记录，跳过" && return
            
            local last_session_id=$(echo "$state" | cut -d'|' -f1)
            local last_line=$(echo "$state" | cut -d'|' -f2)
            
            local session_file=$(get_session_file_path "$agent_dir" "$last_session_id")
            if [ ! -f "$session_file" ]; then
                log_warn "会话文件不存在: $session_file"
                return
            fi
            
            local current_lines=$(wc -l < "$session_file")
            if [ "$current_lines" -gt "$last_line" ]; then
                log_info "增量提取: 从第 $((last_line + 1)) 行开始"
                local count=$(extract_messages "$session_file" "$last_line" "$agent_id" "$last_session_id")
                now=$(date -Iseconds | sed "s/+00:00/Z/" | sed "s/'/''/g")
                sqlite3 "$db_path" "UPDATE extraction_state SET last_line_processed=$current_lines, last_extracted_at='$now' WHERE agent_id='$agent_id';"
                sqlite3 "$db_path" "UPDATE extraction_state SET pending_cleanse=1 WHERE agent_id='$agent_id';"
                log_info "新增 $count 条消息，已设置 pending_cleanse=1"
            else
                log_info "无新增消息"
            fi
            ;;
    esac
}

# ===== 处理 main Agent =====
# 只处理两个指定的 session：
#   1. agent:main:main（基础主会话）
#   2. agent:main:lightclawbot:direct:100018290076（lightclawbot 私聊）
process_main_agent() {
    local agent_dir="$1"
    local agent_id="main"
    
    log_info "=== 处理 main Agent ==="
    
    local sessions_file="$agent_dir/sessions/sessions.json"
    [ ! -f "$sessions_file" ] && log_warn "sessions.json 不存在，跳过" && return
    
    local db_path="$agent_dir/memory.db"
    init_db "$db_path"
    
    # 硬编码 key
    local -a STATIC_KEYS=(
        "agent:main:main"
        "agent:main:lightclawbot:direct:100018290076"
    )

    # 通配符匹配：所有 agent:main:openclaw-weixin:* 开头的 key
    local -a WEIXIN_KEYS=($(jq -r 'to_entries[] | select(.key | startswith("agent:main:openclaw-weixin:")) | .key' "$sessions_file" 2>/dev/null))

    # 合并
    local -a ALL_KEYS=("${STATIC_KEYS[@]}" "${WEIXIN_KEYS[@]}")
    
    local total_count=0
    
    for key in "${ALL_KEYS[@]}"; do
        local session_id=$(jq -r ".[\"$key\"].sessionId // empty" "$sessions_file" 2>/dev/null)
        [ -z "$session_id" ] && log_warn "session 不存在: $key" && continue
        
        log_info "处理会话: $key → $session_id"
        
        local session_file=$(get_session_file_path "$agent_dir" "$session_id")
        [ ! -f "$session_file" ] && log_warn "会话文件不存在: $session_file" && continue
        
        # 检查该 session 是否已处理过
        local state=$(sqlite3 "$db_path" "SELECT session_id, last_line_processed FROM extraction_state WHERE agent_id='main' AND session_id='$session_id';" 2>/dev/null)
        
        if [ -z "$state" ]; then
            # 新会话，提取所有消息
            log_info "新会话: $session_id"
            local count=$(extract_messages "$session_file" 0 "main" "$session_id")
            if [ "$count" -gt 0 ]; then
                now=$(date -Iseconds | sed "s/+00:00/Z/" | sed "s/'/''/g")
                sqlite3 "$db_path" "INSERT OR REPLACE INTO extraction_state (agent_id, session_id, last_line_processed, last_extracted_at, pending_cleanse) VALUES ('main', '$session_id', 0, '$now', 1);"
                total_count=$((total_count + count))
            fi
        else
            # 已处理过，增量提取
            local last_line=$(echo "$state" | cut -d'|' -f2)
            local current_lines=$(wc -l < "$session_file")
            
            if [ "$current_lines" -gt "$last_line" ]; then
                log_info "增量提取: $session_id 从第 $((last_line + 1)) 行开始"
                local count=$(extract_messages "$session_file" "$last_line" "main" "$session_id")
                if [ "$count" -gt 0 ]; then
                    now=$(date -Iseconds | sed "s/+00:00/Z/" | sed "s/'/''/g")
                    sqlite3 "$db_path" "UPDATE extraction_state SET last_line_processed=$current_lines, last_extracted_at='$now' WHERE agent_id='main' AND session_id='$session_id';"
                    sqlite3 "$db_path" "UPDATE extraction_state SET pending_cleanse=1 WHERE agent_id='main' AND session_id='$session_id';"
                    total_count=$((total_count + count))
                fi
            fi
        fi
    done
    
    if [ "$total_count" -gt 0 ]; then
        log_info "main agent 共新增 $total_count 条消息"
    else
        log_info "main agent 无新增消息"
    fi
}

# ===== 导出待清洗消息到文件 =====
export_pending_messages() {
    local agent_id="$1"
    local db_path="$AGENTS_DIR/$agent_id/memory.db"
    
    local pending=$(sqlite3 "$db_path" "SELECT pending_cleanse FROM extraction_state WHERE agent_id='$agent_id' AND pending_cleanse=1;" 2>/dev/null)
    
    if [ "$pending" != "1" ]; then
        log_info "无需清洗"
        return 1
    fi
    
    # 导出消息到临时文件
    sqlite3 "$db_path" "SELECT rowid, role, substr(content, 1, 2000) FROM messages WHERE agent_id='$agent_id' ORDER BY created_at ASC;" 2>/dev/null > "$SCRIPT_DIR/pending_messages_${agent_id}.txt"
    
    log_info "消息已导出到: $SCRIPT_DIR/pending_messages_${agent_id}.txt"
    echo "$SCRIPT_DIR/pending_messages_${agent_id}.txt"
}

# ===== 主流程 =====
main() {
    log_info "========== 会话记忆同步任务 (v7) =========="
    
    # 处理普通 Agent（agent-*）
    for agent_dir in "$AGENTS_DIR"/agent-*; do
        if [ -d "$agent_dir" ] && [ -f "$agent_dir/sessions/sessions.json" ]; then
            process_normal_agent "$agent_dir"
        fi
    done
    
    # 处理 main Agent
    if [ -d "$AGENTS_DIR/main" ] && [ -f "$AGENTS_DIR/main/sessions/sessions.json" ]; then
        process_main_agent "$AGENTS_DIR/main"
    fi
    
    log_info "========== 任务完成 =========="
}

# ===== 命令行参数处理 =====
case "${1:-}" in
    --init)
        for agent_dir in "$AGENTS_DIR"/agent-* "$AGENTS_DIR/main"; do
            if [ -d "$agent_dir" ] && [ -f "$agent_dir/sessions/sessions.json" ]; then
                agent_id=$(basename "$agent_dir")
                db_path="$agent_dir/memory.db"
                init_db "$db_path"
                log_info "已初始化: $agent_id"
            fi
        done
        ;;
    --export)
        export_pending_messages "${2:-agent-0c143551}"
        ;;
    --help)
        echo "用法: $0 [--init|--export|--help]"
        echo "  --init     初始化所有 Agent 的数据库"
        echo "  --export   导出待清洗消息到文件"
        echo "  --help     显示帮助"
        ;;
    *)
        main
        ;;
esac