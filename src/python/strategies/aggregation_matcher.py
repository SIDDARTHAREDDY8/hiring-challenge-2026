#!/usr/bin/env python3
"""
Component Aggregation strategy (Option B).

Finds bounds for BOTH the value and label components and creates a single
synthetic bounding box encompassing them, so a combined entity can be drawn
as one highlight even though its parts live in different places.
"""

from typing import Optional

import fitz

from src.python.base.pdf_bounds_extractor_base import PDFBoundsExtractor
from src.python.base.types import Bounds, BoundsResult, ComponentMatch
from src.python.strategies._components import decompose_entity, label_phrase_candidates


def encompassing_bounds(a: Bounds, b: Bounds) -> Bounds:
    """
    Smallest rectangle containing both bounds (same-page only).

    Coordinates are normalized 0-1, so the encompassing box is simply
    min/max of the corners.
    """
    x0 = min(a.x, b.x)
    y0 = min(a.y, b.y)
    x1 = max(a.x + a.width, b.x + b.width)
    y1 = max(a.y + a.height, b.y + b.height)
    return Bounds(page=a.page, x=x0, y=y0, width=x1 - x0, height=y1 - y0)


class AggregationMatcher:
    """
    Matches by aggregating value + label component bounds.

    - Both components found on the same page: encompassing bounds,
      confidence 0.95 (0.85 when only part of the label was located).
    - Found on different pages: keep the higher-confidence component,
      confidence degraded to 0.60 (cross-page highlights are misleading).
    - Only one component found: degrade to that component, confidence 0.55.
    """

    name = "aggregation"

    _FULL_CONF = 0.95
    _PARTIAL_LABEL_CONF = 0.85
    _CROSS_PAGE_CONF = 0.60
    _SINGLE_CONF = 0.55

    def __init__(self, extractor: PDFBoundsExtractor):
        """
        Args:
            extractor: Shared base extractor bound to the PDF document.
        """
        self.extractor = extractor

    def _search(self, text: str) -> Optional[Bounds]:
        return self.extractor.find_bounds_normalized(text)

    def _find_value(self, value_components: list[str]) -> tuple[Optional[str], Optional[Bounds]]:
        """Return (component_text, bounds) for the first value component found."""
        for token in value_components:
            bounds = self._search(token)
            if bounds is not None:
                return token, bounds
        return None, None

    def _find_label(
        self, label_components: list[str]
    ) -> tuple[Optional[str], Optional[Bounds], bool]:
        """
        Return (component_text, bounds, full_label_found) for the label part.
        Tries the full label phrase first, then longest n-grams.
        """
        full_label = " ".join(label_components)
        for phrase in label_phrase_candidates(label_components):
            bounds = self._search(phrase)
            if bounds is not None:
                return phrase, bounds, phrase == full_label
        return None, None, False

    def match(self, entity: str, pdf_doc: Optional[fitz.Document] = None) -> BoundsResult:
        """
        Match an entity by aggregating its component bounds.

        Args:
            entity: The combined entity text.
            pdf_doc: Unused (kept for the MatchStrategy protocol).

        Returns:
            BoundsResult with encompassing bounds when both components match.
        """
        value_components, label_components = decompose_entity(entity)
        components: list[ComponentMatch] = []

        value_text, value_bounds = self._find_value(value_components)
        components.append(ComponentMatch(text=value_text or " ".join(value_components), bounds=value_bounds))

        label_text, label_bounds, full_label_found = self._find_label(label_components)
        components.append(
            ComponentMatch(text=label_text or " ".join(label_components), bounds=label_bounds)
        )

        found = [b for b in (value_bounds, label_bounds) if b is not None]

        if len(found) == 2:
            if value_bounds.page == label_bounds.page:
                confidence = self._FULL_CONF if full_label_found else self._PARTIAL_LABEL_CONF
                return BoundsResult(
                    True,
                    encompassing_bounds(value_bounds, label_bounds),
                    confidence,
                    components,
                    self.name,
                )
            # Cross-page: keep the stronger component, degrade confidence.
            best = max(
                (value_bounds, self._VALUE_WEIGHT),
                (label_bounds, self._LABEL_WEIGHT),
                key=lambda pair: pair[1],
            )[0]
            return BoundsResult(True, best, self._CROSS_PAGE_CONF, components, self.name)

        if len(found) == 1:
            return BoundsResult(True, found[0], self._SINGLE_CONF, components, self.name)

        return BoundsResult(False, None, 0.0, components, self.name)

    # Component priority weights used for the cross-page fallback.
    _VALUE_WEIGHT = 0.75
    _LABEL_WEIGHT = 0.65
