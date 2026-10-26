"""Tests for the agent tools. Pure Python: no database, no network, no LLM (BRIEF_HERMES H1)."""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from datetime import date

import pytest

from ingest.universe import load_universe
from store import queries
from store.concepts import METRIC_INPUTS
from store.stubs import _load as load_stub
from tools.impl import (AGENT_METRICS, MACRO_METRICS, MAX_QUARTERS, METRIC_OWNER, ToolBudget,
                        ToolBudgetExceeded, ToolError, Tools, _latest_quarter_end, _quarters_back)

AS_OF = date(2019, 6, 30)
YEAR = re.compile(r"\b(19|20)\d{2}\b")
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
REAL_ACCESSION = "0000320193-18-000070"   # holds a year ("18"), so it is a date leak if it escapes


# ---- fakes ------------------------------------------------------------------------------------

def make_bundle(company_id: str, agent: str, as_of: date, values: dict) -> dict:
    """Same shape as get_metrics. A None value is left out, like the real engine does."""
    return {
        "company_id": company_id, "agent": agent, "as_of": as_of.isoformat(),
        "metrics": [{"name": n, "value": v, "unit": "ratio", "as_of": as_of.isoformat(),
                     "inputs": [REAL_ACCESSION]} for n, v in values.items() if v is not None],
    }


class Recorder:
    """A metrics_fn that remembers every (company, agent, as_of) it was asked for."""

    def __init__(self, values_fn=lambda company_id, agent, as_of: {}):
        self.calls: list[tuple[str, str, date]] = []
        self._values_fn = values_fn

    def __call__(self, company_id, agent, as_of):
        self.calls.append((company_id, agent, as_of))
        return make_bundle(company_id, agent, as_of, self._values_fn(company_id, agent, as_of))


def event_row(filed: date, form: str = "8-K", items=("4.01",), company_id: str = "anon_001") -> dict:
    return {"company_id": company_id, "form": form, "items": list(items), "filed_date": filed,
            "accession": REAL_ACCESSION, "text_ref": "https://www.sec.gov/Archives/edgar/data/320193/x"}


@pytest.fixture
def events_backend():
    """Install an in-memory backend behind the real date gate, then put the old one back."""
    saved = queries._backend

    def install(*rows):
        queries.set_backend(queries.InMemoryBackend(events=rows))

    yield install
    queries.set_backend(saved)


def make_tools(metrics_fn=None, as_of: date = AS_OF, company_id: str = "anon_001", **kw) -> Tools:
    kw.setdefault("events_fn", lambda c, a, f: [])
    kw.setdefault("sector_of", {"anon_001": "A"}.get)
    kw.setdefault("universe_ids", ["anon_001"])
    return Tools(company_id, as_of, metrics_fn=metrics_fn or Recorder(), **kw)


# ---- the contract table ---------------------------------------------------------------------------

def test_metric_table_matches_the_locked_contract_and_the_stubs():
    assert set(METRIC_OWNER) == {m for ms in AGENT_METRICS.values() for m in ms}
    assert len(METRIC_OWNER) == sum(len(ms) for ms in AGENT_METRICS.values())  # no name in two agents
    assert set(METRIC_OWNER) <= set(METRIC_INPUTS)
    for agent, names in AGENT_METRICS.items():
        assert {m["name"] for b in load_stub(agent) for m in b["metrics"]} == set(names)
    assert set(MACRO_METRICS) <= set(AGENT_METRICS["scenarios"])


# ---- quarter labels ------------------------------------------------------------------------------

def test_quarter_labels_count_down_from_q0_and_end_on_the_latest_quarter():
    series = make_tools().get_metric_series("fcf_margin_ttm", 4)
    assert [p["quarter"] for p in series] == ["Q-3", "Q-2", "Q-1", "Q0"]


def test_default_series_is_eight_quarters_labelled_q_minus_7_to_q0():
    series = make_tools().get_metric_series("fcf_margin_ttm")
    assert [p["quarter"] for p in series] == ["Q-7", "Q-6", "Q-5", "Q-4", "Q-3", "Q-2", "Q-1", "Q0"]


def test_quarter_end_as_of_is_q0_itself_and_a_mid_quarter_as_of_uses_the_previous_quarter_end():
    rec = Recorder()
    make_tools(rec, as_of=date(2019, 6, 30)).get_metric_series("fcf_margin_ttm", 1)
    assert rec.calls[-1][2] == date(2019, 6, 30)
    rec = Recorder()
    make_tools(rec, as_of=date(2019, 8, 15)).get_metric_series("fcf_margin_ttm", 1)
    assert rec.calls[-1][2] == date(2019, 6, 30)  # Q3 had not ended yet
    rec = Recorder()
    make_tools(rec, as_of=date(2019, 1, 2)).get_metric_series("fcf_margin_ttm", 1)
    assert rec.calls[-1][2] == date(2018, 12, 31)


def test_series_walks_back_over_a_year_boundary_in_calendar_quarter_ends():
    rec = Recorder()
    make_tools(rec, as_of=date(2019, 3, 31)).get_metric_series("fcf_margin_ttm", 5)
    assert [c[2] for c in rec.calls] == [date(2018, 3, 31), date(2018, 6, 30), date(2018, 9, 30),
                                         date(2018, 12, 31), date(2019, 3, 31)]


def test_quarter_helpers_on_the_edges():
    assert _latest_quarter_end(date(2020, 12, 31)) == date(2020, 12, 31)
    assert _latest_quarter_end(date(2020, 3, 30)) == date(2019, 12, 31)
    assert _quarters_back(date(2020, 3, 31), 4) == date(2019, 3, 31)
    assert _quarters_back(date(2020, 3, 31), 0) == date(2020, 3, 31)


# ---- point in time -----------------------------------------------------------------------------

def test_series_never_asks_for_a_date_after_as_of_and_asks_at_each_points_own_date():
    rec = Recorder(lambda c, a, d: {"fcf_margin_ttm": float(d.toordinal())})
    series = make_tools(rec, as_of=date(2019, 8, 15)).get_metric_series("fcf_margin_ttm", 6)
    assert all(call_date <= date(2019, 8, 15) for _, _, call_date in rec.calls)
    # the value at each point is the one computed AT that point's date, not at as_of
    assert [p["value"] for p in series] == [float(c[2].toordinal()) for c in rec.calls]


def test_a_series_for_an_earlier_as_of_never_contains_a_value_that_only_existed_later():
    restated = date(2019, 9, 30)

    def values(company_id, agent, as_of):  # the figure changes once the later filing is out
        return {"fcf_margin_ttm": 1.0 if as_of >= restated else 0.5}

    early = make_tools(Recorder(values), as_of=date(2019, 6, 30)).get_metric_series("fcf_margin_ttm", 4)
    assert {p["value"] for p in early} == {0.5}
    late = make_tools(Recorder(values), as_of=date(2019, 12, 31)).get_metric_series("fcf_margin_ttm", 4)
    # points sit at 03-31, 06-30, 09-30, 12-31; the figure only changes from 09-30
    assert [p["value"] for p in late] == [0.5, 0.5, 1.0, 1.0]


def test_no_tool_asks_for_a_metric_after_as_of():
    rec = Recorder(lambda c, a, d: {n: 1.0 for n in METRIC_OWNER})
    ids = ["anon_001", "anon_002", "anon_003", "anon_004"]
    tools = make_tools(rec, as_of=date(2019, 8, 15), budget=ToolBudget(max_calls=10),
                       sector_of=lambda c: "A", universe_ids=ids)
    tools.get_metric_series("fcf_margin_ttm", 8)
    tools.get_macro_snapshot()
    tools.peer_compare("roic")
    tools.get_recent_events()
    assert rec.calls and all(d <= tools.as_of for _, _, d in rec.calls)


def test_events_filed_after_as_of_are_not_returned(events_backend):
    events_backend(event_row(date(2019, 2, 10), items=["2.02"]),
                   event_row(date(2019, 6, 30), items=["4.01"]),   # on as_of: visible
                   event_row(date(2019, 7, 1), items=["5.02"]))     # the day after: invisible
    tools = Tools("anon_001", AS_OF, events_fn=queries.get_events, metrics_fn=Recorder(),
                  sector_of={"anon_001": "A"}.get, universe_ids=["anon_001"])
    events = tools.get_recent_events()
    assert [e["items"] for e in events] == [["4.01"], ["2.02"]]
    assert [e["quarters_ago"] for e in events] == [0, 1]


def test_events_come_newest_first_are_capped_at_n_and_filtered_by_form(events_backend):
    events_backend(event_row(date(2018, 6, 30), form="10-K", items=[]),
                   event_row(date(2018, 11, 5), form="8-K", items=["2.02"]),
                   event_row(date(2019, 3, 31), form="10-Q", items=[]),
                   event_row(date(2019, 5, 6), form="8-K", items=["4.01"]))
    tools = Tools("anon_001", AS_OF, events_fn=queries.get_events, metrics_fn=Recorder(),
                  sector_of={"anon_001": "A"}.get, universe_ids=["anon_001"], budget=ToolBudget(max_calls=9))
    assert [e["form"] for e in tools.get_recent_events(n=2)] == ["8-K", "10-Q"]
    only_8k = tools.get_recent_events(forms=["8-K"])
    # as_of is in Q2 2019: the 2019-05-06 filing is Q0, the 2018-11-05 one is in Q4 2018, two quarters back
    assert [(e["form"], e["quarters_ago"]) for e in only_8k] == [("8-K", 0), ("8-K", 2)]
    assert [e["form"] for e in tools.get_recent_events(forms="10-K")] == ["10-K"]  # a bare string works


def test_quarters_ago_is_a_whole_number_of_calendar_quarters(events_backend):
    events_backend(event_row(date(2019, 6, 30)), event_row(date(2019, 3, 31)), event_row(date(2018, 6, 30)))
    got = {e["quarters_ago"] for e in make_tools(events_fn=queries.get_events).get_recent_events()}
    assert got == {0, 1, 4}


# ---- nothing that identifies a company or a date leaves the tools -----------------------------------

def test_no_tool_output_holds_a_year_an_accession_a_ticker_or_a_name(events_backend):
    events_backend(event_row(date(2018, 11, 5), items=["2.02"]), event_row(date(2019, 5, 6)))
    universe = load_universe()
    tools = Tools("anon_001", AS_OF, events_fn=queries.get_events, budget=ToolBudget(max_calls=10))  # stub metrics
    outputs = [
        tools.get_metric_series("fcf_margin_ttm", 8),
        tools.get_metric_series("interest_coverage", 4),
        tools.get_recent_events(),
        tools.get_macro_snapshot(),
        tools.peer_compare("operating_margin"),
    ]
    text = json.dumps(outputs)
    assert text.count("quarter") >= 12  # it really did produce a series, so the scan below is not empty
    assert not YEAR.search(text), YEAR.search(text)
    assert not ACCESSION.search(text)
    assert "sec.gov" not in text and "text_ref" not in text and "filed" not in text
    for c in universe:
        assert not re.search(rf"\b{re.escape(c['ticker'])}\b", text), c["ticker"]
        assert c["name"].lower() not in text.lower(), c["name"]


def test_no_tool_takes_a_date_argument_and_the_server_schemas_agree():
    for name in ("get_metric_series", "get_recent_events", "get_macro_snapshot", "peer_compare"):
        params = set(inspect.signature(getattr(Tools, name)).parameters)
        assert not params & {"as_of", "date", "when", "asof"}, (name, params)


# ---- peer_compare -------------------------------------------------------------------------------

SECTORS = {"anon_001": "A", "anon_002": "A", "anon_003": "A", "anon_004": "A", "anon_005": "A",
           "anon_006": "A", "anon_007": "B"}
PEER_VALUES = {"anon_001": 5.0, "anon_002": 1.0, "anon_003": 2.0, "anon_004": 3.0, "anon_005": 10.0,
               "anon_006": None,    # same sector, no value: skipped
               "anon_007": 999.0}   # other sector: must not count


def peer_tools(values=PEER_VALUES, sectors=SECTORS, company_id="anon_001", rec=None) -> tuple[Tools, Recorder]:
    rec = rec or Recorder(lambda c, a, d: {"roic": values[c]})
    return make_tools(rec, company_id=company_id, sector_of=sectors.get, universe_ids=list(sectors)), rec


def test_peer_compare_excludes_self_stays_in_sector_and_skips_peers_without_a_value():
    tools, rec = peer_tools()
    # peers are 002, 003, 004, 005; 006 has no value; 007 is in another sector; 001 is the company
    assert tools.peer_compare("roic") == {"value": 5.0, "peer_median": 2.5, "peer_count": 4, "percentile": 75.0}
    asked = {c[0] for c in rec.calls}
    assert "anon_007" not in asked                # never even computed for another sector
    assert all(c[2] == AS_OF for c in rec.calls)  # every peer at the same as_of


def test_peer_compare_percentile_is_mid_rank_so_ties_land_in_the_middle():
    values = {**PEER_VALUES, "anon_001": 2.0}   # ties with anon_003
    tools, _ = peer_tools(values)
    assert tools.peer_compare("roic")["percentile"] == 37.5   # (1 below + 0.5 equal) / 4


def test_peer_compare_has_null_stats_with_fewer_than_three_peers_and_never_guesses():
    two = {"anon_001": 5.0, "anon_002": 1.0, "anon_003": 2.0}
    tools, _ = peer_tools(two, {k: "A" for k in two})
    assert tools.peer_compare("roic") == {"value": 5.0, "peer_median": None, "peer_count": 2, "percentile": None}
    alone, _ = peer_tools({"anon_001": 5.0}, {"anon_001": "A"})
    assert alone.peer_compare("roic") == {"value": 5.0, "peer_median": None, "peer_count": 0, "percentile": None}


def test_peer_compare_counts_only_peers_with_a_value_when_deciding_if_there_are_enough():
    values = {"anon_001": 5.0, "anon_002": 1.0, "anon_003": 2.0, "anon_004": None, "anon_005": None}
    tools, _ = peer_tools(values, {k: "A" for k in values})
    assert tools.peer_compare("roic")["peer_count"] == 2
    assert tools.peer_compare("roic")["peer_median"] is None


def test_peer_compare_works_at_exactly_three_peers():
    three = {"anon_001": 2.0, "anon_002": 1.0, "anon_003": 2.0, "anon_004": 4.0}
    tools, _ = peer_tools(three, {k: "A" for k in three})
    assert tools.peer_compare("roic") == {"value": 2.0, "peer_median": 2.0, "peer_count": 3, "percentile": 50.0}


def test_peer_compare_when_the_company_itself_has_no_value():
    values = {**PEER_VALUES, "anon_001": None}
    tools, _ = peer_tools(values)
    assert tools.peer_compare("roic") == {"value": None, "peer_median": 2.5, "peer_count": 4, "percentile": None}


def test_peer_compare_asks_the_agent_that_owns_the_metric():
    tools, rec = peer_tools()
    tools.peer_compare("roic")
    assert {c[1] for c in rec.calls} == {"fundamentals"}
    tools2, rec2 = peer_tools(rec=Recorder(lambda c, a, d: {"current_ratio": 1.0}))
    tools2.peer_compare("current_ratio")
    assert {c[1] for c in rec2.calls} == {"risk"}


# ---- macro snapshot ------------------------------------------------------------------------------

def test_macro_snapshot_reads_the_scenarios_bundle_at_as_of():
    macro = {"gdp_growth_yoy": 0.023, "unemployment_rate": 0.037, "yield_curve_10y_2y": 0.001,
             "credit_spread_baa": 0.021, "revenue_growth_yoy": 0.08}
    rec = Recorder(lambda c, a, d: macro)
    assert make_tools(rec).get_macro_snapshot() == {k: macro[k] for k in MACRO_METRICS}
    assert rec.calls == [("anon_001", "scenarios", AS_OF)]


def test_macro_snapshot_says_none_for_a_reading_that_is_not_there():
    rec = Recorder(lambda c, a, d: {"gdp_growth_yoy": 0.02})
    snap = make_tools(rec).get_macro_snapshot()
    assert snap["gdp_growth_yoy"] == 0.02
    assert snap["unemployment_rate"] is None and snap["credit_spread_baa"] is None


# ---- series values ---------------------------------------------------------------------------------

def test_a_quarter_the_metric_could_not_be_computed_is_null_not_a_guess_and_nan_becomes_null():
    def values(c, a, d):
        return {"fcf_margin_ttm": None if d < date(2018, 12, 31) else float("nan") if d == date(2018, 12, 31) else 0.1}

    series = make_tools(Recorder(values), as_of=date(2019, 3, 31)).get_metric_series("fcf_margin_ttm", 4)
    assert [p["value"] for p in series] == [None, None, None, 0.1]
    json.dumps(series, allow_nan=False)  # would raise on a NaN


# ---- the budget -------------------------------------------------------------------------------------

def test_the_fifth_call_works_the_sixth_raises_and_all_four_tools_share_one_count():
    tools = make_tools()
    tools.get_metric_series("fcf_margin_ttm")
    tools.get_recent_events()
    tools.get_macro_snapshot()
    tools.peer_compare("roic")
    assert tools.budget.used == 4
    tools.get_metric_series("roic")                      # the 5th still works
    assert tools.budget.used == 5
    for call in (lambda: tools.get_metric_series("roic"), tools.get_recent_events,
                 tools.get_macro_snapshot, lambda: tools.peer_compare("roic")):
        with pytest.raises(ToolBudgetExceeded):
            call()
    assert tools.budget.used == 5                        # a refused call is not counted: schema allows <= 5


def test_a_call_that_fails_validation_still_costs_a_call():
    tools = make_tools()
    with pytest.raises(ToolError):
        tools.get_metric_series("not_a_metric")
    assert tools.budget.used == 1


def test_the_budget_can_be_shared_or_resized_and_budget_exceeded_is_a_tool_error():
    budget = ToolBudget(max_calls=1)
    tools = make_tools(budget=budget)
    tools.get_macro_snapshot()
    with pytest.raises(ToolError):                       # ToolBudgetExceeded is a ToolError
        tools.get_macro_snapshot()
    assert tools.budget is budget and budget.used == 1


def test_each_run_gets_its_own_default_budget():
    a, b = make_tools(), make_tools()
    a.get_macro_snapshot()
    assert (a.budget.used, b.budget.used) == (1, 0)


# ---- validation ------------------------------------------------------------------------------------

@pytest.mark.parametrize("call", [lambda t: t.get_metric_series("not_a_metric"),
                                  lambda t: t.peer_compare("not_a_metric")])
def test_an_unknown_metric_raises_tool_error_that_names_every_valid_metric(call):
    with pytest.raises(ToolError) as err:
        call(make_tools())
    for name in METRIC_OWNER:
        assert name in str(err.value)


@pytest.mark.parametrize("bad", [0, -1, MAX_QUARTERS + 1, 2.5, "8", True, None])
def test_n_quarters_must_be_a_sensible_whole_number(bad):
    with pytest.raises(ToolError):
        make_tools().get_metric_series("roic", bad)


@pytest.mark.parametrize("bad", [0, -3, 99, 1.5, "5", True])
def test_n_events_must_be_a_sensible_whole_number(bad):
    with pytest.raises(ToolError):
        make_tools().get_recent_events(n=bad)


# ---- defaults wire to the stubs and the universe ----------------------------------------------------

def test_defaults_run_end_to_end_on_the_stubs_with_no_database():
    tools = Tools("anon_001", AS_OF, events_fn=lambda c, a, f: [], budget=ToolBudget(max_calls=9))
    assert len(tools.get_metric_series("fcf_margin_ttm")) == 8
    assert set(tools.get_macro_snapshot()) == set(MACRO_METRICS)
    stats = tools.peer_compare("operating_margin")   # anon_001 is Energy: 3 firms, so 2 peers
    assert stats["peer_count"] == 2 and stats["peer_median"] is None and stats["value"] is not None
    assert tools.get_recent_events() == []


# ---- the MCP server -----------------------------------------------------------------------------------

def test_building_the_server_registers_exactly_the_four_tools():
    pytest.importorskip("mcp")
    from tools.server import build_server

    server = build_server(make_tools())
    registered = asyncio.run(server.list_tools())
    assert sorted(t.name for t in registered) == ["get_macro_snapshot", "get_metric_series",
                                                  "get_recent_events", "peer_compare"]
    for t in registered:   # mcp 1.x says inputSchema, 2.x says input_schema
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema")
        assert not set(schema.get("properties", {})) & {"as_of", "date", "when"}, t.name
        assert t.description


def test_through_the_server_the_model_reads_the_real_error_not_a_generic_crash():
    """The SDK hides the message of any exception that is not its own ToolError."""
    pytest.importorskip("mcp")
    from tools.server import _sdk_tool_error, build_server

    sdk_error = _sdk_tool_error()
    try:
        from mcp.server.mcpserver.exceptions import UnexpectedToolError as crash  # mcp 2.x
    except ImportError:
        crash = ()  # mcp 1.x has no separate crash class; the message check below still applies
    server = build_server(make_tools(budget=ToolBudget(max_calls=2)))

    async def call(name, args):
        return await server.call_tool(name, args)

    with pytest.raises(sdk_error) as bad_metric:
        asyncio.run(call("get_metric_series", {"metric": "not_a_metric"}))
    assert "valid metrics" in str(bad_metric.value) and "fcf_margin_ttm" in str(bad_metric.value)
    assert not (crash and isinstance(bad_metric.value, crash))  # an anticipated error, not a crash

    with pytest.raises(sdk_error) as out_of_budget:   # the bad call above spent 1 of 2; this is the 2nd
        asyncio.run(call("get_macro_snapshot", {}))
        asyncio.run(call("get_macro_snapshot", {}))   # the 3rd is refused
    assert "budget" in str(out_of_budget.value)
    assert not (crash and isinstance(out_of_budget.value, crash))


def test_the_server_tools_return_the_same_data_as_the_python_functions():
    pytest.importorskip("mcp")
    from tools.server import build_server

    tools = make_tools(Recorder(lambda c, a, d: {"fcf_margin_ttm": 0.25}), budget=ToolBudget(max_calls=9))
    server = build_server(tools)
    result = asyncio.run(server.call_tool("get_metric_series", {"metric": "fcf_margin_ttm", "n_quarters": 3}))
    assert not getattr(result, "is_error", False)
    text = json.dumps([getattr(c, "text", "") for c in result.content])
    assert all(q in text for q in ("Q-2", "Q-1", "Q0")) and "0.25" in text
    assert tools.budget.used == 1   # the server spends the same budget as direct calls
