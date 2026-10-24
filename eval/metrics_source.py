"""Where the eval gets its metrics. Flip to the real store when Person A's get_metrics lands.

Today only the stub store exists (store/stubs). `real_inputs()` stays False until the real
`get_metrics` and the real grader rules are wired in, and that keeps stub runs from ever
being written as the official held-out report.
"""
from __future__ import annotations

from store.stubs import get_metrics_stub as metrics_fn  # noqa: F401


def real_inputs() -> bool:
    return False
