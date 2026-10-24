"""The stub/real switch for metrics (USE_STUBS), and Postgres through queries.use_postgres."""
from datetime import date

import pytest

from eval import metrics_source as ms
from metrics.tests import factory as F
from store import queries
from store.stubs import get_metrics_stub

AFTER = date(2019, 3, 1)


@pytest.fixture(autouse=True)
def _restore_backend():
    saved = queries._backend
    yield
    queries._backend = saved


def test_default_is_stubs(monkeypatch):
    monkeypatch.delenv("USE_STUBS", raising=False)
    assert ms.real_inputs() is False
    assert ms.metrics_fn("anon_001", "fundamentals", date(2019, 6, 30)) == get_metrics_stub("anon_001", "fundamentals", date(2019, 6, 30))


@pytest.mark.parametrize("value,expected", [("0", True), ("1", False), ("", False), ("true", False)])
def test_only_use_stubs_zero_means_real(monkeypatch, value, expected):
    monkeypatch.setenv("USE_STUBS", value)
    assert ms.real_inputs() is expected


def test_real_mode_reads_the_gate_and_returns_the_real_bundle_shape(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "0")
    F.install(F.build_facts(), macro=F.build_macro())
    b = ms.metrics_fn("anon_001", "fundamentals", AFTER)
    assert b["usable"] is True and b["missing"] == [] and len(b["metrics"]) == 7
    assert b != get_metrics_stub("anon_001", "fundamentals", AFTER)


def test_real_mode_without_a_database_says_what_to_do(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "0")
    queries._backend = queries._DEFAULT_BACKEND

    def boom(*a, **k):
        raise ConnectionError("refused")
    monkeypatch.setattr(queries, "use_postgres", boom)
    with pytest.raises(RuntimeError, match="needs Postgres with the data loaded"):
        ms.metrics_fn("anon_001", "fundamentals", AFTER)


def test_a_backend_chosen_by_the_caller_is_respected(monkeypatch):
    monkeypatch.setenv("USE_STUBS", "0")
    F.install(F.build_facts())
    monkeypatch.setattr(queries, "use_postgres", lambda *a, **k: pytest.fail("must not reconnect"))
    assert queries.has_backend() and ms.metrics_fn("anon_001", "fundamentals", AFTER)["usable"] is True
