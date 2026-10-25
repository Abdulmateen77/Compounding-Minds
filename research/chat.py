"""One-on-one questions to one investor lens, answered only from that lens's own checks.

The reader asks why an investor reached their reading. The model is given (1) the guide for that investor, distilled from
their books, and (2) the checks the rules already ran on this company, the price comparison and the overall picture. It is told
to add nothing, to speak as an AI portrayal of the lens (never as the real person) and never to say buy, sell or hold. The reply
goes through the same number guard as the written views (research/narrative.py): a number that is not in the checks, the
background, the price line or the reader's own words sends it back once, and then it is replaced by a plain answer built straight
from the checks. So every figure in a chat answer comes from the report, and the chat works without a model.
"""
from __future__ import annotations

import re

from .analysis import guide_text
from .narrative import FREE, numbers

MAX_QUESTION = 400
MAX_TURNS = 6                  # earlier turns kept as context, newest last
MAX_TURN_CHARS = 1200

INSTRUCTIONS = (
    "You are an AI portrayal of how the investor named below reads a company, built only from the background on how they think "
    "(from their published books) and from checks that were already run on this company's SEC filings. You are not the real "
    "person and you never claim to be: no invented quotes, no private opinions, no claims about what the real person said or "
    "thinks about this company. Speak in the first person as that way of thinking ('I look for ...'), in plain English, in 3 to 6 "
    "short sentences.\n\n"
    "Answer the reader's question about why this reading was reached, for example which checks passed or failed and what the "
    "number found was. Use only the background, the checks, the price comparison and the overall picture you are given. If the "
    "answer is not in them, say so and say what the checks do show. Do not add facts, numbers, forecasts or knowledge about the "
    "company from anywhere else. Every number you write must appear in the material you were given, or in the reader's own "
    "question, exactly as given. Do not tell the reader to buy, sell or hold, do not give a price target and do not predict the "
    "share price: if asked, say this is a research tool and not advice, then explain what the checks show. "
    "Reply in plain text only, with no headings, lists or markdown."
)

ADVICE = re.compile(r"\b(buy|sell|hold|short|invest in|price target|will (?:it|the (?:stock|share price)) (?:go|rise|fall|drop|double)|"
                    r"predict|forecast|worth buying|good investment|should i)\b", re.I)
STOP = {"what", "which", "that", "this", "with", "have", "does", "your", "about", "from", "they", "their", "there", "would",
        "could", "should", "reason", "because", "verdict", "reading", "check", "checks", "company", "explain", "tell", "give"}
RESULT_WORD = {"pass": "passes", "partial": "only partly passes", "fail": "fails", "unknown": "could not be tested"}
REFUSAL = ("I can't tell you to buy, sell or hold, or where the price is going: this is a research tool, not advice. "
           "What I can do is show what my checks found. ")


def _label(c: dict) -> str:
    return c["check"].split(":")[0].strip()


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def facts(lens: dict, company: str, report: dict) -> str:
    """Everything the model may use, and the only text numbers are checked against besides the guide."""
    a = report.get("analysis") or {}
    val = a.get("valuation") or {}
    lines = [f"Company: {company}", f"Question this investor asks: {lens['question']}", f"Reading: {lens['word']}"]
    if lens.get("fit") is not None:
        lines.append(f"Share of known checks passed (partly passing counts half): {round(lens['fit'] * 100)}%")
    if lens.get("note"):
        lines.append(f"What kind of stock it looks like: {lens['note']['category']} ({lens['note']['why']})")
    lines += ["", "Checks:"]
    for c in lens["checks"]:
        lines.append(f"- [{c['result'].upper()}] {c['check']} Found: {c['shown']}. Idea: {c['principle']} ({c['source']}).")
    if lens.get("ahead"):
        lines += ["", f"What I would watch over the next few years (written earlier from these same checks): {lens['ahead']}"]
    if val.get("available") and val.get("position_text"):
        lines += ["", f"Price compared with its record: {val['position_text']}"]
    if (a.get("overall") or {}).get("headline"):
        lines += ["", f"Overall picture across all investors: {a['overall']['headline']}"]
    return "\n".join(lines)


def system_for(lens: dict) -> str:
    """Stable per investor, so Mubit sees one task per investor."""
    return f"{INSTRUCTIONS}\n\nInvestor: {lens['name']}\n\nBackground on how {lens['name']} thinks:\n{guide_text(lens['key'])}"


def rules_answer(lens: dict, question: str) -> str:
    """The answer built straight from the checks: used when there is no model, or its reply broke the number guard."""
    prefix = REFUSAL if ADVICE.search(question) else ""
    q = _tokens(question)
    best, score = None, 0
    for c in lens["checks"]:
        s = len(q & _tokens(f"{c['check']} {c['principle']} {c['shown']}"))
        if s > score:
            best, score = c, s
    if best and score >= 2:
        return (f"{prefix}On “{_label(best)}”: I found {best['shown']}. That {RESULT_WORD[best['result']]}. "
                f"The idea behind it: {best['principle']} ({best['source']}).")
    passed = [c for c in lens["checks"] if c["result"] == "pass"]
    failed = [c for c in lens["checks"] if c["result"] == "fail"]
    known = [c for c in lens["checks"] if c["result"] != "unknown"]
    parts = [f"I read this as “{lens['word']}”: {len(passed)} of {len(known)} checks passed."]
    if passed:
        parts.append("What held up: " + "; ".join(_label(c) for c in passed[:3]) + ".")
    if failed:
        parts.append("What did not: " + "; ".join(f"{_label(c)} (I found {c['shown']})" for c in failed[:3]) + ".")
    return prefix + " ".join(parts)


def _ask(gateway, lens: dict, user_block: str, history: list[dict], note: str, company: str = "") -> str | None:
    msgs = [{"role": "system", "content": system_for(lens)}, *history, {"role": "user", "content": user_block + note}]
    try:
        raw = gateway.complete(f"chat_{lens['key']}", msgs, purpose="research_chat", max_tokens=700, session_id=f"chat:{lens['key']}:{company}")
    except Exception:
        return None
    out = str(raw).strip()
    return out or None


def answer(gateway, report: dict, lens: dict, question: str, history: list[dict] | None = None) -> dict:
    """{"answer", "source": "model" | "rules", "lens"}. Never raises on a model failure; the rules answer takes over."""
    question = question.strip()[:MAX_QUESTION]
    turns = [{"role": t["role"], "content": str(t["content"])[:MAX_TURN_CHARS]} for t in (history or [])
             if t.get("role") in ("user", "assistant") and str(t.get("content", "")).strip()][-MAX_TURNS:]
    company = report["company"]["name"]
    if gateway is not None and question:
        sheet = facts(lens, company, report)
        ok = numbers(" ".join([sheet, guide_text(lens["key"]), question] + [t["content"] for t in turns])) | FREE
        # The sheet leads the first user turn only; later turns already carry it through the history.
        block = f"{sheet}\n\nReader's question: {question}" if not turns else f"Reader's question: {question}"
        if turns and turns[0]["role"] == "user":
            turns[0] = {"role": "user", "content": f"{sheet}\n\n{turns[0]['content']}"}
        elif turns:
            block = f"{sheet}\n\nReader's question: {question}"
        note = ""
        for _ in range(2):
            text = _ask(gateway, lens, block, turns, note, company)
            if not text:
                break
            bad = sorted(numbers(text) - ok)
            if not bad:
                return {"answer": text, "source": "model", "lens": lens["key"]}
            note = f"\n\nYour last answer used numbers that are not in the material: {', '.join(bad)}. Answer again without them."
    return {"answer": rules_answer(lens, question), "source": "rules", "lens": lens["key"]}
