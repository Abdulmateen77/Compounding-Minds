"""Builds ingest/universe.json (README 4.2). Run: python -m ingest.build_universe

Person A decides WHO is in the universe; Person B's fetcher resolves each ticker to a CIK
from SEC company_tickers.json and fills `cik`. Names and tickers live only in this file and
the `companies` table. They never go into an agent prompt.

Selection rules (checked by ingest/universe.py and its tests):
  * 50 US operating companies with 10-K/10-Q filings across 2017 to 2025. Palantir, which only
    started filing in late 2020, is kept but flagged `short_history`
  * no banks, insurers or REITs: the metric set (FCF, gross margin, debt/EBITDA) does not
    fit their statements
  * tech-heavy (10 of 50, plus Tesla and Amazon under consumer discretionary), with COVID
    "hit", "resilient" and "mixed" groups, so the replay shows a visible 2020 shock and a recovery
  * 10 held out of ALL learning (README 9), spread over 6 sectors and including distress
    candidates, so the held-out set has positive Risk outcomes
  * anon IDs come from a seeded shuffle so an ID says nothing about sector or ticker

Not included on purpose: private companies (SpaceX, xAI) have no 10-K or 10-Q history to grade
against, and Broadcom changed CIK in 2018 so its history is split across two filers.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20251025
OUT = Path(__file__).parent / "universe.json"
# Tickers whose SEC ticker now points at a new registrant. CIK_OVERRIDES pins the CIK to use (else ingest
# resolves it from company_tickers.json); PRIOR_CIKS lists older registrants whose filings load under the same id.
CIK_OVERRIDES = {"XOM": 34088,    # ticker now maps to ExxonMobil Holdings (2026); history is under the old CIK
                 "DIS": 1744489}  # TWDC Enterprises 18 (2019 Fox deal): filings from 2019-05
PRIOR_CIKS = {"DIS": [1001039]}   # old Walt Disney Co: filings 2009 to 2019-02
SHORT_HISTORY = {"PLTR"}  # first 10-Q was for Q3 2020: metrics exist only from about 2022

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
    ("NVDA", "NVIDIA", "Technology", "resilient", False),
    ("PLTR", "Palantir Technologies", "Technology", "resilient", False),
    ("AMD", "Advanced Micro Devices", "Technology", "resilient", False),
    # Communication
    ("DIS", "Walt Disney", "Communication", "hit", False),
    ("CMCSA", "Comcast", "Communication", "mixed", True),
    ("VZ", "Verizon", "Communication", "resilient", False),
    ("META", "Meta Platforms", "Communication", "resilient", True),
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
    ("BKNG", "Booking Holdings", "Consumer Discretionary", "hit", False),
    ("TSLA", "Tesla", "Consumer Discretionary", "resilient", False),
    ("AMZN", "Amazon.com", "Consumer Discretionary", "resilient", False),
    # Consumer staples
    ("KO", "Coca-Cola", "Consumer Staples", "mixed", False),
    ("PG", "Procter & Gamble", "Consumer Staples", "resilient", False),
    ("WMT", "Walmart", "Consumer Staples", "resilient", False),
    ("COST", "Costco Wholesale", "Consumer Staples", "resilient", False),
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
    ("LMT", "Lockheed Martin", "Industrials", "resilient", False),
    # Energy
    ("XOM", "Exxon Mobil", "Energy", "hit", False),
    ("COP", "ConocoPhillips", "Energy", "hit", False),
    ("SLB", "Schlumberger", "Energy", "hit", True),
    # Materials
    ("NUE", "Nucor", "Materials", "mixed", False),
    # Utilities
    ("DUK", "Duke Energy", "Utilities", "resilient", False),
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
            "short_history": t in SHORT_HISTORY,
            "cik": CIK_OVERRIDES.get(t),  # None: filled by ingest from SEC company_tickers.json
            **({"prior_ciks": PRIOR_CIKS[t]} if t in PRIOR_CIKS else {}),
        }
        for i, (t, n, s, g, h) in enumerate(rows)
    ]
    return {
        "version": 2,
        "note": "Names and tickers stay in the store. Agents only ever see company_id.",
        "companies": companies,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(_COMPANIES)} companies)")
