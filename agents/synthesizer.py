"""Synthesizer: the committee verdict (README 7.3, 8.4).

Input is the other agents' calls, never raw data. Python computes the verdict and its
confidence (no number comes from an LLM); the LLM only writes the rationale bullets.

    score = sum(w_i * d_i * p_i) / sum(w_i)        in [-1, 1]
      d_i  direction of agent i's answer for the business (+1 good, 0 neutral, -1 bad)
      p_i  agent i's probability that its answer is right
      w_i  agent i's trailing accuracy known at as_of, smoothed: (correct + 1) / (graded + 2)

    score >= +THRESHOLD -> attractive, <= -THRESHOLD -> unattractive, else neutral

Point in time: weights only use grades whose resolution_date <= as_of.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from schemas import AgentCall, Grade

from .gateway import LLMGateway, ModelUpdater
from .masking import mask_dates
from .runner import _extract_json

log = logging.getLogger("agents.synthesizer")

QUESTION_ID = "committee_verdict"
VERDICTS = ("attractive", "neutral", "unattractive")
THRESHOLD = 0.2  # tune on the training window only
TRAILING_WINDOW = 12  # most recent resolved grades per agent
SYNTH_TAG = "COMMITTEE SYNTHESIZER"
PYTHON_MODEL = "python/committee-v0"  # no LLM in the loop: weights, verdict and bullets are all Python
DISCLAIMER = "Research tool, not financial advice."

# What each agent's answer (or actual outcome) means for the business outlook.
DIRECTION: dict[str, dict[str, int]] = {
    "fundamentals": {"yes": 1, "no": -1},       # margins improve
    "moat": {"yes": 1, "no": -1},               # gross margin holds
    "valuation": {"yes": -1, "no": 1},          # market implies more growth than delivered
    "risk": {"yes": -1, "no": 1},               # distress event
    "scenarios": {"bull": 1, "base": 0, "bear": -1},
}


@dataclass(frozen=True)
class Weight:
    correct: int
    graded: int

    @property
    def value(self) -> float:
        return (self.correct + 1) / (self.graded + 2)


def trailing_weights(history: list[tuple[AgentCall, Grade]], as_of: date,
                     window: int = TRAILING_WINDOW) -> dict[str, Weight]:
    """Accuracy per agent from grades already resolved at `as_of` (no look-ahead)."""
    seen: dict[str, list[tuple[date, bool]]] = defaultdict(list)
    for call, g in history:
        if g.correct is None or g.resolution_date is None or g.resolution_date > as_of:
            continue
        seen[call.agent].append((g.resolution_date, g.correct))
    out = {}
    for agent, rows in seen.items():
        recent = sorted(rows)[-window:]
        out[agent] = Weight(sum(c for _, c in recent), len(recent))
    return out


def _direction(agent: str, answer: str) -> int:
    return DIRECTION.get(agent, {}).get(answer, 0)


def committee_score(calls: list[AgentCall], weights: dict[str, Weight]) -> tuple[float, dict[str, float]]:
    w = {c.agent: weights.get(c.agent, Weight(0, 0)).value for c in calls}
    total = sum(w.values())
    if not calls or total == 0:
        return 0.0, w
    score = sum(w[c.agent] * _direction(c.agent, c.claim.answer) * c.claim.probability for c in calls) / total
    return score, w


def verdict_for(score: float) -> str:
    if score >= THRESHOLD:
        return "attractive"
    if score <= -THRESHOLD:
        return "unattractive"
    return "neutral"


def confidence_for(score: float, calibration: "Calibration | None" = None) -> float:
    """Committee confidence. With a `Calibration` fitted on training-window outcomes it is the
    empirical hit rate for that |score| band; without one it is an UNCALIBRATED heuristic."""
    if calibration is not None:
        return calibration.confidence(score)
    s = abs(score)
    if s >= THRESHOLD:
        return round(min(0.9, 0.4 + 0.5 * s), 3)
    return round(0.34 + 0.3 * (1 - s / THRESHOLD), 3)


def committee_outcome(outcomes: dict[str, str]) -> str:
    """Grading helper (README 8.4): which verdict the agents' ACTUAL outcomes favoured.

    `outcomes` maps agent -> graded outcome; unresolvable ones are skipped.
    """
    dirs = [_direction(a, o) for a, o in outcomes.items() if o != "unresolvable"]
    total = sum(dirs)
    return "attractive" if total > 0 else "unattractive" if total < 0 else "neutral"


# ---- calibration and grading of the committee itself ------------------------------------

@dataclass(frozen=True)
class Calibration:
    """Maps |score| to the share of past committee verdicts that were right (binned, smoothed).

    Fit on the training window only: pairs of (score, hit) where hit = verdict matched the
    composite outcome. Bin edges are fixed so the fit is deterministic.
    """
    edges: tuple[float, ...]
    rates: tuple[float, ...]  # one per bin, len(edges) + 1

    def confidence(self, score: float) -> float:
        i = sum(abs(score) >= e for e in self.edges)
        return round(min(0.95, max(0.05, self.rates[i])), 3)


def fit_calibration(pairs: list[tuple[float, bool]], edges: tuple[float, ...] = (THRESHOLD, 0.5),
                    prior: float = 0.5, prior_weight: float = 2.0) -> Calibration:
    """Per-bin hit rate with a Beta-style prior so empty or tiny bins stay near `prior`."""
    hits = [0] * (len(edges) + 1)
    totals = [0] * (len(edges) + 1)
    for score, hit in pairs:
        i = sum(abs(score) >= e for e in edges)
        totals[i] += 1
        hits[i] += bool(hit)
    rates = tuple((h + prior * prior_weight) / (t + prior_weight) for h, t in zip(hits, totals))
    return Calibration(edges, rates)


MIN_CALIBRATION_PAIRS = 20  # below this the fit is mostly prior: report the heuristic instead


def calibration_pairs(history: list[tuple[AgentCall, Grade | None]], as_of: date, fit_until: date | None = None,
                      exclude: frozenset[str] | set[str] = frozenset()) -> list[tuple[float, bool]]:
    """(score, hit) for past committee verdicts whose composite outcome is known at `as_of`.

    `history` is every agent call with its grade (None if not graded yet). A past (company, quarter)
    counts only when every call in it has a grade and every resolved grade resolved by `as_of`, so
    no later outcome leaks into the fit. Each score uses the weights known at that quarter.
    `fit_until` keeps the fit inside the training window; `exclude` drops held-out companies.
    """
    graded = [(c, g) for c, g in history if g is not None]
    groups: dict[tuple[str, date], list[tuple[AgentCall, Grade | None]]] = defaultdict(list)
    for c, g in history:
        if c.agent != "synthesizer":
            groups[(c.company_id, c.as_of)].append((c, g))
    last = min(as_of, fit_until) if fit_until else as_of
    weights_at: dict[date, dict[str, Weight]] = {}
    pairs = []
    for (company, t), rows in sorted(groups.items()):
        if t >= as_of or t > last or company in exclude:
            continue
        if any(g is None or (g.correct is not None and (g.resolution_date is None or g.resolution_date > as_of))
               for _, g in rows):
            continue
        outcome = committee_outcome_from_grades(rows)
        if outcome is None:
            continue
        if t not in weights_at:
            weights_at[t] = trailing_weights(graded, t)
        score, _ = committee_score([c for c, _ in rows], weights_at[t])
        pairs.append((score, verdict_for(score) == outcome))
    return pairs


def calibrate(history: list[tuple[AgentCall, Grade | None]], as_of: date, fit_until: date | None = None,
              exclude: frozenset[str] | set[str] = frozenset(),
              min_pairs: int = MIN_CALIBRATION_PAIRS) -> tuple[Calibration | None, int]:
    """A point-in-time Calibration and how many past verdicts it was fitted on (None if too few)."""
    pairs = calibration_pairs(history, as_of, fit_until, exclude)
    return (fit_calibration(pairs) if len(pairs) >= min_pairs else None), len(pairs)


def committee_outcome_from_grades(call_grades: list[tuple[AgentCall, Grade]]) -> str | None:
    """Composite outcome from the underlying agents' graded outcomes (None if none resolved)."""
    outcomes = {c.agent: g.outcome for c, g in call_grades if g.correct is not None}
    return committee_outcome(outcomes) if outcomes else None


def grade_committee(committee: AgentCall, underlying: list[tuple[AgentCall, Grade]]) -> Grade:
    """Grade a synthesizer call as a composite of the underlying agents' outcomes (README 8.4).

    No filing lookup: the committee is right when its verdict equals the verdict the agents'
    ACTUAL outcomes favoured. Brier is the multiclass score over VERDICTS using its confidence.
    """
    from datetime import datetime, timezone

    outcome = committee_outcome_from_grades(underlying)
    now = datetime.now(timezone.utc)
    dates = [g.resolution_date for _, g in underlying if g.resolution_date and g.correct is not None]
    if outcome is None:
        return Grade(call_id=committee.call_id, graded_at=now, resolution_date=None, outcome="unresolvable",
                     correct=None, brier=None, evidence=[])
    p, answer = committee.claim.probability, committee.claim.answer
    others = (1.0 - p) / (len(VERDICTS) - 1)
    brier = sum(((p if v == answer else others) - (1.0 if v == outcome else 0.0)) ** 2 for v in VERDICTS)
    return Grade(call_id=committee.call_id, graded_at=now, resolution_date=max(dates), outcome=outcome,
                 correct=answer == outcome, brier=brier,
                 evidence=[{"agent": c.agent, "outcome": g.outcome} for c, g in underlying if g.correct is not None])


def _fallback_reasoning(calls: list[AgentCall], weights: dict[str, float]) -> list[str]:
    ranked = sorted(calls, key=lambda c: weights[c.agent] * c.claim.probability, reverse=True)
    return [f"{c.agent}: {c.claim.answer} at {c.claim.probability:.0%} (weight {weights[c.agent]:.2f})" for c in ranked[:5]]


def build_rationale_messages(calls: list[AgentCall], weights: dict[str, float], verdict: str,
                             score: float, as_of: date) -> list[dict]:
    rows = []
    for c in calls:
        reasons = "; ".join(mask_dates(r, as_of) for r in c.reasoning)
        rows.append(f"- {c.agent}: answered {c.claim.answer} at {c.claim.probability:.2f}, "
                    f"track-record weight {weights[c.agent]:.2f}. Reasons: {reasons}")
    system = (
        f"{SYNTH_TAG}\nYou explain a committee verdict that has ALREADY been computed from the analysts' calls. "
        "Do not change the verdict and do not add numbers that are not given.\n"
        'Reply with ONE JSON object: {"reasoning": ["max 5 short bullets"]}. '
        "Each bullet should say which analysts drove the verdict and where they disagree. Research, not advice."
    )
    user = f"Verdict: {verdict} (weighted score {score:+.2f})\nANALYST CALLS\n" + "\n".join(rows)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_rationale(raw: str) -> list[str]:
    bullets = _extract_json(raw).get("reasoning")
    if not isinstance(bullets, list) or not bullets or not all(isinstance(b, str) and b.strip() for b in bullets):
        raise ValueError("reasoning must be a non-empty list of strings")
    return [b.strip() for b in bullets[:5]]


def synthesize(calls: list[AgentCall], history: list[tuple[AgentCall, Grade]], gateway: LLMGateway | None,
               updater: ModelUpdater | None, run_id: str | None = None,
               calibration: Calibration | None = None) -> AgentCall:
    """One committee AgentCall for a single (company, as_of).

    `gateway=None` skips the LLM entirely (the report renders this way): the rationale is the
    Python fallback bullets. `updater=None` labels the model PYTHON_MODEL.
    """
    if not calls:
        raise ValueError("synthesizer needs at least one agent call")
    company_id, as_of = calls[0].company_id, calls[0].as_of
    if any(c.company_id != company_id or c.as_of != as_of for c in calls):
        raise ValueError("all calls must share company_id and as_of")
    if any(c.agent == "synthesizer" for c in calls):
        raise ValueError("synthesizer takes agent calls, not its own")

    score, weights = committee_score(calls, trailing_weights(history, as_of))
    verdict, conf = verdict_for(score), confidence_for(score, calibration)

    if gateway is None:
        reasoning = _fallback_reasoning(calls, weights)
    else:
        try:
            messages = build_rationale_messages(calls, weights, verdict, score, as_of)
            reasoning = _parse_rationale(gateway.complete("synthesizer", messages, purpose="rationale"))
        except Exception as err:  # the rationale is decoration; never lose the verdict over it
            log.warning("synthesizer rationale failed, using fallback bullets: %s", err)
            reasoning = _fallback_reasoning(calls, weights)

    evidence = [{"metric": "committee_score", "value": round(score, 6), "as_of": as_of}]
    evidence += [{"metric": f"weight_{a}", "value": round(v, 6), "as_of": as_of} for a, v in weights.items()]
    principles = sorted({p for c in calls for p in c.principles_used})
    return AgentCall(
        call_id=str(uuid.uuid4()), run_id=run_id or calls[0].run_id, agent="synthesizer",
        company_id=company_id, as_of=as_of, horizon="12_months",
        claim={"type": "bucket", "question_id": QUESTION_ID, "answer": verdict, "probability": conf},
        confidence=conf, reasoning=reasoning, evidence=evidence, principles_used=principles,
        tool_calls=0, model=updater.get_model_version("synthesizer") if updater else PYTHON_MODEL,
    )


def main(argv: list[str] | None = None) -> int:
    """Offline demo: three MVP agents on one stub company, then the committee verdict."""
    import argparse
    import tempfile

    from .gateway import FakeModelUpdater, ScriptedGateway
    from .offline import scripted_llm
    from .runner import run_agent
    from store.stubs import get_metrics_stub

    ap = argparse.ArgumentParser(description="Offline committee demo (stub metrics, scripted LLM).")
    ap.add_argument("--company", default="anon_001")
    ap.add_argument("--as-of", default="2019-06-30", type=date.fromisoformat)
    ap.add_argument("--agents", default="fundamentals,risk,scenarios")
    ap.add_argument("--cross-exam", action="store_true", help="one cross-examination round before the verdict")
    args = ap.parse_args(argv)

    gw = ScriptedGateway(scripted_llm)
    upd = FakeModelUpdater(tempfile.mkdtemp(prefix="cm-memory-"))
    run_id = str(uuid.uuid4())
    calls = [c for a in args.agents.split(",")
             if (c := run_agent(a, args.company, args.as_of, get_metrics_stub(args.company, a, args.as_of), gw, upd, run_id))]
    revisions = []
    if args.cross_exam:
        from .cross_exam import cross_examine
        calls, revisions = cross_examine(calls, gw)
    verdict = synthesize(calls, history=[], gateway=gw, updater=upd, run_id=run_id)

    print("OFFLINE DEMO: stub metrics, scripted LLM, no grade history (equal weights). Not real results.")
    print(f"{DISCLAIMER}\n")
    for c in calls:
        print(f"  {c.agent:<13} {c.claim.answer:<5} @ {c.claim.probability:.0%}")
    for r in revisions:
        print(f"  cross-exam {r.agent:<13} {r.original_probability:.0%} -> {r.revised_probability:.0%}  {r.challenge}")
    print(f"\n  COMMITTEE     {verdict.claim.answer} @ {verdict.claim.probability:.0%}")
    for r in verdict.reasoning:
        print(f"    - {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
