"""Where the eval and the replay get their metrics: the stub bundles, or the real `get_metrics`.

    USE_STUBS=0   real metrics from Postgres through the date gate (metrics/, store/queries.py)
    otherwise     the hand-written stub bundles (store/stubs), the default

`real_inputs()` is True only for USE_STUBS=0, and it still needs `--live` before a run counts as real
(eval/run.py), so stub runs can never be written as the official held-out report.

In real mode the first call connects to DATABASE_URL, unless a backend was already chosen (a test, or
`queries.use_postgres(conn)` called by the caller).
"""
from __future__ import annotations

import os
from datetime import date

from store.stubs import get_metrics_stub


def real_inputs() -> bool:
    return os.environ.get("USE_STUBS") == "0"


def _ensure_store() -> None:
    from store import queries
    if not queries.has_backend():
        try:
            queries.use_postgres()
        except Exception as e:  # noqa: BLE001 - say what to do, not just which driver failed
            raise RuntimeError(f"USE_STUBS=0 needs Postgres with the data loaded ({e.__class__.__name__}). "
                               "Start it (docker compose up -d), load the data (python -m ingest), "
                               "or unset USE_STUBS to use the stub metrics.") from e


def metrics_fn(company_id: str, agent: str, as_of: date) -> dict:
    if not real_inputs():
        return get_metrics_stub(company_id, agent, as_of)
    _ensure_store()
    from metrics import get_metrics
    return get_metrics(company_id, agent, as_of)
