# 🧠 Memory Sync for OpenClaw

> **"My AI forgot everything after restart..." — with Memory Sync, never again.**

A zero-config OpenClaw skill that automatically saves and restores AI agent memory across session resets, crashes, and restarts. Install it once, and your AI remembers everything.

---

## 🎯 The Problem

OpenClaw AI agents lose all context when their session resets — whether from a crash, timeout, or restart. Hours of conversation context, learned preferences, and accumulated knowledge vanish instantly.

**Before Memory Sync:**
- Session resets → AI forgets everything
- Long-term projects lost between conversations
- No persistence across restarts

## ✨ The Solution

Memory Sync captures every conversation message to a local SQLite database, detects session resets, and triggers AI-powered memory fusion — so your agent **never forgets**.

**After Memory Sync:**
- Messages automatically saved on every conversation
- Session reset detected → pending memory fusion triggered
- AI restart fuses extracted messages into persistent long-term memory
- Memory versions preserved for rollback

---

## 🚀 Quick Install

```bash
# One-command installation
bash /root/.openclaw/workspace/skills/memory-sync/install.sh
```

That's it. The installer will:
1. Initialize the memory database
2. Detect your agent's active sessions
3. Create a hourly cron job automatically

No manual configuration required.

---

## 🔧 Manual Setup (if auto-install fails)

```bash
# 1. Initialize database
bash /root/.openclaw/workspace/skills/memory-sync/scripts/memory_sync.sh --init

# 2. Create cron job
openclaw cron add \
    --name "memory-sync" \
    --cron "0 * * * *" \
    --session isolated \
    --message "bash /root/.openclaw/workspace/skills/memory-sync/scripts/memory_sync_combined.sh" \
    --timeout-seconds 300 \
    --no-deliver
```

---

## 📖 How It Works

```
Every hour (cron)
    │
    ├─► memory_sync.py
    │       │
    │       ├─ Extract messages from active sessions
    │       │   (agent:main:main)
    │       │   (agent:main:lightclawbot:direct:*)  
    │       │   (agent:main:openclaw-weixin:*)
    │       │
    │       └─ Store to memory.db (incremental, line-by-line)
    │
    └─► cleanup_cron_sessions_v5.py
            │
            └─ Clean up stale session files
                (move to bak/, keep disk tidy)

Session reset detected?
    │
    └─► pending_cleanse = 1
            │
            └─► Next AI start
                    │
                    └─► AI fuses messages into
                          long-term memory summary
```

### Database Schema

| Table | Purpose |
|-------|---------|
| `messages` | Raw extracted conversation messages |
| `extraction_state` | Extraction progress + `pending_cleanse` flag |
| `memory_versions` | Historical memory versions (auditable, rollback support) |
| `memory_summary` | Current AI memory (loaded on startup) |

---

## 🛠️ Management Commands

```bash
# Check cron job status
openclaw cron list | grep memory-sync

# View memory status for all agents
for db in /root/.openclaw/agents/*/memory.db; do
  agent=$(basename $(dirname $db))
  sqlite3 "$db" "SELECT pending_cleanse, last_cleansed_at FROM extraction_state;"
done

# View current memory summary
sqlite3 /root/.openclaw/agents/main/memory.db \
  "SELECT summary FROM memory_summary;"

# View memory version history
sqlite3 /root/.openclaw/agents/main/memory.db \
  "SELECT version, messages_count, created_at FROM memory_versions;"

# Reset cleanse flag (if stuck)
sqlite3 /root/.openclaw/agents/main/memory.db \
  "UPDATE extraction_state SET pending_cleanse=0;"
```

---

## 📦 What's Included

```
memory-sync/
├── SKILL.md                      # OpenClaw skill definition
├── install.sh                    # ⚡ One-click installer
├── scripts/
│   ├── memory_sync.py            # Message extraction engine
│   ├── memory_sync_combined.sh   # Combined sync+cleanup runner
│   ├── cleanse_and_save.py       # AI memory fusion script
│   └── cleanse_memory.py        # Cleanup helper
└── references/
    ├── memory_schema.sql         # Database schema
    └── README.md                 # Full documentation
```

---

## 🌟 Features

- **Zero-config install** — one command, auto-configures everything
- **Incremental extraction** — picks up exactly where it left off (line-by-line)
- **Session reset detection** — automatically triggers memory fusion
- **Version history** — rollback to any previous memory state
- **Multi-session support** — handles lightclawbot, wechat, and main sessions
- **Disk cleanup** — automatically cleans stale session files
- **Per-agent isolation** — each agent has its own independent memory database

---

## ⚙️ Requirements

- OpenClaw installed and running
- `sqlite3` available on the system
- `bash` shell
- `jq` for JSON parsing

---

## 📝 License

MIT — free to use, modify, and distribute.

---

## 🤝 Contributing

Issues and PRs welcome! If you find a bug or want a feature, open an issue.
