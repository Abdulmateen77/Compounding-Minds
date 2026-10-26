Workstream: H1   Branch: hermes/tools   Commits: 1

Done:
- `tools/impl.py`: `Tools(company_id, as_of, metrics_fn, events_fn, sector_of, universe_ids, budget)` with the four tools: `get_metric_series`, `get_recent_events`, `get_macro_snapshot`, `peer_compare`. `as_of` is fixed at construction and no tool takes a date.
- `get_metric_series` asks `metrics_fn` at each earlier calendar quarter-end at that quarter's own date, labelled Q-7..Q0. A quarter the metric could not be computed for is `null`. NaN becomes `null`, so output is always valid JSON.
- `get_recent_events` goes through `store.queries.get_events` (the date gate) and returns only `form`, `items`, `quarters_ago`. No `filed_date`, `accession` or `text_ref` leaves the module.
- `peer_compare` excludes the company itself and stays inside the sector. It skips peers with no value and returns `null` median and percentile under 3 peers.
- `ToolBudget(max_calls=5)` is shared across all four tools. The 6th call raises `ToolBudgetExceeded` and is not counted, so `budget.used` never exceeds 5 and always satisfies the `AgentCall.tool_calls` schema.
- `tools/server.py`: `build_server(tools)` registers exactly four tools on an MCP server. No network or database is touched at build time.

Files:
  tools/__init__.py, tools/impl.py, tools/server.py, tools/tests/__init__.py, tools/tests/test_tools.py
  (deleted tools/.gitkeep, as the brief says)

Tests: 47 new, 162 passing in the full suite, 13 skipped (the same 13 Postgres tests as before, no database here). Baseline before my change was 115 passed, 13 skipped.
  I mutation-checked the tests that matter most. Each of these breakages makes a test fail:
    - the series asking every point at `as_of` (look-ahead)
    - events leaking the accession
    - `peer_compare` counting the company itself
    - an off-by-one that allows a 6th call
    - removing the server's error wrapper (see Deviations, item 4)

Deviations from this brief:
1. `peer_compare` with fewer than 3 peers: the brief says "return `peer_count` and `null` for the other stats". I return the company's OWN `value` as well, and null only the peer median and percentile. The own value is the company's own number, not a peer statistic, so it identifies no other firm. This is my reading of the brief. If you meant `value` should be null too, it is a one-line change in `impl.py` (`return {"value": None, ...}`) plus one test line.
2. Details the brief left open, which I chose:
   - percentile is mid-rank 0-100 (ties count half), so 50 means the peer median and higher means a higher value, not a better one
   - `n_quarters` is capped at 1..20 and `n` events at 1..20
   - `quarters_ago` counts calendar quarters back from the quarter `as_of` falls in
   - a call that fails validation (for example an unknown metric) still costs one call from the budget, so nothing can loop on bad input for free
3. The brief says `from mcp.server.fastmcp import FastMCP`. A plain `pip install mcp` today installs mcp 2.3.0, where that module no longer exists (it raises a ModuleNotFoundError that points to a rename). It is now `mcp.server.mcpserver.MCPServer`. `server.py` tries the new name first and falls back to FastMCP, so it works on both 1.x and 2.x. I only ran it on 2.3.0, and the 1.x fallback is untested.
4. A fourth, less obvious point in mcp 2.x: any exception that is not the SDK's own `ToolError` is treated as a crash, and the model only sees "Error executing tool X". That would have hidden the list of valid metrics and the budget message. `server.py` re-raises our `ToolError` as the SDK's, so the model reads the real message. There is a test for it.

Requests (changes needed in files I may not edit):
- `requirements.txt`: add `mcp` (the comment line already lists it). Both mcp 1.x and 2.x work with `server.py`.
- `agents/runner.py` writes `tool_calls=0` in `_parse` (hardcoded). To record real usage it should take the count from `tools.budget.used`.
- `agents/gateway.py`: `LLMGateway.complete` returns plain text only, with no tool-use loop. Nothing in `agents/` can call these tools yet. Someone has to build the loop that exposes the four tools to the model and feeds results back. That is outside H1, but the tools are not used until it exists.

Wiring (how the runner should use it):
    from tools import Tools
    from tools.server import build_server
    from metrics.engine import get_metrics          # or the stub until it lands

    tools = Tools(company_id, as_of, metrics_fn=get_metrics)   # one per (agent, company, as_of)
    server = build_server(tools)
    ...                                                        # run the agent with `server` attached
    call.tool_calls = tools.budget.used                        # 0..5
  Defaults: `metrics_fn=store.stubs.get_metrics_stub`, `events_fn=store.queries.get_events` (set the backend once with `queries.set_backend(...)`), sectors and peers from `ingest/universe.json`.

Dependencies: `mcp` 2.3.0 (plus its own dependencies) in a throwaway venv outside the repo. requirements.txt is untouched.

Open questions / things I did not verify:
- I did NOT run the tools against the real `metrics.engine.get_metrics`. It is still uncommitted in the main checkout. I read it: it returns the same bundle shape plus extra `missing` and `usable` keys, which the tools ignore. My tests use a fake `metrics_fn` with that shape.
- Cost against the real engine: `peer_compare` computes the metric for every same-sector company. The largest sector has 15 firms, so one call is up to 15 metric computations. `get_metric_series` is up to 20 (the cap). Check that is fast enough for the replay.
- With the stub as `metrics_fn`, every quarter returns the same bundle re-stamped, so series come out flat. That is a property of the stub, not of the tool. It will show real movement once the real engine is plugged in.
