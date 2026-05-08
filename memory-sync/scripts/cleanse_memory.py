#!/usr/bin/env python3
"""
AI 记忆清洗脚本
在 Agent 会话启动时调用，执行 pending_cleanse 消息的 AI 清洗
"""
import sqlite3
import json
import sys
import re
from datetime import datetime, timezone

AGENT_ID = "agent-0c143551"
DB_PATH = f"/root/.openclaw/agents/{AGENT_ID}/memory.db"

def get_pending_messages(limit=50):
    """获取待清洗消息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT rowid, role, content FROM messages ORDER BY rowid ASC LIMIT ?",
        (limit,)
    )
    messages = cursor.fetchall()
    conn.close()
    return messages

def get_current_summary():
    """获取当前记忆"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary FROM memory_summary WHERE agent_id = ?", (AGENT_ID,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_latest_version():
    """获取最新版本号"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(version) FROM memory_versions WHERE agent_id=?", (AGENT_ID,))
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0

def save_memory_version(version, summary, message_count):
    """保存记忆版本"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
    
    cursor.execute(
        "INSERT INTO memory_versions (agent_id, version, summary, messages_count, created_at) VALUES (?, ?, ?, ?, ?)",
        (AGENT_ID, version, summary, message_count, now)
    )
    cursor.execute(
        "INSERT OR REPLACE INTO memory_summary (agent_id, summary, version, updated_at) VALUES (?, ?, ?, ?)",
        (AGENT_ID, summary, version, now)
    )
    conn.commit()
    conn.close()

def build_messages_text(messages):
    """构建消息文本用于 AI 处理"""
    text = ""
    for rowid, role, content in messages:
        # 截断过长内容
        if len(content) > 1000:
            content = content[:1000] + "..."
        text += f"\n[{role}](rowid={rowid}):\n{content}\n"
    return text

def extract_markdown_content(text):
    """从 AI 回复中提取 markdown 内容"""
    # 尝试提取 <final>...</final> 中的内容
    match = re.search(r'<final>\s*(.*?)\s*</final>', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 尝试提取 markdown 代码块
    match = re.search(r'```markdown\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 尝试直接返回非空内容
    text = text.strip()
    if text and len(text) > 50:
        return text
    
    return None

def main():
    agent_id = sys.argv[1] if len(sys.argv) > 1 else AGENT_ID
    
    print("=" * 60)
    print(f"  AI 记忆清洗开始 (Agent: {agent_id})")
    print("=" * 60)
    
    # 检查待清洗状态
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pending_cleanse FROM extraction_state WHERE agent_id=?", (agent_id,))
    row = cursor.fetchone()
    
    if not row or row[0] != 1:
        print("无需清洗 (pending_cleanse != 1)")
        conn.close()
        return
    
    conn.close()
    
    # 获取历史记忆
    history = get_current_summary()
    if history:
        print(f"历史记忆: 有 ({len(history)} 字符)")
    else:
        print("历史记忆: 无")
    
    # 获取待处理消息
    messages = get_pending_messages(limit=50)
    print(f"待处理消息: {len(messages)} 条")
    
    if not messages:
        # 没有消息，标记完成
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
        cursor.execute("UPDATE extraction_state SET pending_cleanse=0, last_cleansed_at=? WHERE agent_id=?", (now, agent_id))
        conn.commit()
        conn.close()
        print("没有待处理消息，标记完成")
        return
    
    # 构建消息文本
    messages_text = build_messages_text(messages)
    
    # 获取当前版本
    current_version = get_latest_version()
    new_version = current_version + 1
    
    # 这里需要 AI 处理，由于我们在 shell 上下文中
    # 输出提示信息，由调用方通过 AI 模型处理
    print(f"\n准备清洗 {len(messages)} 条消息...")
    print(f"历史版本: v{current_version}, 将创建: v{new_version}")
    print("\n" + "=" * 60)
    print("  消息内容预览")
    print("=" * 60)
    print(messages_text[:800])
    print("\n...")
    
    # 输出结构化数据供 AI 处理
    print("\n" + "=" * 60)
    print("  AI 处理所需信息")
    print("=" * 60)
    print(f"AGENT_ID={agent_id}")
    print(f"DB_PATH={DB_PATH}")
    print(f"VERSION={new_version}")
    print(f"HISTORY_LENGTH={len(history) if history else 0}")

if __name__ == "__main__":
    main()