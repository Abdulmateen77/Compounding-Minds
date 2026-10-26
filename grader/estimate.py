"""Cost and time estimate for the full replay (run BEFORE starting it; --observe checks it while it runs).

    python -m grader.estimate                       # prints the table, writes docs/replay_cost_estimate.md
    python -m grader.estimate --companies 50 --agents 3 --quarters 28 --held-out 10 --workers 8
    python -m grader.estimate --observe data/runs_final --tag final --out /tmp/estimate.md

Assumptions (all overridable, all printed in the output):
  * analyst calls = companies x agents x quarters x 2 LLM arms (learned + frozen; baseline has no LLM),
    + repair retries (--repair-rate). Settle quarters only grade: no analyst calls.
  * reflection calls (learned arm, train window only, held-out companies excluded) = wrong-rate x graded
    train calls, capped at MAX_CORRECTIONS_PER_AGENT_PER_QUARTER per agent and quarter. No grades in the
    first quarter, so it has no reflections.
  * tokens per call are MEASURED, not guessed: data/mubit_batch_run2.json (90 live claude-haiku-5-5 calls
    through Mubit) averaged 1,395 input and 1,061 output tokens. Haiku 5.5 thinks by default, so output is
    about 3x the visible reply. Real-metric prompts are the same size as stub ones (~2,500 chars, measured).
  * the learned arm's prompt also carries its lessons: --avg-lessons on average (the prompt holds at most
    MAX_LESSONS_IN_PROMPT), ~351 chars each (measured on the running replay), ~4 chars per token
  * prices are USD per million tokens from the Claude API skill price table (cached 2026-10-06)
  * the reply cache means a re-run costs $0; frozen-arm prompts never share with learned ones (the model
    version is part of the key)
  * wall time = calls x latency / workers, floored by --rpm. Latency 4.6 s is measured: 8 workers gave
    ~105 calls/min on the running 50-company replay.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

from agents.gateway import DEFAULT_MODEL, MAX_LESSONS_IN_PROMPT
from grader.config import MAX_CORRECTIONS_PER_AGENT_PER_QUARTER as CAP

IN_ANALYST, OUT_ANALYST = 1395, 1061      # measured per call, claude-haiku-5-5 via Mubit
REFLECT_EXTRA_IN, OUT_REFLECT = 450, 800  # reflection: the call plus its grade and evidence
LESSON_CHARS, CHARS_PER_TOKEN_PROSE = 351, 4.0
PRICES = {  # model: (input, output) USD per MTok (Claude API skill table, cached 2026-10-06)
    "claude-haiku-5-5": (0.10, 0.50),   # the replay's model (MUBIT_MODEL in .env)
    "claude-haiku-4-5": (1.00, 5.00),   # agents/gateway.py DEFAULT_MODEL
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
TRAIN_QUARTERS = 20  # 2018-2022


def estimate(companies, agents, quarters, held_out=10, wrong_rate=0.45, repair_rate=0.05, avg_lessons=30,
             rpm=600, latency=4.6, workers=8, train_quarters=TRAIN_QUARTERS) -> dict:
    per_arm = companies * agents * quarters * (1 + repair_rate)
    lesson_tok = min(avg_lessons, MAX_LESSONS_IN_PROMPT) * LESSON_CHARS / CHARS_PER_TOKEN_PROSE
    learn_q = max(0, min(train_quarters, quarters) - 1)          # quarter 1 has nothing graded yet
    reflect = learn_q * min(CAP * agents, wrong_rate * (companies - held_out) * agents)
    calls = 2 * per_arm + reflect
    tok_in = per_arm * IN_ANALYST + per_arm * (IN_ANALYST + lesson_tok) + reflect * (IN_ANALYST + lesson_tok + REFLECT_EXTRA_IN)
    tok_out = 2 * per_arm * OUT_ANALYST + reflect * OUT_REFLECT
    wall_min = max(calls / rpm, calls * latency / max(1, workers) / 60)
    return dict(analyst=2 * per_arm, reflect=reflect, calls=calls, tok_in=tok_in, tok_out=tok_out,
                lesson_tokens=lesson_tok, wall_min=wall_min,
                usd={m: (tok_in * i + tok_out * o) / 1e6 for m, (i, o) in PRICES.items()})


def observe(run_dir: Path | str, tag: str, cache_dir: Path | str | None = None) -> dict:
    """What a replay in progress has done so far (read only): quarters, calls, corrections, and the live
    call rate, from the reply-cache entries saved since the replay's directory was created."""
    run_dir = Path(run_dir)
    root = run_dir / f"replay_{tag}"
    state = json.loads((root / "state.json").read_text()) if (root / "state.json").is_file() else {}

    def count(table, pred=lambda r: True):
        p = run_dir / f"{table}.jsonl"
        return sum(1 for line in p.read_text().splitlines() if line and pred(json.loads(line))) if p.is_file() else 0
    mine = lambda r: str(r.get("run_id", "")).startswith(f"{tag}-")
    out = {"quarters_done": len(state.get("done_quarters", [])), "partial": state.get("partial") or {},
           "calls": count("calls", mine), "corrections": count("corrections"),
           "lessons": sum(len(p.read_text().splitlines()) for p in (root / "memory").rglob("*.jsonl"))
           if (root / "memory").is_dir() else 0}
    cache = Path(cache_dir) if cache_dir else run_dir.parent / "llm_cache"
    if root.is_dir() and cache.is_dir():
        t0 = root.stat().st_birthtime if hasattr(root.stat(), "st_birthtime") else root.stat().st_ctime
        saved = []
        for p in cache.glob("*.json"):
            if p.stat().st_mtime >= t0:
                try:
                    saved.append(json.loads(p.read_text()).get("saved_at", p.stat().st_mtime))
                except (OSError, ValueError):
                    continue
        if len(saved) > 1:
            minutes = (max(saved) - min(saved)) / 60
            out.update(live_calls=len(saved), minutes=round(minutes, 1),
                       calls_per_min=round(len(saved) / minutes, 1) if minutes else None,
                       last_saved=time.strftime("%H:%M", time.localtime(max(saved))))
    return out


def render(args) -> str:
    e = estimate(args.companies, args.agents, args.quarters, args.held_out, args.wrong_rate, args.repair_rate,
                 args.avg_lessons, rpm=args.rpm, latency=args.latency, workers=args.workers)
    model = os.environ.get("MUBIT_MODEL") or DEFAULT_MODEL
    lines = [
        "# Replay cost and time estimate", "",
        f"Inputs: {args.companies} companies ({args.held_out} held out) x {args.agents} agents x {args.quarters} "
        f"quarters (+{args.settle} grade-only), 2 LLM arms (learned, frozen; baseline is free). Model: {model}.", "",
        f"- analyst calls: {e['analyst']:,.0f}  (incl. {args.repair_rate:.0%} repair retries)",
        f"- reflection calls: {e['reflect']:,.0f}  (upper bound: {args.wrong_rate:.0%} wrong, train window only, "
        f"cap {CAP} per agent-quarter)",
        f"- total calls: {e['calls']:,.0f}",
        f"- tokens: {e['tok_in']/1e6:.1f}M in, {e['tok_out']/1e6:.1f}M out (measured {IN_ANALYST} in / "
        f"{OUT_ANALYST} out per call; learned prompt +{e['lesson_tokens']:.0f} tokens of lessons)", "",
        "| model | $/MTok in | $/MTok out | total USD |", "|---|---|---|---|",
    ]
    for m, (i, o) in PRICES.items():
        lines.append(f"| {m}{' (this run)' if m == model else ''} | {i:.2f} | {o:.2f} | ${e['usd'][m]:,.2f} |")
    lines += ["", f"| workers | wall time at {args.latency:.1f}s/call |", "|---|---|"]
    for w in (1, 4, 8, 16):
        x = estimate(args.companies, args.agents, args.quarters, args.held_out, args.wrong_rate, args.repair_rate,
                     args.avg_lessons, rpm=args.rpm, latency=args.latency, workers=w)
        lines.append(f"| {w} | {x['wall_min']/60:.1f} h |" if x["wall_min"] > 120 else f"| {w} | {x['wall_min']:.0f} min |")
    if args.observe:
        o = observe(args.observe, args.tag, args.cache_dir)
        lines += ["", f"## Observed so far ({args.observe}, tag {args.tag})", "",
                  f"- quarters done: {o['quarters_done']} of {args.quarters} (+{args.settle} settle); "
                  f"calls stored: {o['calls']:,}; corrections: {o['corrections']}; lessons: {o['lessons']}"]
        if o.get("calls_per_min"):
            left = e["calls"] * max(0, args.quarters - o["quarters_done"]) / args.quarters
            lines.append(f"- live calls: {o['live_calls']:,} in {o['minutes']} min = {o['calls_per_min']} calls/min "
                         f"(last at {o['last_saved']}); about {left:,.0f} calls and "
                         f"{left / o['calls_per_min']:.0f} min left")
    lines += ["", "Notes: prices from the Claude API skill table (cached 2026-10-06); Haiku 5.5 is $0.50/$2.50 above "
              "100K prompt tokens, which no replay prompt reaches. Mubit's own fees are not included. `temperature` "
              "is rejected by the API from 2026-10-21, so determinism comes from the reply cache (prompt hash + model "
              "version): a second run is free. Run the demo from cache with `--replay-only`."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=int, default=50)
    ap.add_argument("--held-out", type=int, default=10)
    ap.add_argument("--agents", type=int, default=3)
    ap.add_argument("--quarters", type=int, default=28)
    ap.add_argument("--settle", type=int, default=4)
    ap.add_argument("--wrong-rate", type=float, default=0.45)
    ap.add_argument("--repair-rate", type=float, default=0.05)
    ap.add_argument("--avg-lessons", type=float, default=30, help=f"lessons in a learned prompt (max {MAX_LESSONS_IN_PROMPT})")
    ap.add_argument("--rpm", type=int, default=600)
    ap.add_argument("--latency", type=float, default=4.6)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--observe", help="a replay --out directory to read progress from (read only)")
    ap.add_argument("--tag", default="final")
    ap.add_argument("--cache-dir", help="reply cache to time live calls from (default <observe>/../llm_cache)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "replay_cost_estimate.md"))
    a = ap.parse_args(argv)
    text = render(a)
    print(text)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text + "\n")
    print(f"\nsaved {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
