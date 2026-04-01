"""Chat 应用服务"""
import logging
from typing import Optional, Dict, Any, List, AsyncIterator
from datetime import datetime

from domain.chat.chat_thread import ChatThread
from domain.chat.chat_message import ChatMessage, ToolCall
from domain.chat.chat_repository import ChatRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.novel_repository import NovelRepository
from domain.bible.repositories.bible_repository import BibleRepository
from domain.cast.repositories.cast_repository import CastRepository
from domain.knowledge.repositories.knowledge_repository import KnowledgeRepository
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


class ChatService:
    """Chat 应用服务

    协调聊天、AI 生成和领域服务，实现聊天功能。
    """

    def __init__(
        self,
        chat_repository: ChatRepository,
        llm_service: Optional[LLMService],
        novel_repository: NovelRepository,
        bible_repository: BibleRepository,
        cast_repository: CastRepository,
        knowledge_repository: KnowledgeRepository
    ):
        """初始化服务

        Args:
            chat_repository: 聊天仓储
            llm_service: LLM 服务（未配置 API Key 时为 None，仅只读接口可用）
            novel_repository: 小说仓储
            bible_repository: Bible 仓储
            cast_repository: Cast 仓储
            knowledge_repository: Knowledge 仓储
        """
        self.chat_repository = chat_repository
        self.llm_service = llm_service
        self.novel_repository = novel_repository
        self.bible_repository = bible_repository
        self.cast_repository = cast_repository
        self.knowledge_repository = knowledge_repository

    def get_messages(self, novel_id: str) -> Dict[str, Any]:
        """获取聊天消息

        Args:
            novel_id: 小说 ID

        Returns:
            包含消息列表的字典
        """
        thread = self.chat_repository.get_by_novel_id(novel_id)

        if thread is None:
            # 返回空消息列表
            return {"messages": []}

        out: List[Dict[str, Any]] = []
        for msg in thread.messages:
            try:
                out.append(msg.to_dict())
            except Exception as e:
                logger.warning("跳过无法序列化的聊天消息：%s", e, exc_info=True)
        return {"messages": out}

    async def send_message(
        self,
        novel_id: str,
        message: str,
        use_cast_tools: bool = True,
        history_mode: str = "full",
        clear_thread: bool = False
    ) -> Dict[str, Any]:
        """发送消息（非流式）

        Args:
            novel_id: 小说 ID
            message: 用户消息
            use_cast_tools: 是否使用 cast 工具
            history_mode: 历史模式 (full/fresh)
            clear_thread: 是否清空线程

        Returns:
            包含回复的字典

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        # 验证小说存在
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        # 获取或创建线程
        thread = self.chat_repository.get_by_novel_id(novel_id)
        if thread is None:
            thread = ChatThread.create(novel_id)

        # 清空线程（如果需要）
        if clear_thread:
            thread.clear_messages()

        # 添加用户消息
        user_msg = ChatMessage.create_user_message(message)
        thread.add_message(user_msg)

        if self.llm_service is None:
            raise ValueError("LLM 未配置：请设置环境变量 ANTHROPIC_API_KEY")

        # 构建提示词
        prompt = await self._build_prompt(novel_id, thread, history_mode, use_cast_tools)

        # 调用 LLM
        try:
            config = GenerationConfig()
            result = await self.llm_service.generate(prompt, config)

            # 创建助手消息
            assistant_msg = ChatMessage.create_assistant_message(result.content)
            thread.add_message(assistant_msg)

            # 保存线程
            self.chat_repository.save(thread)

            return {
                "ok": True,
                "reply": result.content
            }
        except Exception as e:
            logger.error(f"LLM generation failed for novel {novel_id}: {str(e)}")
            return {
                "ok": False,
                "reply": f"生成失败: {str(e)}"
            }

    async def send_message_stream(
        self,
        novel_id: str,
        message: str,
        use_cast_tools: bool = True,
        history_mode: str = "full",
        clear_thread: bool = False
    ) -> AsyncIterator[Dict[str, Any]]:
        """发送消息（流式）

        Args:
            novel_id: 小说 ID
            message: 用户消息
            use_cast_tools: 是否使用 cast 工具
            history_mode: 历史模式 (full/fresh)
            clear_thread: 是否清空线程

        Yields:
            SSE 事件字典

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        # 验证小说存在
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        # 获取或创建线程
        thread = self.chat_repository.get_by_novel_id(novel_id)
        if thread is None:
            thread = ChatThread.create(novel_id)

        # 清空线程（如果需要）
        if clear_thread:
            thread.clear_messages()

        # 添加用户消息
        user_msg = ChatMessage.create_user_message(message)
        thread.add_message(user_msg)

        if self.llm_service is None:
            yield {"type": "error", "message": "LLM 未配置：请设置环境变量 ANTHROPIC_API_KEY"}
            return

        # 构建提示词
        prompt = await self._build_prompt(novel_id, thread, history_mode, use_cast_tools)

        # 流式调用 LLM
        full_content = ""
        tools: List[ToolCall] = []

        try:
            # 模拟工具调用（如果启用）
            if use_cast_tools:
                # TODO: 实际实现工具调用逻辑
                yield {
                    "type": "tool",
                    "name": "cast_get_snapshot",
                    "ok": True,
                    "detail": "获取人物关系快照"
                }

            # 流式生成内容
            config = GenerationConfig()
            async for chunk in self.llm_service.generate_stream(prompt, config):
                full_content += chunk.content
                yield {
                    "type": "chunk",
                    "text": chunk.content
                }

            # 创建助手消息
            assistant_msg = ChatMessage.create_assistant_message(full_content, tools if tools else None)
            thread.add_message(assistant_msg)

            # 保存线程
            self.chat_repository.save(thread)

            # 发送完成事件
            yield {"type": "done"}

        except Exception as e:
            logger.error(f"Stream generation failed for novel {novel_id}: {str(e)}")
            yield {
                "type": "error",
                "message": f"生成失败: {str(e)}"
            }

    async def clear_thread(self, novel_id: str, digest_too: bool = False) -> None:
        """清空聊天线程

        Args:
            novel_id: 小说 ID
            digest_too: 是否同时删除摘要文件

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        # 验证小说存在
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        # 获取线程
        thread = self.chat_repository.get_by_novel_id(novel_id)

        if thread is not None:
            # 清空消息
            thread.clear_messages()
            self.chat_repository.save(thread)

        # 删除摘要文件（如果需要）
        if digest_too:
            # TODO: 实现删除 context_digest.md 的逻辑
            digest_path = f"novels/{novel_id}/chat/context_digest.md"
            # self.storage.delete(digest_path)
            pass

    async def _build_prompt(
        self,
        novel_id: str,
        thread: ChatThread,
        history_mode: str,
        use_cast_tools: bool
    ) -> Prompt:
        """构建聊天提示词

        Args:
            novel_id: 小说 ID
            thread: 聊天线程
            history_mode: 历史模式
            use_cast_tools: 是否使用工具

        Returns:
            Prompt 对象
        """
        # 获取小说信息
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))

        # 构建系统消息
        system_parts = [f"你是《{novel.title}》的创作助手。"]

        # 添加 Bible 信息
        if bible and bible.characters:
            char_info = "\n".join([
                f"- {char.name}: {char.description}"
                for char in bible.characters
            ])
            system_parts.append(f"\n主要人物：\n{char_info}")

        if bible and bible.world_settings:
            setting_info = "\n".join([
                f"- {setting.name}: {setting.description}"
                for setting in bible.world_settings
            ])
            system_parts.append(f"\n世界设定：\n{setting_info}")

        if use_cast_tools:
            system_parts.append("\n你可以使用工具来查询和更新人物关系、故事知识等信息。")

        system_message = "".join(system_parts)

        # 构建用户消息（包含历史）
        if history_mode == "full" and len(thread.messages) > 1:
            # 包含历史消息
            history = "\n\n".join([
                f"{msg.role}: {msg.content}"
                for msg in thread.messages[:-1]  # 排除最后一条（刚添加的用户消息）
            ])
            user_message = f"历史对话：\n{history}\n\n当前问题：\n{thread.messages[-1].content}"
        else:
            # 仅当前消息
            user_message = thread.messages[-1].content

        return Prompt(system=system_message, user=user_message)
