"""
故事结构节点领域模型

支持四级叙事结构：
- Part (部)
- Volume (卷)
- Act (幕)
- Chapter (章) - 通过 chapters 表关联
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class NodeType(str, Enum):
    """节点类型"""
    PART = "part"      # 部
    VOLUME = "volume"  # 卷
    ACT = "act"        # 幕
    CHAPTER = "chapter"  # 章


@dataclass
class StoryNode:
    """故事结构节点"""
    id: str
    novel_id: str
    node_type: NodeType
    number: int
    title: str
    order_index: int
    parent_id: Optional[str] = None
    description: Optional[str] = None

    # 章节范围（仅用于 part/volume/act）
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    chapter_count: int = 0

    # 章节内容（仅用于 chapter 类型）
    content: Optional[str] = None
    word_count: int = 0
    status: str = "draft"  # draft, completed, reviewed

    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """类型转换"""
        if isinstance(self.node_type, str):
            self.node_type = NodeType(self.node_type)
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if isinstance(self.updated_at, str):
            self.updated_at = datetime.fromisoformat(self.updated_at)

    @property
    def level(self) -> int:
        """获取层级（1=部, 2=卷, 3=幕, 4=章）"""
        return {
            NodeType.PART: 1,
            NodeType.VOLUME: 2,
            NodeType.ACT: 3,
            NodeType.CHAPTER: 4
        }[self.node_type]

    @property
    def icon(self) -> str:
        """获取图标"""
        return {
            NodeType.PART: "📚",
            NodeType.VOLUME: "📖",
            NodeType.ACT: "🎬",
            NodeType.CHAPTER: "📄"
        }[self.node_type]

    @property
    def display_name(self) -> str:
        """显示名称"""
        type_names = {
            NodeType.PART: "部",
            NodeType.VOLUME: "卷",
            NodeType.ACT: "幕",
            NodeType.CHAPTER: "章"
        }
        return f"第{self.number}{type_names[self.node_type]}：{self.title}"

    def update_chapter_range(self, start: int, end: int):
        """更新章节范围"""
        self.chapter_start = start
        self.chapter_end = end
        self.chapter_count = end - start + 1 if start and end else 0
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "novel_id": self.novel_id,
            "parent_id": self.parent_id,
            "node_type": self.node_type.value,
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "order_index": self.order_index,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "level": self.level,
            "icon": self.icon,
            "display_name": self.display_name
        }

        # 章节范围（仅用于 part/volume/act）
        if self.node_type != NodeType.CHAPTER:
            result.update({
                "chapter_start": self.chapter_start,
                "chapter_end": self.chapter_end,
                "chapter_count": self.chapter_count
            })

        # 章节内容（仅用于 chapter）
        if self.node_type == NodeType.CHAPTER:
            result.update({
                "content": self.content,
                "word_count": self.word_count,
                "status": self.status
            })

        return result


@dataclass
class StoryTree:
    """故事结构树"""
    novel_id: str
    nodes: List[StoryNode] = field(default_factory=list)

    def add_node(self, node: StoryNode):
        """添加节点"""
        self.nodes.append(node)

    def get_node(self, node_id: str) -> Optional[StoryNode]:
        """获取节点"""
        return next((n for n in self.nodes if n.id == node_id), None)

    def get_children(self, parent_id: Optional[str] = None) -> List[StoryNode]:
        """获取子节点"""
        return [n for n in self.nodes if n.parent_id == parent_id]

    def get_by_type(self, node_type: NodeType) -> List[StoryNode]:
        """按类型获取节点"""
        return [n for n in self.nodes if n.node_type == node_type]

    def to_tree_dict(self) -> List[Dict[str, Any]]:
        """转换为树形结构字典"""
        def build_tree(parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
            children = sorted(
                self.get_children(parent_id),
                key=lambda n: n.order_index
            )
            result = []
            for child in children:
                node_dict = child.to_dict()
                node_dict["children"] = build_tree(child.id)
                result.append(node_dict)
            return result

        return build_tree(None)
