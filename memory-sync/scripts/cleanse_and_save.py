#!/usr/bin/env python3
"""
记忆清洗主脚本 - 由 Agent 在会话中调用执行 AI 清洗
用法: python3 /root/.openclaw/workspace/scripts/memory-sync/cleanse_and_save.py [agent_id]
"""
import sqlite3
import json
import sys
import re
from datetime import datetime, timezone

AGENT_ID = "agent-0c143551"
DB_PATH = f"/root/.openclaw/agents/{AGENT_ID}/memory.db"

def get_pending_messages(limit=50):
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT summary FROM memory_summary WHERE agent_id = ?", (AGENT_ID,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_latest_version():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(version) FROM memory_versions WHERE agent_id=?", (AGENT_ID,))
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0

def save_memory_version(version, summary, message_count):
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
    cursor.execute("UPDATE extraction_state SET pending_cleanse=0, last_cleansed_at=? WHERE agent_id=?", (now, AGENT_ID))
    
    conn.commit()
    conn.close()

def build_prompt(messages, history):
    """构建 AI 清洗提示词"""
    # 历史记忆部分
    history_part = f"## 历史记忆\n\n{history}\n\n" if history else "## 历史记忆\n\n（无）\n\n"
    
    # 消息部分
    messages_text = ""
    for rowid, role, content in messages:
        if len(content) > 1500:
            content = content[:1500] + "..."
        messages_text += f"\n[{role}](rowid={rowid}):\n{content[:2000]}\n"
    
    prompt = f"""{history_part}
## 待清洗消息（共 {len(messages)} 条）

{messages_text}

---

请分析以上消息，提取关键信息，生成一份简洁的记忆总结。

要求：
1. 提取：用户信息、项目背景、待办事项、技术细节、重要决策
2. 使用中文
3. 总结长度：300-600字
4. 结构化输出（使用 ### 标题）
5. 只输出记忆总结内容，不要其他解释

记忆总结："""

    return prompt

def main():
    agent_id = sys.argv[1] if len(sys.argv) > 1 else AGENT_ID
    
    print("=" * 60)
    print(f"  AI 记忆清洗脚本")
    print(f"  Agent: {agent_id}")
    print("=" * 60)
    
    # 检查待清洗状态
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pending_cleanse FROM extraction_state WHERE agent_id=?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or row[0] != 1:
        print("✅ 无需清洗 (pending_cleanse=0)")
        return
    
    print("⚠️ pending_cleanse=1，开始清洗...")
    
    # 获取历史记忆
    history = get_current_summary()
    history_len = len(history) if history else 0
    print(f"历史记忆: {'有' if history else '无'} ({history_len} 字符)")
    
    # 获取待处理消息
    messages = get_pending_messages(limit=50)
    print(f"待处理消息: {len(messages)} 条")
    
    if not messages:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
        cursor.execute("UPDATE extraction_state SET pending_cleanse=0, last_cleansed_at=? WHERE agent_id=?", (now, agent_id))
        conn.commit()
        conn.close()
        print("没有消息，标记完成")
        return
    
    # 获取新版本号
    current_version = get_latest_version()
    new_version = current_version + 1
    
    # 输出 prompt（供 AI 模型处理）
    prompt = build_prompt(messages, history)
    
    print("\n" + "=" * 60)
    print("  AI 清洗 Prompt")
    print("=" * 60)
    print(f"VERSION={new_version}")
    print(f"MESSAGE_COUNT={len(messages)}")
    print(f"HISTORY_EXISTS={'yes' if history else 'no'}")
    print(f"PROMPT_LENGTH={len(prompt)}")
    print("\n--- PROMPT START ---")
    print(prompt[:2000])
    print("\n... (truncated) ...\n")
    print("--- PROMPT END ---")
    
    # 输出用于后续处理的元数据
    print("\n" + "=" * 60)
    print("  处理指令")
    print("=" * 60)
    print("""
请用 AI 模型处理以上 prompt，生成记忆总结。

AI 模型应：
1. 分析历史记忆和待清洗消息
2. 生成结构化的记忆总结（300-600字，中文）
3. 输出格式示例：
   ## YYYY-MM-DD 记忆总结
   
   ### 用户信息
   ...
   
   ### 项目背景
   ...

处理完成后，将总结保存到数据库：
- 版本: v{version}
- 调用: save_memory_version({version}, <summary>, {count})
""".format(version=new_version, count=len(messages)))
    
    # 提示结束
    print("\n✅ AI 清洗提示已生成，请在 AI 会话中继续处理")

if __name__ == "__main__":
    main()