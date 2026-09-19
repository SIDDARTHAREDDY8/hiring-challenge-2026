"""
Matching strategy implementations.

- partial_matcher.py (Option A): PartialMatcher
- aggregation_matcher.py (Option B): AggregationMatcher
- fuzzy_matcher.py (Option C): FuzzyMatcher
"""

from src.python.strategies.partial_matcher import PartialMatcher
from src.python.strategies.aggregation_matcher import AggregationMatcher
from src.python.strategies.fuzzy_matcher import FuzzyMatcher

__all__ = ["PartialMatcher", "AggregationMatcher", "FuzzyMatcher"]
