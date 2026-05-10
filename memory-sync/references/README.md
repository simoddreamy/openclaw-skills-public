# Memory Sync Skill 使用说明

## 概述

Memory Sync 是一个 OpenClaw Skill，用于将会话消息增量提取到每个 agent 的独立 `memory.db`，并在 session 变化时触发安全的历史消息清洗。

## 核心功能

1. **会话提取**：动态发现活跃会话，优先使用 `openclaw sessions --all-agents`
2. **重置检测**：检测 session_id 变化，判断是否发生会话重置
3. **记忆清洗**：分批处理历史消息，与 AI 融合生成长期记忆
4. **版本管理**：保留记忆版本历史，支持回溯
5. **安全边界**：历史消息仅用于总结，不作为执行指令

## 目录结构

```
/root/.openclaw/workspace/agent-756cc864/memory-sync/
├── SKILL.md
├── install.sh
├── scripts/
│   ├── memory_sync.py
│   ├── memory_sync.sh
│   ├── memory_sync_combined.sh
│   ├── cleanse_and_save.py
│   └── cleanse_memory.py
└── references/
    ├── memory_schema.sql
    └── README.md
```

## 快速开始

### 1. 初始化

```bash
bash /root/.openclaw/workspace/agent-756cc864/memory-sync/install.sh
```

### 2. 配置 Cron 任务

在 OpenClaw 中创建 Cron 任务：

```bash
openclaw cron add \
  --name "memory-sync" \
  --cron "0 * * * *" \
  --session isolated \
  --message "bash /root/.openclaw/workspace/agent-756cc864/memory-sync/scripts/memory_sync_combined.sh" \
  --timeout-seconds 300 \
  --no-deliver
```

## 数据库结构

### messages 表
存储提取的会话消息。

### extraction_state 表
追踪提取和清洗状态。

### memory_versions 表
记忆版本历史。

### memory_summary 表
当前记忆。

## 执行流程

### Cron 触发

```
Cron → memory_sync_combined.sh
    ↓
memory_sync.py / memory_sync.sh
    ↓
增量提取新消息到 memory.db
    ↓
检测 session_id 变化
    ↓
设置 pending_cleanse=1（如有重置）
```

### Agent 启动时检查

```
Agent 启动 → 检查 pending_cleanse
    ↓
pending_cleanse=1?
    ├─ 是 → 执行清洗
    └─ 否 → 正常启动
```

## 手动命令

```bash
# 初始化数据库
bash /root/.openclaw/workspace/agent-756cc864/memory-sync/scripts/memory_sync.sh --init

# 执行记忆清洗
bash /root/.openclaw/workspace/agent-756cc864/memory-sync/scripts/cleanse_memory.py [agent-id]
```

## 注意事项

1. **独立性**：每个 agent 的数据库独立存储
2. **增量处理**：使用 `last_line_processed` 避免重复提取
3. **分批处理**：每批 50 条，避免单次超时
4. **安全边界**：历史消息只用于总结，不会被执行
