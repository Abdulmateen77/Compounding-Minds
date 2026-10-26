"""See exactly what an agent would be sent, without calling any model.

    python -m agents.dryrun --company anon_007 --as-of 2019-06-30                  # real metrics from Postgres
    python -m agents.dryrun --company anon_001 --as-of 2019-06-30 --stubs          # hand-written stub metrics
    python -m agents.dryrun --company anon_007 --as-of 2019-06-30 --agent risk

Prints each agent's metric bundle (and what is missing), the user message the model would receive,
the size of the full prompt, and the leak check. Use it to review prompts before spending any model
calls, and to find a company whose data is too thin to ask.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from .leakcheck import find_leaks
from .runner import build_messages
from .specs import SPECS

AGENTS = ("fundamentals", "risk", "scenarios")


def render(agent: str, company_id: str, as_of: date, bundle: dict, lessons: list[str]) -> tuple[str, list[str]]:
    msgs = build_messages(agent, company_id, as_of, bundle, lessons)
    leaks = find_leaks(msgs[1]["content"])
    size = sum(len(m["content"]) for m in msgs)
    out = [f"=== {agent} ({SPECS[agent].question_id}) for {company_id}",
           f"metrics: {len(bundle['metrics'])} computed, {len(bundle.get('missing', []))} missing "
           f"{bundle.get('missing', [])}, usable={bundle.get('usable', True)}",
           f"prompt size: {size} characters (about {size // 4} tokens)",
           f"leak check: {'CLEAN' if not leaks else 'BLOCKED ' + str(leaks)}",
           "--- user message", msgs[1]["content"], ""]
    return "\n".join(out), leaks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", required=True)
    ap.add_argument("--as-of", required=True, type=date.fromisoformat)
    ap.add_argument("--agent", choices=AGENTS + ("all",), default="all")
    ap.add_argument("--stubs", action="store_true", help="use the hand-written stub metrics, no database")
    ap.add_argument("--lesson", action="append", default=[], help="add a lesson to the prompt (repeatable)")
    args = ap.parse_args(argv)

    if args.stubs:
        from store.stubs import get_metrics_stub as metrics_fn
    else:
        from dotenv import load_dotenv
        from metrics import get_metrics as metrics_fn
        from store import db, queries
        from store.pg import PostgresBackend
        load_dotenv()
        try:
            queries.set_backend(PostgresBackend(db.connect(timeout=3)))
        except Exception as e:  # noqa: BLE001 - a clear message beats a driver traceback here
            print(f"cannot reach the database ({e.__class__.__name__}). Start it with `docker compose up -d`, "
                  f"load data, or pass --stubs.", file=sys.stderr)
            return 2

    blocked = False
    for agent in AGENTS if args.agent == "all" else (args.agent,):
        text, leaks = render(agent, args.company, args.as_of, metrics_fn(args.company, agent, args.as_of), args.lesson)
        print(text)
        blocked = blocked or bool(leaks)
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
