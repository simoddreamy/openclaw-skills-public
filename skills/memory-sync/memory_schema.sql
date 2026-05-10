-- Memory Sync Schema
-- Each agent has its own memory.db in /root/.openclaw/agents/<agent-id>/

-- messages: 存储提取的会话消息
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_agent_time ON messages(agent_id, created_at);

-- extraction_state: 状态追踪
CREATE TABLE IF NOT EXISTS extraction_state (
    agent_id TEXT PRIMARY KEY,
    session_id TEXT,
    last_line_processed INTEGER DEFAULT 0,
    last_extracted_at TEXT,
    last_cleansed_at TEXT,
    pending_cleanse INTEGER DEFAULT 0
);

-- memory_versions: 版本历史
CREATE TABLE IF NOT EXISTS memory_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    summary TEXT NOT NULL,
    messages_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_versions_agent ON memory_versions(agent_id, version);

-- memory_summary: 当前记忆
CREATE TABLE IF NOT EXISTS memory_summary (
    agent_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);