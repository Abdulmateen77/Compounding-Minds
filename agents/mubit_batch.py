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
fill its console. They are not results and must never be reported as such.

--source real builds the prompts from the real store instead: training companies only (the held-out ones in
ingest/universe.json are never sent recorded), every quarter 2018Q1-2026Q3 in a seeded random order, usable
bundles only, and the learned lessons in the prompt as the replay sends them (--lessons-dir). This is the
training set for the adapters; check its effect with `python -m agents.agreement` and in the Mubit console.

    python -m agents.mubit_batch --source real --per-agent 200 --workers 4 \
        --lessons-dir data/runs_final/replay_final/memory/learned --max-calls 700 --yes
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from store.stubs import get_metrics_stub, list_stub_cases

from .cache import CachingGateway, CacheMiss
from .gateway import MAX_LESSONS_IN_PROMPT, LLMGateway, MubitUpdater
from .leakcheck import find_leaks
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
    lessons: tuple[str, ...] = ()

    def messages(self, format_rules: bool = True) -> list[dict]:
        return build_messages(self.agent, self.company_id, self.as_of, self.metrics, list(self.lessons),
                              format_rules=format_rules)


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


def training_companies() -> list[str]:
    """Every company in the universe except the held-out ones."""
    from ingest.universe import load_universe
    return [c["company_id"] for c in load_universe() if not c.get("held_out")]


def load_lessons(lessons_dir: Path | str | None, agent: str) -> tuple[str, ...]:
    """The lessons the learned arm would put in this agent's prompt (the most recent MAX_LESSONS_IN_PROMPT)."""
    if not lessons_dir:
        return ()
    p = Path(lessons_dir) / f"{agent}.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    return tuple(r["lesson"] for r in rows)[-MAX_LESSONS_IN_PROMPT:]


def real_cases(per_agent: int, agents=AGENTS, seed: str = "train", metrics_fn=None, companies=None,
               quarters=None, lessons_dir: Path | str | None = None, log=lambda *_: None) -> list[Case]:
    """Up to `per_agent` real prompts per agent: (company, quarter) pairs in a seeded random order, skipping
    unusable bundles and any prompt the leak check would block. Training companies only by default."""
    if metrics_fn is None:
        from store import queries
        if not queries.has_backend():
            queries.use_postgres()
        from metrics import get_metrics as metrics_fn
    if quarters is None:
        from eval.split import quarter_ends
        quarters = [q for q in quarter_ends(2018, 2026) if q <= date.today()]
    companies = list(companies) if companies is not None else training_companies()
    out: list[Case] = []
    for agent in agents:
        lessons = load_lessons(lessons_dir, agent)
        pairs = [(c, q) for c in companies for q in quarters]
        random.Random(f"{seed}:{agent}").shuffle(pairs)
        made = tried = 0
        for company_id, as_of in pairs:
            if made >= per_agent:
                break
            tried += 1
            bundle = metrics_fn(company_id, agent, as_of)
            if not bundle.get("usable", True) or not bundle.get("metrics"):
                continue
            case = Case(agent, company_id, as_of, bundle, False, lessons)
            if find_leaks(case.messages()[1]["content"]):
                continue
            out.append(case)
            made += 1
        log(f"{agent}: {made} usable prompts from {tried} (company, quarter) pairs, {len(lessons)} lessons")
    return out


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


def run_batch(cases: list[Case], gateway: LLMGateway, max_consecutive_errors: int = 3, log=print,
              workers: int = 1) -> dict:
    """Run every case through the gateway. Stops early if the API keeps failing.
    With workers > 1 the request id in the log may belong to a neighbouring call; the ledger has them all."""
    updater = MubitUpdater(tempfile.mkdtemp(prefix="cm-batch-"), model=getattr(gateway, "model", None))
    rows, state, lock = [], {"errors": 0, "streak": 0, "stop": False}, threading.Lock()

    def one(item: tuple[int, Case]) -> None:
        n, c = item
        if state["stop"]:
            return
        try:
            call = run_agent(c.agent, c.company_id, c.as_of, c.metrics, gateway, updater, lessons=list(c.lessons))
        except CacheMiss:
            raise
        except Exception as err:  # network / API error: don't burn credit on a broken setup
            with lock:
                state["errors"] += 1
                state["streak"] += 1
                log(f"[{n}/{len(cases)}] {c.agent:<12} {c.company_id} ERROR {type(err).__name__}: {str(err)[:140]}")
                if state["streak"] >= max_consecutive_errors and not state["stop"]:
                    state["stop"] = True
                    log(f"stopping: {state['streak']} errors in a row")
            return
        with lock:
            state["streak"] = 0
            rid = getattr(gateway, "last_request_id", None)
            rows.append({"agent": c.agent, "company_id": c.company_id, "as_of": c.as_of.isoformat(),
                         "synthetic": c.synthetic, "answer": call.claim.answer if call else None, "mubit_request_id": rid})
            tag = "synthetic" if c.synthetic else ("real" if "usable" in c.metrics else "stub")   # stub bundles carry no `usable`
            log(f"[{n}/{len(cases)}] {c.agent:<12} {c.company_id} {tag:<9} -> "
                f"{(call.claim.answer + f' {call.claim.probability:.0%}') if call else 'DROPPED'}  {rid or ''}")

    items = list(enumerate(cases, 1))
    if workers <= 1:
        for item in items:
            if state["stop"]:
                break
            one(item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, items))
    return {"sent": len(rows), "dropped": sum(r["answer"] is None for r in rows), "errors": state["errors"], "rows": rows}


def _money(usd: float | None) -> str:
    return f"about ${usd:.2f}" if usd is not None else "unknown (no price on file for this model)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-agent", type=int, default=30, help="distinct prompts per agent (default 30: 25 needed + headroom)")
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--source", choices=("stub", "real"), default="stub",
                    help="stub: stub cases + synthetic variants; real: the real store, training companies only")
    ap.add_argument("--lessons-dir", help="--source real: the learned arm's lesson files to put in each prompt")
    ap.add_argument("--seed", default="train", help="--source real: order in which (company, quarter) pairs are taken")
    ap.add_argument("--workers", type=int, default=1, help="calls in flight at once")
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
    if args.source == "real":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")   # DATABASE_URL for the store
        built = real_cases(args.per_agent, agents, seed=args.seed, lessons_dir=args.lessons_dir, log=print)
    else:
        built = build_cases(args.per_agent, agents)
    cases = distinct(built, cache)
    est = estimate(cases, cache)

    print(f"model: {cache.model}   cache: {cache.dir}")
    print(f"agents: {', '.join(agents)}   distinct prompts: {est.calls} "
          f"({sum(c.synthetic for c in cases)} synthetic, {sum(not c.synthetic for c in cases)} {args.source})")
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
    result = run_batch(cases, live, workers=args.workers)

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
