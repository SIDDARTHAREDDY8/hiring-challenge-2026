#!/usr/bin/env python3
"""
Type definitions for the bounds matching system.
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol
import fitz


@dataclass
class Bounds:
    """Normalized bounding box coordinates (0.0 to 1.0)."""

    page: int
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "x": round(self.x, 6),
            "y": round(self.y, 6),
            "width": round(self.width, 6),
            "height": round(self.height, 6),
        }


@dataclass
class ComponentMatch:
    """A matched component of a combined entity."""

    text: str
    bounds: Optional[Bounds]

    def to_dict(self) -> dict:
        return {"text": self.text, "bounds": self.bounds.to_dict() if self.bounds else None}


@dataclass
class MatchedEntity:
    """Result of matching an entity to PDF bounds."""

    entity_name: str
    entity_type: str
    match_strategy: str
    confidence: float
    bounds: Optional[Bounds]
    component_matches: list[ComponentMatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "match_strategy": self.match_strategy,
            "confidence": round(self.confidence, 4),
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "component_matches": [c.to_dict() for c in self.component_matches],
        }


@dataclass
class BoundsResult:
    """Result from a matching strategy."""

    success: bool
    bounds: Optional[Bounds]
    confidence: float
    components: list[ComponentMatch] = field(default_factory=list)
    strategy_name: str = ""


@dataclass
class MatchStatistics:
    """Statistics about matching results."""

    total_entities: int
    matched: int
    partial_matched: int
    unmatched: int
    strategies_used: dict[str, int]


class MatchStrategy(Protocol):
    """Protocol defining the interface for matching strategies."""

    def match(self, entity: str, pdf_doc: fitz.Document) -> BoundsResult:
        """Match an entity and return bounds result."""
        ...

    @property
    def name(self) -> str:
        """Strategy name for reporting."""
        ...
