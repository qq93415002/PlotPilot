"""Foreshadow Ledger API 路由"""
from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from application.services.subtext_matching_service import SubtextMatchingService
from infrastructure.persistence.repositories.file_foreshadowing_repository import FileForeshadowingRepository
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import EntityNotFoundError, InvalidOperationError
from interfaces.api.dependencies import get_foreshadowing_repository


router = APIRouter(tags=["foreshadow-ledger"])


# Request Models
class CreateSubtextEntryRequest(BaseModel):
    """创建潜台词账本条目请求"""
    entry_id: str = Field(..., description="条目 ID")
    chapter: int = Field(..., ge=1, description="章节号")
    character_id: str = Field(..., description="角色 ID")
    hidden_clue: str = Field(..., min_length=1, description="隐藏线索")
    sensory_anchors: Dict[str, str] = Field(..., description="感官锚点")


class UpdateSubtextEntryRequest(BaseModel):
    """更新潜台词账本条目请求"""
    chapter: Optional[int] = Field(None, ge=1, description="章节号")
    character_id: Optional[str] = Field(None, description="角色 ID")
    hidden_clue: Optional[str] = Field(None, min_length=1, description="隐藏线索")
    sensory_anchors: Optional[Dict[str, str]] = Field(None, description="感官锚点")
    status: Optional[str] = Field(None, description="状态：pending | consumed")
    consumed_at_chapter: Optional[int] = Field(None, ge=1, description="消费章节号")


class MatchSubtextRequest(BaseModel):
    """匹配潜台词请求"""
    current_anchors: Dict[str, str] = Field(..., description="当前场景的感官锚点")


# Response Models
class SubtextEntryResponse(BaseModel):
    """潜台词账本条目响应"""
    id: str
    chapter: int
    character_id: str
    hidden_clue: str
    sensory_anchors: Dict[str, str]
    status: str
    consumed_at_chapter: Optional[int]
    created_at: str


class MatchSubtextResponse(BaseModel):
    """匹配潜台词响应"""
    matched: bool
    entry: Optional[SubtextEntryResponse]


def _entry_to_response(entry: SubtextLedgerEntry) -> SubtextEntryResponse:
    """将 SubtextLedgerEntry 转换为响应模型"""
    return SubtextEntryResponse(
        id=entry.id,
        chapter=entry.chapter,
        character_id=entry.character_id,
        hidden_clue=entry.hidden_clue,
        sensory_anchors=entry.sensory_anchors,
        status=entry.status,
        consumed_at_chapter=entry.consumed_at_chapter,
        created_at=entry.created_at.isoformat()
    )


@router.post("/novels/{novel_id}/foreshadow-ledger", response_model=SubtextEntryResponse, status_code=201)
def create_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    request: CreateSubtextEntryRequest = ...,
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """创建潜台词账本条目"""
    try:
        # 获取或创建 ForeshadowingRegistry
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        # 创建新条目
        entry = SubtextLedgerEntry(
            id=request.entry_id,
            chapter=request.chapter,
            character_id=request.character_id,
            hidden_clue=request.hidden_clue,
            sensory_anchors=request.sensory_anchors,
            status="pending"
        )

        # 添加到注册表
        registry.add_subtext_entry(entry)
        repo.save(registry)

        return _entry_to_response(entry)

    except InvalidOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/novels/{novel_id}/foreshadow-ledger", response_model=List[SubtextEntryResponse])
def list_subtext_entries(
    novel_id: str = Path(..., description="小说 ID"),
    status: Optional[str] = None,
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """列出所有潜台词账本条目"""
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        entries = registry.subtext_entries

        # 按状态过滤
        if status:
            entries = [e for e in entries if e.status == status]

        return [_entry_to_response(e) for e in entries]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/novels/{novel_id}/foreshadow-ledger/{entry_id}", response_model=SubtextEntryResponse)
def get_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """获取单个潜台词账本条目"""
    registry = repo.get_by_novel_id(NovelId(novel_id))
    if not registry:
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

    entry = registry.get_subtext_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    return _entry_to_response(entry)


@router.put("/novels/{novel_id}/foreshadow-ledger/{entry_id}", response_model=SubtextEntryResponse)
def update_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    request: UpdateSubtextEntryRequest = ...,
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """更新潜台词账本条目"""
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        entry = registry.get_subtext_entry_by_id(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

        # 构建更新后的条目（使用 dataclass replace）
        from dataclasses import replace

        updated_entry = replace(
            entry,
            chapter=request.chapter if request.chapter is not None else entry.chapter,
            character_id=request.character_id if request.character_id is not None else entry.character_id,
            hidden_clue=request.hidden_clue if request.hidden_clue is not None else entry.hidden_clue,
            sensory_anchors=request.sensory_anchors if request.sensory_anchors is not None else entry.sensory_anchors,
            status=request.status if request.status is not None else entry.status,
            consumed_at_chapter=request.consumed_at_chapter if request.consumed_at_chapter is not None else entry.consumed_at_chapter
        )

        registry.update_subtext_entry(entry_id, updated_entry)
        repo.save(registry)

        return _entry_to_response(updated_entry)

    except InvalidOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/novels/{novel_id}/foreshadow-ledger/{entry_id}", status_code=204)
def delete_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """删除潜台词账本条目"""
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        registry.remove_subtext_entry(entry_id)
        repo.save(registry)

    except InvalidOperationError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/novels/{novel_id}/foreshadow-ledger/match", response_model=MatchSubtextResponse)
def match_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    request: MatchSubtextRequest = ...,
    repo: FileForeshadowingRepository = Depends(get_foreshadowing_repository)
):
    """查找匹配的潜台词账本条目"""
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        # 使用匹配服务查找最佳匹配
        matching_service = SubtextMatchingService()
        matched_entry = matching_service.find_best_anchor_match(
            request.current_anchors,
            registry.subtext_entries
        )

        if matched_entry:
            return MatchSubtextResponse(
                matched=True,
                entry=_entry_to_response(matched_entry)
            )
        else:
            return MatchSubtextResponse(
                matched=False,
                entry=None
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
