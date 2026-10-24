"""A short plain-English paragraph per investor, written by a model from the checks, with a guard on every number.

The model is given only the checks the rules produced (what was measured, the number it found, the principle) and is
told to add nothing. The reply is then checked: any number it uses that is not in the checks, the headline or the
company figures sends the paragraph back, once, and then drops it. A dropped paragraph leaves the checks, which are
the report; the paragraph is a convenience and is never the source of a figure.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

SYSTEM = (
    "You explain, in plain English for an ordinary reader, how the investor named in the next message would think about a "
    "company. You are given checks that were already run on the company's filings: what was measured, the number found, "
    "whether it passed, and the idea behind it. Write one paragraph of three or four sentences in the third person "
    "(for example: Buffett would ...). Use only the information in the checks. Do not add facts, numbers, forecasts, "
    "or knowledge about the company from anywhere else. Every number you write must appear in the checks exactly as given. "
    "Do not tell the reader to buy, sell or hold. Reply with JSON only: {\"paragraph\": \"...\"}."
)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
FREE = {str(i) for i in range(0, 11)}          # small counts ("3 of 5 checks") need no source


def numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".") for m in NUM.finditer(text)}


def allowed(lens: dict, extra: list[str]) -> set[str]:
    corpus = " ".join([c["shown"] for c in lens["checks"]] + [c["check"] for c in lens["checks"]] + extra)
    return numbers(corpus) | FREE


def prompt(lens: dict, company: str, headline: str) -> str:
    lines = [f"Investor: {lens['name']}", f"Company: {company}", f"Question this investor asks: {lens['question']}",
             f"Overall result of the checks: {lens['word']}", "", "Checks:"]
    for c in lens["checks"]:
        lines.append(f"- [{c['result'].upper()}] {c['check']} Found: {c['shown']}. Idea: {c['principle']}.")
    lines += ["", f"Overall picture for context: {headline}"]
    return "\n".join(lines)


def _ask(gateway, lens: dict, company: str, headline: str, note: str = "") -> str | None:
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt(lens, company, headline) + note}]
    try:
        raw = gateway.complete(f"narrative_{lens['key']}", msgs, purpose="research_narrative", max_tokens=700,
                               session_id=f"narrative:{lens['key']}")
        return str(json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["paragraph"]).strip()
    except Exception:
        return None


def write(gateway, lens: dict, company: str, headline: str, extra_numbers: list[str] = ()) -> str | None:
    ok = allowed(lens, list(extra_numbers) + [headline])
    note = ""
    for _ in range(2):
        text = _ask(gateway, lens, company, headline, note)
        if not text:
            return None
        bad = sorted(numbers(text) - ok)
        if not bad:
            return text
        note = f"\n\nYour last answer used numbers that are not in the checks: {', '.join(bad)}. Rewrite without them."
    return None


def attach(gateway, analysis: dict, company: str, extra_numbers: list[str] = ()) -> None:
    """Add `narrative` (or None) to every lens, the four calls side by side."""
    head = analysis["overall"]["headline"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        texts = list(pool.map(lambda l: write(gateway, l, company, head, extra_numbers), analysis["lenses"]))
    for lens, t in zip(analysis["lenses"], texts):
        lens["narrative"] = t
