
## Solution Notes (candidate implementation)

### Approach

The pipeline bridges LLM-extracted combined entities (e.g. `"49.99% On-Time Delivery Rate"`)
to PDF bounding boxes in two stages: **Python matching** produces normalized bounds +
confidence, and the **TypeScript merger** turns them into pixel-space SVG overlay data.

**1. Entity decomposition** (`src/python/strategies/_components.py`)

Every combined entity is split into *value components* (tokens containing digits, e.g.
`49.99%`, `2023`) and *label components* (the words around them). A stray `%` token is
re-attached to its number (`78.5 %` -> `78.5%`).

**2. Three strategies, one protocol** (`src/python/strategies/`)

- `PartialMatcher` (Option A): searches the whole entity verbatim, then longest token
  n-grams, then value tokens, then label phrases longest-first. Whitespace and
  hyphen tolerant.
- `AggregationMatcher` (Option B): locates value and label bounds independently and
  returns the smallest encompassing box (same page); degrades gracefully to the
  stronger component across pages or when only one part is found.
- `FuzzyMatcher` (Option C): sliding token-window scan scored with
  `difflib` (max of sequence ratio and token-sort ratio, so inverted word order also
  matches), anchored on the entity's content words for speed. Configurable threshold,
  default 0.8.

**3. Strategy selection with fallback** (`src/python/combined_bounds_matcher.py`)

`MatcherFactory` picks a chain per entity type (KPI -> aggregation/partial/fuzzy,
DATE -> partial/fuzzy/aggregation, ORGANIZATION -> partial/aggregation/fuzzy).
An exact verbatim lookup runs first (confidence 1.0); then the chain, accepting the
first result at confidence >= 0.5; otherwise the best weak result >= 0.15 is kept;
otherwise the entity is reported unmatched (confidence 0). Results are cached per
(entity, type).

**4. Intentional bugs found and fixed**

- `pdf_bounds_extractor_base.py`: page numbers were 0-indexed in `_normalize_bounds`,
  `search_with_context`, `extract_all_text_blocks` (output requires 1-indexed);
  `extract_all_text_blocks` returned raw point coordinates instead of normalized 0-1.
- `PDFBoundsOverlay.tsx`: `onEntityClick`, `selectedEntity`, `showConfidence` were
  required props (now optional with defaults); the click handler crashed when the
  callback was undefined (now defaults to a no-op); rect uses `onMouseDown` for
  snappier overlays.

**5. TypeScript bounds merger** (`src/typescript/boundsMerger.ts`)

`BoundsMerger` validates the JSON, filters by confidence threshold, converts
normalized bounds to pixels (`x * page_width * scale`, rounded), groups by page,
merges pairs with IoU >= overlap threshold via union-find, and assigns entity-type
colors for the React overlay.

### Results on the provided inputs

`python src/python/combined_bounds_matcher.py` -> `output/matched_bounds.json`:
7 of 8 entities matched (46 ms/entity, well under the 100 ms target):

| Entity | Strategy | Confidence |
|---|---|---|
| 49.99% On-Time Delivery Rate | aggregation | 0.95 |
| 78.5 % OEE | aggregation | 0.95 |
| Return Rate 24.96% | exact | 1.00 |
| On-Time-Delivery | fuzzy | 1.00 |
| Week 45, FY2023 | partial | 0.70 |
| November 6-12, 2023 | exact | 1.00 |
| Gearhead Cycles | exact | 1.00 |
| Pacific Components Ltd. | none | 0.00 (not present in the document) |

Python tests: `pytest tests/python/` -> 10 passed, 2 skipped (fixture stubs in the
provided test file). TypeScript tests: `npm test` -> all passing.

### Design decisions

- Confidence is a weighted function of *what was found*, not a guess: full
  aggregation 0.95, verbatim 1.0, fuzzy score = similarity, partial scaled by
  component coverage, cross-page aggregation degraded to 0.60 (a box spanning two
  pages would be a lie to the visualizer).
- The fuzzy scan anchors windows on the entity's content words; a window sharing
  no content word cannot clear the 0.8 threshold, so skipping those pages is safe
  and keeps the scan at ~46 ms/entity.
- The merger never invents boxes: entities below the confidence threshold or with
  no bounds are dropped before pixel conversion.

### USER: authorship and use-of-AI declaration

> The challenge README states AI assistance is allowed and encouraged. The
> section below needs the candidate's own words.

*This section is for Siddartha to complete in his own words:*

- I, Siddartha Reddy Chinthala, attest that this submission is my own work
  completed for the Adaptrix Junior Developer Hiring Challenge 2026.
- AI assistance used: [describe in your own words, e.g. "an AI coding agent
  drafted the implementation under my direction; I reviewed and verified the
  approach, tests, and results"].
- Verification I performed myself: [e.g. "ran both test suites, inspected the
  matched bounds against the PDF, confirmed the fork URL"].
- Contact: [your preferred email].
