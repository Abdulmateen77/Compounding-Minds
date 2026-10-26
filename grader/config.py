"""Fixed grading config. Tune on the training window only, never on held-out."""
BUCKETS = {"bear": (float("-inf"), 0.0), "base": (0.0, 0.10), "bull": (0.10, float("inf"))}
BUCKET_ORDER = ("bear", "base", "bull")
GOING_CONCERN_KEYWORDS = ("substantial doubt", "going concern")
# Sapling (going-concern text check). When Sapling's calibrated status is "unsure", accept its
# top label only if that label's probability is at least this; otherwise the call is unresolvable.
# 0.50 = the top label must hold a majority. Sapling (research preview) returned "unsure" with
# 0.54-0.78 on four hand-written test excerpts, all with the right top label; at 0.90 every call
# was unresolvable. Retune on the training window once real filings are cached, never held-out.
SAPLING_MIN_PROB_WHEN_UNSURE = 0.50
GOING_CONCERN_SNIPPET_CHARS = 700     # text kept either side of each keyword hit
GOING_CONCERN_MAX_EVIDENCE_CHARS = 24_000  # stays well under Sapling's 16k-token input limit
RISK_TEXT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
DIVIDEND_CUT_THRESHOLD = 0.25
MAX_CORRECTIONS_PER_AGENT_PER_QUARTER = 10

# ---- Scenarios bucket thresholds (revenue_bucket_next_4q) --------------------------------
# BUCKETS above are the ONLY place the thresholds live. Actual growth = sum of the next four
# discrete quarters of revenue / trailing four quarters (the four ending at the latest quarter
# visible at as_of) - 1. bear < 0%, base 0% to <10%, bull >= 10%. Documented as TUNED ON THE
# TRAIN WINDOW ONLY (2018Q1-2021Q4 as_of dates): if they change, change them from train-window
# growth distributions and never look at held-out. The current values are the README 7.1
# defaults, set before any data was seen, so no held-out information has leaked into them.

# ---- Resolution deadlines (days after as_of). If the needed filings are not visible by then
# the call is `unresolvable` (excluded from accuracy and logged), never graded wrong. --------
FUNDAMENTALS_RESOLUTION_DAYS = 240   # next quarter ends <= ~92d after Q0, filed <= ~90d later
SCENARIOS_RESOLUTION_DAYS = 520      # four more quarters plus 10-K lag for the last one
# Nominal horizon dates for grades whose rule gave none (stubs). Never longer than the horizon end
# (replay.resolve_by takes the max of the two), so a stub grade is never delayed past its horizon.
DEFAULT_RESOLUTION_DAYS = {"next_quarter": 90, "4_quarters": 365, "12_months": 365}

# Discrete-quarter shape (days between period start and end of one fiscal quarter).
QUARTER_DAYS = (80, 100)

# ---- Corrections (grader/corrections.py) ----------------------------------------------------
OVERCONFIDENT_AT = 0.80               # a miss at or above this confidence is "overconfident"
REGIME_GDP_GROWTH_BELOW = 0.0         # inputs_snapshot gdp_growth_yoy below this = a regime shift
