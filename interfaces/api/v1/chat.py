"""Chat API 路由"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
from typing import Optional

from application.services.chat_service import ChatService
from interfaces.api.dependencies import get_chat_service
from domain.shared.exceptions import EntityNotFoundError


logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# Request Models
class SendMessageRequest(BaseModel):
    """发送消息请求"""
    message: str = Field(..., description="用户消息")
    use_cast_tools: bool = Field(True, description="是否使用 cast 工具")
    history_mode: str = Field("full", description="历史模式 (full/fresh)")
    clear_thread: bool = Field(False, description="是否清空线程")


class ClearThreadRequest(BaseModel):
    """清空线程请求"""
    digest_too: bool = Field(False, description="是否同时删除摘要")


# Response Models
class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    role: str
    content: str
    ts: str
    meta: Optional[dict] = None


class GetMessagesResponse(BaseModel):
    """获取消息响应"""
    messages: list[MessageResponse]


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    ok: bool
    reply: str


class SimpleResponse(BaseModel):
    """简单响应"""
    ok: bool
    message: str


# Routes
@router.get("/novels/{novel_id}/chat/messages", response_model=GetMessagesResponse)
async def get_messages(
    novel_id: str,
    service: ChatService = Depends(get_chat_service)
):
    """获取聊天消息

    Args:
        novel_id: 小说 ID
        service: 聊天服务

    Returns:
        消息列表

    Raises:
        HTTPException: 如果获取失败
    """
    try:
        result = service.get_messages(novel_id)
        return GetMessagesResponse(messages=result["messages"])
    except ValidationError:
        logger.exception("聊天消息响应校验失败 novel_id=%s", novel_id)
        return GetMessagesResponse(messages=[])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/novels/{novel_id}/chat", response_model=SendMessageResponse)
async def send_message(
    novel_id: str,
    request: SendMessageRequest,
    service: ChatService = Depends(get_chat_service)
):
    """发送消息（非流式）

    Args:
        novel_id: 小说 ID
        request: 发送消息请求
        service: 聊天服务

    Returns:
        助手回复

    Raises:
        HTTPException: 如果小说不存在或发送失败
    """
    try:
        result = await service.send_message(
            novel_id=novel_id,
            message=request.message,
            use_cast_tools=request.use_cast_tools,
            history_mode=request.history_mode,
            clear_thread=request.clear_thread
        )
        return SendMessageResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/novels/{novel_id}/chat/stream")
async def send_message_stream(
    novel_id: str,
    request: SendMessageRequest,
    service: ChatService = Depends(get_chat_service)
):
    """发送消息（流式 SSE）

    Args:
        novel_id: 小说 ID
        request: 发送消息请求
        service: 聊天服务

    Returns:
        SSE 流

    Raises:
        HTTPException: 如果小说不存在或发送失败
    """
    async def event_generator():
        """SSE 事件生成器"""
        try:
            async for event in service.send_message_stream(
                novel_id=novel_id,
                message=request.message,
                use_cast_tools=request.use_cast_tools,
                history_mode=request.history_mode,
                clear_thread=request.clear_thread
            ):
                # 格式化为 SSE
                import json
                yield f"data: {json.dumps(event)}\n\n"
        except EntityNotFoundError as e:
            import json
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        except Exception as e:
            import json
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/novels/{novel_id}/chat/clear", response_model=SimpleResponse)
async def clear_thread(
    novel_id: str,
    request: ClearThreadRequest,
    service: ChatService = Depends(get_chat_service)
):
    """清空聊天线程

    Args:
        novel_id: 小说 ID
        request: 清空线程请求
        service: 聊天服务

    Returns:
        操作结果

    Raises:
        HTTPException: 如果小说不存在或清空失败
    """
    try:
        await service.clear_thread(
            novel_id=novel_id,
            digest_too=request.digest_too
        )
        return SimpleResponse(ok=True, message="清空成功")
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
