"""
故事结构 Repository
"""

import json
import sqlite3
from typing import List, Optional
from datetime import datetime

from domain.structure.story_node import StoryNode, StoryTree, NodeType


class StoryNodeRepository:
    """故事结构节点仓储"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_node(self, row: sqlite3.Row) -> StoryNode:
        """将数据库行转换为 StoryNode"""
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}

        # 基础字段
        node_data = {
            "id": row["id"],
            "novel_id": row["novel_id"],
            "parent_id": row["parent_id"],
            "node_type": NodeType(row["node_type"]),
            "number": row["number"],
            "title": row["title"],
            "description": row["description"],
            "order_index": row["order_index"],
            "metadata": metadata,
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"])
        }

        # 章节范围字段（part/volume/act）
        if row["node_type"] != "chapter":
            node_data.update({
                "chapter_start": row["chapter_start"],
                "chapter_end": row["chapter_end"],
                "chapter_count": row["chapter_count"] or 0
            })

        # 章节内容字段（chapter）
        if row["node_type"] == "chapter":
            node_data.update({
                "content": row["content"],
                "word_count": row["word_count"] or 0,
                "status": row["status"] or "draft"
            })

        return StoryNode(**node_data)

    def get_by_id(self, node_id: str) -> Optional[StoryNode]:
        """根据 ID 获取节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM story_nodes WHERE id = ?",
                (node_id,)
            )
            row = cursor.fetchone()
            return self._row_to_node(row) if row else None
        finally:
            conn.close()

    def get_by_novel(self, novel_id: str) -> List[StoryNode]:
        """获取小说的所有节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM story_nodes WHERE novel_id = ? ORDER BY order_index",
                (novel_id,)
            )
            return [self._row_to_node(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_tree(self, novel_id: str) -> StoryTree:
        """获取小说的完整结构树"""
        nodes = self.get_by_novel(novel_id)
        tree = StoryTree(novel_id=novel_id)
        for node in nodes:
            tree.add_node(node)
        return tree

    def get_children(self, parent_id: Optional[str], novel_id: str) -> List[StoryNode]:
        """获取子节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if parent_id is None:
                cursor.execute(
                    "SELECT * FROM story_nodes WHERE novel_id = ? AND parent_id IS NULL ORDER BY order_index",
                    (novel_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM story_nodes WHERE parent_id = ? ORDER BY order_index",
                    (parent_id,)
                )
            return [self._row_to_node(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save(self, node: StoryNode) -> StoryNode:
        """保存节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            node.updated_at = datetime.now()

            cursor.execute("""
                INSERT OR REPLACE INTO story_nodes (
                    id, novel_id, parent_id, node_type, number, title,
                    description, order_index, chapter_start, chapter_end,
                    chapter_count, content, word_count, status, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.id,
                node.novel_id,
                node.parent_id,
                node.node_type.value,
                node.number,
                node.title,
                node.description,
                node.order_index,
                node.chapter_start if node.node_type != NodeType.CHAPTER else None,
                node.chapter_end if node.node_type != NodeType.CHAPTER else None,
                node.chapter_count if node.node_type != NodeType.CHAPTER else 0,
                node.content if node.node_type == NodeType.CHAPTER else None,
                node.word_count if node.node_type == NodeType.CHAPTER else 0,
                node.status if node.node_type == NodeType.CHAPTER else None,
                json.dumps(node.metadata, ensure_ascii=False),
                node.created_at.isoformat(),
                node.updated_at.isoformat()
            ))
            conn.commit()
            return node
        finally:
            conn.close()

    def save_batch(self, nodes: List[StoryNode]) -> List[StoryNode]:
        """批量保存节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now()

            for node in nodes:
                node.updated_at = now
                cursor.execute("""
                    INSERT OR REPLACE INTO story_nodes (
                        id, novel_id, parent_id, node_type, number, title,
                        description, order_index, chapter_start, chapter_end,
                        chapter_count, content, word_count, status, metadata,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.id,
                    node.novel_id,
                    node.parent_id,
                    node.node_type.value,
                    node.number,
                    node.title,
                    node.description,
                    node.order_index,
                    node.chapter_start if node.node_type != NodeType.CHAPTER else None,
                    node.chapter_end if node.node_type != NodeType.CHAPTER else None,
                    node.chapter_count if node.node_type != NodeType.CHAPTER else 0,
                    node.content if node.node_type == NodeType.CHAPTER else None,
                    node.word_count if node.node_type == NodeType.CHAPTER else 0,
                    node.status if node.node_type == NodeType.CHAPTER else None,
                    json.dumps(node.metadata, ensure_ascii=False),
                    node.created_at.isoformat(),
                    node.updated_at.isoformat()
                ))

            conn.commit()
            return nodes
        finally:
            conn.close()

    def delete(self, node_id: str) -> bool:
        """删除节点（级联删除子节点）"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM story_nodes WHERE id = ?", (node_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_chapter_ranges(self, novel_id: str):
        """更新所有节点的章节范围（基于子节点计算）"""
        tree = self.get_tree(novel_id)

        def update_node_range(node: StoryNode):
            """递归更新节点的章节范围"""
            children = tree.get_children(node.id)

            if not children:
                # 叶子节点（幕），从关联的章节计算
                return

            # 非叶子节点，从子节点计算
            child_starts = [c.chapter_start for c in children if c.chapter_start]
            child_ends = [c.chapter_end for c in children if c.chapter_end]

            if child_starts and child_ends:
                node.update_chapter_range(min(child_starts), max(child_ends))
                self.save(node)

            # 递归更新子节点
            for child in children:
                update_node_range(child)

        # 从根节点开始更新
        root_nodes = tree.get_children(None)
        for root in root_nodes:
            update_node_range(root)
