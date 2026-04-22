"""LLM 会话仓库接口"""
from abc import ABC, abstractmethod
from typing import List, Optional


class LLMSessionRepository(ABC):
    """LLM 会话数据仓库接口"""

    @abstractmethod
    def save(self, novel_id: str, role: str, chat: str, model: Optional[str] = None,
             prompt_node: Optional[str] = None, chapter_number: Optional[int] = None) -> str:
        """保存一条 LLM 会话记录"""
        pass

    @abstractmethod
    def get_by_novel_id(self, novel_id: str, limit: int = 100) -> List[dict]:
        """获取指定小说的所有 LLM 会话记录"""
        pass

    @abstractmethod
    def delete_by_novel_id(self, novel_id: str) -> int:
        """删除指定小说的所有 LLM 会话记录"""
        pass

    @abstractmethod
    def count_by_novel_id(self, novel_id: str) -> int:
        """统计指定小说的 LLM 会话记录数量"""
        pass
