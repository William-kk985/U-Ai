import os
import json
import time
from typing import List, Dict, Optional

class ChatSession:
    def __init__(self, session_id: str = "default", max_history: int = 10, storage_dir: str = None):
        self.session_id = session_id
        self.max_history = max_history
        self.history: List[Dict[str, str]] = []
        self.current_ai_response = ""
        self.attached_files: List[Dict[str, str]] = [] # 存储该会话关联的文件 [{name, content}]
        
        if storage_dir is None:
            storage_dir = os.path.join(os.path.dirname(__file__), '..', '05_Data', 'sessions')
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.storage_file = os.path.join(self.storage_dir, f"{session_id}.json")
        
        self.load_history()

    def add_message(self, role: str, content: str):
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        if len(self.history) > self.max_history * 2:
            self.history = self.history[-(self.max_history * 2):]
        self.save_history()

    def append_to_current_response(self, text: str):
        self.current_ai_response += text

    def finalize_ai_response(self):
        if self.current_ai_response:
            self.add_message("assistant", self.current_ai_response)
            self.current_ai_response = ""

    def get_formatted_history(self, limit: int = None) -> str:
        """获取格式化的历史记录
        
        Args:
            limit: 可选，限制返回最近的消息数量
        """
        history_to_format = self.history
        if limit is not None:
            history_to_format = self.history[-limit:]
        
        formatted = ""
        for msg in history_to_format:
            formatted += f"{msg['role']}: {msg['content']}\n"
        return formatted

    def clear(self):
        self.history = []
        self.save_history()

    def save_history(self):
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "session_id": self.session_id,
                    "history": self.history,
                    "attached_files": self.attached_files,
                    "last_updated": time.time()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存会话失败: {e}")

    def load_history(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = data.get("history", [])
                    self.attached_files = data.get("attached_files", [])
            except Exception as e:
                print(f"⚠️ 加载会话失败: {e}")
                self.history = []
                self.attached_files = []


class SessionManager:
    def __init__(self, storage_dir: str, max_sessions: int = 50, cleanup_days: int = 30):
        self.storage_dir = storage_dir
        self.max_sessions = max_sessions  # 最大会话数量
        self.cleanup_days = cleanup_days  # 清理超过 N 天的会话
        os.makedirs(storage_dir, exist_ok=True)
        self.active_session: Optional[ChatSession] = None
        self.sessions_meta = {}
        self._load_meta()
        
        # 启动时执行一次清理
        self.auto_cleanup()

    def _load_meta(self):
        meta_file = os.path.join(self.storage_dir, "_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    self.sessions_meta = json.load(f)
            except Exception as e:
                print(f"⚠️ 加载元数据失败: {e}")

    def _save_meta(self):
        meta_file = os.path.join(self.storage_dir, "_meta.json")
        try:
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions_meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存元数据失败: {e}")

    def get_or_create_session(self, session_id: str, name: str = None):
        if self.active_session is None or self.active_session.session_id != session_id:
            self.active_session = ChatSession(session_id, storage_dir=self.storage_dir)
        
        if session_id not in self.sessions_meta:
            self.sessions_meta[session_id] = {
                "name": name or session_id,
                "created": time.time(),
                "updated": time.time()
            }
            self._save_meta()
        else:
            self.sessions_meta[session_id]["updated"] = time.time()
            if name: 
                self.sessions_meta[session_id]["name"] = name
            self._save_meta()
            
        return self.active_session

    def list_sessions(self):
        sessions = []
        for sid, meta in self.sessions_meta.items():
            meta['id'] = sid
            sessions.append(meta)
        return sorted(sessions, key=lambda x: x['updated'], reverse=True)

    def delete_session(self, session_id: str):
        if session_id in self.sessions_meta:
            del self.sessions_meta[session_id]
            self._save_meta()
            
            file_path = os.path.join(self.storage_dir, f"{session_id}.json")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            if self.active_session and self.active_session.session_id == session_id:
                self.active_session = None
            return True
        return False

    def auto_cleanup(self):
        """自动清理过期和超量的会话"""
        if not self.sessions_meta:
            return
        
        now = time.time()
        cleanup_threshold = now - (self.cleanup_days * 24 * 3600)  # N 天前的时间戳
        
        # 1. 找出需要删除的会话（按时间排序）
        sessions_by_time = sorted(
            self.sessions_meta.items(),
            key=lambda x: x[1].get('updated', 0)
        )
        
        to_delete = []
        
        # 策略 1: 删除超过 N 天的会话
        for sid, meta in sessions_by_time:
            if meta.get('updated', 0) < cleanup_threshold:
                to_delete.append(sid)
        
        # 策略 2: 如果会话数量超过上限，删除最旧的（不包括已标记删除的）
        remaining_count = len(self.sessions_meta) - len(to_delete)
        if remaining_count > self.max_sessions:
            excess_count = remaining_count - self.max_sessions
            for sid, meta in sessions_by_time:
                if sid not in to_delete and excess_count > 0:
                    to_delete.append(sid)
                    excess_count -= 1
        
        # 执行删除
        if to_delete:
            print(f"🧹 开始清理 {len(to_delete)} 个过期/超量会话...")
            for sid in to_delete:
                self.delete_session(sid)
                print(f"   - 已删除: {sid}")
            print(f"✅ 清理完成，剩余 {len(self.sessions_meta)} 个会话")
