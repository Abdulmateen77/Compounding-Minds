"""Builds ingest/universe.json (README 4.2). Run: python -m ingest.build_universe

Person A decides WHO is in the universe; Person B's fetcher resolves each ticker to a CIK
from SEC company_tickers.json and fills `cik`. Names and tickers live only in this file and
the `companies` table. They never go into an agent prompt.

Selection rules (checked by ingest/universe.py and its tests):
  * 50 US operating companies with 10-K/10-Q filings across 2017 to 2025
  * no banks, insurers or REITs: the metric set (FCF, gross margin, debt/EBITDA) does not
    fit their statements
  * a mix of sectors, with COVID "hit", "resilient" and "mixed" groups, so the replay shows
    a visible 2020 shock and a recovery
  * 10 held out of ALL learning (README 9), spread over sectors and COVID groups, and
    including some distress candidates so the held-out set has positive Risk outcomes
  * anon IDs come from a seeded shuffle so an ID says nothing about sector or ticker
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


def build() -> dict:
    rows = list(_COMPANIES)
    random.Random(SEED).shuffle(rows)
    companies = [
        {
            "company_id": f"anon_{i + 1:03d}",
            "ticker": t,
            "name": n,
            "sector": s,
            "covid_group": g,
            "held_out": h,
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
    print(f"wrote {OUT} ({len(_COMPANIES)} companies)")
