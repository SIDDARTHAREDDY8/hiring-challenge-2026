#!/usr/bin/env python3
"""
Shared helpers for the combined-entity matching strategies.

An LLM-extracted entity such as "49.99% On-Time Delivery Rate" is a
*combined* entity: a value component ("49.99%") glued to a label component
("On-Time Delivery Rate"). These helpers split an entity into those parts so
each strategy can search for them independently.
"""

import re

_VALUE_RE = re.compile(r"\d")


def merge_stray_percent(tokens: list[str]) -> list[str]:
    """Attach a standalone '%' token to the preceding token ('78.5 %' -> '78.5%')."""
    merged: list[str] = []
    for token in tokens:
        if token == "%" and merged:
            merged[-1] = merged[-1] + "%"
        else:
            merged.append(token)
    return merged


def decompose_entity(entity: str) -> tuple[list[str], list[str]]:
    """
    Split an entity into (value_components, label_components).

    A component counts as a "value" if it contains a digit (e.g. "49.99%",
    "2023", "6-12,"); everything else is a label component.

    Args:
        entity: The extracted entity text.

    Returns:
        (value_components, label_components) token lists.
    """
    tokens = merge_stray_percent(entity.split())
    value = [t for t in tokens if _VALUE_RE.search(t)]
    label = [t for t in tokens if not _VALUE_RE.search(t)]
    return value, label


def label_phrase_candidates(label_tokens: list[str]) -> list[str]:
    """
    Candidate search phrases for the label part, longest first.

    Includes whitespace-normalized variants and hyphen-to-space variants so
    "On-Time-Delivery" also matches "On-Time Delivery" / "On Time Delivery".
    """
    phrases: list[str] = []
    seen: set[str] = set()

    def add(phrase: str) -> None:
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    n = len(label_tokens)
    # All contiguous n-grams, longest first.
    for length in range(n, 0, -1):
        for start in range(0, n - length + 1):
            add(" ".join(label_tokens[start : start + length]))

    # Hyphen/dash-insensitive variants (longest n-grams first).
    for phrase in list(phrases):
        dashed = phrase.replace("-", " ").replace("–", " ").replace("—", " ")
        collapsed = " ".join(dashed.split())
        add(collapsed)

    return phrases


def token_ngrams(tokens: list[str]) -> list[str]:
    """All contiguous n-grams of the full entity token list, longest first."""
    phrases: list[str] = []
    seen: set[str] = set()
    n = len(tokens)
    for length in range(n, 0, -1):
        for start in range(0, n - length + 1):
            phrase = " ".join(tokens[start : start + length])
            if phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return phrases
