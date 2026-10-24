import json
from datetime import date

import pytest

from agents.adapters import ADAPTERS, get_adapter
from agents.frozen import FrozenUpdater
from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import scripted_llm
from agents.runner import build_messages
from agents.specs import SPECS
from store.stubs import get_metrics_stub


def test_one_adapter_per_agent():
    assert set(ADAPTERS) == {"fundamentals", "risk", "scenarios", "valuation", "moat"}
    with pytest.raises(KeyError):
        get_adapter("nope")


def test_each_adapter_has_its_own_identity_and_stable_system_prompt():
    ids = {a.identity for a in ADAPTERS.values()}
    prompts = {a.system_prompt() for a in ADAPTERS.values()}
    assert len(ids) == len(prompts) == len(ADAPTERS)
    for agent, ad in ADAPTERS.items():
        m = get_metrics_stub("anon_002", agent, date(2020, 3, 31))
        live = build_messages(agent, "anon_002", date(2020, 3, 31), m, ["a lesson"])[0]["content"]
        assert ad.system_prompt() == live  # lessons and metrics never reach the system prompt
        assert SPECS[agent].investor in ad.identity


@pytest.mark.parametrize("agent", ["fundamentals", "risk", "scenarios", "valuation", "moat"])
def test_adapter_runs_an_agent(agent, tmp_path):
    m = get_metrics_stub("anon_001", agent, date(2019, 6, 30))
    call = get_adapter(agent).run("anon_001", date(2019, 6, 30), m, ScriptedGateway(scripted_llm), FakeModelUpdater(tmp_path))
    assert call is not None and call.agent == agent


def test_frozen_twin_never_learns(tmp_path):
    frozen = FrozenUpdater("m")
    assert frozen.lessons("fundamentals") == []
    before = frozen.get_model_version("fundamentals")
    ref = frozen.submit_corrections("fundamentals", [])
    assert frozen.get_model_version("fundamentals") == before == "frozen:m+fundamentals-v0"
    assert frozen.status(ref).state == "applied" and not ref.fallback


def test_moat_has_its_own_principles_so_fundamentals_prompt_is_unchanged():
    from agents.reflection import principle_ids
    assert SPECS["moat"].investor == SPECS["fundamentals"].investor == "buffett"
    assert SPECS["moat"].principles_file == "buffett_moat"
    assert principle_ids("buffett_moat") and not principle_ids("buffett_moat") & principle_ids("buffett")
    fund = ADAPTERS["fundamentals"].system_prompt()
    assert "moat." not in fund and "moat.01" in ADAPTERS["moat"].system_prompt()


@pytest.mark.parametrize("agent", ["valuation", "moat"])
def test_stretch_agents_have_5_to_10_principles_and_stub_cases(agent):
    from agents.reflection import principle_ids
    from store.stubs import list_stub_cases
    assert 5 <= len(principle_ids(SPECS[agent].principles_file)) <= 10
    assert len(list_stub_cases(agent)) == 5
