#!/usr/bin/env python3
"""
Memory Sync Python 版本
功能：增量提取 Agent 会话消息，检测重置并触发 AI 记忆清洗
替代 bash 版本，解决特殊字符导致的 SQL 解析错误
"""
import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ===== 配置 =====
SCRIPT_DIR = Path(__file__).parent
SCHEMA_FILE = SCRIPT_DIR / "memory_schema.sql"
AGENTS_DIR = Path("/root/.openclaw/agents")

def init_db(db_path):
    """初始化数据库"""
    if not db_path.exists():
        print(f"初始化数据库: {db_path}")
        with open(SCHEMA_FILE, 'r') as f:
            schema = f.read()
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema)
        conn.close()

def get_sessions_info(agent_dir):
    """获取所有会话信息"""
    sessions_file = agent_dir / "sessions" / "sessions.json"
    if not sessions_file.exists():
        return []
    
    with open(sessions_file, 'r') as f:
        sessions = json.load(f)
    
    result = []
    for key, value in sessions.items():
        result.append({
            'key': key,
            'session_id': value.get('sessionId', ''),
            'chat_type': value.get('chatType') or 'unknown'
        })
    return result

def get_active_session_id(agent_dir, agent_id=None):
    """获取当前活跃 session ID（用于判断重置）"""
    sessions_file = agent_dir / "sessions" / "sessions.json"
    if not sessions_file.exists():
        return None
    
    with open(sessions_file, 'r') as f:
        sessions = json.load(f)
    
    if agent_id == "main":
        # 获取 lightclawbot direct 会话
        # 动态选择 lightclawbot direct 会话（优先最新匹配）
        for key in sorted(sessions.keys(), reverse=True):
            if key.startswith("agent:main:lightclawbot:direct:"):
                return sessions.get(key, {}).get('sessionId')
        return None
    else:
        # 获取第一个（最新）的 direct session
        for key, value in sessions.items():
            if ":direct:" in key:
                return value.get('sessionId')
        for key, value in sessions.items():
            return value.get('sessionId')

def get_session_file_path(agent_dir, session_id):
    """获取 session 文件路径"""
    return agent_dir / "sessions" / f"{session_id}.jsonl"

def detect_session_reset(db_path, agent_id, current_session_id):
    """检测会话重置"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT session_id FROM extraction_state WHERE agent_id=?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return "first_run"
    
    if row[0] != current_session_id:
        return "reset"
    return "normal"

def parse_jsonl_messages(jsonl_file, from_line=0):
    """解析 JSONL 文件，提取消息"""
    if not jsonl_file.exists():
        return []
    
    messages = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        if i < from_line:
            continue
        try:
            obj = json.loads(line.strip())
            if obj.get('type') != 'message':
                continue
            
            msg = obj.get('message', {})
            role = msg.get('role', '')
            content = msg.get('content', '')
            
            # 处理 content 数组
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                content = ''.join(text_parts)
            elif not isinstance(content, str):
                continue
            
            if role and content:
                messages.append({'role': role, 'content': content})
        except (json.JSONDecodeError, KeyError):
            continue
    
    return messages

def extract_messages(session_file, from_line, agent_id, session_id, db_path):
    """提取消息并存储到数据库"""
    messages = parse_jsonl_messages(session_file, from_line)
    
    if not messages:
        return 0
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
    
    count = 0
    for msg in messages:
        try:
            cursor.execute(
                "SELECT 1 FROM messages WHERE agent_id=? AND session_id=? AND role=? AND content=? LIMIT 1",
                (agent_id, session_id, msg['role'], msg['content'])
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                "INSERT INTO messages (agent_id, session_id, created_at, role, content) VALUES (?, ?, ?, ?, ?)",
                (agent_id, session_id, timestamp, msg['role'], msg['content'])
            )
            count += 1
        except sqlite3.Error as e:
            # 跳过插入失败的消息
            print(f"插入失败: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    return count

def process_normal_agent(agent_dir):
    """处理普通 Agent（agent-*）"""
    agent_id = agent_dir.name
    print(f"=== 处理 Agent: {agent_id} ===")
    
    current_session_id = get_active_session_id(agent_dir)
    if not current_session_id:
        print(f"  无法获取 session_id，跳过")
        return
    
    print(f"  当前 session: {current_session_id}")
    
    db_path = agent_dir / "memory.db"
    init_db(db_path)
    
    status = detect_session_reset(db_path, agent_id, current_session_id)
    print(f"  状态: {status}")
    
    session_file = get_session_file_path(agent_dir, current_session_id)
    
    if status in ("first_run", "reset"):
        if status == "reset":
            print(f"  检测到会话重置: {agent_id}")
        else:
            print(f"  首次运行: {agent_id}")
        
        if session_file.exists():
            count = extract_messages(session_file, 0, agent_id, current_session_id, db_path)
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            current_lines = sum(1 for _ in open(session_file))
            cursor.execute(
                "INSERT OR REPLACE INTO extraction_state (agent_id, session_id, last_line_processed, last_extracted_at, pending_cleanse) VALUES (?, ?, ?, ?, ?)",
                (agent_id, current_session_id, current_lines, timestamp, 1)
            )
            conn.commit()
            conn.close()
            
            print(f"  已设置 pending_cleanse=1，新增 {count} 条消息")
    
    elif status == "normal":
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, last_line_processed FROM extraction_state WHERE agent_id=?", (agent_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"  无状态记录，跳过")
            return
        
        last_session_id, last_line = row
        
        if not session_file.exists():
            print(f"  会话文件不存在: {session_file}")
            return
        
        current_lines = sum(1 for _ in open(session_file))
        
        if current_lines > last_line:
            print(f"  增量提取: 从第 {last_line + 1} 行开始")
            count = extract_messages(session_file, last_line, agent_id, last_session_id, db_path)
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE extraction_state SET last_line_processed=?, last_extracted_at=? WHERE agent_id=?",
                (current_lines, timestamp, agent_id)
            )
            cursor.execute(
                "UPDATE extraction_state SET pending_cleanse=1 WHERE agent_id=?",
                (agent_id,)
            )
            conn.commit()
            conn.close()
            
            print(f"  新增 {count} 条消息，已设置 pending_cleanse=1")
        else:
            print(f"  无新增消息")

def process_main_agent(agent_dir):
    """处理 main Agent - 只处理指定的两个 session"""
    print(f"=== 处理 main Agent ===")
    
    sessions_file = agent_dir / "sessions" / "sessions.json"
    if not sessions_file.exists():
        print(f"  sessions.json 不存在，跳过")
        return
    
    db_path = agent_dir / "memory.db"
    init_db(db_path)
    
    with open(sessions_file, 'r') as f:
        sessions = json.load(f)
    
    # 硬编码 key
    static_keys = [
        "agent:main:main",
        "agent:main:lightclawbot:direct:100018290076",
    ]

    # 通配符匹配：所有 agent:main:openclaw-weixin:* 开头的 key
    weixin_keys = [k for k in sessions if k.startswith("agent:main:openclaw-weixin:")]

    # 合并
    target_keys = static_keys + weixin_keys
    
    total_count = 0
    
    for key in target_keys:
        if key not in sessions:
            print(f"  session 不存在: {key}")
            continue
        
        session_id = sessions[key].get('sessionId', '')
        if not session_id:
            continue
        
        print(f"  处理会话: {key} → {session_id}")
        
        session_file = get_session_file_path(agent_dir, session_id)
        if not session_file.exists():
            print(f"    会话文件不存在: {session_file}")
            continue
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, last_line_processed FROM extraction_state WHERE agent_id='main' AND session_id=?",
            (session_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            # 新会话，提取所有消息
            print(f"    新会话: {session_id}")
            count = extract_messages(session_file, 0, "main", session_id, db_path)
            
            if count > 0:
                timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO extraction_state (agent_id, session_id, last_line_processed, last_extracted_at, pending_cleanse) VALUES ('main', ?, ?, ?, ?)",
                    (session_id, 0, timestamp, 1)
                )
                conn.commit()
                conn.close()
                total_count += count
                print(f"    提取了 {count} 条消息")
        else:
            # 已处理过，增量提取
            last_session_id, last_line = row
            current_lines = sum(1 for _ in open(session_file))
            
            if current_lines > last_line:
                print(f"    增量提取: 从第 {last_line + 1} 行开始")
                count = extract_messages(session_file, last_line, "main", session_id, db_path)
                
                if count > 0:
                    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+08:00')
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE extraction_state SET last_line_processed=?, last_extracted_at=? WHERE agent_id='main' AND session_id=?",
                        (current_lines, timestamp, session_id)
                    )
                    cursor.execute(
                        "UPDATE extraction_state SET pending_cleanse=1 WHERE agent_id='main' AND session_id=?",
                        (session_id,)
                    )
                    conn.commit()
                    conn.close()
                    total_count += count
                    print(f"    提取了 {count} 条消息")
    
    if total_count > 0:
        print(f"  main agent 共新增 {total_count} 条消息")
    else:
        print(f"  main agent 无新增消息")

def main():
    print("========== 会话记忆同步任务 (Python v1) ==========")
    
    # 处理普通 Agent（agent-*）
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        if agent_dir.name.startswith('agent-'):
            if (agent_dir / "sessions" / "sessions.json").exists():
                process_normal_agent(agent_dir)
    
    # 处理 main Agent
    main_dir = AGENTS_DIR / "main"
    if main_dir.is_dir() and (main_dir / "sessions" / "sessions.json").exists():
        process_main_agent(main_dir)
    
    print("========== 任务完成 ==========")

if __name__ == "__main__":
    main()