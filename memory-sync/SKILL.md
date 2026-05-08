---
name: memory-sync
description: AI 记忆同步与清洗系统。当 AI 因会话重置（session 重启/崩溃）导致丢失上下文时，使用此技能恢复和保存记忆。功能：(1) 定时提取会话消息到 memory.db，(2) 检测 session 重置并标记清洗，(3) AI 融合历史消息生成长期记忆，(4) 记忆版本管理。支持查看清洗状态、手动触发清洗、重置清洗队列等操作。
---

# Memory Sync Skill

解决 AI Agent 会话重置导致记忆丢失的问题。

## ⚡ 自动安装（推荐）

安装后自动配置定时任务（每小时执行）：

```bash
bash /root/.openclaw/workspace/skills/memory-sync/install.sh
```

安装脚本会自动：
1. 初始化 memory.db 数据库
2. 检测 lightclawbot direct session
3. 创建每小时整点的定时任务
4. 定时任务在独立 session 中执行，不干扰正常聊天

---

## ⚠️ 如果自动安装失败（手动配置）

```bash
# 1. 初始化数据库
bash /root/.openclaw/workspace/skills/memory-sync/scripts/memory_sync.sh --init

# 2. 手动创建 Cron 任务
openclaw cron add \
    --name "memory-sync（记忆同步与会话清理）" \
    --cron "0 * * * *" \
    --session isolated \
    --message "bash /root/.openclaw/workspace/skills/memory-sync/scripts/memory_sync_combined.sh" \
    --timeout-seconds 300 \
    --no-deliver
```

---

## 📊 监控命令

```bash
# 查看定时任务状态
openclaw cron list | grep memory-sync

# 查看所有 Agent 清洗状态
for db in /root/.openclaw/agents/agent-*/memory.db /root/.openclaw/agents/main/memory.db; do
  agent=$(basename $(dirname $db))
  state=$(sqlite3 "$db" "SELECT pending_cleanse, last_cleansed_at FROM extraction_state;" 2>/dev/null)
  [ -n "$state" ] && echo "$agent: $state"
done

# 查看指定 Agent 的记忆摘要
sqlite3 /root/.openclaw/agents/<agent-id>/memory.db \
  "SELECT agent_id, summary, version, updated_at FROM memory_summary;"

# 查看记忆版本历史
sqlite3 /root/.openclaw/agents/<agent-id>/memory.db \
  "SELECT version, messages_count, created_at FROM memory_versions ORDER BY version DESC;"

# 查看待清洗消息（供 AI 清洗用）
sqlite3 /root/.openclaw/agents/<agent-id>/memory.db \
  "SELECT rowid, role, substr(content,1,200) FROM messages ORDER BY rowid ASC LIMIT 20;"

# 重置清洗状态（pending_cleanse 异常时）
sqlite3 /root/.openclaw/agents/<agent-id>/memory.db \
  "UPDATE extraction_state SET pending_cleanse=0 WHERE agent_id='<agent-id>';"
```

---

## 🧠 工作原理

```
每小时 Cron
    │
    └─→ memory_sync_combined.sh
            │
            ├─→ memory_sync.py（提取消息）
            │       ↓
            │   只处理：
            │   ✅ agent:main:main（主会话）
            │   ✅ agent:main:lightclawbot:direct:100018290076（lightclawbot）
            │   ✅ agent:main:openclaw-weixin:*（所有微信会话）
            │       ↓
            │   消息 → memory.db（增量提取，按 last_line_processed 断点续跑）
            │       ↓
            │   session_id 变了 → pending_cleanse = 1（等待清洗）
            │
            └─→ cleanup_cron_sessions_v5.py（会话清理）
                    ↓
                读取 pending_cleanup.json → 移动废弃 session → bak/
```

---

## 📁 数据库结构

详见 [references/memory_schema.sql](references/memory_schema.sql)

| 表 | 说明 |
|---|---|
| `messages` | 提取的原始会话消息 |
| `extraction_state` | 提取进度 + pending_cleanse 标记 |
| `memory_versions` | 历史记忆版本（可回溯） |
| `memory_summary` | 当前记忆（Agent 启动时加载） |

## 📂 执行脚本

| 脚本 | 用途 |
|------|------|
| `memory_sync.py` | Python 版消息提取（Cron 调用） |
| `memory_sync_combined.sh` | 合并版：记忆同步 + 会话清理 |
| `cleanse_and_save.py` | AI 清洗脚本，生成融合记忆的 prompt |
| `cleanse_memory.py` | 辅助清洗脚本 |

## 注意事项

- 每个 Agent 独立 database（`/root/.openclaw/agents/<agent-id>/memory.db`）
- main agent 只处理 lightclawbot + 主会话 + 微信会话
- 增量提取，靠 `last_line_processed` 避免重复
- 清洗分批（每批 50 条），避免超时
- 完整说明见 [references/README.md](references/README.md)