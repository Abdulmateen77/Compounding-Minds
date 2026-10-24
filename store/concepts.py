"""The XBRL concept map: which us-gaap tags feed which of OUR concepts, and which concepts
each metric needs (README 4.1, metrics/SPEC.md). Person A decides this; Person B's ingest
uses `TAG_TO_CONCEPT` to know what to keep and `resolve_concept` to pick between tags.

Why a map: companies tag the same idea differently (Revenues vs
RevenueFromContractWithCustomerExcludingAssessedTax) and often switch tags over time (the
2018 revenue-recognition change). Everything downstream asks for ONE name, e.g. "revenue".

Tag names are standard us-gaap elements. They are checked against real `companyfacts` as
soon as Person B's data lands (see store/tests/test_concepts.py::test_real_coverage).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    key: str
    tags: tuple[str, ...]          # us-gaap tags, best first
    unit: str                      # USD | USD/shares | shares
    kind: str                      # duration | instant
    cumulative_in_10q: bool = False  # 10-Q reports year-to-date totals (cash-flow items)
    note: str = ""


def _c(key, tags, unit="USD", kind="duration", cum=False, note=""):
    return Concept(key, tuple(tags), unit, kind, cum, note)


CONCEPTS: dict[str, Concept] = {c.key: c for c in [
    # ---- income statement: 10-Qs report discrete 3-month facts, so no derivation needed
    _c("revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                   "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                   "SalesRevenueGoodsNet"]),
    _c("cost_of_revenue", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    _c("gross_profit", ["GrossProfit"], note="if missing: revenue - cost_of_revenue, decided in metrics/"),
    _c("operating_income", ["OperatingIncomeLoss"],
       note="many filers (pharma, energy, Nike, Nucor) never tag it: metrics/context.py derives it, see costs_and_expenses"),
    _c("costs_and_expenses", ["CostsAndExpenses", "OperatingCostsAndExpenses"],
       note="fallback: operating income = revenue - costs_and_expenses"),
    _c("net_income", ["NetIncomeLoss"]),
    _c("pretax_income", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    _c("income_tax_expense", ["IncomeTaxExpenseBenefit"]),
    _c("interest_expense", ["InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense"]),
    _c("rnd_expense", ["ResearchAndDevelopmentExpense"], note="Moat agent only"),
    _c("sga_expense", ["SellingGeneralAndAdministrativeExpense"], note="Moat agent only"),
    # ---- cash flow: 10-Qs report year-to-date (3, 6, 9 months), Q4 = full year - 9 months
    _c("op_cash_flow", ["NetCashProvidedByUsedInOperatingActivities"], cum=True),
    _c("capex", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                 "PaymentsToAcquireOtherPropertyPlantAndEquipment"], cum=True,
       note="reported as a positive outflow; FCF = op_cash_flow - capex"),
    _c("depreciation_amortization", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                                     "DepreciationAmortizationAndAccretionNet", "DepreciationAmortizationAndOther",
                                     "Depreciation"], cum=True,
       note="Depreciation alone understates D&A a little (amortization is separate); it beats having no figure"),
    _c("dividends_paid", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends"], cum=True),
    _c("dividends_per_share", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"],
       unit="USD/shares", note="cross-check for dividend cuts; not every filer tags it"),
    # ---- balance sheet: point-in-time (instant) values
    _c("current_assets", ["AssetsCurrent"], kind="instant"),
    _c("current_liabilities", ["LiabilitiesCurrent"], kind="instant"),
    _c("total_assets", ["Assets"], kind="instant"),
    _c("cash", ["CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], kind="instant"),
    _c("equity", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
       kind="instant"),
    # Debt is tagged three ways. `total_debt` (current + non-current in one figure) is used when reported;
    # otherwise the two parts are added.
    _c("total_debt", ["DebtLongtermAndShorttermCombinedAmount",
                      "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "LongTermDebt"],
       kind="instant", note="includes the current part: never add short_term_debt on top"),
    _c("long_term_debt", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"], kind="instant",
       note="the non-current part only"),
    _c("short_term_debt", ["DebtCurrent", "ShortTermBorrowings", "LongTermDebtCurrent",
                           "LongTermDebtAndCapitalLeaseObligationsCurrent", "CommercialPaper"], kind="instant",
       note="the current part: current maturities plus short-term borrowings"),
]}

TAG_TO_CONCEPT: dict[str, str] = {tag: c.key for c in CONCEPTS.values() for tag in c.tags}
ALL_TAGS: frozenset[str] = frozenset(TAG_TO_CONCEPT)

# Macro series: (FRED id, needs vintages, note). ALFRED vintages for revised series so we only
# see what was known at `as_of`. Market rates are never revised: vintage_date = obs_date.
MACRO_SERIES: dict[str, tuple[str, bool, str]] = {
    "gdp": ("GDPC1", True, "real GDP, quarterly, revised: ALFRED vintages required"),
    "unemployment": ("UNRATE", True, "revised by seasonal adjustment: ALFRED vintages"),
    "yield_curve": ("T10Y2Y", False, "10y minus 2y Treasury spread, market series"),
    "credit_spread": ("BAA10Y", False, "Moody's Baa yield minus 10y Treasury, market series"),
}

# Inputs each metric needs. Concept keys come from CONCEPTS; "event:" and "macro:" are the
# other two sources. The metric names are the contract with agents, principles/ and the stubs.
METRIC_INPUTS: dict[str, tuple[str, ...]] = {
    # Fundamentals (Buffett)
    "fcf_margin_ttm": ("op_cash_flow", "capex", "revenue"),
    "fcf_margin_qoq_change": ("op_cash_flow", "capex", "revenue"),
    "operating_margin": ("operating_income", "costs_and_expenses", "pretax_income", "interest_expense", "revenue"),
    "roic": ("operating_income", "costs_and_expenses", "income_tax_expense", "pretax_income", "equity",
             "total_debt", "long_term_debt", "short_term_debt", "cash"),
    "debt_to_ebitda": ("total_debt", "long_term_debt", "short_term_debt", "operating_income",
                       "costs_and_expenses", "pretax_income", "interest_expense", "depreciation_amortization"),
    "fcf_slope_8q": ("op_cash_flow", "capex", "revenue"),
    "capex_to_revenue": ("capex", "revenue"),
    # Risk (Munger)
    "interest_coverage": ("operating_income", "costs_and_expenses", "pretax_income", "interest_expense"),
    "current_ratio": ("current_assets", "current_liabilities"),
    "cash_runway_quarters": ("cash", "op_cash_flow", "capex"),
    "dividend_cut_history_5y": ("dividends_paid", "dividends_per_share"),
    "auditor_changes_5y": ("event:8-K item 4.01",),
    "going_concern_hits": ("event:10-K/10-Q going-concern passages",),
    "leverage_trend_8q": ("total_debt", "long_term_debt", "short_term_debt", "operating_income",
                          "costs_and_expenses", "pretax_income", "interest_expense", "depreciation_amortization"),
    # Scenarios (Dalio)
    "revenue_growth_yoy": ("revenue",),
    "revenue_growth_mean_5y": ("revenue",),
    "revenue_growth_std_5y": ("revenue",),
    "revenue_macro_beta": ("revenue", "macro:gdp"),
    "gdp_growth_yoy": ("macro:gdp",),
    "unemployment_rate": ("macro:unemployment",),
    "yield_curve_10y_2y": ("macro:yield_curve",),
    "credit_spread_baa": ("macro:credit_spread",),
}


def resolve_concept(key: str, rows_by_tag: dict[str, list[dict]]) -> list[dict]:
    """Merge rows from several tags into one series for concept `key`.

    Within ONE filing (accession) and ONE period, several tags may carry the same idea; keep the
    highest-priority one. Across filings keep every row: a restated value (same period, later
    accession) stays visible to the date gate, even when the restating filing used a different
    tag (the 2018 revenue-recognition change moved many filers from `Revenues` to
    `RevenueFromContract...`, so the old and new values sit under different tags).
    """
    concept = CONCEPTS[key]
    rank = {t: i for i, t in enumerate(concept.tags)}
    best: dict[tuple, tuple[int, str]] = {}
    for tag, rows in rows_by_tag.items():
        if tag not in rank:
            continue
        for r in rows:
            k = (r.get("period_start"), r["period_end"], r.get("accession"))
            if k not in best or rank[tag] < best[k][0]:
                best[k] = (rank[tag], tag)
    out: list[dict] = []
    for tag, rows in rows_by_tag.items():
        for r in rows:
            k = (r.get("period_start"), r["period_end"], r.get("accession"))
            if best.get(k, (None, None))[1] == tag:
                out.append({**r, "concept": key, "source_tag": tag})
    return out
