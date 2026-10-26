"""Research any listed company on demand (the pivot: a report on a company as it stands today).

    resolve.py   a name or ticker  ->  the listed company and its market
    live.py      load that company's SEC data into memory, read through the same date gate as the replay
    report.py    Python computes every figure; sections: growth, profit, cash, balance sheet, reinvestment, risk
    text.py      what the company says about its own plans and R&D: verbatim sentences from its latest 10-K
    market.py    price and shares, for market value and multiples (context, never a prediction)

The replay (grader/, agents/) is the evidence of how far to trust the analysts; this package is what a user reads.
"""
