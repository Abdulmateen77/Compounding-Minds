"""principles/*.md are part of every prompt and every reflection. A rule that points at a metric the
agent is never given invites an evidence the parser will reject, so check the contract here."""
import re
from pathlib import Path

import pytest

from store.concepts import METRIC_INPUTS
from store.stubs import _load  # the stubs define which metrics each agent is shown

PRINCIPLES = Path(__file__).resolve().parents[2] / "principles"
LINE = re.compile(r"^([a-z]+)\.(\d{2}) \| ([^|]+) \| ([^|]+) \| (.+)$")
METRIC_TOKEN = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
# investor file -> the MVP agent whose metric bundle it must match
INVESTOR_AGENT = {"buffett": "fundamentals", "munger": "risk", "dalio": "scenarios"}


def _rules(investor):
    rows = []
    for line in (PRINCIPLES / f"{investor}.md").read_text().splitlines():
        m = LINE.match(line)
        if m:
            rows.append(m.groups())
    return rows


@pytest.mark.parametrize("investor", ["buffett", "munger", "dalio", "graham"])
def test_five_to_ten_rules_with_sequential_ids_and_sources(investor):
    rules = _rules(investor)
    assert 5 <= len(rules) <= 10, f"{investor}: {len(rules)} rules"
    assert [int(r[1]) for r in rules] == list(range(1, len(rules) + 1))
    assert all(r[0] == investor and r[4].strip() for r in rules)


@pytest.mark.parametrize("investor,agent", INVESTOR_AGENT.items())
def test_how_to_check_only_names_metrics_the_agent_is_shown(investor, agent):
    shown = {m["name"] for b in _load(agent) for m in b["metrics"]}
    for _, num, _, check, _ in _rules(investor):
        for token in METRIC_TOKEN.findall(check):
            assert token in shown, f"{investor}.{num} checks {token}, which the {agent} agent is not given"


def test_every_shown_metric_is_a_known_metric():
    for agent in ("fundamentals", "risk", "scenarios"):
        assert {m["name"] for b in _load(agent) for m in b["metrics"]} <= set(METRIC_INPUTS)
