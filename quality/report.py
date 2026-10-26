"""The held-out report and the quality report (BRIEF_HERMES H2, README 9).

heldout.json is the contract with the dashboard: its keys are fixed (see the brief), a slice
with no calls gets `null`, never NaN, and a note is added whenever the learned agent does not
beat its frozen twin. quality.md is one section per agent with the numbers and a short
critique. The critique is written by fixed rules from those numbers, never by an LLM.

Nothing in this module is tuned against held-out data: the only fitted thing is the
base-rate baseline, and it is fitted on the training cell alone (see baselines.py).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Collection, Mapping, Sequence

from . import metrics as M
from .baselines import (ALWAYS_YES, BASE_RATE, BaseRateFit, Pick, always_yes_pick, fit_base_rate,
                        score_outcomes)
from .metrics import Scored
from .split import HELDOUT_YEARS, SLICES, TRAIN_YEARS, slice_of

VARIANTS = ("learned", "frozen")
FOOTER = "Research tool, not financial advice."

# Thresholds for the rule-written critique. Fixed here, in one place, and never tuned on held-out data.
OVERCONFIDENT_GAP = 0.10   # the brief's example rule: a gap above this reads as "overconfident"
BIN_GAP = 0.15             # one confidence range this far off, with enough calls, is worth naming
BIN_MIN_CALLS = 5
SMALL_SAMPLE = 20
VALID_JSON_FLOOR = 0.95


def _r(x: float | None, places: int = 6) -> float | None:
    return None if x is None else round(x, places)


# ---- preparing the records --------------------------------------------------------------------------

def _prepare(scored: Sequence[Scored]) -> tuple[list[Scored], list[str]]:
    """Keep only learned and frozen records, and only one record per (variant, agent, company, quarter).

    Two runs can contain the same case. Counting both would double its weight, so the most
    recently graded one wins and the note says how many were replaced."""
    notes: list[str] = []
    odd = Counter(s.variant for s in scored if s.variant not in VARIANTS)
    for name, n in sorted(odd.items()):
        notes.append(f"ignored {n} records with variant {name!r}: only learned and frozen are reported")
    best: dict[tuple, Scored] = {}
    dupes: Counter = Counter()
    for s in scored:
        if s.variant not in VARIANTS:
            continue
        key = (s.variant, s.call.agent, s.call.company_id, s.call.as_of)
        if key in best:
            dupes[(s.variant, s.call.agent)] += 1
            if s.grade.graded_at <= best[key].grade.graded_at:
                continue
        best[key] = s
    for (variant, agent), n in sorted(dupes.items()):
        notes.append(f"{n} {variant} cases for {agent} appeared in more than one run: kept the latest graded record")
    return list(best.values()), notes


def _by_case(records: Sequence[Scored]) -> dict[tuple[str, object], Scored]:
    return {(s.call.company_id, s.call.as_of): s for s in records}


# ---- heldout.json -----------------------------------------------------------------------------------

def _null_stats() -> dict:
    return {"accuracy": None, "brier": None}


def _stats(records: Sequence[Scored]) -> dict:
    return {"accuracy": _r(M.accuracy(records)), "brier": _r(M.mean_brier(records))}


def _baseline_stats(pick: Pick | None, claim_type: str, outcomes: Sequence[str]) -> dict:
    acc, brier = score_outcomes(pick, claim_type, outcomes)
    return {"accuracy": _r(acc), "brier": _r(brier)}


def _agent_block(agent: str, records: Sequence[Scored], fit: BaseRateFit,
                 held_out_ids: Collection[str]) -> tuple[dict, list[str]]:
    notes: list[str] = []
    cases = {v: _by_case([s for s in records if s.variant == v]) for v in VARIANTS}
    present = [v for v in VARIANTS if cases[v]]
    for v in VARIANTS:
        if v not in present:
            notes.append(f"no {v} records for {agent}: its {v} column is null")
    claim_type = records[0].call.claim.type
    base_pick = fit.picks.get(agent)
    if base_pick is None:
        notes.append(f"no training cases for {agent}: its base_rate baseline is null")
    unresolvable_cases = {k for v in present for k, s in cases[v].items() if s.grade.outcome == "unresolvable"}

    slices: dict[str, dict] = {}
    for name in SLICES:
        # a case counts only if EVERY present variant resolved it, so the columns compare like with like
        per_variant = [
            {k for k, s in cases[v].items() if M.is_resolved(s) and name in slice_of(s.call, held_out_ids)}
            for v in present]
        keys = set.intersection(*per_variant)
        one_sided = set.union(*per_variant) - keys
        if one_sided:
            notes.append(f"{len(one_sided)} {agent}/{name} cases had a resolved call from only one of learned and "
                         "frozen (the other was dropped, unresolved or missing): left out so both are scored on "
                         "the same cases")
        conflicts = {k for k in keys if len({cases[v][k].grade.outcome for v in present}) > 1}
        if conflicts:
            notes.append(f"{len(conflicts)} {agent}/{name} cases had different outcomes for learned and frozen: left out")
            keys -= conflicts
        ordered = sorted(keys, key=lambda k: (k[0], k[1]))
        outcomes = [cases[present[0]][k].grade.outcome for k in ordered]
        slices[name] = {
            "n": len(ordered),
            "learned": _stats([cases["learned"][k] for k in ordered]) if "learned" in present else _null_stats(),
            "frozen": _stats([cases["frozen"][k] for k in ordered]) if "frozen" in present else _null_stats(),
            ALWAYS_YES: _baseline_stats(always_yes_pick(claim_type), claim_type, outcomes),
            BASE_RATE: _baseline_stats(base_pick, claim_type, outcomes),
        }
        if not ordered:
            notes.append(f"no comparable calls in {agent}/{name}: nothing to compare")
        elif len(present) == 2 and not _learned_beats_frozen(slices[name]):
            notes.append(f"learned does not beat frozen on {agent}/{name}: {_why_not(slices[name])}")
    return {"slices": slices, "unresolvable": len(unresolvable_cases)}, notes


def _learned_beats_frozen(s: dict) -> bool:
    """Strictly better on Brier (lower), the proper score. Accuracy alone is too coarse: one
    lucky call can flip it. If Brier is missing the learning claim is unproven, so False."""
    lb, fb = s["learned"]["brier"], s["frozen"]["brier"]
    return lb is not None and fb is not None and lb < fb


def _why_not(s: dict) -> str:
    lb, fb = s["learned"]["brier"], s["frozen"]["brier"]
    la, fa = s["learned"]["accuracy"], s["frozen"]["accuracy"]
    if lb is None or fb is None:
        return "no Brier score to compare"
    verb = "matched it" if lb == fb else "is worse"
    return f"Brier {lb:.4f} vs {fb:.4f} and accuracy {la:.3f} vs {fa:.3f}, so it {verb}"


def build_heldout(scored: Sequence[Scored], held_out_ids: Collection[str], now: datetime | None = None,
                  extra_notes: Sequence[str] = ()) -> dict:
    records, notes = _prepare(scored)
    notes = list(extra_notes) + notes
    fit = fit_base_rate(records, held_out_ids)
    notes += fit.notes
    by_agent: dict[str, list[Scored]] = defaultdict(list)
    for s in records:
        by_agent[s.call.agent].append(s)
    agents = {}
    for agent in sorted(by_agent):
        agents[agent], agent_notes = _agent_block(agent, by_agent[agent], fit, held_out_ids)
        notes += agent_notes
    return {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "split": {"train_years": list(TRAIN_YEARS), "heldout_years": list(HELDOUT_YEARS),
                  "heldout_company_ids": sorted(held_out_ids)},
        "agents": agents,
        "notes": notes,
    }


# ---- quality.md --------------------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _num(x: float | None, places: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{places}f}"


def _variant_stats(records: Sequence[Scored], agent: str, variant: str,
                   attempted: Mapping[str, int] | None, bundles) -> dict:
    mine = [s for s in records if s.variant == variant]
    calls = [s.call for s in mine]
    return {
        "variant": variant, "produced": len(calls), "resolved": len(M.resolved(mine)),
        "unresolvable": M.n_unresolvable(mine),
        "valid_json_rate": M.valid_json_rate(calls, attempted[agent]) if attempted and agent in attempted else None,
        "evidence_match": M.evidence_match_rate(calls, bundles) if bundles is not None and calls else None,
        "accuracy": M.accuracy(mine), "brier": M.mean_brier(mine),
        "mean_confidence": M.mean_confidence(mine), "gap": M.overconfidence_gap(mine),
        "bins": M.calibration_bins(mine),
    }


def critique(stats: dict, baseline_acc: float | None, baseline_brier: float | None) -> str:
    """One or two sentences on where the agent is weak, from fixed rules. Never an LLM.

    Candidates are ranked by how far the number is from healthy, and the top two are kept. A
    small sample always leads, because every other number is then rough."""
    if stats["resolved"] == 0:
        return "No resolved calls yet, so there is nothing to assess."
    acc, brier, gap = stats["accuracy"], stats["brier"], stats["gap"]
    conf = stats["mean_confidence"]
    lead: list[str] = []
    if stats["resolved"] < SMALL_SAMPLE:
        lead.append(f"Only {stats['resolved']} resolved calls, so these numbers are rough.")
    found: list[tuple[float, str]] = []
    overconfident = gap is not None and gap > OVERCONFIDENT_GAP
    if overconfident:
        found.append((gap, f"It is overconfident: its average confidence is {_pct(conf)} but it is right "
                           f"{_pct(acc)} of the time."))
    elif gap is not None and gap < -OVERCONFIDENT_GAP:
        found.append((-gap, f"It is underconfident: its average confidence is {_pct(conf)} but it is right "
                            f"{_pct(acc)} of the time."))
    if baseline_brier is not None and brier is not None and brier >= baseline_brier:
        found.append((brier - baseline_brier + 0.05,
                      f"Its Brier score ({brier:.3f}) is no better than the base-rate baseline "
                      f"({baseline_brier:.3f}), so its probabilities add nothing over guessing the usual answer."))
    elif baseline_acc is not None and acc is not None and acc <= baseline_acc:
        found.append((baseline_acc - acc + 0.05,
                      f"It is right {_pct(acc)} of the time against {_pct(baseline_acc)} for the base-rate baseline."))
    rate = stats["valid_json_rate"]
    if rate is not None and rate < VALID_JSON_FLOOR:
        found.append((1 - rate, f"It returned an invalid reply on {_pct(1 - rate)} of attempts, and those calls were dropped."))
    match = stats["evidence_match"]
    if match is not None and match < 1.0:
        found.append((1 - match, f"In {_pct(1 - match)} of calls its evidence did not match the metrics it was given."))
    if not overconfident:
        for b in stats["bins"]:
            if b["n"] >= BIN_MIN_CALLS and b["mean_confidence"] - b["accuracy"] > BIN_GAP:
                found.append((b["mean_confidence"] - b["accuracy"],
                              f"When {_pct(b['lo'])} to {_pct(b['hi'])} confident it was right only "
                              f"{_pct(b['accuracy'])} of the time ({b['n']} calls)."))
    found.sort(key=lambda t: -t[0])
    sentences = (lead + [t for _, t in found])[:2]
    if not sentences:
        return ("No clear weakness on these numbers: calibration is within "
                f"{OVERCONFIDENT_GAP:.0%} points, it beats the base-rate baseline and its replies are valid. "
                "That is a check on the numbers, not proof the agent is good.")
    return " ".join(sentences)


def _agent_quality(agent: str, records: Sequence[Scored], fit: BaseRateFit, attempted, bundles) -> str:
    claim_type = records[0].call.claim.type
    stats = {v: _variant_stats(records, agent, v, attempted, bundles)
             for v in VARIANTS if any(s.variant == v for s in records)}
    lines = [f"## {agent}", ""]
    cols = list(stats)
    lines += ["| Measure | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    rows = [("Calls produced", lambda s: str(s["produced"])),
            ("Resolved calls", lambda s: str(s["resolved"])),
            ("Unresolvable (not scored)", lambda s: str(s["unresolvable"])),
            ("Valid-JSON rate", lambda s: _pct(s["valid_json_rate"])),
            ("Evidence match", lambda s: _pct(s["evidence_match"])),
            ("Accuracy", lambda s: _num(s["accuracy"])),
            ("Brier (lower is better)", lambda s: _num(s["brier"], 4)),
            ("Mean confidence", lambda s: _num(s["mean_confidence"])),
            ("Overconfidence gap", lambda s: _num(s["gap"]))]
    lines += [f"| {label} | " + " | ".join(fn(stats[c]) for c in cols) + " |" for label, fn in rows]

    primary = "learned" if "learned" in stats else cols[0]
    resolved_records = M.resolved([s for s in records if s.variant == primary])
    outcomes = [s.grade.outcome for s in resolved_records]
    base_pick = fit.picks.get(agent)
    base_acc, base_brier = score_outcomes(base_pick, claim_type, outcomes)
    yes_acc, yes_brier = score_outcomes(always_yes_pick(claim_type), claim_type, outcomes)
    lines += ["", f"Baselines on the same {len(outcomes)} calls as {primary}:", "",
              "| Baseline | Accuracy | Brier |", "|---|---|---|",
              f"| always_yes | {_num(yes_acc)} | {_num(yes_brier, 4)} |",
              f"| base_rate | {_num(base_acc)} | {_num(base_brier, 4)} |", "",
              "base_rate is fitted on the training window, so it is scored in-sample there. That flatters "
              "it, which makes it a fair test for the agent to beat.", ""]
    for c in cols:
        lines += [f"Calibration, {c}:", "", "| Confidence | Calls | Mean confidence | Accuracy |", "|---|---|---|---|"]
        lines += [f"| {_pct(b['lo'])} to {_pct(b['hi'])} | {b['n']} | {_num(b['mean_confidence'])} | {_num(b['accuracy'])} |"
                  for b in stats[c]["bins"]]
        lines.append("")
    lines += [f"**Critique ({primary}).** {critique(stats[primary], base_acc, base_brier)}", ""]
    return "\n".join(lines)


def build_quality(scored: Sequence[Scored], held_out_ids: Collection[str],
                  attempted: Mapping[str, int] | None = None, bundles=None,
                  now: datetime | None = None, extra_notes: Sequence[str] = ()) -> str:
    """`attempted` maps agent -> how many calls were tried (the runner drops invalid replies, so
    the surviving calls cannot say). `bundles` maps (agent, company_id, as_of) to the metric bundle
    the agent was shown. Without either, that row of the table says n/a rather than guessing."""
    records, notes = _prepare(scored)
    notes = list(extra_notes) + notes
    fit = fit_base_rate(records, held_out_ids)
    by_agent: dict[str, list[Scored]] = defaultdict(list)
    for s in records:
        by_agent[s.call.agent].append(s)
    head = ["# Quality report", "", f"_{FOOTER}_", "",
            f"Generated {(now or datetime.now(timezone.utc)).isoformat()}.", ""]
    if notes:
        head += ["Notes:", ""] + [f"- {n}" for n in notes] + [""]
    if not by_agent:
        head += ["No scored calls were found, so there is nothing to report.", ""]
    body = [_agent_quality(a, by_agent[a], fit, attempted, bundles) for a in sorted(by_agent)]
    return "\n".join(head + body + [f"_{FOOTER}_", ""])


# ---- writing both files ------------------------------------------------------------------------------

def write_reports(out_dir: Path | str, scored: Sequence[Scored], held_out_ids: Collection[str],
                  attempted: Mapping[str, int] | None = None, bundles=None,
                  now: datetime | None = None, extra_notes: Sequence[str] = ()) -> tuple[dict, Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    heldout = build_heldout(scored, held_out_ids, now=now, extra_notes=extra_notes)
    heldout_path, quality_path = out / "heldout.json", out / "quality.md"
    # allow_nan=False makes a stray NaN fail loudly here instead of producing JSON the dashboard cannot parse
    heldout_path.write_text(json.dumps(heldout, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    quality_path.write_text(build_quality(scored, held_out_ids, attempted, bundles, now, extra_notes), encoding="utf-8")
    return heldout, heldout_path, quality_path
