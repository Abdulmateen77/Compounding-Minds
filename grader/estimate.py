"""Cost and time estimate for the full replay (run BEFORE starting it).

    python -m grader.estimate                       # prints the table, writes docs/replay_cost_estimate.md
    python -m grader.estimate --companies 50 --agents 3 --quarters 28 --rpm 50 --concurrency 4

Assumptions (all overridable, all printed in the output):
  * calls = companies x agents x quarters x LLM arms (learned + frozen; baseline has no LLM)
  * + repair retries (--repair-rate) + tool-loop extra calls (--tool-calls per call)
  * + reflection calls = wrong-call rate x train-window learned calls (cap 10 per agent-quarter)
  * prompt size is measured from the real prompt builder on stub metrics (chars / 3.6)
  * output tokens per analyst call 350, per reflection call 200
  * prices are USD per million tokens from the Claude API skill price table (cached 2026-10-06)
  * the reply cache means a re-run costs $0; frozen-arm prompts never share with learned ones
  * grader/replay.py runs calls sequentially (concurrency 1); the concurrency columns are what a
    threaded runner would give. Wall time = max(calls / RPM, calls x latency / concurrency).
"""
from __future__ import annotations

import argparse
import math
from datetime import date
from pathlib import Path

from agents.runner import build_messages
from store.stubs import get_metrics_stub

CHARS_PER_TOKEN = 3.6
OUT_ANALYST, OUT_REFLECT, REFLECT_EXTRA_IN = 350, 200, 450
PRICES = {  # model: (input, output) USD per MTok
    "claude-haiku-4-5": (1.00, 5.00),   # current project default (agents/gateway.py DEFAULT_MODEL)
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
TRAIN_SHARE = 20 / 28  # 2018-2022 of 2018-2024


def prompt_tokens(agent: str = "fundamentals") -> int:
    msgs = build_messages(agent, "anon_001", date(2019, 6, 30), get_metrics_stub("anon_001", agent, date(2019, 6, 30)), [])
    return math.ceil(sum(len(m["content"]) for m in msgs) / CHARS_PER_TOKEN)


def estimate(companies, agents, quarters, wrong_rate=0.45, repair_rate=0.05, tool_calls=0.0, lessons_tokens=150,
             rpm=50, latency=4.0, concurrency=1) -> dict:
    arms = 2
    analyst = companies * agents * quarters * arms
    analyst_total = analyst * (1 + repair_rate + tool_calls)
    reflect = companies * agents * quarters * TRAIN_SHARE * wrong_rate  # learned arm only
    per_agent_q_cap = 10 * agents * quarters * TRAIN_SHARE
    reflect = min(reflect, per_agent_q_cap)
    calls = analyst_total + reflect
    p = prompt_tokens() + lessons_tokens / 2  # lessons grow over the run: average half
    tok_in = analyst_total * (p * (1 + tool_calls / 2)) + reflect * (p + REFLECT_EXTRA_IN)
    tok_out = analyst_total * OUT_ANALYST + reflect * OUT_REFLECT
    wall_min = max(calls / rpm, calls * latency / concurrency / 60)
    return dict(analyst=analyst_total, reflect=reflect, calls=calls, tok_in=tok_in, tok_out=tok_out,
                wall_min=wall_min, usd={m: (tok_in * i + tok_out * o) / 1e6 for m, (i, o) in PRICES.items()})


def render(a, args) -> str:
    e = estimate(args.companies, args.agents, args.quarters, args.wrong_rate, args.repair_rate, args.tool_calls,
                 rpm=args.rpm, latency=args.latency, concurrency=args.concurrency)
    lines = [
        "# Replay cost and time estimate", "",
        f"Inputs: {args.companies} companies x {args.agents} agents x {args.quarters} quarters, 2 LLM arms "
        f"(learned, frozen; baseline is free).", "",
        f"- analyst calls: {e['analyst']:,.0f}  (incl. {args.repair_rate:.0%} repair retries, {args.tool_calls} tool calls/call)",
        f"- reflection calls: {e['reflect']:,.0f}  ({args.wrong_rate:.0%} wrong, train window only, cap 10 per agent-quarter)",
        f"- total calls: {e['calls']:,.0f}",
        f"- tokens: {e['tok_in']/1e6:.1f}M in, {e['tok_out']/1e6:.1f}M out "
        f"(prompt measured at {prompt_tokens()} tokens, chars/{CHARS_PER_TOKEN})", "",
        "| model | $/MTok in | $/MTok out | total USD |", "|---|---|---|---|",
    ]
    for m, (i, o) in PRICES.items():
        lines.append(f"| {m} | {i:.2f} | {o:.2f} | ${e['usd'][m]:,.2f} |")
    lines += ["", "| concurrency | wall time at "
              f"{args.rpm} RPM, {args.latency:.0f}s/call |", "|---|---|"]
    for c in (1, 4, 8, 16):
        x = estimate(args.companies, args.agents, args.quarters, args.wrong_rate, args.repair_rate, args.tool_calls,
                     rpm=args.rpm, latency=args.latency, concurrency=c)
        lines.append(f"| {c} | {x['wall_min']/60:.1f} h |" if x["wall_min"] > 120 else f"| {c} | {x['wall_min']:.0f} min |")
    lines += ["", "Notes: prices from the Claude API skill table (cached 2026-10-06). Mubit's own fees are not "
              "included. `temperature` is rejected by the API from 2026-10-21, so determinism comes from the reply "
              "cache (prompt hash + model version): a second run is free. Run the demo from cache with "
              "`--replay-only`. Full replay is sequential today; the 1-concurrency row is what it will take."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--companies", type=int, default=50)
    ap.add_argument("--agents", type=int, default=3)
    ap.add_argument("--quarters", type=int, default=28)
    ap.add_argument("--wrong-rate", type=float, default=0.45)
    ap.add_argument("--repair-rate", type=float, default=0.05)
    ap.add_argument("--tool-calls", type=float, default=0.0)
    ap.add_argument("--rpm", type=int, default=50)
    ap.add_argument("--latency", type=float, default=4.0)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "replay_cost_estimate.md"))
    a = ap.parse_args(argv)
    text = render(None, a)
    print(text)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text + "\n")
    print(f"\nsaved {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
