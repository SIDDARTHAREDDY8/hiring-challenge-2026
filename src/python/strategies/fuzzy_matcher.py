#!/usr/bin/env python3
"""
Fuzzy Matching strategy (Option C).

Handles entities whose wording does not appear verbatim anywhere: hyphen vs
space differences ("On-Time-Delivery" vs "On-Time Delivery"), reworded
phrases, and minor OCR/extraction noise. A sliding token-window scan over
each page's text is scored with difflib similarity; the best window above
the threshold wins.
"""

import difflib
import re
from typing import Optional

import fitz

from src.python.base.pdf_bounds_extractor_base import PDFBoundsExtractor
from src.python.base.types import Bounds, BoundsResult, ComponentMatch

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """
    Normalize text for similarity comparison: lowercase, collapse
    whitespace, and drop punctuation (hyphens included) so that
    "On-Time-Delivery" and "On Time Delivery" compare as equals.
    """
    text = _PUNCT_RE.sub(" ", text.lower())
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    """
    Similarity between two strings, 0.0-1.0.

    Takes the max of sequence ratio (word order matters) and token-sort
    ratio (word order ignored), so inverted entities like
    "Return Rate 24.96%" also match "24.96% Return Rate".
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = sorted(na.split()), sorted(nb.split())
    token_sort = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return max(seq, token_sort)


class FuzzyMatcher:
    """
    Fuzzy-matches an entity against sliding windows of page text.

    Window sizes cluster around the entity's word count (+/-2), which keeps
    the scan cheap: a few thousand windows per page at most.
    """

    name = "fuzzy"
    DEFAULT_THRESHOLD = 0.8

    def __init__(self, extractor: PDFBoundsExtractor, threshold: float = DEFAULT_THRESHOLD):
        """
        Args:
            extractor: Shared base extractor bound to the PDF document.
            threshold: Minimum similarity (0-1) to accept a match.
        """
        self.extractor = extractor
        self.threshold = threshold

    def _best_window(self, page_text: str, entity: str) -> tuple[Optional[str], float]:
        """
        Best (window_text, score) on one page's text.

        Windows are only opened around "anchor" positions: words of the
        page that share a content word with the entity. A window with no
        content word in common cannot reach the acceptance threshold, so
        restricting the scan this way is safe and much faster.
        """
        words = page_text.split()
        if not words:
            return None, 0.0

        entity_words = normalize(entity).split()
        entity_len = max(1, len(entity_words))
        # Content words: long words or digit-bearing tokens (the distinctive ones).
        content = {w for w in entity_words if len(w) > 3 or any(c.isdigit() for c in w)}
        if not content:
            content = set(entity_words)

        anchors = [i for i, w in enumerate(words) if normalize(w) in content]
        if not anchors:
            return None, 0.0

        # Candidate window starts: near an anchor, so the window can cover it.
        starts: set[int] = set()
        for pos in anchors:
            lo = max(0, pos - entity_len)
            hi = min(len(words), pos + 1)
            starts.update(range(lo, hi))

        best_text: Optional[str] = None
        best_score = 0.0

        for size in range(max(1, entity_len - 2), entity_len + 3):
            if size > len(words):
                continue
            for start in starts:
                if start + size > len(words):
                    continue
                window = " ".join(words[start : start + size])
                score = similarity(entity, window)
                if score > best_score:
                    best_score = score
                    best_text = window

        return best_text, best_score

    def match(
        self,
        entity: str,
        pdf_doc: Optional[fitz.Document] = None,
        threshold: Optional[float] = None,
    ) -> BoundsResult:
        """
        Fuzzy-match an entity against the document.

        Args:
            entity: The entity text to match.
            pdf_doc: Unused (kept for the MatchStrategy protocol).
            threshold: Override for the instance threshold.

        Returns:
            BoundsResult with the best window's bounds when above threshold.
        """
        limit = self.DEFAULT_THRESHOLD if threshold is None else threshold
        components: list[ComponentMatch] = []

        best_text: Optional[str] = None
        best_score = 0.0

        for page_num in range(self.extractor.num_pages):
            page_text = self.extractor.get_page_text(page_num)
            window_text, score = self._best_window(page_text, entity)
            if score > best_score:
                best_score = score
                best_text = window_text

        if best_text is not None and best_score >= limit:
            bounds = self.extractor.find_bounds_normalized(best_text)
            if bounds is None:
                # The window text came straight from the page, so a bounds
                # lookup should succeed; if it does not, treat as no match
                # rather than returning bounds for the wrong text.
                return BoundsResult(False, None, 0.0, components, self.name)
            components.append(ComponentMatch(text=best_text, bounds=bounds))
            return BoundsResult(True, bounds, round(best_score, 4), components, self.name)

        return BoundsResult(False, None, 0.0, components, self.name)
