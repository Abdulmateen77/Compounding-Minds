"""store/quality.py: composites count as present, and only the listed companies are exempt from operating_income."""
from store import quality
from store.concepts import COMPOSITES, CONCEPTS


def test_composite_parts_are_known_concepts_and_the_total_is_one_too():
    for total, parts in COMPOSITES.items():
        assert total in CONCEPTS and all(p in CONCEPTS for p in parts)


def test_exemption_list_is_exactly_the_ten_without_a_usable_operating_income_line():
    ex = quality.OPERATING_INCOME_EXEMPT
    assert {v.split(":")[0] for v in ex.values()} == {"COP", "MRK", "NKE", "XOM", "NUE", "PFE", "LLY", "HON", "JNJ", "GE"}
    assert all(len(v.split(":", 1)[1].strip()) > 10 for v in ex.values()), "every exemption carries a reason"


def test_parts_satisfy_a_required_composite_and_the_exemption_is_company_specific(pg_conn, monkeypatch):
    monkeypatch.setattr(quality, "COMPOSITE_MIN_FACTS", 1)
    cols = "(company_id, concept, unit, value, period_start, period_end, filed_date, accession, form)"
    with pg_conn.cursor() as cur:
        for cid in ("anon_001", "anon_002"):       # anon_001 is exempt from operating_income, anon_002 is not
            cur.execute("INSERT INTO companies (company_id, cik, ticker, name, sector, held_out, short_history) "
                        "VALUES (%s, %s, %s, %s, 'Tech', false, false)", (cid, cid[-3:], cid, cid))
            for c in quality.REQUIRED:
                if c in ("operating_income", "depreciation_amortization", "pretax_income"):
                    continue
                cur.execute(f"INSERT INTO facts {cols} VALUES (%s,%s,'USD',1,'2010-01-01','2010-03-31','2010-05-01','A','10-Q')",
                            (cid, c))
            for c in ("depreciation", "amortization_intangibles", "pretax_income_domestic", "pretax_income_foreign"):
                cur.execute(f"INSERT INTO facts {cols} VALUES (%s,%s,'USD',1,'2010-01-01','2010-03-31','2010-05-01','A','10-Q')",
                            (cid, c))
    rep = {r["company_id"]: r for r in quality.coverage(pg_conn)}
    assert rep["anon_001"]["missing_required"] == [] and rep["anon_001"]["exempt"] == ["operating_income"]
    assert rep["anon_001"]["exempt_reason"].startswith("COP:")
    assert rep["anon_002"]["missing_required"] == ["operating_income"]


def test_parts_reported_too_rarely_to_build_quarters_do_not_count(pg_conn):
    """MSFT and MCD tag their parts once a year: present, but useless for a quarter, so still flagged."""
    cols = "(company_id, concept, unit, value, period_start, period_end, filed_date, accession, form)"
    with pg_conn.cursor() as cur:
        cur.execute("INSERT INTO companies (company_id, cik, ticker, name, sector, held_out, short_history) "
                    "VALUES ('anon_002', '2', 'X', 'X', 'Tech', false, false)")
        for c in quality.REQUIRED:
            if c in ("depreciation_amortization", "operating_income", "pretax_income"):
                continue
            cur.execute(f"INSERT INTO facts {cols} VALUES ('anon_002',%s,'USD',1,'2010-01-01','2010-03-31','2010-05-01','A','10-Q')", (c,))
        for c in ("depreciation", "amortization_intangibles"):
            cur.execute(f"INSERT INTO facts {cols} VALUES ('anon_002',%s,'USD',1,'2010-01-01','2010-12-31','2011-02-01','A','10-K')", (c,))
    rep = {r["company_id"]: r for r in quality.coverage(pg_conn)}
    assert "depreciation_amortization" in rep["anon_002"]["missing_required"]


def test_known_gaps_are_reported_but_are_not_drop_candidates():
    rep = [{"company_id": "anon_006", "ok": False, "known_gap": quality.KNOWN_GAPS["anon_006"]},
           {"company_id": "anon_099", "ok": False, "known_gap": None},
           {"company_id": "anon_016", "ok": True, "known_gap": quality.KNOWN_GAPS["anon_016"]}]  # fixed since
    assert quality.drop_candidates(rep) == ["anon_099"]
    assert list(quality.known_gaps(rep)) == ["anon_006"]
    rep.append({"company_id": "anon_031", "ok": True, "known_gap": quality.KNOWN_GAPS["anon_031"]})
    assert "anon_031" in quality.known_gaps(rep)          # a period gap the existence check cannot see


def test_known_gaps_are_exactly_mcd_msft_nvda():
    assert {v.split(":")[0] for v in quality.KNOWN_GAPS.values()} == {"MCD", "MSFT", "NVDA"}
