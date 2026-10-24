import json
from collections import Counter

import pytest

from ingest import universe
from ingest.build_universe import build


def test_committed_file_is_valid_and_matches_the_builder():
    on_disk = json.loads(universe.PATH.read_text(encoding="utf-8"))
    assert on_disk == build(), "universe.json is stale: run python -m ingest.build_universe"
    assert len(universe.load_universe()) == 50


def test_ids_do_not_leak_sector_or_order():
    companies = universe.load_universe()
    by_id = sorted(companies, key=lambda c: c["company_id"])
    first_ten = Counter(c["sector"] for c in by_id[:10])
    assert max(first_ten.values()) < 8, "anon IDs look sorted by sector"
    assert [c["ticker"] for c in by_id] != sorted(c["ticker"] for c in by_id), "anon IDs look alphabetical"


def test_held_out_and_train_are_disjoint_and_cover_everything():
    held, train = universe.held_out_ids(), universe.train_ids()
    assert len(held) == 10 and len(train) == 40
    assert not held & train


def test_held_out_has_distress_candidates_and_resilient_names():
    companies = universe.load_universe()
    held = [c for c in companies if c["held_out"]]
    groups = Counter(c["covid_group"] for c in held)
    assert groups["hit"] >= 3 and groups["resilient"] >= 1


def test_validator_reports_every_problem_at_once():
    companies = universe.load_universe()
    bad = [dict(c) for c in companies[:48]]
    bad[0]["covid_group"] = "nope"
    bad[1]["sector"] = "Financials"
    with pytest.raises(ValueError) as e:
        universe.validate(bad)
    msg = str(e.value)
    assert "expected 50" in msg and "bad covid_group" in msg and "not supported" in msg
