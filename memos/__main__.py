"""Draft one memo.

    python -m memos --company anon_001 --as-of 2019-06-30              # offline: stub metrics, scripted LLM
    python -m memos --company anon_001 --as-of 2019-06-30 --live       # drafter through Mubit (cached)

Offline memos are built from STUB metrics and are not research about any real company.
"""
from __future__ import annotations

import argparse
import tempfile
import uuid
from datetime import date
from pathlib import Path

from agents.gateway import FakeModelUpdater, ScriptedGateway
from agents.offline import scripted_llm
from agents.runner import run_agent
from agents.specs import MVP_AGENTS
from agents.synthesizer import synthesize
from store.stubs import get_metrics_stub

from .memo import MemoInputs, write_memo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", default="anon_001")
    ap.add_argument("--as-of", default="2019-06-30", type=date.fromisoformat)
    ap.add_argument("--agents", default=",".join(MVP_AGENTS))
    ap.add_argument("--live", action="store_true", help="draft the prose through Mubit (agents stay offline)")
    ap.add_argument("--out", help="write the memo Markdown here")
    args = ap.parse_args(argv)

    scripted = ScriptedGateway(scripted_llm)
    upd = FakeModelUpdater(tempfile.mkdtemp(prefix="cm-memo-"))
    run_id = str(uuid.uuid4())
    metrics = {a: get_metrics_stub(args.company, a, args.as_of) for a in args.agents.split(",")}
    calls = [c for a, m in metrics.items() if (c := run_agent(a, args.company, args.as_of, m, scripted, upd, run_id))]
    verdict = synthesize(calls, history=[], gateway=scripted, updater=upd, run_id=run_id)

    drafter = scripted
    if args.live:
        from dotenv import find_dotenv, load_dotenv
        from agents.cache import CachingGateway
        from agents.gateway import MubitGateway
        load_dotenv(find_dotenv(usecwd=True))
        drafter = CachingGateway(MubitGateway())

    memo = write_memo(MemoInputs(args.company, args.as_of, metrics, calls, verdict), drafter)
    print("OFFLINE INPUTS: stub metrics and scripted analysts. Not research about a real company.\n")
    print(memo.markdown)
    if memo.problems:
        print("drafter problems:", *memo.problems, sep="\n  ")
    if args.out:
        Path(args.out).write_text(memo.markdown)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
