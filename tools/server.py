"""MCP server around `Tools` (BRIEF_HERMES H1).

    tools = Tools(company_id, as_of, metrics_fn=get_metrics)
    server = build_server(tools)       # one server per agent run
    ...                                # after the run: AgentCall.tool_calls = tools.budget.used

Building the server opens no network and no database. The tool functions only call what was
injected into `Tools`.

The brief names `mcp.server.fastmcp.FastMCP`. mcp 2.x renamed it `MCPServer`
(`mcp.server.mcpserver`), so a plain `pip install mcp` today would break that import. Both have
the same `.tool()` decorator and `list_tools()`, so we try the new name first.
"""
from __future__ import annotations

import functools
from typing import Any

from .impl import ToolError, Tools


def _server_class():
    try:
        from mcp.server.mcpserver import MCPServer  # mcp 2.x
        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x
        return FastMCP
    except ImportError as err:
        raise RuntimeError("the tools server needs the 'mcp' package: pip install mcp") from err


def _sdk_tool_error():
    """The SDK's own ToolError. Only this class gets its message to the model."""
    try:
        from mcp.server.mcpserver.exceptions import ToolError  # mcp 2.x
    except ImportError:
        from mcp.server.fastmcp.exceptions import ToolError    # mcp 1.x
    return ToolError


def _expose(fn):
    """Re-raise our ToolError as the SDK's, so the model reads the message.

    The SDK treats any other exception as a crash and tells the model only "Error executing
    tool X", which would hide the list of valid metrics (and the budget message) and log a
    traceback on every typo."""
    sdk_error = _sdk_tool_error()

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError as err:
            raise sdk_error(str(err)) from None
    return wrapper


def build_server(tools: Tools):
    """Register the four tools on a new server. None of them takes a date."""
    server = _server_class()(
        "compounding-minds-tools",
        instructions="Read-only research tools. Every answer is limited to what was public at the "
                     "analysis date, which you cannot change. Calls are limited, so use them sparingly.",
    )

    @server.tool(name="get_metric_series", description=(
        "One metric at each of the last n_quarters quarter-ends, oldest first, labelled Q-7 to Q0 "
        "(Q0 is the latest). A quarter with no value shows null."))
    @_expose
    def get_metric_series(metric: str, n_quarters: int = 8) -> list[dict[str, Any]]:
        return tools.get_metric_series(metric, n_quarters)

    @server.tool(name="get_recent_events", description=(
        "Recent filing events, newest first: form type, item codes and how many quarters ago each "
        "was filed. Optional forms filter, for example ['8-K']."))
    @_expose
    def get_recent_events(forms: list[str] | None = None, n: int = 5) -> list[dict[str, Any]]:
        return tools.get_recent_events(forms, n)

    @server.tool(name="get_macro_snapshot", description=(
        "Macro readings now: GDP growth, unemployment rate, 10y-2y yield curve and Baa credit spread."))
    @_expose
    def get_macro_snapshot() -> dict[str, Any]:
        return tools.get_macro_snapshot()

    @server.tool(name="peer_compare", description=(
        "Where this company's metric sits among same-sector peers: its value, the peer median, the "
        "peer count and a percentile. A higher percentile means a higher value, not a better one. "
        "Median and percentile are null when there are fewer than 3 peers."))
    @_expose
    def peer_compare(metric: str) -> dict[str, Any]:
        return tools.peer_compare(metric)

    return server
