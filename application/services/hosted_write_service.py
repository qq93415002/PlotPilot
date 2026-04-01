"""托管连写：自动规划大纲 + 按章流式生成 + 可选落库，上下文由 ContextBuilder 维护。"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict

from application.services.chapter_service import ChapterService
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


class HostedWriteService:
    """多章连续托管写作（单连接 SSE 推送全程事件）。"""

    def __init__(
        self,
        workflow: AutoNovelGenerationWorkflow,
        chapter_service: ChapterService,
    ):
        self._workflow = workflow
        self._chapter = chapter_service

    def _fallback_outline(self, novel_id: str, chapter_number: int) -> str:
        dto = self._chapter.get_chapter_by_novel_and_number(novel_id, chapter_number)
        title = dto.title if dto else f"第{chapter_number}章"
        return (
            f"【托管】{title}\n\n"
            "承接已有正文与设定，推进本章情节与人物；保持人称、时态与全书一致。"
        )

    async def stream_hosted_write(
        self,
        novel_id: str,
        from_chapter: int,
        to_chapter: int,
        auto_save: bool = True,
        auto_outline: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        """按章节区间连续生成；每章先大纲（LLM 或模板），再复用 generate_chapter_stream。

        事件在单章事件上增加 ``chapter``；并可能发出 ``session`` / ``chapter_start`` /
        ``outline`` / ``saved``。
        """
        if from_chapter < 1 or to_chapter < 1 or to_chapter < from_chapter:
            yield {"type": "error", "message": "invalid chapter range"}
            return

        total = to_chapter - from_chapter + 1
        yield {
            "type": "session",
            "novel_id": novel_id,
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "total": total,
        }

        for index, n in enumerate(range(from_chapter, to_chapter + 1), start=1):
            yield {"type": "chapter_start", "chapter": n, "index": index, "total": total}

            if auto_outline:
                try:
                    outline = await self._workflow.suggest_outline(novel_id, n)
                except Exception as e:
                    logger.warning("suggest_outline raised: %s", e)
                    outline = self._fallback_outline(novel_id, n)
            else:
                outline = self._fallback_outline(novel_id, n)

            yield {"type": "outline", "chapter": n, "text": outline}

            async for ev in self._workflow.generate_chapter_stream(novel_id, n, outline):
                merged: Dict[str, Any] = dict(ev)
                merged["chapter"] = n
                yield merged

                if ev.get("type") == "done" and auto_save:
                    content = ev.get("content") or ""
                    try:
                        self._chapter.update_chapter_by_novel_and_number(
                            novel_id, n, content
                        )
                        yield {"type": "saved", "chapter": n, "ok": True}
                    except EntityNotFoundError:
                        yield {
                            "type": "saved",
                            "chapter": n,
                            "ok": False,
                            "message": "章节不存在，请先在结构中创建该章",
                        }
                    except Exception as ex:
                        yield {
                            "type": "saved",
                            "chapter": n,
                            "ok": False,
                            "message": str(ex),
                        }

                if ev.get("type") == "error":
                    return

        yield {"type": "session_done", "novel_id": novel_id}
