"""Glossary data models and profiles."""

import uuid
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from bookbridge.config.constants import GlossaryCategory, MatchType


class GlossaryTerm(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    glossary_id: str = "default"
    source: str
    target: str
    category: GlossaryCategory = GlossaryCategory.GENERAL
    priority: int = 100  # Higher number = higher priority
    match_type: MatchType = MatchType.EXACT
    case_sensitive: bool = False
    locked: bool = True  # Strict deterministic replacement
    enabled: bool = True
    notes: Optional[str] = None

    @property
    def length_weight(self) -> int:
        """Weight for sorting matches (longer terms match first to prevent collision)."""
        return len(self.source)


class GlossaryProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Profile"
    description: str = ""
    genre: str = "General"  # e.g., 'Xianxia', 'Xuanhuan', 'LitRPG', 'Fantasy'
    enabled_categories: List[GlossaryCategory] = Field(
        default_factory=lambda: list(GlossaryCategory)
    )
    terms: List[GlossaryTerm] = Field(default_factory=list)
    custom_rules: Dict[str, str] = Field(default_factory=dict)
    version: int = 1

    def active_terms(self) -> List[GlossaryTerm]:
        return [t for t in self.terms if t.enabled and t.category in self.enabled_categories]
