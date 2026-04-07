"""流式消息总线 - 用于自动驾驶守护进程与 SSE 接口之间的实时通信

守护进程在独立进程中运行，SSE 接口在主进程中运行。

Windows 兼容性说明：
- Windows 使用 spawn 方式创建子进程，需要 pickle 序列化参数
- multiprocessing.Manager() 对象包含弱引用，无法被 pickle
- 解决方案：使用 multiprocessing.Queue / SimpleQueue，它们可以安全序列化传递

设计：
- 主进程创建 Queue，通过参数传递给守护进程
- 守护进程调用 publish() 写入队列
- SSE 接口调用 get_chunk() 从队列读取
"""
import asyncio
import json
import multiprocessing as mp
import threading
import time
import logging
from collections import defaultdict
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# 全局队列 - 单一队列处理所有小说的流式消息
# 使用 dict 存储：novel_id -> List[chunk]
# 由于 Queue 是先进先出，我们需要在消息中携带 novel_id
_stream_queue: Optional[mp.Queue] = None
_lock = threading.Lock()
_initialized = False

# 子进程注入的队列（守护进程启动时设置）
_injected_queue: Optional[mp.Queue] = None


def init_streaming_bus() -> mp.Queue:
    """在主进程中初始化流式队列。
    
    必须在启动守护进程前调用。
    返回的 Queue 对象需要传递给守护进程。
    
    Returns:
        mp.Queue: 可跨进程传递的队列
        
    Example:
        from application.engine.services.streaming_bus import init_streaming_bus
        queue = init_streaming_bus()
        # 将 queue 传递给守护进程
    """
    global _stream_queue, _initialized
    
    if _initialized and _stream_queue is not None:
        logger.debug("[StreamingBus] 已初始化，跳过")
        return _stream_queue
    
    with _lock:
        if _initialized and _stream_queue is not None:
            return _stream_queue
        
        logger.info("[StreamingBus] 在主进程中初始化 Queue...")
        # 使用普通 Queue（可以 pickle 序列化）
        _stream_queue = mp.Queue(maxsize=5000)
        _initialized = True
        logger.info("[StreamingBus] Queue 初始化完成")
        
    return _stream_queue


def inject_stream_queue(queue: mp.Queue):
    """在子进程（守护进程）中注入队列。
    
    守护进程启动时调用，设置从主进程传入的队列。
    
    Args:
        queue: 从主进程传入的 Queue 对象
    """
    global _injected_queue
    _injected_queue = queue
    logger.info("[StreamingBus] 子进程已注入队列")


def _get_queue() -> Optional[mp.Queue]:
    """获取流式队列。
    
    主进程：返回主进程的 _stream_queue
    子进程：返回通过 inject_stream_queue 设置的 _injected_queue
    """
    global _stream_queue, _injected_queue
    
    # 优先使用注入的队列（子进程）
    if _injected_queue is not None:
        return _injected_queue
    
    # 主进程的队列
    if _stream_queue is not None:
        return _stream_queue
    
    # 尝试初始化（仅在非守护进程中有效）
    current_process = mp.current_process()
    
    if current_process.daemon:
        logger.warning(
            "[StreamingBus] 守护进程未注入队列，流式推送不可用。"
            "请确保在启动守护进程时传入 Queue。"
        )
        return None
    
    # 非守护进程：可以尝试初始化
    logger.debug("[StreamingBus] _get_queue: 队列未初始化，尝试初始化...")
    init_streaming_bus()
    return _stream_queue


class StreamingBus:
    """流式消息总线 - 发布/订阅模式（基于 multiprocessing.Queue）
    
    消息格式：
        {
            "novel_id": "novel-xxx",
            "chunk": "增量文字内容"
        }
    """
    
    def __init__(self, queue: Optional[mp.Queue] = None):
        """初始化 StreamingBus。
        
        Args:
            queue: 可选的队列对象（子进程使用）
        """
        # 如果提供了队列，注入到全局
        if queue is not None:
            inject_stream_queue(queue)
        
        # 本地订阅者（SSE 接口使用，仅主进程）
        self._subscribers: Dict[str, list] = defaultdict(list)
        # 本地读取位置追踪
        self._local_positions: Dict[str, int] = defaultdict(int)
    
    def publish(self, novel_id: str, chunk: str):
        """发布增量文字（守护进程调用）
        
        Args:
            novel_id: 小说ID
            chunk: 增量文字内容
        """
        if not chunk:
            return
        
        queue = _get_queue()
        if queue is None:
            return
        
        try:
            # 消息格式：携带 novel_id
            message = {
                "novel_id": novel_id,
                "chunk": chunk
            }
            
            # 非阻塞写入
            try:
                queue.put_nowait(message)
            except:
                # 队列满，丢弃部分旧消息后重试
                try:
                    for _ in range(100):
                        queue.get_nowait()
                except:
                    pass
                try:
                    queue.put_nowait(message)
                except:
                    pass
            
            logger.debug(f"[StreamingBus] publish: {novel_id}, {len(chunk)} chars")
        except Exception as e:
            logger.error(f"[StreamingBus] publish 失败: {e}")
    
    def subscribe(self, novel_id: str) -> asyncio.Queue:
        """订阅增量文字（SSE 接口调用）"""
        queue = asyncio.Queue(maxsize=1000)
        self._subscribers[novel_id].append(queue)
        return queue
    
    def unsubscribe(self, novel_id: str, queue: asyncio.Queue):
        """取消订阅"""
        if novel_id in self._subscribers:
            try:
                self._subscribers[novel_id].remove(queue)
            except ValueError:
                pass
    
    def get_chunk(self, novel_id: str, timeout: float = 0.05) -> Optional[str]:
        """从跨进程队列获取增量文字（非阻塞，带超时）
        
        Args:
            novel_id: 小说ID（用于过滤消息）
            timeout: 超时时间（秒）
            
        Returns:
            Optional[str]: 增量文字，如果没有则返回 None
        """
        queue = _get_queue()
        if queue is None:
            logger.debug("[StreamingBus] get_chunk: 队列不可用")
            return None
        
        # 尝试多次读取，直到找到匹配的小说消息或超时
        start_time = time.time()
        max_wait_time = timeout
        
        while (time.time() - start_time) < max_wait_time:
            try:
                # 使用短超时避免长时间阻塞
                remaining_time = max_wait_time - (time.time() - start_time)
                if remaining_time <= 0:
                    break
                    
                message = queue.get(timeout=min(remaining_time, 0.01))
                
                # 检查消息是否属于当前小说
                if isinstance(message, dict):
                    msg_novel_id = message.get("novel_id")
                    if msg_novel_id == novel_id:
                        return message.get("chunk")
                    else:
                        # 消息不属于当前小说，重新放回队列
                        # 使用非阻塞方式放回，避免死锁
                        try:
                            queue.put_nowait(message)
                        except:
                            # 如果队列已满，至少不丢失当前消息
                            logger.warning(f"[StreamingBus] 无法将消息重新放回队列，小说ID: {msg_novel_id}")
                            
                # 继续尝试获取下一条消息
                
            except Exception as e:
                # 队列为空，继续等待
                time.sleep(0.001)  # 短暂休眠避免忙等待
                
        # 超时未找到匹配消息
        return None
    
    def get_chunk_non_blocking(self, novel_id: str) -> Optional[str]:
        """非阻塞获取增量文字
        
        Args:
            novel_id: 小说ID
            
        Returns:
            Optional[str]: 增量文字，如果没有则返回 None
        """
        queue = _get_queue()
        if queue is None:
            return None
        
        # 非阻塞模式下，最多检查20条消息
        max_checks = 20
        checks = 0
        
        while checks < max_checks:
            try:
                message = queue.get_nowait()
                checks += 1
                
                if isinstance(message, dict) and message.get("novel_id") == novel_id:
                    return message.get("chunk")
                else:
                    # 消息不属于当前小说，重新放回队列
                    try:
                        queue.put_nowait(message)
                    except:
                        # 队列已满，至少不阻塞当前操作
                        logger.warning(f"[StreamingBus] get_chunk_non_blocking: 无法重新放回消息")
                        
            except:
                # 队列为空
                break
                
        return None
    
    def clear(self, novel_id: str):
        """清空指定小说的队列中的消息"""
        queue = _get_queue()
        if queue is None:
            return
        
        # 临时存储不属于该小说的消息
        temp_messages = []
        
        try:
            # 遍历队列，移除目标小说的消息
            while True:
                try:
                    message = queue.get_nowait()
                    
                    if isinstance(message, dict) and message.get("novel_id") == novel_id:
                        # 属于目标小说，丢弃
                        logger.debug(f"[StreamingBus] 清空队列: 移除小说 {novel_id} 的消息")
                    else:
                        # 不属于目标小说，暂存
                        temp_messages.append(message)
                        
                except:
                    # 队列为空，停止遍历
                    break
                    
            # 将其他小说的消息重新放回队列
            for message in temp_messages:
                try:
                    queue.put_nowait(message)
                except:
                    logger.warning(f"[StreamingBus] clear: 无法将消息重新放回队列")
                    
            logger.debug(f"[StreamingBus] 清空队列完成: {novel_id}, 保留 {len(temp_messages)} 条其他小说消息")
            
        except Exception as e:
            logger.debug(f"[StreamingBus] clear 异常: {e}")


# 全局单例
streaming_bus = StreamingBus()
