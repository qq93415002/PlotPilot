from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SceneDirectorAnalyzeRequest(BaseModel):
    """Request model for scene director analysis.

    Attributes:
        chapter_number: Chapter number (must be >= 1)
        outline: Scene outline text (must not be empty or whitespace-only)
    """
    chapter_number: int = Field(ge=1)
    outline: str = Field(min_length=1)

    @field_validator("outline", mode="before")
    @classmethod
    def outline_not_empty(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("outline cannot be empty or whitespace only")
        return v


class SceneDirectorAnalysis(BaseModel):
    """Analysis result model with default values for optional fields.

    This model is used internally for analysis operations where fields may not
    be populated. All fields have sensible defaults to support partial analysis.

    Attributes:
        characters: List of character names (defaults to empty list)
        locations: List of location names (defaults to empty list)
        action_types: List of action types (defaults to empty list)
        trigger_keywords: List of trigger keywords (defaults to empty list)
        emotional_state: Emotional state description (defaults to empty string)
        pov: Point of view character (defaults to None)
    """
    characters: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    action_types: List[str] = Field(default_factory=list)
    trigger_keywords: List[str] = Field(default_factory=list)
    emotional_state: str = ""
    pov: Optional[str] = None


class SceneDirectorAnalyzeResponse(SceneDirectorAnalysis):
    """Response model for scene director analysis.

    Inherits from SceneDirectorAnalysis to maintain consistency while allowing
    for future response-specific fields or validation logic. Currently identical
    to parent but provides semantic clarity that this is a response object.
    """
    pass
