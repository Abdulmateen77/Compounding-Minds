"""The 5-minute check and the split-proof share-count history."""
from datetime import date

import pytest

from metrics.tests import factory as F
from research import live, quick_check
from research.report import build_report

AFTER = date(2019, 3, 1)
PROFILE = {"name": "Synthetic Co", "ticker": "SYN", "exchange": "Nasdaq", "market": "US", "cik": 1}


@pytest.fixture(autouse=True)
def _reset():
    yield
    F.reset()


def _fact(accn, filed, start, end, val):
    return {"form": "10-K", "accn": accn, "filed": filed, "start": start, "end": end, "val": val}


def test_a_stock_split_does_not_look_like_dilution():
    # a 10-for-1 split in 2024: the 2025 10-K restates its comparatives, the 2023 10-K does not
    rows = [_fact("old", "2023-02-20", "2020-01-01", "2020-12-31", 100), _fact("old", "2023-02-20", "2021-01-01", "2021-12-31", 100),
            _fact("old", "2023-02-20", "2022-01-01", "2022-12-31", 99),
            _fact("new", "2025-02-20", "2022-01-01", "2022-12-31", 990), _fact("new", "2025-02-20", "2023-01-01", "2023-12-31", 985),
            _fact("new", "2025-02-20", "2024-01-01", "2024-12-31", 980)]
    hist = live._share_history({"facts": {"us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": rows}}}}})
    values = [h["value"] for h in hist]
    assert [h["end"][:4] for h in hist] == ["2020", "2021", "2022", "2023", "2024"]
    assert values[0] == pytest.approx(1000) and values[-1] == 980            # the old years scaled onto the new basis


def test_the_quick_check_runs_its_five_tests_and_labels_what_it_cannot_check():
    F.install(F.build_facts())
    r = build_report("anon_001", AFTER, PROFILE, share_history=[{"end": "2016-12-31", "value": 100.0}, {"end": "2017-12-31", "value": 99.0},
                                                                 {"end": "2018-12-31", "value": 98.0}])
    q = r["quick_check"]
    assert q["applies"] and [i["key"] for i in q["items"]] == ["debt_to_equity", "roce", "sales_growth", "promoter", "dilution"]
    by = {i["key"]: i for i in q["items"]}
    assert by["promoter"]["result"] == "unknown"
    assert by["sales_growth"]["result"] == "pass"                            # the synthetic company grows every year
    assert by["dilution"]["result"] == "pass" and "buybacks" in by["dilution"]["found"]
    assert by["debt_to_equity"]["result"] in ("pass", "partial", "fail") and q["verdict"]


def test_banks_and_insurers_are_told_the_check_does_not_apply():
    F.install(F.build_facts())
    r = build_report("anon_001", AFTER, {**PROFILE, "sic": "6021"})
    assert r["quick_check"]["applies"] is False and "banks" in r["quick_check"]["note"]
