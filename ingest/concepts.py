"""Adapter over Person A's concept map (`store/concepts.py`). Ingest owns no concept decisions.

`CONCEPT_MAP` is A's `CONCEPTS` (`{key: Concept(key, tags, unit, kind, cumulative_in_10q, note)}`).
parse.py only needs `.tags` (best first) and `.unit`, so any object with those two attributes works
as a `concept_map=` override (see `Concept` below, kept for tests and ad-hoc maps).
"""
from __future__ import annotations

from typing import NamedTuple

from store.concepts import ALL_TAGS, CONCEPTS, MACRO_SERIES, METRIC_INPUTS, TAG_TO_CONCEPT, resolve_concept

CONCEPT_MAP = CONCEPTS
MACRO_SERIES_IDS: tuple[str, ...] = tuple(v[0] for v in MACRO_SERIES.values())
VINTAGED_SERIES: frozenset[str] = frozenset(v[0] for v in MACRO_SERIES.values() if v[1])


class Concept(NamedTuple):
    """Minimal override shape for `concept_map=`: tags (best first) and unit."""
    tags: tuple[str, ...]
    unit: str


def needed_concepts() -> set[str]:
    """Concept keys that any metric in `METRIC_INPUTS` reads (excludes event: and macro: inputs)."""
    return {i for ins in METRIC_INPUTS.values() for i in ins if not i.startswith(("event:", "macro:"))}


def needed_macro_series() -> set[str]:
    """FRED ids required by `macro:<name>` metric inputs."""
    return {MACRO_SERIES[i.split(":", 1)[1]][0] for ins in METRIC_INPUTS.values() for i in ins
            if i.startswith("macro:")}


def coverage_gaps(concept_map=None) -> dict[str, list[str]]:
    """What the metric spec needs that the map does not fetch (for the A handoff). Empty = no gaps."""
    cmap = CONCEPT_MAP if concept_map is None else concept_map
    return {"concepts": sorted(needed_concepts() - set(cmap)),
            "macro": sorted(needed_macro_series() - set(MACRO_SERIES_IDS))}
