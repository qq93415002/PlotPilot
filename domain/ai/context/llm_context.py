"""LLM 会话上下文管理"""
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

@dataclass
class LLMCallContext:
    """LLM 调用上下文"""
    novel_id: Optional[str] = None
    prompt_node: Optional[str] = None
    chapter_number: Optional[int] = None

_llm_context: ContextVar[LLMCallContext] = ContextVar('llm_context', default=None)

def set_llm_context(novel_id: str, prompt_node: str = None, chapter_number: int = None) -> None:
    """设置当前 LLM 调用上下文"""
    _llm_context.set(LLMCallContext(
        novel_id=novel_id,
        prompt_node=prompt_node,
        chapter_number=chapter_number
    ))

def get_llm_context() -> Optional[LLMCallContext]:
    """获取当前 LLM 调用上下文"""
    return _llm_context.get()

def clear_llm_context() -> None:
    """清除当前 LLM 调用上下文"""
    _llm_context.set(None)
