"""`get_metrics`: the one call an agent's metric bundle comes from (README 4.5).

    get_metrics("anon_007", "fundamentals", date(2019, 6, 30))
    -> {"company_id", "agent", "as_of", "metrics": [{name, value, unit, as_of, inputs}],
        "missing": [names that could not be computed], "usable": bool}

Same shape as `store.stubs.get_metrics_stub`, plus `missing` and `usable`. A metric that cannot
be computed from what was filed by `as_of` is left OUT and named in `missing`; it is never
guessed. A bundle with 3 or more missing metrics is not `usable`, and the replay skips that
company for that agent and quarter (metrics/SPEC.md section 1).
"""
from __future__ import annotations

from datetime import date

from . import fundamentals, risk, scenarios
from .context import Context

MAX_MISSING = 3     # at this many missing metrics the bundle is not usable
DECIMALS = 4        # values are rounded so a model can copy them back exactly (evidence check)

# Order matters: it is the order the agent sees. Units match store/stubs.
AGENT_METRICS: dict[str, dict[str, str]] = {
    "fundamentals": {"fcf_margin_ttm": "ratio", "fcf_margin_qoq_change": "ratio", "operating_margin": "ratio",
                     "roic": "ratio", "debt_to_ebitda": "x", "fcf_slope_8q": "ratio/q",
                     "capex_to_revenue": "ratio"},
    "risk": {"interest_coverage": "x", "current_ratio": "x", "cash_runway_quarters": "q",
             "dividend_cut_history_5y": "count", "auditor_changes_5y": "count", "going_concern_hits": "count",
             "leverage_trend_8q": "x/q"},
    "scenarios": {"revenue_growth_yoy": "ratio", "revenue_growth_mean_5y": "ratio",
                  "revenue_growth_std_5y": "ratio", "revenue_macro_beta": "x", "gdp_growth_yoy": "ratio",
                  "unemployment_rate": "ratio", "yield_curve_10y_2y": "ratio", "credit_spread_baa": "ratio"},
}
_COMPUTE = {"fundamentals": fundamentals.compute, "risk": risk.compute, "scenarios": scenarios.compute}


def get_metrics(company_id: str, agent: str, as_of: date) -> dict:
    if agent not in _COMPUTE:
        raise KeyError(f"no metrics for agent {agent!r}; have {sorted(_COMPUTE)}")
    results = _COMPUTE[agent](Context(company_id, as_of))
    metrics, missing = [], []
    for name, unit in AGENT_METRICS[agent].items():
        r = results.get(name)
        if r is None:
            missing.append(name)
            continue
        metrics.append({"name": name, "value": round(r.value, DECIMALS), "unit": unit,
                        "as_of": as_of.isoformat(), "inputs": sorted(r.inputs)})
    return {"company_id": company_id, "agent": agent, "as_of": as_of.isoformat(),
            "metrics": metrics, "missing": missing, "usable": len(missing) < MAX_MISSING}
