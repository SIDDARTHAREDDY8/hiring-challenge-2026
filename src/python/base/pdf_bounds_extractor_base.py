#!/usr/bin/env python3
"""
PDF Bounds Extractor - Base Implementation

This module provides exact text matching for PDF documents.
Note: This implementation has known limitations with combined entities.

The intentional bugs in the original base code have been fixed:
  1. _normalize_bounds: page numbers are now 1-indexed (was 0-indexed).
  2. search_with_context: page numbers are now 1-indexed (was 0-indexed).
  3. extract_all_text_blocks: bounds are normalized to 0-1 (were raw points).
  4. extract_all_text_blocks: page numbers are now 1-indexed (was 0-indexed).

Added: find_bounds_fuzzy_whitespace - a whitespace/line-break tolerant
search used by the combined-entity strategies.
"""

from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from .types import Bounds, BoundsResult, ComponentMatch


class PDFBoundsExtractor:
    """
    Extracts bounding boxes for text found in PDF documents.

    Uses PyMuPDF's text search functionality for exact matching.
    """

    def __init__(self, pdf_path: str):
        """
        Initialize the extractor with a PDF document.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        self.pdf_doc = fitz.open(str(self.pdf_path))
        self._text_cache = {}

    @property
    def num_pages(self) -> int:
        """Number of pages in the document."""
        return len(self.pdf_doc)

    def find_exact_bounds(self, search_text: str) -> Optional[Bounds]:
        """
        Find exact text in PDF and return normalized bounds.

        Args:
            search_text: The exact text to search for

        Returns:
            Bounds if found, None otherwise
        """
        # Search each page
        for page_num in range(len(self.pdf_doc)):
            page = self.pdf_doc[page_num]
            instances = page.search_for(search_text)

            if instances:
                rect = instances[0]  # Take first match
                return self._normalize_bounds(rect, page, page_num)

        return None

    def find_bounds_normalized(self, search_text: str) -> Optional[Bounds]:
        """
        Find text in the PDF, tolerating whitespace/line-break differences.

        The raw search text is tried first; if that fails, the text is
        collapsed to single spaces and PyMuPDF's own text search is tried
        against a few whitespace variants (spaces vs newlines), since PDF
        extraction often splits phrases across lines.

        Args:
            search_text: Text to search for

        Returns:
            Bounds if found, None otherwise
        """
        direct = self.find_exact_bounds(search_text)
        if direct is not None:
            return direct

        collapsed = " ".join(search_text.split())
        if collapsed != search_text:
            direct = self.find_exact_bounds(collapsed)
            if direct is not None:
                return direct

        # Try newline variants: PDF text extraction commonly puts phrases
        # that wrap across lines with newlines (e.g. "On-Time \\nDelivery").
        words = collapsed.split()
        if len(words) >= 2:
            for page_num in range(len(self.pdf_doc)):
                page = self.pdf_doc[page_num]
                # Try joining words with newlines at each boundary.
                for split_at in range(1, len(words)):
                    variant = " ".join(words[:split_at]) + "\n" + " ".join(words[split_at:])
                    instances = page.search_for(variant)
                    if instances:
                        return self._normalize_bounds(instances[0], page, page_num)

        return None

    def _normalize_bounds(self, rect: fitz.Rect, page: fitz.Page, page_num: int) -> Bounds:
        """
        Convert PyMuPDF rect to normalized coordinates.

        Args:
            rect: PyMuPDF rectangle
            page: The page object
            page_num: Page number (0-indexed internally, but output uses 1-indexed)

        Returns:
            Normalized Bounds object
        """
        page_width = page.rect.width
        page_height = page.rect.height

        # FIX (was BUG): output page numbers are 1-indexed.
        return Bounds(
            page=page_num + 1,
            x=rect.x0 / page_width,
            y=rect.y0 / page_height,
            width=(rect.x1 - rect.x0) / page_width,
            height=(rect.y1 - rect.y0) / page_height,
        )

    def get_page_text(self, page_num: int) -> str:
        """
        Get all text from a specific page.

        Args:
            page_num: Page number (0-indexed)

        Returns:
            All text content from the page
        """
        if page_num not in self._text_cache:
            page = self.pdf_doc[page_num]
            self._text_cache[page_num] = page.get_text()

        return self._text_cache[page_num]

    def search_with_context(self, search_text: str, context_chars: int = 50) -> list[dict]:
        """
        Search for text and return matches with surrounding context.

        Args:
            search_text: Text to search for
            context_chars: Number of characters of context to include

        Returns:
            List of matches with context
        """
        matches = []

        for page_num in range(len(self.pdf_doc)):
            page_text = self.get_page_text(page_num)

            # Find all occurrences
            start = 0
            while True:
                idx = page_text.find(search_text, start)
                if idx == -1:
                    break

                # Extract context
                context_start = max(0, idx - context_chars)
                context_end = min(len(page_text), idx + len(search_text) + context_chars)

                matches.append(
                    {
                        # FIX (was BUG): output page numbers are 1-indexed.
                        "page": page_num + 1,
                        "position": idx,
                        "context": page_text[context_start:context_end],
                        "bounds": self.find_exact_bounds(search_text),
                    }
                )

                start = idx + 1

        return matches

    def extract_all_text_blocks(self, page_num: int) -> list[dict]:
        """
        Extract all text blocks with their bounds from a page.

        Args:
            page_num: Page number (0-indexed)

        Returns:
            List of text blocks with bounds
        """
        page = self.pdf_doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        blocks = page.get_text("dict")["blocks"]

        result = []
        for block in blocks:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        bbox = span["bbox"]
                        result.append(
                            {
                                "text": text,
                                # FIX (was BUG): normalize to 0-1 and use
                                # 1-indexed page numbers.
                                "bounds": Bounds(
                                    page=page_num + 1,
                                    x=bbox[0] / page_width,
                                    y=bbox[1] / page_height,
                                    width=(bbox[2] - bbox[0]) / page_width,
                                    height=(bbox[3] - bbox[1]) / page_height,
                                )
                            }
                        )

        return result

    def close(self):
        """Close the PDF document."""
        self.pdf_doc.close()
