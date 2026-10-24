"""Read-only data layer for the dashboard (README 11).

The dashboard never calls live APIs (CLAUDE.md rule 5). It reads the tables the agents and
eval write (agents/run_store.py) from one of two places with the same row shapes:

    postgres            DATABASE_URL, tables from store/schema.sql + schemas/run_extras.sql
    <directory>         offline JSONL tables, e.g. data/runs from `python -m eval.run --save data/runs`

Everything here is plain pandas so it can be tested without Streamlit.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from agents.run_store import TABLES
from agents.synthesizer import DIRECTION, committee_score, confidence_for, trailing_weights, verdict_for
from schemas import AgentCall, Grade

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSONL_DIR = ROOT / "data" / "runs"

AGENTS = ("fundamentals", "risk", "scenarios", "valuation", "moat")
INVESTOR = {"fundamentals": "Buffett", "moat": "Buffett (moat)", "valuation": "Graham",
            "risk": "Munger", "scenarios": "Dalio"}
QUESTION = {
    "fundamentals": "FCF and margins improve next quarter?",
    "valuation": "Market-implied growth above what gets delivered?",
    "moat": "Gross margin holds within ±2pts over 4 quarters?",
    "risk": "Distress event (auditor change, dividend cut, going concern) in 12 months?",
    "scenarios": "Revenue bucket over the next 4 quarters (bull / base / bear)?",
}
COVID_WINDOW = (date(2020, 1, 1), date(2020, 12, 31))
HORIZON_QUARTERS = {"next_quarter": 1, "4_quarters": 4, "12_months": 4}
# A's official held-out report first (TASKS B6 path), then where eval.run actually writes today.
HELDOUT_CANDIDATES = (ROOT / "eval" / "out" / "heldout.json", ROOT / "eval" / "reports" / "heldout_report.json",
                      ROOT / "data" / "eval_preview" / "heldout_report.json")


@dataclass
class Bundle:
    """All dashboard tables, already flattened into DataFrames."""
    source: str
    runs: pd.DataFrame
    calls: pd.DataFrame
    grades: pd.DataFrame
    corrections: pd.DataFrame
    snapshots: pd.DataFrame
    eval_results: pd.DataFrame
    companies: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["company_id", "sector"]))

    @property
    def empty(self) -> bool:
        return self.calls.empty

    def provenance(self) -> dict:
        """The most recent run's provenance block (offline_demo, real_results, metrics, llm)."""
        if self.runs.empty:
            return {}
        cfg = self.runs.sort_values("started_at").iloc[-1]["config"] or {}
        return cfg.get("provenance", {}) or {}

    def uses_fallback_updater(self) -> bool:
        """True when lessons were applied by the FakeModelUpdater, not Mubit (README 10: label it)."""
        refs = self.corrections.get("mubit_ref", pd.Series(dtype=str)).dropna().astype(str)
        models = self.calls.get("model", pd.Series(dtype=str)).astype(str)
        return bool(refs.str.startswith("fake:").any() or models.str.startswith("fallback/").any())


# ---- loading -----------------------------------------------------------------

def _read_jsonl(directory: Path) -> dict[str, list[dict]]:
    out = {}
    for t in TABLES:
        p = directory / f"{t}.jsonl"
        out[t] = [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []
    return out


def _read_postgres(dsn: str) -> dict[str, list[dict]]:
    import psycopg
    from psycopg.rows import dict_row

    out = {}
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=3) as conn:
        for t in TABLES:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {t}")  # table names come from a fixed tuple
                out[t] = cur.fetchall()
    return out


def resolve_source(requested: str | None = None) -> str:
    """'postgres' when asked for (or DATABASE_URL is reachable), otherwise the JSONL directory."""
    requested = requested or os.environ.get("DASHBOARD_SOURCE")
    if requested:
        return requested
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        try:
            import psycopg
            with psycopg.connect(dsn, connect_timeout=2) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM calls LIMIT 1")
            return "postgres"
        except Exception:
            pass
    return str(DEFAULT_JSONL_DIR)


def load(source: str) -> Bundle:
    raw = _read_postgres(os.environ["DATABASE_URL"]) if source == "postgres" else _read_jsonl(Path(source))
    b = build_bundle(source, raw)
    b.companies = _load_companies(source)
    return b


def _load_companies(source: str) -> pd.DataFrame:
    """company_id + sector from the companies table (Postgres) or companies.jsonl; empty if absent."""
    cols = ["company_id", "sector"]
    try:
        if source == "postgres":
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=3) as conn, \
                    conn.cursor() as cur:
                cur.execute("SELECT company_id, sector FROM companies")
                rows = cur.fetchall()
        else:
            p = Path(source) / "companies.jsonl"
            rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return pd.DataFrame(columns=cols)


def build_bundle(source: str, raw: dict[str, list[dict]]) -> Bundle:
    runs = pd.DataFrame(raw.get("runs", []), columns=["run_id", "kind", "config", "started_at"])
    runs["started_at"] = runs["started_at"].astype(str)

    calls = pd.DataFrame([_flatten_call(r) for r in raw.get("calls", [])],
                         columns=["call_id", "run_id", "agent", "company_id", "as_of", "arm", "model",
                                  "question_id", "answer", "probability", "confidence", "reasoning",
                                  "evidence", "principles_used", "payload"])
    calls["as_of"] = pd.to_datetime(calls["as_of"]).dt.date

    grades = pd.DataFrame(raw.get("grades", []),
                          columns=["call_id", "graded_at", "outcome", "correct", "brier", "evidence",
                                   "resolution_date"])
    grades = grades.rename(columns={"evidence": "grade_evidence"})

    corrections = pd.DataFrame(raw.get("corrections", []),
                               columns=["correction_id", "call_id", "agent", "summary", "payload",
                                        "mubit_ref", "applied_at"])
    if not corrections.empty:
        corrections["error_type"] = corrections["payload"].map(lambda p: p.get("error_type"))
        corrections["principle_refs"] = corrections["payload"].map(lambda p: p.get("principle_refs", []))
        corrections["as_of"] = pd.to_datetime(corrections["payload"].map(lambda p: p.get("as_of"))).dt.date
        corrections["company_id"] = corrections["payload"].map(lambda p: p.get("company_id"))

    snapshots = pd.DataFrame(raw.get("snapshots", []),
                             columns=["run_id", "agent", "variant", "as_of", "n_calls", "n_correct", "accuracy", "brier", "model"])
    snapshots["as_of"] = pd.to_datetime(snapshots["as_of"]).dt.date

    eval_results = pd.DataFrame(raw.get("eval_results", []),
                                columns=["run_id", "generated_at", "real_results", "report"])
    return Bundle(source, runs, calls, grades, corrections, snapshots, eval_results)


def _flatten_call(row: dict) -> dict:
    p = row["payload"]
    model = p.get("model", "")
    return {"call_id": row["call_id"], "run_id": row["run_id"], "agent": row["agent"],
            "company_id": row["company_id"], "as_of": row["as_of"],
            "arm": arm_for_model(model), "model": model,
            "question_id": p["claim"]["question_id"], "answer": p["claim"]["answer"],
            "probability": p["claim"].get("probability"), "confidence": p.get("confidence"),
            "reasoning": p.get("reasoning", []), "evidence": p.get("evidence", []),
            "principles_used": p.get("principles_used", []), "payload": p}


def arm_for_model(model: str) -> str:
    """The frozen twin stamps its model as 'frozen:<base>+<agent>-v0'; frontier as 'frontier:'."""
    if model.startswith("frozen:"):
        return "frozen"
    if model.startswith("frontier:"):
        return "frontier"
    return "learned"


# ---- derived views -------------------------------------------------------------

def quarters(b: Bundle) -> list[date]:
    return sorted(set(b.calls["as_of"]))


def _resolved_by(r) -> date | None:
    """When the outcome became knowable: the grader's resolution_date, else as_of + horizon."""
    rd = r.get("resolution_date")
    if rd is not None and not pd.isna(rd):
        return pd.Timestamp(rd).date()
    n = HORIZON_QUARTERS.get(r["payload"].get("horizon"))
    if n is None:
        return None
    return (pd.Timestamp(r["as_of"]) + pd.offsets.QuarterEnd(n)).date()


def graded_calls(b: Bundle) -> pd.DataFrame:
    gc = b.calls.merge(b.grades, on="call_id", how="left")
    gc["resolved_by"] = [_resolved_by(r) for r in gc.to_dict("records")]
    return gc


def is_resolved(r, as_of: date) -> bool:
    """True when this graded call's outcome was knowable at `as_of` (no peeking at the future)."""
    rb = r["resolved_by"]
    return bool(pd.notna(r["outcome"]) and rb is not None and not pd.isna(rb) and rb <= as_of)


def just_resolved(b: Bundle, prev: date | None, as_of: date, arm: str = "learned",
                  company_id: str | None = None) -> pd.DataFrame:
    """Calls whose outcome landed in (prev, as_of]: the right/wrong reveal after a Step."""
    gc = graded_calls(b)
    gc = gc[(gc["arm"] == arm) & gc["outcome"].notna() & gc["resolved_by"].notna()]
    gc = gc[gc["resolved_by"].map(lambda d: d <= as_of and (prev is None or d > prev))]
    if company_id:
        gc = gc[gc["company_id"] == company_id]
    return gc.sort_values(["company_id", "agent"])


def visible_corrections(b: Bundle, as_of: date) -> pd.DataFrame:
    """Corrections the replay could know about at `as_of`: those whose graded call had resolved."""
    c = b.corrections
    if c.empty:
        return c
    rb = graded_calls(b).set_index("call_id")["resolved_by"]
    when = c["call_id"].map(rb)
    keep = when.map(lambda d: d is not None and not pd.isna(d) and d <= as_of)
    return c[keep.astype(bool)]


def is_fallback(ref=None, model=None) -> bool:
    """FakeModelUpdater refs look like 'fake:<agent>:<n>'; its models like 'fallback/<agent>-vN'."""
    return str(ref or "").startswith("fake:") or str(model or "").startswith("fallback/")


def company_table(b: Bundle) -> pd.DataFrame:
    """One row per company in the runs: company_id, sector ('unknown' if no companies table), label."""
    ids = pd.DataFrame({"company_id": sorted(b.calls["company_id"].unique())})
    t = ids.merge(b.companies.drop_duplicates("company_id"), on="company_id", how="left")
    t["sector"] = t["sector"].fillna("unknown")
    t["label"] = t["company_id"] + " · " + t["sector"]
    return t


def filter_companies(t: pd.DataFrame, query: str) -> pd.DataFrame:
    q = (query or "").strip().lower()
    return t if not q else t[t["label"].str.lower().str.contains(q, regex=False)]


def find_heldout_report(candidates=None) -> tuple[Path | None, dict | None, str | None]:
    """First readable held-out report file: (path, report, None) or (None, None, why not)."""
    tried = []
    for p in candidates or HELDOUT_CANDIDATES:
        p = Path(p)
        if not p.exists():
            continue
        try:
            rep = json.loads(p.read_text())
            if not isinstance(rep, dict) or "agents" not in rep:
                raise ValueError("no 'agents' key")
            return p, rep, None
        except Exception as e:  # noqa: BLE001
            tried.append(f"{p.name}: {e}")
    return None, None, ("; ".join(tried) if tried else "no report file found")


def run_live_loop(agent: str, company_id: str, as_of: date, next_as_of: date) -> dict:
    """One company/quarter correction loop on the OFFLINE path (scripted LLM, fallback updater,
    stub metrics). Nothing here touches the network; the result is labelled fallback."""
    import tempfile
    from agents.correction_loop import run_correction_loop
    from agents.gateway import FakeModelUpdater, ScriptedGateway
    from agents.offline import demo_reality, scripted_llm
    with tempfile.TemporaryDirectory(prefix="cm-dash-memory-") as mem:
        res = run_correction_loop(agent, company_id, as_of, next_as_of, ScriptedGateway(scripted_llm),
                                  FakeModelUpdater(mem), outcome_fn=demo_reality)
    return {**res.to_dict(), "offline_demo": True}


def accuracy_curves(b: Bundle, as_of: date | None = None, window: int = 4) -> pd.DataFrame:
    """Per agent and arm: per-quarter accuracy/Brier plus an n-weighted rolling mean.

    Train and held-out runs are concatenated so the curve spans the whole replay.
    """
    s = b.snapshots.copy()
    if as_of is not None:
        s = s[s["as_of"] <= as_of]
    if s.empty:
        return s.assign(rolling_accuracy=[], rolling_brier=[])
    s = s.sort_values("as_of")
    out = []
    for (agent, variant), g in s.groupby(["agent", "variant"], sort=False):
        g = g.copy()
        w = g["n_calls"].astype(float)
        g["rolling_accuracy"] = ((g["accuracy"] * w).rolling(window, min_periods=1).sum()
                                 / w.where(g["accuracy"].notna()).rolling(window, min_periods=1).sum())
        g["rolling_brier"] = ((g["brier"] * w).rolling(window, min_periods=1).sum()
                              / w.where(g["brier"].notna()).rolling(window, min_periods=1).sum())
        out.append(g)
    return pd.concat(out, ignore_index=True)


def committee(b: Bundle, company_id: str, as_of: date, arm: str = "learned") -> dict:
    """Each agent's call for one company and quarter, plus the synthesizer verdict.

    Uses the synthesizer's own scoring (agents/synthesizer.py): Python computes the verdict,
    and weights only see grades resolved by `as_of`.
    """
    gc = graded_calls(b)
    rows = gc[(gc["company_id"] == company_id) & (gc["as_of"] == as_of) & (gc["arm"] == arm)]
    rows = rows.drop_duplicates("agent", keep="last")
    if rows.empty:
        return {"rows": rows, "verdict": None}

    history = []
    hist = gc[(gc["arm"] == arm) & gc["outcome"].notna()]
    hist = hist[hist["resolved_by"].map(lambda d: d is not None and not pd.isna(d) and d <= as_of)]
    for _, r in hist.iterrows():
        try:
            history.append((AgentCall.model_validate(r["payload"]), _grade(r)))
        except Exception:
            continue
    weights = trailing_weights(history, as_of)
    calls = [AgentCall.model_validate(p) for p in rows["payload"]]
    score, used = committee_score(calls, weights)
    return {"rows": rows, "score": score, "weights": used, "verdict": verdict_for(score),
            "confidence": confidence_for(score), "graded_weights": sum(w.graded for w in weights.values())}


def _grade(r: pd.Series) -> Grade:
    return Grade(call_id=r["call_id"], graded_at=r["graded_at"], resolution_date=r["resolution_date"],
                 outcome=r["outcome"], correct=None if pd.isna(r["correct"]) else bool(r["correct"]),
                 brier=None if pd.isna(r["brier"]) else float(r["brier"]), evidence=r["grade_evidence"] or [])


def direction(agent: str, answer: str) -> int:
    return DIRECTION.get(agent, {}).get(answer, 0)


def correction_story(b: Bundle, correction_id: str) -> dict:
    """The judging moment: original call -> actual -> lesson -> update ref -> re-ask next quarter."""
    c = b.corrections.set_index("correction_id").loc[correction_id]
    gc = graded_calls(b)
    before = gc[gc["call_id"] == c["call_id"]].iloc[0]
    later = gc[(gc["agent"] == before["agent"]) & (gc["company_id"] == before["company_id"])
               & (gc["arm"] == "learned") & (gc["as_of"] > before["as_of"])].sort_values("as_of")
    twin = gc[(gc["agent"] == before["agent"]) & (gc["company_id"] == before["company_id"])
              & (gc["arm"] == "frozen")]
    # A call resolves only after its horizon, so the update lands some quarters later. Show the
    # first later call that carries it: version >= the ref's number, else the first new model.
    target = _version(c["mubit_ref"])
    if target is not None:
        carrying = later[later["model"].map(lambda m: (_version(m) or -1) >= target)]
    else:
        carrying = later[later["model"] != before["model"]]
    later = carrying if not carrying.empty else later
    after = later.iloc[0] if not later.empty else None
    twin_after = None
    if after is not None:
        t = twin[twin["as_of"] == after["as_of"]]
        twin_after = t.iloc[0] if not t.empty else None
    return {"correction": c, "before": before, "after": after, "frozen_after": twin_after}


def _version(s) -> int | None:
    """Trailing version number of 'fallback/risk-v12' or 'fake:risk:12'; None for opaque refs."""
    m = re.search(r"(?:-v|:)(\d+)$", str(s or ""))
    return int(m.group(1)) if m else None


def corrections_by_quarter(b: Bundle, as_of: date | None = None) -> pd.DataFrame:
    c = b.corrections
    if c.empty:
        return pd.DataFrame(columns=["as_of", "agent", "count", "cumulative"])
    if as_of is not None:
        c = c[c["as_of"] <= as_of]
    g = c.groupby(["as_of", "agent"]).size().rename("count").reset_index().sort_values("as_of")
    g["cumulative"] = g.groupby("agent")["count"].cumsum()
    return g


def scoreboard(b: Bundle, as_of: date, arm: str = "learned", window: int = 4) -> pd.DataFrame:
    """Legend scoreboard: which investor's rules are doing best over the last `window` quarters."""
    gc = graded_calls(b)
    gc = gc[(gc["arm"] == arm) & (gc["as_of"] <= as_of) & gc["correct"].notna()]
    recent = sorted(set(gc["as_of"]))[-window:]
    gc = gc[gc["as_of"].isin(recent)]
    if gc.empty:
        return pd.DataFrame(columns=["agent", "investor", "calls", "accuracy", "brier", "corrections"])
    out = gc.groupby("agent").agg(calls=("call_id", "count"), accuracy=("correct", "mean"),
                                  brier=("brier", "mean")).reset_index()
    corr = b.corrections[b.corrections["as_of"] <= as_of].groupby("agent").size() if not b.corrections.empty else {}
    out["corrections"] = out["agent"].map(lambda a: int(corr.get(a, 0)) if len(corr) else 0)
    out["investor"] = out["agent"].map(INVESTOR)
    return out.sort_values(["accuracy", "brier"], ascending=[False, True])[
        ["agent", "investor", "calls", "accuracy", "brier", "corrections"]]


def model_version_at(b: Bundle, agent: str, as_of: date) -> str | None:
    c = b.calls[(b.calls["agent"] == agent) & (b.calls["arm"] == "learned") & (b.calls["as_of"] <= as_of)]
    return None if c.empty else c.sort_values("as_of").iloc[-1]["model"]


def heldout_table(report: dict, agent: str, segment: str) -> pd.DataFrame:
    seg = report["agents"][agent]["segments"].get(segment)
    if not seg:
        return pd.DataFrame()
    rows = []
    for arm in ("frozen", "learned", "frontier"):
        if seg.get(arm):
            rows.append({"arm": arm, "n": seg[arm]["n"], "accuracy": seg[arm]["accuracy"], "brier": seg[arm]["brier"]})
    for name, v in (seg.get("baselines") or {}).items():
        rows.append({"arm": f"baseline: {name}", "n": v["n"], "accuracy": v["accuracy"], "brier": v["brier"]})
    return pd.DataFrame(rows)
