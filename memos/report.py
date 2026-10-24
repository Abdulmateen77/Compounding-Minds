"""Final report per company and quarter (TASKS B5). Python only: no LLM call, no network.

Reads the run store files that agents/run_store.JsonlRunStore writes (runs.jsonl, calls.jsonl,
grades.jsonl, corrections.jsonl) and renders Markdown:

  - the committee verdict, recomputed here with agents/synthesizer.py from the stored calls:
    weights from each agent's trailing accuracy at the as-of date, confidence calibrated on past
    committee verdicts already resolved by then (training window, held-out companies excluded),
    and the committee's own grade as a composite of the agents' graded outcomes
  - each agent's call, its reasoning (the agent's words, verbatim), its grade and any lesson
  - a metric table rendered by Python, with the source accessions behind every value

Metric sources (`--metrics`):
    files      the run files only: the metrics snapshot saved with a correction, else the call's
               evidence values (already checked against the metrics engine; accessions not stored)
    postgres   the metrics engine itself, point in time, read-only (DATABASE_URL)
    stub       the stub bundles (offline tests and demos; not research)

The company stays anonymous. `--reveal` shows its name and ticker, read from
ingest/universe.json at render time, and only for the demo company (DEMO_COMPANY, default
anon_007). Nothing here builds a prompt, so the name never reaches a model.

    python -m memos.report --runs data/runs_final --company anon_007 --quarter 2019Q2
    python -m memos.report --runs data/runs_final --company anon_007 --quarter 2019Q2 --metrics postgres --reveal

Research tool, not financial advice.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from agents.synthesizer import (DIRECTION, THRESHOLD, Weight, calibrate, grade_committee, synthesize,
                                trailing_weights)
from schemas import AgentCall, Grade

from .memo import DISCLAIMER, format_value

DEMO_COMPANY = os.environ.get("DEMO_COMPANY", "anon_007")
ARMS = ("learned", "frozen", "baseline")
METRIC_SOURCES = ("files", "postgres", "stub")
_QUARTER = re.compile(r"^(\d{4})Q([1-4])$")
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}

MetricsFn = Callable[[str, str, date], dict]


def quarter_end(spec: str) -> date:
    """'2019Q2' -> 2019-06-30. An ISO date is accepted as is."""
    if m := _QUARTER.match(spec.strip().upper()):
        return date(int(m.group(1)), *_QUARTER_END[int(m.group(2))])
    return date.fromisoformat(spec)


def quarter_label(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ---- reading the run files ---------------------------------------------------------------

@dataclass
class RunFiles:
    runs: dict[str, dict] = field(default_factory=dict)
    calls: list[tuple[str, str, AgentCall]] = field(default_factory=list)  # (tag, arm, call)
    grades: dict[str, Grade] = field(default_factory=dict)                  # call_id -> grade
    corrections: dict[str, dict] = field(default_factory=dict)              # call_id -> correction row


def _rows(directory: Path, table: str) -> list[dict]:
    p = directory / f"{table}.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def arm_of(run: dict, call: AgentCall) -> str:
    """Replay runs say their arm in config.variant; eval-harness runs only in the model label."""
    variant = run.get("config", {}).get("variant")
    if variant:
        return variant
    if call.model.startswith("frozen:"):
        return "frozen"
    return "baseline" if call.model.startswith("baseline") else "learned"


def load_run_files(directory: Path | str) -> RunFiles:
    """Read-only: never creates or rewrites anything in `directory`."""
    d = Path(directory)
    if not (d / "calls.jsonl").exists():
        raise FileNotFoundError(f"no calls.jsonl in {d} (point --runs at a run_store directory)")
    out = RunFiles(runs={r["run_id"]: r for r in _rows(d, "runs")})
    for r in _rows(d, "calls"):
        call = AgentCall.model_validate(r["payload"])
        run = out.runs.get(call.run_id, {})
        out.calls.append((run.get("config", {}).get("tag", ""), arm_of(run, call), call))
    out.grades = {r["call_id"]: Grade.model_validate(r) for r in _rows(d, "grades")}
    out.corrections = {r["call_id"]: r for r in _rows(d, "corrections")}
    return out


def _pick_tag(files: RunFiles, tag: str | None) -> str:
    tags = sorted({t for t, _, _ in files.calls})
    if tag is not None:
        if tag not in tags:
            raise ValueError(f"no calls for tag {tag!r}; have {tags}")
        return tag
    if len(tags) > 1:
        raise ValueError(f"several replay tags in these files, pick one with --tag: {tags}")
    return tags[0] if tags else ""


# ---- the report --------------------------------------------------------------------------

@dataclass
class Report:
    markdown: str
    verdict: AgentCall
    committee_grade: Grade | None
    calibrated_on: int          # past committee verdicts behind the confidence (0 = heuristic)
    revealed: bool


def _reveal(company_id: str, reveal: bool, demo_company: str, universe_path: Path | None) -> str | None:
    if not reveal or company_id != demo_company:
        return None
    from ingest.universe import PATH, load_universe
    for c in load_universe(universe_path or PATH):
        if c["company_id"] == company_id:
            return f"{c['name']} ({c['ticker']})"
    return None


def _grade_text(g: Grade | None) -> str:
    if g is None:
        return "not graded yet"
    if g.correct is None:
        return f"unresolvable ({g.outcome})"
    brier = f", Brier {g.brier:.3f}" if g.brier is not None else ""
    return (f"outcome **{g.outcome}**, {'right' if g.correct else 'wrong'}{brier}, "
            f"resolved {g.resolution_date.isoformat() if g.resolution_date else 'n/a'}")


def _metric_rows(call: AgentCall, bundle: dict | list | None, source: str) -> list[tuple[str, str, str, bool, list[str]]]:
    """(metric, value, source label, cited by the agent, accessions) for one agent."""
    from metrics import AGENT_METRICS
    cited = {e.metric for e in call.evidence}
    metrics = bundle.get("metrics", []) if isinstance(bundle, dict) else (bundle or [])
    if metrics:
        return [(m["name"], format_value(m["value"], m["unit"]) if m.get("value") is not None else "missing",
                 source, m["name"] in cited, list(m.get("inputs") or [])) for m in metrics]
    units = AGENT_METRICS.get(call.agent, {})
    return [(e.metric, format_value(e.value, units[e.metric]) if e.metric in units else f"{e.value:g}",
             "call evidence", True, []) for e in call.evidence]


ROW_ACCESSIONS = 4  # per table row; the full list is in the Source accessions section


def _accession_cell(inputs: list[str], source: str) -> str:
    if not inputs:
        return "not stored in run files" if source == "call evidence" else "none (no filing input, e.g. a macro series)"
    latest = sorted(inputs)[-ROW_ACCESSIONS:]
    more = len(inputs) - len(latest)
    return ", ".join(latest) + (f" (+{more} earlier)" if more else "")


def build_report(files: RunFiles, company_id: str, as_of: date, *, arm: str = "learned", tag: str | None = None,
                 metrics: str = "files", metrics_fn: MetricsFn | None = None, reveal: bool = False,
                 demo_company: str = DEMO_COMPANY, universe_path: Path | None = None) -> Report:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    tag = _pick_tag(files, tag)
    mine = [c for t, a, c in files.calls if t == tag and a == arm and c.agent != "synthesizer"]
    one_per_agent = {c.agent: c for c in mine if c.company_id == company_id and c.as_of == as_of}
    calls = [one_per_agent[a] for a in sorted(one_per_agent)]
    if not calls:
        have = sorted({quarter_label(c.as_of) for c in mine if c.company_id == company_id})
        raise ValueError(f"no {arm} calls for {company_id} at {as_of} (tag {tag!r}); quarters with calls: "
                         + (", ".join(have) if have else "none"))

    runs = [files.runs.get(c.run_id, {}) for c in calls]
    cfg = next((r.get("config", {}) for r in runs if r), {})
    held_out = set(cfg.get("held_out_companies") or cfg.get("split", {}).get("held_out_companies") or [])
    train_end = cfg.get("train_end") or (cfg.get("split", {}).get("train_window") or [None, None])[1]
    fit_until = date.fromisoformat(train_end) if train_end else None

    history = [(c, files.grades.get(c.call_id)) for c in mine]
    graded = [(c, g) for c, g in history if g is not None]
    weights = trailing_weights(graded, as_of)
    calibration, n_pairs = calibrate(history, as_of, fit_until=fit_until, exclude=held_out)
    verdict = synthesize(calls, graded, gateway=None, updater=None, run_id=calls[0].run_id, calibration=calibration)
    underlying = [(c, files.grades[c.call_id]) for c in calls if c.call_id in files.grades]
    committee_grade = grade_committee(verdict, underlying) if len(underlying) == len(calls) else None
    score = verdict.evidence[0].value
    name = _reveal(company_id, reveal, demo_company, universe_path)

    out = [f"# Committee report: {company_id}, {quarter_label(as_of)} (as of {as_of.isoformat()})", "",
           f"*{DISCLAIMER}*", "",
           f"- Run: tag `{tag or '(none)'}`, arm **{arm}**, run id `{calls[0].run_id}`"
           + (" (held-out company: never learned from)" if company_id in held_out else ""),
           "- Company: " + (f"**{name}**, revealed at render time for the demo company only" if name
                             else "anonymous id only (names never enter prompts or reports by default)"),
           "- Every number below is computed in Python from the run files and the metrics engine. "
           "The agents' reasoning is quoted verbatim.", ""]

    # committee
    if calibration is not None:
        conf_note = (f"calibrated: hit rate of {n_pairs} past committee verdicts in the same |score| band, "
                     f"resolved by {as_of.isoformat()}" + (", training window only" if fit_until else ""))
    else:
        conf_note = (f"uncalibrated heuristic: only {n_pairs} past committee verdicts resolved by "
                     f"{as_of.isoformat()}, too few to fit")
    out += ["## Committee verdict", "",
            f"**{verdict.claim.answer}** at {verdict.claim.probability:.0%} confidence ({conf_note}).", "",
            f"Weighted score {score:+.3f} (attractive at or above {THRESHOLD:+.2f}, unattractive at or below "
            f"{-THRESHOLD:+.2f}). Score = sum(weight x direction x probability) / sum(weight); weight = "
            "(correct + 1) / (graded + 2) over the agent's latest resolved grades.", "",
            "Committee grade (composite of the agents' actual outcomes): "
            + (_grade_text(committee_grade) if committee_grade else
               f"pending: {len(underlying)} of {len(calls)} agent calls graded so far."), "",
            "| agent | answer | probability | direction | trailing record | weight |", "|---|---|---|---|---|---|"]
    for c in calls:
        w = weights.get(c.agent, Weight(0, 0))
        d = DIRECTION.get(c.agent, {}).get(c.claim.answer, 0)
        out.append(f"| {c.agent} | {c.claim.answer} | {c.claim.probability:.0%} | {d:+d} | "
                   f"{w.correct}/{w.graded} right | {w.value:.3f} |")
    out += ["", "Drivers, strongest first:", "", *[f"- {r}" for r in verdict.reasoning], ""]

    # agents
    out += ["## Agent calls", ""]
    for c in calls:
        corr = files.corrections.get(c.call_id)
        out += [f"### {c.agent}", "",
                f"- Question `{c.claim.question_id}`, horizon {c.horizon}: answered **{c.claim.answer}** "
                f"at {c.claim.probability:.0%}",
                f"- Model `{c.model}`, principles {', '.join(c.principles_used) or 'none'}, tool calls {c.tool_calls}",
                f"- Grade: {_grade_text(files.grades.get(c.call_id))}"]
        if corr:
            ref = f" (Mubit ref `{corr['mubit_ref']}`)" if corr.get("mubit_ref") else ""
            out.append(f"- Lesson recorded{ref}: {corr['summary']}")
        out += ["", "Reasoning (the agent's words):", "", *([f"> - {r}" for r in c.reasoning] or ["> (none)"]), ""]

    # metrics
    out += ["## Metrics", "", "| agent | metric | value | cited | source | source accessions |",
            "|---|---|---|---|---|---|"]
    accessions: set[str] = set()
    sources: set[str] = set()
    for c in calls:
        if metrics_fn is not None:
            bundle, src = metrics_fn(company_id, c.agent, as_of), f"metrics engine ({metrics})"
        else:
            corr = files.corrections.get(c.call_id)
            bundle = (corr or {}).get("payload", {}).get("inputs_snapshot", {}).get("metrics")
            src = "correction snapshot"
        for metric, value, label, cited, inputs in _metric_rows(c, bundle, src):
            sources.add(label)
            accessions.update(inputs)
            out.append(f"| {c.agent} | {metric} | {value} | {'yes' if cited else ''} | {label} | "
                       f"{_accession_cell(inputs, label)} |")
    out.append("")
    if "call evidence" in sources:
        out += ["Rows sourced from call evidence carry the values the runner checked against the metrics engine; "
                "their accessions are not in the run files. Re-render with `--metrics postgres` to list them.", ""]
    out += ["## Source accessions", "", *([f"- {a}" for a in sorted(accessions)] or ["- none in this source"]), "",
            "---", "", f"*{DISCLAIMER}*", ""]
    return Report("\n".join(out), verdict, committee_grade, n_pairs if calibration else 0, name is not None)


def metrics_source(kind: str) -> MetricsFn | None:
    if kind == "files":
        return None
    if kind == "stub":
        from store.stubs import get_metrics_stub
        return get_metrics_stub
    if kind == "postgres":
        from dotenv import find_dotenv, load_dotenv
        from metrics import get_metrics
        from store import queries
        load_dotenv(find_dotenv(usecwd=True))
        if not queries.has_backend():
            queries.use_postgres()
        return get_metrics
    raise ValueError(f"--metrics must be one of {METRIC_SOURCES}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="a run_store directory (calls.jsonl, grades.jsonl, ...)")
    ap.add_argument("--company", required=True, help="anonymous id, e.g. anon_007")
    ap.add_argument("--quarter", required=True, help="2019Q2, or an ISO as-of date")
    ap.add_argument("--arm", default="learned", choices=ARMS)
    ap.add_argument("--tag", help="replay tag, when the files hold more than one")
    ap.add_argument("--metrics", default="files", choices=METRIC_SOURCES)
    ap.add_argument("--reveal", action="store_true", help=f"show the name, demo company only ({DEMO_COMPANY})")
    ap.add_argument("--out", help="also write the Markdown here")
    a = ap.parse_args(argv)

    files = load_run_files(a.runs)
    rep = build_report(files, a.company, quarter_end(a.quarter), arm=a.arm, tag=a.tag, metrics=a.metrics,
                       metrics_fn=metrics_source(a.metrics), reveal=a.reveal)
    if a.reveal and not rep.revealed:
        print(f"(--reveal ignored: only the demo company {DEMO_COMPANY} is ever named)\n")
    print(rep.markdown)
    if a.out:
        Path(a.out).write_text(rep.markdown)
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
