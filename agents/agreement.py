"""How often the provider model agrees with ITSELF on an analyst prompt: the ceiling for a Mubit adapter.

Mubit tests an adapter version by how often it matches the provider model's answers ("Matched {a}% ... needs
{need}%"). If the provider gives two different replies to the same prompt, an adapter cannot match both, so its
score is capped by the provider's own agreement. This sends each sampled prompt twice with record=False (Mubit
answers but keeps nothing, so no task is trained on these calls or uses its review budget) and scores the pair.

A pair MATCHES when all of these hold:
  * the same answer
  * probabilities within 0.05
  * the same set of evidence metrics
  * principles_used sets overlap by at least 0.75 (Jaccard)
Reasoning wording is reported (token Jaccard) but does not decide a match: its words vary even when the call does not.

    python -m agents.agreement --per-agent 15                 # dry run: prompts and cost, nothing sent
    python -m agents.agreement --per-agent 15 --yes           # live, with FORMAT_RULES (what the agents now send)
    python -m agents.agreement --per-agent 15 --yes --compare # live, with and without FORMAT_RULES, side by side

Exit code 0 when every agent reaches --target (default 0.96), else 1, so it can gate a script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .mubit_batch import AGENTS, Case, real_cases

TARGET = 0.96
P_TOLERANCE = 0.05
PRINCIPLES_MIN_JACCARD = 0.75


def _jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def _words(bullets: list) -> set[str]:
    return set(re.findall(r"[a-z_]+", " ".join(map(str, bullets)).lower()))


def parse_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        claim = d["claim"]
        return {"answer": claim["answer"], "p": float(claim["probability"]),
                "evidence": {e["metric"] for e in d.get("evidence", []) if isinstance(e, dict) and "metric" in e},
                "principles": set(d.get("principles_used", [])), "reasoning": d.get("reasoning", []),
                "fenced": "```" in text}
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PairScore:
    parsed: bool
    answer: bool = False
    probability: bool = False
    evidence: bool = False
    principles: bool = False
    reasoning_jaccard: float = 0.0

    @property
    def match(self) -> bool:
        return self.parsed and self.answer and self.probability and self.evidence and self.principles


def score_pair(a_text: str, b_text: str) -> PairScore:
    a, b = parse_reply(a_text), parse_reply(b_text)
    if a is None or b is None:
        return PairScore(parsed=False)
    return PairScore(True, a["answer"] == b["answer"], abs(a["p"] - b["p"]) <= P_TOLERANCE + 1e-9,
                     a["evidence"] == b["evidence"],
                     _jaccard(a["principles"], b["principles"]) >= PRINCIPLES_MIN_JACCARD,
                     _jaccard(_words(a["reasoning"]), _words(b["reasoning"])))


def summarise(scores: list[PairScore]) -> dict:
    n = len(scores)
    rate = lambda f: sum(map(f, scores)) / n if n else None  # noqa: E731
    return {"pairs": n, "match": rate(lambda s: s.match), "parsed": rate(lambda s: s.parsed),
            "answer": rate(lambda s: s.answer), "probability": rate(lambda s: s.probability),
            "evidence": rate(lambda s: s.evidence), "principles": rate(lambda s: s.principles),
            "reasoning_jaccard": rate(lambda s: s.reasoning_jaccard)}


def measure(cases: list[Case], gateway, format_rules: bool, workers: int = 4) -> dict[str, dict]:
    """Ask each case twice, unrecorded; return per-agent summaries."""
    def pair(c: Case) -> tuple[str, PairScore]:
        msgs = c.messages(format_rules=format_rules)
        session = f"agreement:{c.agent}:{c.company_id}:{c.as_of.isoformat()}"
        one, two = (gateway.complete(c.agent, msgs, record=False, purpose="agreement", session_id=session)
                    for _ in range(2))
        return c.agent, score_pair(one, two)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(pair, cases))
    return {agent: summarise([s for a, s in results if a == agent]) for agent in dict.fromkeys(c.agent for c in cases)}


def table(label: str, by_agent: dict[str, dict], target: float) -> list[str]:
    pct = lambda v: "  n/a" if v is None else f"{v:5.0%}"  # noqa: E731
    out = [f"{label}", f"  {'agent':<13}{'pairs':>6}{'MATCH':>7}{'answer':>8}{'prob':>6}{'evid':>6}{'princ':>7}"
                       f"{'words':>7}  vs {target:.0%}"]
    for agent, s in by_agent.items():
        ok = s["match"] is not None and s["match"] >= target
        out.append(f"  {agent:<13}{s['pairs']:>6}{pct(s['match']):>7}{pct(s['answer']):>8}{pct(s['probability']):>6}"
                   f"{pct(s['evidence']):>6}{pct(s['principles']):>7}{pct(s['reasoning_jaccard']):>7}  "
                   f"{'reaches it' if ok else 'BELOW'}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-agent", type=int, default=15)
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--compare", action="store_true", help="also measure the prompt without FORMAT_RULES")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", default="agreement")
    ap.add_argument("--yes", action="store_true", help="send the live (unrecorded) calls")
    ap.add_argument("--json", help="write the summaries here")
    args = ap.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    agents = tuple(a.strip() for a in args.agents.split(",") if a.strip())
    cases = real_cases(args.per_agent, agents, seed=args.seed)
    arms = [("with FORMAT_RULES", True)] + ([("without FORMAT_RULES", False)] if args.compare else [])
    calls = 2 * len(cases) * len(arms)
    print(f"{len(cases)} real prompts ({', '.join(agents)}), {calls} unrecorded calls")
    if not args.yes:
        print("DRY RUN: nothing was sent. Add --yes to measure.")
        return 0

    from .gateway import MubitGateway
    gw = MubitGateway()
    report, ok = {}, True
    for label, rules in arms:
        by_agent = measure(cases, gw, rules, args.workers)
        report[label] = by_agent
        print("\n".join(table(f"\n{label} ({gw.model})", by_agent, args.target)))
        if rules:
            ok = all(s["match"] is not None and s["match"] >= args.target for s in by_agent.values())
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"model": gw.model, "target": args.target, **report}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
