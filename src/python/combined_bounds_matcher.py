#!/usr/bin/env python3
"""
Combined Bounds Matcher - challenge implementation.

Orchestrates the three matching strategies (partial, aggregation, fuzzy)
behind a strategy-pattern factory with auto-selection per entity type and
a fallback chain, plus result caching.

Pipeline per entity:
  1. Cache lookup.
  2. Exact verbatim match (strategy "exact", confidence 1.0).
  3. Entity-type-specific strategy chain; accept the first strategy whose
     result is a solid match (confidence >= 0.5).
  4. Otherwise fall back to the best weak result (confidence >= 0.15).
  5. Otherwise report unmatched (strategy "none", confidence 0.0).
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Make the repository root importable so the `src.python...` package imports
# resolve whether this file is run as a script or imported under pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fitz  # PyMuPDF

from src.python.base.pdf_bounds_extractor_base import PDFBoundsExtractor
from src.python.base.types import (
    Bounds,
    BoundsResult,
    ComponentMatch,
    MatchedEntity,
    MatchStatistics,
)
from src.python.strategies import AggregationMatcher, FuzzyMatcher, PartialMatcher


class MatcherFactory:
    """
    Factory (ARCHITECTURE.md design pattern) mapping entity types to an
    ordered strategy chain: the primary strategy plus fallbacks.
    """

    _CHAINS = {
        "KPI": ("aggregation", "partial", "fuzzy"),
        "DATE": ("partial", "fuzzy", "aggregation"),
        "ORGANIZATION": ("partial", "aggregation", "fuzzy"),
    }
    _DEFAULT_CHAIN = ("partial", "fuzzy", "aggregation")

    @staticmethod
    def chain_for(entity_type: str) -> tuple[str, ...]:
        """Ordered strategy names for an entity type."""
        return MatcherFactory._CHAINS.get(entity_type.upper(), MatcherFactory._DEFAULT_CHAIN)


class CombinedBoundsMatcher:
    """
    Main matcher class that orchestrates different matching strategies.

    Selects the appropriate strategy chain based on entity type, falls back
    through the chain on failure, scores confidence, and caches results.
    """

    #: Confidence >= this counts as a solid match (stops the fallback chain).
    SOLID_MATCH_CONFIDENCE = 0.5
    #: Confidence >= this is still reported as a (partial) match.
    WEAK_MATCH_CONFIDENCE = 0.15

    def __init__(self, pdf_path: str):
        """
        Initialize the matcher with a PDF document.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = Path(pdf_path)
        self.pdf_doc = fitz.open(str(self.pdf_path))
        self.base_extractor = PDFBoundsExtractor(str(self.pdf_path))

        self.strategies = {
            "partial": PartialMatcher(self.base_extractor),
            "aggregation": AggregationMatcher(self.base_extractor),
            "fuzzy": FuzzyMatcher(self.base_extractor),
        }

        # Cache: (entity_name, entity_type) -> MatchedEntity
        self._cache: dict[tuple[str, str], MatchedEntity] = {}

    def match_entity(self, entity_name: str, entity_type: str) -> MatchedEntity:
        """
        Match a single entity and return its bounds.

        Args:
            entity_name: The entity text to match (e.g., "49.99% On-Time Delivery Rate")
            entity_type: The type of entity (e.g., "KPI", "DATE", "ORGANIZATION")

        Returns:
            MatchedEntity with bounds and confidence
        """
        cache_key = (entity_name, entity_type)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Exact verbatim match first - cheapest and most confident.
        exact_bounds = self.base_extractor.find_bounds_normalized(entity_name)
        if exact_bounds is not None:
            result = MatchedEntity(
                entity_name=entity_name,
                entity_type=entity_type,
                match_strategy="exact",
                confidence=1.0,
                bounds=exact_bounds,
                component_matches=[ComponentMatch(text=entity_name, bounds=exact_bounds)],
            )
            self._cache[cache_key] = result
            return result

        # 2-3. Strategy chain with fallback.
        best: Optional[BoundsResult] = None
        for strategy_name in MatcherFactory.chain_for(entity_type):
            strategy = self.strategies[strategy_name]
            candidate = strategy.match(entity_name, self.pdf_doc)
            if candidate.success and candidate.confidence >= self.SOLID_MATCH_CONFIDENCE:
                best = candidate
                break
            if candidate.success and (
                best is None or candidate.confidence > best.confidence
            ):
                best = candidate

        if best is not None and best.confidence >= self.WEAK_MATCH_CONFIDENCE:
            result = MatchedEntity(
                entity_name=entity_name,
                entity_type=entity_type,
                match_strategy=best.strategy_name,
                confidence=best.confidence,
                bounds=best.bounds,
                component_matches=best.components,
            )
        else:
            # 5. Nothing found: graceful degradation, confidence 0.
            result = MatchedEntity(
                entity_name=entity_name,
                entity_type=entity_type,
                match_strategy="none",
                confidence=0.0,
                bounds=None,
                component_matches=[],
            )

        self._cache[cache_key] = result
        return result

    def match_all(self, entities: list[dict]) -> dict:
        """
        Match all entities and return comprehensive results.

        Args:
            entities: List of entity dicts with 'name' and 'type' keys

        Returns:
            Dictionary with matched_entities and statistics
        """
        matched_entities = []
        strategies_used = {}

        for entity in entities:
            result = self.match_entity(
                entity_name=entity["name"], entity_type=entity["type"]
            )
            matched_entities.append(result.to_dict())

            # Track strategy usage
            strategy = result.match_strategy
            strategies_used[strategy] = strategies_used.get(strategy, 0) + 1

        # Calculate statistics
        matched = sum(1 for e in matched_entities if e["confidence"] > 0.5)
        partial = sum(1 for e in matched_entities if 0 < e["confidence"] <= 0.5)
        unmatched = sum(1 for e in matched_entities if e["confidence"] == 0)

        return {
            "matched_entities": matched_entities,
            "statistics": {
                "total_entities": len(entities),
                "matched": matched,
                "partial_matched": partial,
                "unmatched": unmatched,
                "strategies_used": strategies_used,
            },
        }

    def close(self):
        """Close the PDF document."""
        self.base_extractor.close()
        self.pdf_doc.close()


def main():
    """
    Main entry point - process entities and generate output.

    Paths resolve from the repository root (two levels above this file),
    so the script runs from any working directory.
    """
    repo_root = Path(__file__).resolve().parents[2]
    input_path = repo_root / "input" / "entities_to_match.json"
    with open(input_path) as f:
        data = json.load(f)

    entities = data["entities"]
    pdf_path = repo_root / "input" / data["pdf_file"]

    # Process entities
    started = time.perf_counter()
    matcher = CombinedBoundsMatcher(str(pdf_path))
    results = matcher.match_all(entities)
    matcher.close()
    elapsed_ms = (time.perf_counter() - started) * 1000

    # Save output
    output_path = repo_root / "output" / "matched_bounds.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    stats = results["statistics"]
    print(f"Results saved to {output_path}")
    print(f"Matched: {stats['matched']}/{stats['total_entities']} "
          f"(partial: {stats['partial_matched']}, unmatched: {stats['unmatched']})")
    print(f"Strategies used: {stats['strategies_used']}")
    print(f"Elapsed: {elapsed_ms:.0f} ms "
          f"({elapsed_ms / max(1, stats['total_entities']):.0f} ms/entity)")
    for e in results["matched_entities"]:
        b = e["bounds"]
        loc = f"p{b['page']} ({b['x']:.2f},{b['y']:.2f})" if b else "no bounds"
        print(f"  [{e['match_strategy']:>11}] {e['confidence']:.2f}  {e['entity_name']}  {loc}")


if __name__ == "__main__":
    main()
