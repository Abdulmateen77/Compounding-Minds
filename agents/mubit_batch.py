"""Send enough analyst calls through Mubit for each agent's task to reach its first training.

Mubit groups calls into one task per agent (same system prompt + model) and trains the
first adapter once a task has 25 kept examples. Not every call is kept, so we send a few
extra (--per-agent, default 30).

SAFE BY DEFAULT: with no flags this is a DRY RUN. It spends nothing, needs no key, and
prints how many live calls it would make and a rough cost. Live calls need --yes.

    python -m agents.mubit_batch                       # dry run + estimate
    python -m agents.mubit_batch --per-agent 30 --yes  # send for real

DATA NOTE: the stub store has only 5 real stub cases per agent, and Mubit needs distinct
prompts. The rest are SYNTHETIC variants (stub metrics nudged by +-25%, seeded, so the
same run always makes the same prompts). They exist to exercise the Mubit pipeline and
fill its console. They are not results and must never be reported as such. With Person A's
real data (about 50 companies x 28 quarters), pass real cases and set --variants 0.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from store.stubs import get_metrics_stub, list_stub_cases

from .cache import CachingGateway, CacheMiss
from .gateway import LLMGateway, MubitUpdater
from .runner import build_messages, run_agent

AGENTS = ("fundamentals", "risk", "scenarios")
FIRST_TRAINING_EXAMPLES = 25  # Mubit: "First trains at 25 examples"
CHARS_PER_TOKEN = 3.6         # rough, for the estimate only
ASSUMED_OUTPUT_TOKENS = 350   # a JSON reply with up to 5 reasoning bullets
# USD per million tokens (input, output). Only models whose price we know are listed.
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-haiku-4-5-20251001": (1.0, 5.0)}


@dataclass(frozen=True)
class Case:
    agent: str
    company_id: str
    as_of: date
    metrics: dict
    synthetic: bool

    def messages(self) -> list[dict]:
        return build_messages(self.agent, self.company_id, self.as_of, self.metrics, [])


def _jitter(metrics: dict, rng: random.Random) -> dict:
    """Nudge float metrics by up to +-25%. Integer counts (e.g. going_concern_hits) are kept."""
    out = []
    for m in metrics["metrics"]:
        v = m["value"]
        if isinstance(v, float):
            v = float(f"{v * (1 + rng.uniform(-0.25, 0.25)):.3g}")
        out.append({**m, "value": v})
    return {**metrics, "metrics": out}


def build_cases(per_agent: int, agents=AGENTS) -> list[Case]:
    """`per_agent` distinct prompts per agent: the stub cases first, then synthetic variants."""
    cases: list[Case] = []
    for agent in agents:
        base = [(c, d, get_metrics_stub(c, agent, d)) for c, d in list_stub_cases(agent)]
        made = [Case(agent, c, d, m, False) for c, d, m in base[:per_agent]]
        i = 0
        while len(made) < per_agent:
            c, d, m = base[i % len(base)]
            rng = random.Random(f"{agent}:{c}:{i}")  # deterministic per slot
            made.append(Case(agent, c, d, _jitter(m, rng), True))
            i += 1
        cases.extend(made)
    return cases


def distinct(cases: list[Case], gateway: CachingGateway) -> list[Case]:
    """Drop cases whose prompt repeats, so no call is paid for twice."""
    seen, out = set(), []
    for c in cases:
        k = gateway.key_for(c.agent, c.messages())
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


@dataclass(frozen=True)
class Estimate:
    calls: int
    cached: int
    live: int
    input_tokens: int
    output_tokens: int
    usd: float | None  # None when we don't know the model's price


def estimate(cases: list[Case], gateway: CachingGateway) -> Estimate:
    live_in = live_out = cached = 0
    for c in cases:
        msgs = c.messages()
        if gateway.has(c.agent, msgs):
            cached += 1
            continue
        chars = sum(len(m["content"]) for m in msgs)
        live_in += math.ceil(chars / CHARS_PER_TOKEN)
        live_out += ASSUMED_OUTPUT_TOKENS
    price = PRICES.get(gateway.model)
    usd = (live_in * price[0] + live_out * price[1]) / 1e6 if price else None
    return Estimate(len(cases), cached, len(cases) - cached, live_in, live_out, usd)


def run_batch(cases: list[Case], gateway: LLMGateway, max_consecutive_errors: int = 3, log=print) -> dict:
    """Run every case through the gateway. Stops early if the API keeps failing."""
    updater = MubitUpdater(tempfile.mkdtemp(prefix="cm-batch-"), model=getattr(gateway, "model", None))
    rows, errors, streak = [], 0, 0
    for n, c in enumerate(cases, 1):
        try:
            call = run_agent(c.agent, c.company_id, c.as_of, c.metrics, gateway, updater, lessons=[])
            streak = 0
        except CacheMiss:
            raise
        except Exception as err:  # network / API error: don't burn credit on a broken setup
            errors, streak = errors + 1, streak + 1
            log(f"[{n}/{len(cases)}] {c.agent:<12} {c.company_id} ERROR {type(err).__name__}: {str(err)[:140]}")
            if streak >= max_consecutive_errors:
                log(f"stopping: {streak} errors in a row")
                break
            continue
        rid = getattr(gateway, "last_request_id", None)
        rows.append({"agent": c.agent, "company_id": c.company_id, "synthetic": c.synthetic,
                     "answer": call.claim.answer if call else None, "mubit_request_id": rid})
        tag = "synthetic" if c.synthetic else "stub"
        log(f"[{n}/{len(cases)}] {c.agent:<12} {c.company_id} {tag:<9} -> "
            f"{(call.claim.answer + f' {call.claim.probability:.0%}') if call else 'DROPPED'}  {rid or ''}")
    return {"sent": len(rows), "dropped": sum(r["answer"] is None for r in rows), "errors": errors, "rows": rows}


def _money(usd: float | None) -> str:
    return f"about ${usd:.2f}" if usd is not None else "unknown (no price on file for this model)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-agent", type=int, default=30, help="distinct prompts per agent (default 30: 25 needed + headroom)")
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--yes", action="store_true", help="actually send live calls (default is a dry run)")
    ap.add_argument("--max-calls", type=int, default=120, help="safety cap on live calls this run")
    ap.add_argument("--replay-only", action="store_true", help="never go live; fail on any uncached prompt")
    ap.add_argument("--cache-dir")
    ap.add_argument("--json", help="write a log of this run")
    args = ap.parse_args(argv)

    agents = tuple(a.strip() for a in args.agents.split(",") if a.strip())
    # Dry run builds no network client: the cache only needs a model name to key on.
    from .gateway import MubitGateway
    probe = MubitGateway(client=object())
    cache = CachingGateway(probe, args.cache_dir, replay_only=args.replay_only)
    cases = distinct(build_cases(args.per_agent, agents), cache)
    est = estimate(cases, cache)

    print(f"model: {cache.model}   cache: {cache.dir}")
    print(f"agents: {', '.join(agents)}   distinct prompts: {est.calls} "
          f"({sum(c.synthetic for c in cases)} synthetic, {sum(not c.synthetic for c in cases)} stub)")
    print(f"already cached (free, and NOT sent to Mubit): {est.cached}")
    print(f"live calls to Mubit: {est.live}   ~{est.input_tokens:,} input + ~{est.output_tokens:,} output tokens")
    print(f"estimated cost: {_money(est.usd)}  (rough: tokens counted as characters / {CHARS_PER_TOKEN}; "
          f"{ASSUMED_OUTPUT_TOKENS} output tokens per call assumed)")

    if not args.yes:
        print("\nDRY RUN: nothing was sent. Add --yes to send the live calls.")
        return 0
    if est.live > args.max_calls:
        print(f"\nrefusing: {est.live} live calls is above --max-calls {args.max_calls}.")
        return 2
    if args.replay_only and est.live:
        print(f"\nrefusing: --replay-only but {est.live} prompts are not cached.")
        return 2

    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))
    live = CachingGateway(MubitGateway(), args.cache_dir, replay_only=args.replay_only)
    print(f"\nsending {est.live} live calls through Mubit ({live.model}) ...\n")
    result = run_batch(cases, live)

    toks_in = sum(r.input_tokens or 0 for r in live.requests)
    toks_out = sum(r.output_tokens or 0 for r in live.requests)
    price = PRICES.get(live.model)
    actual = (toks_in * price[0] + toks_out * price[1]) / 1e6 if price else None
    print(f"\ndone: {result['sent']} sent ({live.misses} live, {live.hits} from cache), "
          f"{result['dropped']} dropped, {result['errors']} errors")
    print(f"actual usage: {toks_in:,} input + {toks_out:,} output tokens  ->  {_money(actual)}")
    print("next: open Mubit console > Tasks; each analyst should list its example count "
          f"(first training at {FIRST_TRAINING_EXAMPLES}).")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({**result, "model": live.model, "input_tokens": toks_in,
                                               "output_tokens": toks_out}, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
