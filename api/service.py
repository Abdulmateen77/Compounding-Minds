"""Assemble an Assessment for one company and quarter from stored runs (no LLM, no live calls).

Everything here reads dashboard.data (the same tables the Streamlit view reads) and the synthesizer's own
scoring, so the verdict matches the rest of the system. Numbers come from stored metrics/evidence only.
"""
from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import pandas as pd

from api import models as M
from dashboard import data as D

ROOT = Path(__file__).resolve().parent.parent
NAMES_FILE = Path(__file__).resolve().parent / "display_names.json"
UNIVERSE_FILE = ROOT / "ingest" / "universe.json"
LABEL = {"attractive": "investable", "neutral": "watch", "unattractive": "not_investable"}
FULL_COMMITTEE = 3  # minimum agents with a call for a quarter to count as a committee
AGENT_ORDER = ["fundamentals", "moat", "valuation", "risk", "scenarios"]


class NotFound(Exception):
    pass


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


class Service:
    def __init__(self, source: str | None = None):
        self.source = D.resolve_source(source)
        self.bundle = D.load(self.source)
        self._names = _load_json(NAMES_FILE)
        self._universe = self._read_universe()
        self.gc = D.graded_calls(self.bundle) if not self.bundle.empty else pd.DataFrame()

    # ---- universe -----------------------------------------------------------
    def _read_universe(self) -> dict[str, dict]:
        raw = _load_json(UNIVERSE_FILE)
        rows = raw.get("companies", raw) if isinstance(raw, dict) else raw
        out = {}
        for r in rows if isinstance(rows, list) else []:
            cid = r.get("company_id") or r.get("id")
            if cid:
                out[cid] = r
        return out

    def _held_out(self) -> set[str]:
        return self.bundle.held_out_companies()  # eval.run's split or grader.replay's top-level list

    def companies(self) -> list[M.Company]:
        if self.bundle.empty:
            return []
        ids = sorted(set(self.bundle.calls["company_id"]))
        held = self._held_out()
        return [M.Company(id=i, name=self._names.get(i) or self._universe.get(i, {}).get("name") or f"Company {i[-3:]}",
                          sector=self._universe.get(i, {}).get("sector"), held_out=i in held) for i in ids]

    def company(self, company_id: str) -> M.Company:
        for c in self.companies():
            if c.id == company_id:
                return c
        raise NotFound(f"unknown company {company_id}")

    # ---- quarters -----------------------------------------------------------
    def quarters_for(self, company_id: str) -> list[date]:
        if self.gc.empty:
            return []
        g = self.gc[(self.gc["company_id"] == company_id) & (self.gc["arm"] == "learned")]
        counts = g.groupby("as_of")["agent"].nunique()
        return sorted(counts[counts >= FULL_COMMITTEE].index)

    def quarters(self) -> list[str]:
        return [q.isoformat() for q in D.quarters(self.bundle)] if not self.bundle.empty else []

    # ---- banner -------------------------------------------------------------
    def provenance(self) -> tuple[bool, str | None]:
        prov = self.bundle.provenance()
        stub = not prov.get("real_results", False)
        banner = None
        if stub:
            banner = "NOT RESULTS. Stub or scripted inputs: this view only exercises the pipeline. Do not quote these numbers."
        return stub, banner

    # ---- assessment ---------------------------------------------------------
    def assessment_id(self, company_id: str, as_of: date) -> str:
        return f"{company_id}_{as_of.isoformat()}"

    def parse_id(self, assessment_id: str) -> tuple[str, date]:
        try:
            cid, d = assessment_id.rsplit("_", 1)
            return cid, date.fromisoformat(d)
        except ValueError as e:
            raise NotFound(f"bad assessment id {assessment_id}") from e

    def assess(self, company_id: str, as_of: date | None = None) -> M.Assessment:
        company = self.company(company_id)
        qs = self.quarters_for(company_id)
        if not qs:
            raise NotFound(f"no committee runs for {company_id}")
        if as_of is None:
            as_of = qs[-1]
        elif as_of not in qs:
            raise NotFound(f"no committee for {company_id} at {as_of}")

        com = D.committee(self.bundle, company_id, as_of, arm="learned")
        rows: pd.DataFrame = com["rows"]
        if rows.empty or com["verdict"] is None:
            raise NotFound(f"no committee for {company_id} at {as_of}")

        weights = com["weights"]
        acc = self._accessions()
        views = []
        for _, r in rows.iterrows():
            p = r["payload"]
            ans, prob = p["claim"]["answer"], p["claim"]["probability"]
            d = D.direction(r["agent"], ans)
            outcome, correct, resolved_on = _settled(r)
            views.append(M.AgentView(
                outcome=outcome, correct=correct, resolved_on=resolved_on,
                what_happened=_what_happened(r["agent"], outcome, r.get("grade_evidence")),
                agent=r["agent"], investor=D.INVESTOR.get(r["agent"], r["agent"]),
                question=D.QUESTION.get(r["agent"], p["claim"]["question_id"]),
                answer=ans, probability=prob, confidence=p["confidence"],
                stance="for" if d > 0 else "against" if d < 0 else "neutral",
                weight=round(float(weights.get(r["agent"], 0.5)), 3),
                reasoning=list(p.get("reasoning", [])),
                evidence=[M.EvidenceChip(metric=e["metric"], value=e["value"], as_of=str(e["as_of"]),
                                         accession=acc.get((company_id, e["metric"], str(e["as_of"])))) for e in p.get("evidence", [])],
                principles=list(p.get("principles_used", [])), model=p["model"],
                revised_from=_revised_from(p)))
        views.sort(key=lambda v: AGENT_ORDER.index(v.agent) if v.agent in AGENT_ORDER else 99)

        votes = M.Votes(**{"for": sum(v.stance == "for" for v in views),
                           "neutral": sum(v.stance == "neutral" for v in views),
                           "against": sum(v.stance == "against" for v in views)})
        verdict = com["verdict"]
        label = LABEL[verdict]
        majority = "for" if verdict == "attractive" else "against" if verdict == "unattractive" else None
        dissent = [f"{v.investor} ({v.agent}) leans {v.stance}: {v.reasoning[0] if v.reasoning else v.answer}"
                   for v in views if majority and v.stance != majority]
        stub, banner = self.provenance()
        return M.Assessment(
            assessment_id=self.assessment_id(company_id, as_of), company=company, as_of=as_of.isoformat(),
            label=label, verdict=verdict, score=round(float(com["score"]), 3), confidence=float(com["confidence"]),
            votes=votes, summary=self._summary(views, label), committee=views, dissent=dissent,
            metrics=self._metrics(company_id, as_of), risks=self._risks(views), scenarios=self._scenarios(views),
            mubit=self._mubit(as_of), stub=stub, banner=banner)

    def _summary(self, views: list[M.AgentView], label: str) -> list[str]:
        ranked = sorted(views, key=lambda v: v.weight * v.probability, reverse=True)
        return [f"{v.investor}: {v.answer} at {v.probability:.0%} (committee weight {v.weight:.2f})" for v in ranked[:3]]

    def _metrics(self, company_id: str, as_of: date) -> list[M.MetricCard]:
        g = self.gc[(self.gc["company_id"] == company_id) & (self.gc["arm"] == "learned") & (self.gc["as_of"] <= as_of)]
        series: dict[str, dict[date, float]] = {}
        for _, r in g.sort_values("as_of").iterrows():
            for e in r["payload"].get("evidence", []):
                series.setdefault(e["metric"], {})[r["as_of"]] = e["value"]
        cards = []
        for name, pts in series.items():
            if as_of not in pts:
                continue
            ordered = [pts[d] for d in sorted(pts)][-12:]
            a = self._accessions().get((company_id, name, as_of.isoformat()))
            cards.append(M.MetricCard(name=name, value=pts[as_of], trend=ordered, accessions=[a] if a else []))
        return sorted(cards, key=lambda c: c.name)

    def _risks(self, views: list[M.AgentView]) -> list[str]:
        out = []
        for v in views:
            if v.agent == "risk":
                out += v.reasoning
                if v.stance == "against":
                    out.insert(0, f"Risk agent expects a distress event: {v.probability:.0%}")
        return out

    def _scenarios(self, views: list[M.AgentView]) -> list[M.Scenario]:
        for v in views:
            if v.agent == "scenarios":
                return [M.Scenario(bucket=v.answer, probability=v.probability, reasoning=v.reasoning)]
        return []

    def _accessions(self) -> dict[tuple[str, str, str], str]:
        """(company, metric, as_of) -> filing accession, from the metric inputs stored with corrections."""
        if getattr(self, "_acc", None) is None:
            self._acc = {}
            c = self.bundle.corrections
            for pl in ([] if c.empty else c["payload"]):
                for m in (pl.get("inputs_snapshot") or {}).get("metrics", []):
                    if m.get("inputs"):
                        self._acc[(pl["company_id"], m["name"], str(m["as_of"]))] = m["inputs"][0]
        return self._acc

    def _correction(self, c: pd.Series) -> M.Correction:
        pl = c["payload"]
        story = {}
        try:
            story = D.correction_story(self.bundle, c["correction_id"])
        except Exception:
            pass
        after, before = story.get("after"), story.get("before")
        return M.Correction(
            summary=c["summary"], error_type=pl.get("error_type") or c.get("error_type"), as_of=c["as_of"].isoformat(),
            predicted=_ans(pl.get("predicted"), "answer"), actual=_ans(pl.get("actual"), "outcome"),
            mubit_ref=c["mubit_ref"], applied=bool(pd.notna(c["applied_at"])), lesson=pl.get("lesson") or c["summary"],
            principle_refs=list(pl.get("principle_refs") or []), call_company=pl.get("company_id"),
            version_before=None if before is None else before["model"],
            version_after=None if after is None else after["model"],
            reasked_answer=None if after is None else str(after["answer"]))

    def _corrections_upto(self, agent: str, as_of: date) -> pd.DataFrame:
        c = self.bundle.corrections
        if c.empty:
            return c
        return c[(c["agent"] == agent) & (c["as_of"] <= as_of)].sort_values("as_of")

    def _mubit(self, as_of: date) -> list[M.MubitState]:
        b = self.bundle
        fallback = b.uses_fallback_updater()
        board = D.scoreboard(b, as_of).set_index("agent") if not b.empty else pd.DataFrame()
        snaps = b.snapshots[(b.snapshots["variant"] == "learned") & (b.snapshots["as_of"] <= as_of)]
        out = []
        for agent in AGENT_ORDER:
            if agent not in set(b.calls["agent"]):
                continue
            s = snaps[snaps["agent"] == agent].sort_values("as_of")
            trend = [float(x) for x in s["accuracy"].dropna().tail(12)]
            corr = self._corrections_upto(agent, as_of)
            last = self._correction(corr.iloc[-1]) if len(corr) else None
            row = board.loc[agent] if agent in board.index else None
            out.append(M.MubitState(
                agent=agent, investor=D.INVESTOR.get(agent, agent), model_version=D.model_version_at(b, agent, as_of),
                accuracy=None if row is None else float(row["accuracy"]), calls_graded=0 if row is None else int(row["calls"]),
                corrections_applied=int(len(corr)), accuracy_trend=trend, last_correction=last, fallback_updater=fallback))
        return out

    def _checked_share(self, agent: str) -> float | None:
        b = self.bundle
        if b.grades.empty or b.calls.empty:
            return None
        g = b.grades.merge(b.calls[["call_id", "agent", "arm"]], on="call_id")
        g = g[(g["agent"] == agent) & (g["arm"] == "learned")]
        return None if g.empty else round(float((g["outcome"] != "unresolvable").mean()), 3)

    def track_record(self, agent: str, as_of: date | None = None) -> M.TrackRecord:
        b = self.bundle
        if b.snapshots.empty or b.snapshots[b.snapshots["agent"] == agent].empty:
            raise NotFound(f"no track record for {agent}")
        as_of = as_of or max(b.snapshots["as_of"])
        curves = D.accuracy_curves(b, as_of)
        c = curves[curves["agent"] == agent]
        learned = c[c["variant"] == "learned"].sort_values("as_of")
        frozen = c[c["variant"] == "frozen"].sort_values("as_of")
        if learned.empty:
            raise NotFound(f"no track record for {agent} as of {as_of}")
        board = D.scoreboard(b, as_of).set_index("agent")
        row = board.loc[agent] if agent in board.index else None
        corr = self._corrections_upto(agent, as_of)
        # Start at the first quarter with a graded call: before that there is no accuracy, not 0% accuracy.
        acc = pd.DataFrame({"as_of": learned["as_of"].values, "learned": learned["rolling_accuracy"].values}).merge(
            pd.DataFrame({"as_of": frozen["as_of"].values, "frozen": frozen["rolling_accuracy"].values}),
            on="as_of", how="left")
        seen = acc[["learned", "frozen"]].notna().any(axis=1)
        acc = acc[seen.cummax()].ffill().fillna(0)
        return M.TrackRecord(
            agent=agent, investor=D.INVESTOR.get(agent, agent), as_of=as_of.isoformat(),
            learned=[float(x) for x in acc["learned"]],
            frozen=[float(x) for x in acc["frozen"]],
            quarters=[q.isoformat() for q in acc["as_of"]],
            model_version=D.model_version_at(b, agent, as_of),
            accuracy=None if row is None else float(row["accuracy"]),
            brier=None if row is None or pd.isna(row["brier"]) else float(row["brier"]),
            calls_graded=0 if row is None else int(row["calls"]), corrections_applied=len(corr),
            checked_share=self._checked_share(agent),
            last_correction=self._correction(corr.iloc[-1]) if len(corr) else None,
            fallback_updater=b.uses_fallback_updater())


def _settled(r: pd.Series) -> tuple[str | None, bool | None, str | None]:
    """(outcome, correct, resolved_on) when the grader settled the call, else Nones."""
    outcome = r.get("outcome")
    if outcome is None or pd.isna(outcome) or outcome == "unresolvable":
        return None, None, None
    correct = r.get("correct")
    rd = r.get("resolution_date")
    return (str(outcome), None if correct is None or pd.isna(correct) else bool(correct),
            None if rd is None or pd.isna(rd) else str(pd.Timestamp(rd).date()))


def _p(x: float) -> str:
    return f"{x * 100:.1f}%"


def _what_happened(agent: str, outcome: str | None, evidence) -> str | None:
    """One plain sentence from the grader's own evidence. Every number in it was computed by the grader."""
    if outcome is None:
        return None
    info = next((e for e in (evidence or []) if isinstance(e, dict)), {})
    if agent == "fundamentals":
        q0, q1 = info.get("q0") or {}, info.get("q1") or {}
        if "fcf_margin_ttm" in q0 and "fcf_margin_ttm" in q1 and "operating_margin" in q0 and "operating_margin" in q1:
            return (f"Free-cash-flow margin went {_p(q0['fcf_margin_ttm'])} → {_p(q1['fcf_margin_ttm'])} and operating "
                    f"margin {_p(q0['operating_margin'])} → {_p(q1['operating_margin'])}: "
                    + ("both improved." if outcome == "yes" else "they did not both improve."))
        return "Both margins improved." if outcome == "yes" else "Margins did not both improve."
    if agent == "scenarios":
        g = info.get("revenue_growth")
        band = {"bear": "shrank (bear: below 0%)", "base": "grew modestly (base: 0 to 10%)",
                "bull": "grew strongly (bull: 10% or more)"}.get(outcome, outcome)
        return f"Revenue over the next four quarters {band}" + (f", at {g * 100:+.1f}%." if g is not None else ".")
    if agent == "risk":
        if outcome == "no":
            return "No distress event in the next 12 months: no dividend cut, auditor change or going-concern warning."
        hit = [k.replace("_", " ") for k, v in (info.get("components") or {}).items() if v.get("result") == "yes"]
        return f"A distress event happened within 12 months: {', '.join(hit) or 'see filings'}."
    return f"Outcome: {outcome}."


def _revised_from(p: dict) -> float | None:
    """Pre-cross-examination probability, when the stored call carries it (agents/cross_exam.py Revision)."""
    for k in ("revised_from", "original_probability"):
        if p.get(k) is not None:
            return float(p[k])
    x = p.get("cross_exam") or {}
    return None if x.get("original_probability") is None else float(x["original_probability"])


def _ans(d: dict | None, key: str) -> str | None:
    return None if not d else str(d.get(key))


_svc: tuple[float, Service] | None = None
_svc_lock = threading.Lock()


def get_service() -> Service:
    """One Service per state of the run files: a replay still writing (each quarter rewrites the JSONL) shows up
    on the next request instead of after a restart. Postgres has no stamp, so it loads once."""
    global _svc
    stamp = D.source_stamp(D.resolve_source(None))
    if _svc is None or _svc[0] != stamp:
        with _svc_lock:
            if _svc is None or _svc[0] != stamp:
                _svc = (stamp, Service())
    return _svc[1]
