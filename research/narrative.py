"""A short view and a look ahead per investor, written by a model from the checks and the investor's guide.

The model is given only (1) the guide for that investor, distilled from the books in the Personal Finance folder
(principles/guides/), and (2) the checks the rules produced for this company: what was measured, the number found,
whether it passed. It is told to add nothing. The reply is then checked: any number it uses that is not in the checks,
the guide or the company figures sends the paragraph back, once, and then drops it. A dropped paragraph leaves the
checks, which are the report; the paragraphs are a convenience and never the source of a figure.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from .analysis import guide_text

INSTRUCTIONS = (
    "You explain, in plain English for an ordinary reader, how the investor named below would think about a company, "
    "and what they would watch over the coming years. You are given background on how this investor thinks (from "
    "their own books), then checks that were already run on the company's filings: what was measured, the number found, "
    "and whether it passed.\n\n"
    "Write two short parts in the third person (for example: Buffett would ...). 'view': three or four sentences on how "
    "the investor reads this company today, using the checks. 'ahead': two or three sentences on what the investor would "
    "watch over the next few years and what would change their mind, using their way of thinking and this company's checks. "
    "Use only the background and the checks. Do not add facts, numbers, forecasts, or knowledge about the company from "
    "anywhere else. Every number you write must appear in the checks or the background exactly as given. Do not tell the "
    "reader to buy, sell or hold, and do not predict the share price. "
    "Reply with JSON only: {\"view\": \"...\", \"ahead\": \"...\"}."
)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
FREE = {str(i) for i in range(0, 11)}          # small counts ("3 of 5 checks") need no source


def numbers(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".") for m in NUM.finditer(text)}


def system_for(lens: dict) -> str:
    """Stable per investor, so Mubit sees one task per investor."""
    return f"{INSTRUCTIONS}\n\nInvestor: {lens['name']}\n\nBackground on how {lens['name']} thinks:\n{guide_text(lens['key'])}"


def allowed(lens: dict, extra: list[str]) -> set[str]:
    corpus = " ".join([c["shown"] for c in lens["checks"]] + [c["check"] for c in lens["checks"]]
                      + [guide_text(lens["key"])] + [(lens.get("note") or {}).get("why", "")] + extra)
    return numbers(corpus) | FREE


def prompt(lens: dict, company: str, headline: str) -> str:
    lines = [f"Company: {company}", f"Question this investor asks: {lens['question']}", f"Overall result of the checks: {lens['word']}"]
    if lens.get("note"):
        lines.append(f"What kind of stock it looks like: {lens['note']['category']} ({lens['note']['why']})")
    lines += ["", "Checks:"]
    for c in lens["checks"]:
        lines.append(f"- [{c['result'].upper()}] {c['check']} Found: {c['shown']}. Idea: {c['principle']}.")
    lines += ["", f"Overall picture for context: {headline}"]
    return "\n".join(lines)


def _ask(gateway, lens: dict, company: str, headline: str, note: str = "") -> dict | None:
    msgs = [{"role": "system", "content": system_for(lens)}, {"role": "user", "content": prompt(lens, company, headline) + note}]
    try:
        raw = gateway.complete(f"narrative_{lens['key']}", msgs, purpose="research_narrative", max_tokens=900,
                               session_id=f"narrative:{lens['key']}")
        got = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        view, ahead = str(got["view"]).strip(), str(got["ahead"]).strip()
        return {"view": view, "ahead": ahead} if view and ahead else None
    except Exception:
        return None


def write(gateway, lens: dict, company: str, headline: str, extra_numbers: list[str] = ()) -> dict | None:
    ok = allowed(lens, list(extra_numbers) + [headline])
    note = ""
    for _ in range(2):
        got = _ask(gateway, lens, company, headline, note)
        if not got:
            return None
        bad = sorted((numbers(got["view"]) | numbers(got["ahead"])) - ok)
        if not bad:
            return got
        note = f"\n\nYour last answer used numbers that are not in the checks or the background: {', '.join(bad)}. Rewrite without them."
    return None


def attach(gateway, analysis: dict, company: str, extra_numbers: list[str] = ()) -> None:
    """Add `narrative` (the view) and `ahead` to every lens, or None for both; the calls run side by side."""
    head = analysis["overall"]["headline"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        texts = list(pool.map(lambda l: write(gateway, l, company, head, extra_numbers), analysis["lenses"]))
    for lens, t in zip(analysis["lenses"], texts):
        lens["narrative"] = t["view"] if t else None
        lens["ahead"] = t["ahead"] if t else None
