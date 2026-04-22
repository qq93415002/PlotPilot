"""LLM 会话数据访问层"""
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from domain.novel.repositories.llm_session_repository import LLMSessionRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteLLMSessionRepository(LLMSessionRepository):
    """SQLite 实现的 LLM 会话仓库"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, novel_id: str, role: str, chat: str, model: Optional[str] = None,
             prompt_node: Optional[str] = None, chapter_number: Optional[int] = None) -> str:
        """保存一条 LLM 会话记录"""
        session_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self.db.get_connection()
        conn.execute(
            """
            INSERT INTO llm_sessions (id, novel_id, role, chat, model, prompt_node, chapter_number, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, novel_id, role, chat, model, prompt_node, chapter_number, created_at)
        )
        conn.commit()
        logger.debug(f"保存 LLM 会话: novel_id={novel_id}, role={role}, id={session_id}")
        return session_id

    def get_by_novel_id(self, novel_id: str, limit: int = 100) -> List[dict]:
        """获取指定小说的所有 LLM 会话记录（按时间倒序）"""
        conn = self.db.get_connection()
        cursor = conn.execute(
            """
            SELECT role, created_at, chat, model, prompt_node, chapter_number
            FROM llm_sessions
            WHERE novel_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (novel_id, limit)
        )
        rows = cursor.fetchall()
        return [
            {
                "ROLE": row[0],
                "DATE": row[1],
                "CHAT": row[2],
                "MODEL": row[3],
                "PROMPT_NODE": row[4],
                "CHAPTER": row[5]
            }
            for row in rows
        ]

    def delete_by_novel_id(self, novel_id: str) -> int:
        """删除指定小说的所有 LLM 会话记录，返回删除数量"""
        conn = self.db.get_connection()
        cursor = conn.execute(
            "DELETE FROM llm_sessions WHERE novel_id = ?",
            (novel_id,)
        )
        conn.commit()
        return cursor.rowcount

    def count_by_novel_id(self, novel_id: str) -> int:
        """统计指定小说的 LLM 会话记录数量"""
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM llm_sessions WHERE novel_id = ?",
            (novel_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
