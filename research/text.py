"""What the company says about itself: verbatim sentences from its latest 10-K.

No model writes this. Sentences are picked by simple rules (strategy words in the Business section, R&D words,
forward-looking words in Management's Discussion) and shown with the filing they came from, so a reader can
check every line. The same pass counts going-concern language for the Risk analyst.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

from ingest.events import detect_going_concern, strip_html
from ingest.sec import SecClient

MAX_CHARS = 8_000_000
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"])")
NOISE = re.compile(r"audit years|tax law|income tax|litigation|lawsuit|court|legal proceeding|investigation|fight|"
                   r"indemnif|regulatory authorit|settlement|stock-based|warrant|covenant", re.I)
HEADING = re.compile(r"^(?:(?:[A-Z][A-Za-z&/-]+|[A-Z]{2,})\s){1,3}(?=(?:We|Our|The|To|In|As|This|These|Through|With|Each)\s)")
BOILERPLATE = re.compile(
    r"forward-looking|risks? and uncertaint|actual results|could differ|safe harbor|incorporated by reference|"
    r"see (item|part|note)|refer to|table of contents|pursuant to|annual report on form", re.I)

STRATEGY = re.compile(
    r"\b(our strategy|our strategic|we plan to|we intend to|we are focused on|we continue to (invest|expand|build|focus)|"
    r"we aim to|our goal|our mission|we seek to|we are (building|expanding|investing))\b", re.I)
RND = re.compile(r"\b(research and development|R&D)\b", re.I)
RND_ACTION = re.compile(r"\b(invest|develop|focus|increase|expect|innovat|new product|technolog)", re.I)
OUTLOOK = re.compile(r"\b(we expect|we currently expect|we anticipate|we project|the company (expects|anticipates)|"
                     r"management (expects|anticipates)|we believe (that )?(our|demand|revenue|growth|capital))\b", re.I)
OUTLOOK_TOPIC = re.compile(r"growth|demand|capital expenditure|production|margin|cost reduction|liquidity|revenue|capacity|deliver|invest", re.I)
WHAT_WE_DO = re.compile(r"^(We|Our company|The Company|[A-Z][\w&.,' -]{2,40}) (design|develop|manufactur|operate|provid|offer|is a|are a|sell|produce|engage)", re.I)


@dataclass
class Plans:
    source: dict
    about: str | None
    strategy: list[str] = field(default_factory=list)
    rnd: list[str] = field(default_factory=list)
    outlook: list[str] = field(default_factory=list)
    going_concern_hits: int = 0

    def as_dict(self) -> dict:
        return {"source": self.source, "about": self.about, "strategy": self.strategy, "rnd": self.rnd,
                "outlook": self.outlook, "going_concern_hits": self.going_concern_hits}


def latest_10k(filings: list[dict]) -> dict | None:
    rows = [f for f in filings if f.get("form") == "10-K" and f.get("primaryDocument")]
    return max(rows, key=lambda f: f["filingDate"]) if rows else None


RISKY = re.compile(r"\b(may|might|could|would|if we|no assurance|adversely|unable|unforeseen|fail to|failure to)\b", re.I)
ABOUT_HEAD = 150_000            # the company description is near the start of the filing
PER_CATEGORY = 25               # candidates offered to the chooser
KEEP = {"strategy": 3, "rnd": 3, "outlook": 3}


def _sentences(block: str) -> list[str]:
    out = []
    for s in SENTENCE.split(re.sub(r"\s+", " ", html.unescape(block))):
        s = HEADING.sub("", s.strip(), count=1).strip()      # "BUSINESS Overview We are ..." -> "We are ..."
        if 70 <= len(s) <= 380 and not BOILERPLATE.search(s) and not NOISE.search(s) and s[0].isupper():
            out.append(s)
    return out


def _spread(hits: list[str], n: int) -> list[str]:
    if len(hits) <= n:
        return hits
    step = len(hits) / n                      # spread through the filing, not the first n
    return [hits[int(i * step)] for i in range(n)]


def candidates(text: str) -> dict[str, list[str]]:
    """Declarative sentences (no 'may / could / if we': those are risk factors) that talk about plans, R&D or
    expectations, found anywhere in the filing. Rules give recall; the chooser below gives judgement."""
    sents = _sentences(text)
    plain = [s for s in sents if not RISKY.search(s)]
    about = [s for s in _sentences(text[:ABOUT_HEAD]) if not RISKY.search(s) and WHAT_WE_DO.match(s)]
    return {
        "about": about[:10],
        "strategy": _spread([s for s in plain if STRATEGY.search(s)], PER_CATEGORY),
        "rnd": _spread([s for s in plain if RND.search(s) and RND_ACTION.search(s)], PER_CATEGORY),
        "outlook": _spread([s for s in plain if OUTLOOK.search(s) and OUTLOOK_TOPIC.search(s)], PER_CATEGORY),
    }


CHOOSER_SYSTEM = (
    "You help a reader understand a company from its own annual report. You are given numbered sentences copied from the "
    "filing, in four groups. Choose the sentences that best answer each group's question for an investor. Reply with "
    "JSON only, no other text, in this shape: "
    '{"about": <number or null>, "strategy": [numbers], "rnd": [numbers], "outlook": [numbers]}. '
    "about: the one sentence that says what the company does. strategy: up to 3 sentences about concrete plans or "
    "priorities (new products, markets, capacity, acquisitions). rnd: up to 3 about what it is researching or developing. "
    "outlook: up to 3 about what management expects for demand, costs, spending or growth. Prefer specific sentences over "
    "generic ones. Only use the numbers you were given."
)


def _choose(cands: dict[str, list[str]], gateway) -> dict | None:
    lines, n = [], 0
    index: dict[int, str] = {}
    for group, label in (("about", "WHAT THE COMPANY DOES"), ("strategy", "PLANS AND PRIORITIES"),
                         ("rnd", "RESEARCH AND DEVELOPMENT"), ("outlook", "MANAGEMENT EXPECTATIONS")):
        lines.append(f"## {label}")
        for sentence in cands[group]:
            n += 1
            index[n] = sentence
            lines.append(f"{n}. {sentence}")
    try:
        raw = gateway.complete("research_text", [{"role": "system", "content": CHOOSER_SYSTEM},
                                                 {"role": "user", "content": "\n".join(lines)}],
                               purpose="research_plans", max_tokens=600)
        picked = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except Exception:
        return None

    def get(i):
        return index.get(i) if isinstance(i, int) else None

    return {
        "about": get(picked.get("about")),
        **{k: [x for x in (get(i) for i in (picked.get(k) or [])[: KEEP[k]]) if x] for k in KEEP},
    }


def extract(text: str, gateway=None) -> tuple[str | None, list[str], list[str], list[str]]:
    c = candidates(text)
    chosen = _choose(c, gateway) if gateway is not None else None
    if chosen is None:        # no model (or it failed): the first few candidates, still verbatim
        chosen = {"about": c["about"][0] if c["about"] else None, **{k: c[k][: KEEP[k]] for k in KEEP}}
    return chosen["about"], chosen["strategy"], chosen["rnd"], chosen["outlook"]


def read_plans(sec: SecClient, cik: int, filings: list[dict], gateway=None) -> Plans | None:
    f = latest_10k(filings)
    if not f:
        return None
    try:
        raw = sec.filing_document(cik, f["accessionNumber"], f["primaryDocument"])
    except Exception:
        return None
    text = strip_html(raw.decode("utf-8", errors="ignore")[:MAX_CHARS])
    about, strategy, rnd, outlook = extract(text, gateway)
    src = {"form": "10-K", "filed": f["filingDate"], "accession": f["accessionNumber"],
           "url": sec.archive_url(cik, f["accessionNumber"], f["primaryDocument"])}
    return Plans(src, about, strategy, rnd, outlook, len(detect_going_concern(text)))
