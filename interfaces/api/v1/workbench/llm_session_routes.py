"""LLM 会话记录 API endpoints"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from domain.novel.repositories.llm_session_repository import LLMSessionRepository
from infrastructure.persistence.database.sqlite_llm_session_repository import SqliteLLMSessionRepository
from infrastructure.persistence.database.connection import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["llm-session"])


class LLMSessionRecord(BaseModel):
    """单条 LLM 会话记录"""
    ROLE: str
    DATE: str
    CHAT: str
    MODEL: Optional[str] = None
    PROMPT_NODE: Optional[str] = None
    CHAPTER: Optional[int] = None


class LLMSessionListResponse(BaseModel):
    """LLM 会话列表响应"""
    sessions: List[LLMSessionRecord]
    total: int


class SaveLLMSessionRequest(BaseModel):
    """保存 LLM 会话请求"""
    novel_id: str
    role: str
    chat: str
    model: Optional[str] = None
    prompt_node: Optional[str] = None
    chapter_number: Optional[int] = None


class SaveLLMSessionResponse(BaseModel):
    """保存 LLM 会话响应"""
    id: str
    success: bool


def get_llm_session_repository(db=Depends(get_database)) -> LLMSessionRepository:
    return SqliteLLMSessionRepository(db)


@router.get("/{novel_id}/llm-sessions", response_model=LLMSessionListResponse)
async def get_llm_sessions(
    novel_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回记录数量限制"),
    repository: LLMSessionRepository = Depends(get_llm_session_repository)
) -> LLMSessionListResponse:
    """
    获取指定小说的 LLM 会话记录列表（按时间倒序）

    返回数据结构：
    [
        {"ROLE": "USER", "DATE": "2026-04-22 11:11:22", "CHAT": "xxxxxx1"},
        {"ROLE": "USER", "DATE": "2026-04-22 11:10:22", "CHAT": "xxxxxx2"},
        ...
    ]
    """
    try:
        sessions = repository.get_by_novel_id(novel_id, limit)
        total = len(sessions)
        return LLMSessionListResponse(sessions=sessions, total=total)
    except Exception as e:
        logger.error(f"获取 LLM 会话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 LLM 会话失败: {str(e)}"
        )


@router.post("/llm-sessions", response_model=SaveLLMSessionResponse)
async def save_llm_session(
    request: SaveLLMSessionRequest,
    repository: LLMSessionRepository = Depends(get_llm_session_repository)
) -> SaveLLMSessionResponse:
    """
    保存一条 LLM 会话记录

    - novel_id: 小说 ID
    - role: 角色 (USER=用户提交, ASSISTANT=AI 响应)
    - chat: 对话内容
    - model: 使用的模型（可选）
    - prompt_node: 提示词节点（可选）
    - chapter_number: 章节号（可选）
    """
    try:
        if request.role not in ('USER', 'ASSISTANT'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="role must be 'USER' or 'ASSISTANT'"
            )

        session_id = repository.save(
            novel_id=request.novel_id,
            role=request.role,
            chat=request.chat,
            model=request.model,
            prompt_node=request.prompt_node,
            chapter_number=request.chapter_number
        )
        return SaveLLMSessionResponse(id=session_id, success=True)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存 LLM 会话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存 LLM 会话失败: {str(e)}"
        )


@router.delete("/{novel_id}/llm-sessions")
async def delete_llm_sessions(
    novel_id: str,
    repository: LLMSessionRepository = Depends(get_llm_session_repository)
) -> dict:
    """删除指定小说的所有 LLM 会话记录"""
    try:
        count = repository.delete_by_novel_id(novel_id)
        return {"success": True, "deleted": count}
    except Exception as e:
        logger.error(f"删除 LLM 会话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除 LLM 会话失败: {str(e)}"
        )
