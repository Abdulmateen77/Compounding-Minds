"""Builds ingest/universe.json (README 4.2). Run: python -m ingest.build_universe

Person A decides WHO is in the universe; Person B's fetcher resolves each ticker to a CIK
from SEC company_tickers.json and fills `cik`. Names and tickers live only in this file and
the `companies` table. They never go into an agent prompt.

Selection rules (checked by ingest/universe.py and its tests):
  * 62 US operating companies with 10-K/10-Q filings across 2017 to 2025 (Palantir, which only
    started filing in late 2020, is kept but flagged `short_history`)
  * no banks, insurers or REITs: the metric set (FCF, gross margin, debt/EBITDA) does not
    fit their statements
  * a mix of sectors, with COVID "hit", "resilient" and "mixed" groups, so the replay shows
    a visible 2020 shock and a recovery
  * 12 held out of ALL learning (README 9), spread over sectors and COVID groups, and
    including some distress candidates so the held-out set has positive Risk outcomes
  * anon IDs come from a seeded shuffle so an ID says nothing about sector or ticker. The first
    50 companies keep the IDs they were first given (anon_001 to anon_050) so nothing already
    loaded changes; the 12 added later take anon_051 to anon_062

Not included on purpose: private companies (SpaceX, xAI) have no 10-K or 10-Q history to grade
against, and Broadcom changed CIK in 2018 so its history is split across two filers.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20251025
OUT = Path(__file__).parent / "universe.json"

# ticker, name, sector, covid_group, held_out
_COMPANIES = [
    # Technology
    ("AAPL", "Apple", "Technology", "resilient", False),
    ("MSFT", "Microsoft", "Technology", "resilient", False),
    ("INTC", "Intel", "Technology", "mixed", True),
    ("ORCL", "Oracle", "Technology", "resilient", True),
    ("CSCO", "Cisco Systems", "Technology", "mixed", False),
    ("ADBE", "Adobe", "Technology", "resilient", False),
    ("TXN", "Texas Instruments", "Technology", "mixed", False),
    # Communication
    ("DIS", "Walt Disney", "Communication", "hit", False),
    ("CMCSA", "Comcast", "Communication", "mixed", True),
    ("VZ", "Verizon", "Communication", "resilient", False),
    # Consumer discretionary
    ("HD", "Home Depot", "Consumer Discretionary", "resilient", False),
    ("NKE", "Nike", "Consumer Discretionary", "mixed", True),
    ("MCD", "McDonald's", "Consumer Discretionary", "mixed", False),
    ("SBUX", "Starbucks", "Consumer Discretionary", "hit", False),
    ("MAR", "Marriott International", "Consumer Discretionary", "hit", False),
    ("F", "Ford Motor", "Consumer Discretionary", "hit", True),
    ("GM", "General Motors", "Consumer Discretionary", "hit", False),
    ("DAL", "Delta Air Lines", "Consumer Discretionary", "hit", True),
    ("UAL", "United Airlines Holdings", "Consumer Discretionary", "hit", False),
    ("CCL", "Carnival", "Consumer Discretionary", "hit", False),
    ("TGT", "Target", "Consumer Discretionary", "resilient", False),
    ("M", "Macy's", "Consumer Discretionary", "hit", False),
    ("KSS", "Kohl's", "Consumer Discretionary", "hit", False),
    ("BKNG", "Booking Holdings", "Consumer Discretionary", "hit", False),
    # Consumer staples
    ("KO", "Coca-Cola", "Consumer Staples", "mixed", True),
    ("PG", "Procter & Gamble", "Consumer Staples", "resilient", False),
    ("WMT", "Walmart", "Consumer Staples", "resilient", False),
    ("COST", "Costco Wholesale", "Consumer Staples", "resilient", False),
    ("PEP", "PepsiCo", "Consumer Staples", "resilient", False),
    # Health care
    ("JNJ", "Johnson & Johnson", "Health Care", "resilient", False),
    ("PFE", "Pfizer", "Health Care", "resilient", False),
    ("MRK", "Merck", "Health Care", "resilient", True),
    ("ABT", "Abbott Laboratories", "Health Care", "resilient", False),
    ("MDT", "Medtronic", "Health Care", "hit", False),
    ("LLY", "Eli Lilly", "Health Care", "resilient", False),
    # Industrials
    ("BA", "Boeing", "Industrials", "hit", True),
    ("CAT", "Caterpillar", "Industrials", "mixed", False),
    ("HON", "Honeywell", "Industrials", "mixed", False),
    ("UPS", "United Parcel Service", "Industrials", "resilient", False),
    ("GE", "General Electric", "Industrials", "hit", False),
    ("MMM", "3M", "Industrials", "mixed", False),
    ("LMT", "Lockheed Martin", "Industrials", "resilient", False),
    # Energy
    ("XOM", "Exxon Mobil", "Energy", "hit", False),
    ("CVX", "Chevron", "Energy", "hit", False),
    ("COP", "ConocoPhillips", "Energy", "hit", False),
    ("SLB", "Schlumberger", "Energy", "hit", True),
    # Materials
    ("NUE", "Nucor", "Materials", "mixed", False),
    ("FCX", "Freeport-McMoRan", "Materials", "mixed", False),
    # Utilities
    ("DUK", "Duke Energy", "Utilities", "resilient", False),
    ("NEE", "NextEra Energy", "Utilities", "resilient", False),
]


# Added after the first 50 (tech-heavy). Same tuple shape.
_ADDED = [
    ("TSLA", "Tesla", "Consumer Discretionary", "resilient", False),
    ("NVDA", "NVIDIA", "Technology", "resilient", False),
    ("PLTR", "Palantir Technologies", "Technology", "resilient", False),
    ("AMD", "Advanced Micro Devices", "Technology", "resilient", False),
    ("META", "Meta Platforms", "Communication", "resilient", True),
    ("GOOGL", "Alphabet", "Communication", "mixed", False),
    ("AMZN", "Amazon.com", "Consumer Discretionary", "resilient", False),
    ("NFLX", "Netflix", "Communication", "resilient", False),
    ("CRM", "Salesforce", "Technology", "resilient", False),
    ("QCOM", "Qualcomm", "Technology", "mixed", False),
    ("MU", "Micron Technology", "Technology", "mixed", True),
    ("AMAT", "Applied Materials", "Technology", "resilient", False),
]
SHORT_HISTORY = {"PLTR"}  # first 10-Q was for Q3 2020: metrics exist only from about 2022


def build() -> dict:
    rows = list(_COMPANIES)
    random.Random(SEED).shuffle(rows)  # unchanged: the first 50 keep their IDs
    added = list(_ADDED)
    random.Random(SEED + 1).shuffle(added)
    rows += added
    companies = [
        {
            "company_id": f"anon_{i + 1:03d}",
            "ticker": t,
            "name": n,
            "sector": s,
            "covid_group": g,
            "held_out": h,
            "short_history": t in SHORT_HISTORY,
            "cik": None,  # filled by ingest from SEC company_tickers.json
        }
        for i, (t, n, s, g, h) in enumerate(rows)
    ]
    return {
        "version": 1,
        "note": "Names and tickers stay in the store. Agents only ever see company_id.",
        "companies": companies,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(_COMPANIES) + len(_ADDED)} companies)")
