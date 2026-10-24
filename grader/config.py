"""Fixed grading config. Tune on the training window only, never on held-out."""
BUCKETS = {"bear": (float("-inf"), 0.0), "base": (0.0, 0.10), "bull": (0.10, float("inf"))}
BUCKET_ORDER = ("bear", "base", "bull")
GOING_CONCERN_KEYWORDS = ("substantial doubt", "going concern")
# Sapling (going-concern text check). When Sapling's calibrated status is "unsure", accept its
# top label only if that label's probability is at least this; otherwise the call is unresolvable.
SAPLING_MIN_PROB_WHEN_UNSURE = 0.90
GOING_CONCERN_SNIPPET_CHARS = 700     # text kept either side of each keyword hit
GOING_CONCERN_MAX_EVIDENCE_CHARS = 24_000  # stays well under Sapling's 16k-token input limit
RISK_TEXT_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
DIVIDEND_CUT_THRESHOLD = 0.25
MAX_CORRECTIONS_PER_AGENT_PER_QUARTER = 10
