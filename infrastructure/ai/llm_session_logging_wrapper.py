"""LLM 服务包装器 - 自动记录会话"""
import logging
from typing import AsyncIterator, Optional

from domain.ai.context.llm_context import get_llm_context, clear_llm_context
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)


class LLMSessionLoggingWrapper(LLMService):
    """LLM 服务包装器 - 自动记录所有 generate 调用"""

    def __init__(self, delegate: LLMService):
        self._delegate = delegate

    def _log_call(self, prompt: Prompt, config: GenerationConfig, result: Optional[GenerationResult] = None):
        """记录 LLM 调用"""
        try:
            context = get_llm_context()
            logger.warning(f"[LLM_LOG] Context: {context}")
            if not context or not context.novel_id:
                logger.warning(f"[LLM_LOG] No context or novel_id, skipping logging")
                return

            prompt_text = prompt.to_string() if hasattr(prompt, 'to_string') else str(prompt)
            model = config.model or None

            logger.warning(f"[LLM_LOG] Logging: novel_id={context.novel_id}, prompt_node={context.prompt_node}")

            if result:
                try:
                    from application.workbench.services.llm_session_logger import llm_session_logger
                    llm_session_logger.log_user_message(
                        novel_id=context.novel_id,
                        chat=prompt_text,
                        model=model,
                        prompt_node=context.prompt_node,
                        chapter_number=context.chapter_number
                    )
                    llm_session_logger.log_assistant_message(
                        novel_id=context.novel_id,
                        chat=result.content,
                        model=model,
                        prompt_node=context.prompt_node,
                        chapter_number=context.chapter_number
                    )
                    logger.warning(f"[LLM_LOG] Successfully logged both messages")
                except Exception as log_err:
                    logger.warning(f"[LLM_LOG] Failed to log LLM session: {log_err}")
        except Exception as e:
            logger.warning(f"[LLM_LOG] Error in _log_call: {e}")

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        result = await self._delegate.generate(prompt, config)
        self._log_call(prompt, config, result)
        return result

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        full_content = []
        async for chunk in self._delegate.stream_generate(prompt, config):
            full_content.append(chunk)
            yield chunk

        if full_content:
            result = GenerationResult(content="".join(full_content), token_usage=None)
            self._log_call(prompt, config, result)
