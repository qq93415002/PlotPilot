from typing import List
from domain.shared.base_entity import BaseEntity
from domain.bible.value_objects.character_id import CharacterId
from domain.shared.exceptions import InvalidOperationError


class Character(BaseEntity):
    """人物实体"""

    def __init__(
        self,
        id: CharacterId,
        name: str,
        description: str,
        relationships: List[str] = None
    ):
        super().__init__(id.value)
        self.character_id = id
        self.name = name
        self.description = description
        self.relationships = relationships or []

    def add_relationship(self, relationship: str) -> None:
        """添加关系"""
        if relationship in self.relationships:
            raise InvalidOperationError(f"Relationship already exists: {relationship}")
        self.relationships.append(relationship)

    def remove_relationship(self, relationship: str) -> None:
        """删除关系"""
        if relationship not in self.relationships:
            raise InvalidOperationError(f"Relationship not found: {relationship}")
        self.relationships.remove(relationship)

    def update_description(self, description: str) -> None:
        """更新描述"""
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")
        self.description = description
