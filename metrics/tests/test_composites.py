"""Concepts a filer reports only as parts (SPEC section 1b): D&A = depreciation + amortization of
intangibles, pretax income = domestic + foreign. Expected values are worked out by hand from the
factory's synthetic company, not from the code under test."""
from datetime import date

from metrics import get_metrics

from . import factory as F
from .test_metrics import AFTER, close, metric, opinc, ttm  # noqa: F401  (opinc/ttm: reference series)

DEP = lambda i: 3                                      # noqa: E731
AMORT = lambda i: 2                                    # noqa: E731


def facts_with_parts(**extra):
    """The default company, but D&A reported only as two parts (5 = 3 + 2)."""
    return F.build_facts(depreciation_amortization=None, depreciation=DEP, amortization_intangibles=AMORT, **extra)


def test_da_reported_as_parts_gives_the_same_debt_to_ebitda_as_a_reported_total():
    F.install(F.build_facts())
    want = metric(get_metrics("anon_001", "fundamentals", AFTER), "debt_to_ebitda")
    F.install(facts_with_parts())
    got = metric(get_metrics("anon_001", "fundamentals", AFTER), "debt_to_ebitda")
    close(got, want)
    close(got, (100 + 20) / (ttm(opinc, 23) + 4 * 5))   # (long + short debt) / (EBIT + D&A), by hand


def test_a_reported_total_beats_the_parts():
    parts = facts_with_parts()
    total = F.build_facts(depreciation_amortization=lambda i: 9)
    F.install(parts + [f for f in total if f["concept"] == "depreciation_amortization"])
    b = get_metrics("anon_001", "fundamentals", AFTER)
    close(metric(b, "debt_to_ebitda"), 120 / (ttm(opinc, 23) + 4 * 9))


def test_a_quarter_missing_one_part_is_missing_not_half_a_value():
    facts = [f for f in facts_with_parts()
             if not (f["concept"] == "amortization_intangibles" and f["fiscal_year"] == 2018)]
    F.install(facts)
    b = get_metrics("anon_001", "fundamentals", AFTER)
    assert metric(b, "debt_to_ebitda") is None           # TTM D&A at 2018Q4 needs all four quarters


def test_pretax_income_reported_as_domestic_and_foreign_feeds_roic():
    F.install(F.build_facts())
    want = metric(get_metrics("anon_001", "fundamentals", AFTER), "roic")
    F.install(F.build_facts(pretax_income=None, pretax_income_domestic=lambda i: 10 + i,
                            pretax_income_foreign=lambda i: 8))          # sums to the default 18 + i
    got = metric(get_metrics("anon_001", "fundamentals", AFTER), "roic")
    close(got, want)


def test_the_sum_is_only_available_from_the_later_filing():
    """Parts filed on different dates: the sum cannot be known before both are public."""
    facts = facts_with_parts()
    for f in facts:
        if f["concept"] == "amortization_intangibles" and f["accession"] == "ACC-2018-FY":
            f["accession"], f["filed_date"] = "ACC-2018-FY-LATE", date(2019, 4, 1)   # one part arrives late
    F.install(facts)
    assert metric(get_metrics("anon_001", "fundamentals", AFTER), "debt_to_ebitda") is None   # 2018Q4 D&A unknown
    late = get_metrics("anon_001", "fundamentals", date(2019, 4, 2))
    close(metric(late, "debt_to_ebitda"), 120 / (ttm(opinc, 23) + 20))


def test_inputs_cite_the_filings_of_both_parts():
    facts = facts_with_parts()
    for f in facts:
        if f["concept"] == "amortization_intangibles" and f["accession"] == "ACC-2018-FY":
            f["accession"] = "ACC-2018-FY-AMORT"
    F.install(facts)
    b = get_metrics("anon_001", "fundamentals", AFTER)
    cited = next(m["inputs"] for m in b["metrics"] if m["name"] == "debt_to_ebitda")
    assert {"ACC-2018-FY", "ACC-2018-FY-AMORT"} <= set(cited) <= F.all_accessions(facts)
