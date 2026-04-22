"""LLM 会话记录服务"""
import logging
from typing import Optional

from domain.novel.repositories.llm_session_repository import LLMSessionRepository
from infrastructure.persistence.database.connection import get_database

logger = logging.getLogger(__name__)


class LLMSessionLogger:
    """LLM 会话记录器（单例）"""

    _instance: Optional['LLMSessionLogger'] = None
    _repository: Optional[LLMSessionRepository] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_repository(self, repository: LLMSessionRepository) -> None:
        self._repository = repository

    def get_repository(self) -> LLMSessionRepository:
        if self._repository is None:
            from infrastructure.persistence.database.sqlite_llm_session_repository import SqliteLLMSessionRepository
            db = get_database()
            self._repository = SqliteLLMSessionRepository(db)
        return self._repository

    def log_user_message(
        self,
        novel_id: str,
        chat: str,
        model: Optional[str] = None,
        prompt_node: Optional[str] = None,
        chapter_number: Optional[int] = None
    ) -> str:
        """记录用户提交到 AI 的消息"""
        return self.get_repository().save(
            novel_id=novel_id,
            role='USER',
            chat=chat,
            model=model,
            prompt_node=prompt_node,
            chapter_number=chapter_number
        )

    def log_assistant_message(
        self,
        novel_id: str,
        chat: str,
        model: Optional[str] = None,
        prompt_node: Optional[str] = None,
        chapter_number: Optional[int] = None
    ) -> str:
        """记录 AI 返回的消息"""
        return self.get_repository().save(
            novel_id=novel_id,
            role='ASSISTANT',
            chat=chat,
            model=model,
            prompt_node=prompt_node,
            chapter_number=chapter_number
        )

    def get_sessions(self, novel_id: str, limit: int = 100):
        """获取会话记录"""
        return self.get_repository().get_by_novel_id(novel_id, limit)


llm_session_logger = LLMSessionLogger()
