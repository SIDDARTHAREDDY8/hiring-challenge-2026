#!/usr/bin/env python3
"""
Partial Text Matching strategy (Option A).

Finds the bounding rect for either the value OR the label component of a
combined entity, returning the bounds of the first component found.
"""

from typing import Optional

import fitz

from src.python.base.pdf_bounds_extractor_base import PDFBoundsExtractor
from src.python.base.types import Bounds, BoundsResult, ComponentMatch
from src.python.strategies._components import (
    decompose_entity,
    label_phrase_candidates,
    token_ngrams,
)


class PartialMatcher:
    """
    Matches a combined entity by locating any single component.

    Search order (most distinctive first):
      1. Whole entity verbatim (whitespace tolerant).
      2. Longest token n-grams of the full entity ("Week 45" from
         "Week 45, FY2023").
      3. Value components ("49.99%", "2023") - usually the most unique.
      4. Label phrases, longest first ("On-Time Delivery Rate").
    """

    name = "partial"

    # Confidence weights
    _EXACT_CONF = 0.95
    _NGRAM_CONF = 0.70
    _VALUE_CONF = 0.75
    _LABEL_FULL_CONF = 0.65
    _LABEL_PART_CONF = 0.50

    def __init__(self, extractor: PDFBoundsExtractor):
        """
        Args:
            extractor: Shared base extractor bound to the PDF document.
        """
        self.extractor = extractor

    def _search(self, text: str) -> Optional[Bounds]:
        """Whitespace-tolerant bounds lookup."""
        return self.extractor.find_bounds_normalized(text)

    def match(self, entity: str, pdf_doc: Optional[fitz.Document] = None) -> BoundsResult:
        """
        Match an entity by locating any single component.

        Args:
            entity: The combined entity text.
            pdf_doc: Unused (kept for the MatchStrategy protocol); the
                extractor supplied at construction owns the document.

        Returns:
            BoundsResult with success=True when any component is found.
        """
        value_components, label_components = decompose_entity(entity)
        components: list[ComponentMatch] = []

        def locate(text: str) -> tuple[Optional[Bounds], bool]:
            bounds = self._search(text)
            components.append(ComponentMatch(text=text, bounds=bounds))
            return bounds, bounds is not None

        # 1. Whole entity verbatim.
        bounds, found = locate(entity)
        if found:
            return BoundsResult(True, bounds, self._EXACT_CONF, components, self.name)

        # 2. Longest n-grams of the full entity ("Week 45" from "Week 45, FY2023").
        for phrase in token_ngrams(entity.split()):
            if phrase == entity:
                continue
            bounds, found = locate(phrase)
            if found:
                return BoundsResult(True, bounds, self._NGRAM_CONF, components, self.name)

        # 3. Value components - the most distinctive part of a KPI.
        for token in value_components:
            bounds, found = locate(token)
            if found:
                return BoundsResult(True, bounds, self._VALUE_CONF, components, self.name)

        # 4. Label phrases, longest first.
        full_label = " ".join(label_components)
        for phrase in label_phrase_candidates(label_components):
            bounds, found = locate(phrase)
            if found:
                confidence = (
                    self._LABEL_FULL_CONF
                    if phrase == full_label
                    else self._LABEL_PART_CONF
                )
                return BoundsResult(True, bounds, confidence, components, self.name)

        return BoundsResult(False, None, 0.0, components, self.name)
