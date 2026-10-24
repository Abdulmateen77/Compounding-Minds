"""Risk rule (distress_event_12m) with a fake Sapling: no network in tests."""
from datetime import date

import pytest

from grader import risk
from grader.grade import grade
from grader.risk import resolve_distress, verdict_to_outcome
from grader.sapling import CacheMiss, SaplingClient, SaplingError, Verdict
from schemas import AgentCall, Claim
from store import queries
from store.queries import InMemoryBackend

AS_OF = date(2019, 6, 30)
GC_TEXT = ("Liquidity. Recurring losses and negative operating cash flow raise substantial doubt "
           "about the Company's ability to continue as a going concern within one year.")
BOILERPLATE = ("Risk factors. If we fail to raise capital, our auditors could in future express "
               "substantial doubt about our ability to continue as a going concern.")
CLEAN = "Revenue grew 4% and the company remains well funded. Nothing unusual to report."


def reply(label, status=None, p=0.97):
    probs = {k: (p if k == label else (1 - p) / 3) for k in
             ("supported", "violation", "insufficient_information", "inconsistent_context")}
    return {"status": status or label, "raw_label": label, "prediction_set": [label], "probabilities": probs}


def make_call(answer="yes", prob=0.7):
    return AgentCall(call_id="c1", run_id="r1", agent="risk", company_id="anon_001", as_of=AS_OF,
                     horizon="12_months", claim=Claim(type="binary", question_id="distress_event_12m",
                                                      answer=answer, probability=prob),
                     confidence=prob, reasoning=["x"], evidence=[], tool_calls=0, model="m")


def ev(form, filed, acc, items=(), text_ref=None):
    return dict(company_id="anon_001", form=form, items=list(items), filed_date=filed,
                accession=acc, text_ref=text_ref)


class FakePost:
    def __init__(self, reply_):
        self.reply, self.calls = reply_, []

    def __call__(self, payload):
        self.calls.append(payload)
        return self.reply


@pytest.fixture
def texts():
    return {"gc": GC_TEXT, "boiler": BOILERPLATE, "clean": CLEAN}


def run(tmp_path, events, texts, sapling_reply=None):
    queries.set_backend(InMemoryBackend(events=events))
    post = FakePost(sapling_reply or reply("violation"))
    client = SaplingClient(cache_dir=tmp_path, post=post)
    out = resolve_distress(make_call(), sapling=client, load_text=lambda e: texts.get(e.text_ref))
    queries.set_backend(InMemoryBackend())
    return out, post


def test_real_going_concern_is_yes(tmp_path, texts):
    (outcome, info), post = run(tmp_path, [ev("10-K", date(2020, 2, 20), "k1", text_ref="gc")],
                                texts, reply("supported"))
    assert outcome == "yes"
    assert post.calls[0]["inputs"]["claim"] == risk.GOING_CONCERN_CLAIM
    assert "substantial doubt" in post.calls[0]["inputs"]["evidence"]
    assert info["resolution_date"] == "2020-06-30"


def test_boilerplate_keyword_hit_judged_no(tmp_path, texts):
    (outcome, _), post = run(tmp_path, [ev("10-K", date(2020, 2, 20), "k1", text_ref="boiler")],
                             texts, reply("violation"))
    assert outcome == "no" and len(post.calls) == 1


def test_no_keyword_never_calls_sapling(tmp_path, texts):
    (outcome, _), post = run(tmp_path, [ev("10-Q", date(2019, 8, 1), "q1", text_ref="clean")], texts)
    assert outcome == "no" and post.calls == []


@pytest.mark.parametrize("label", ["insufficient_information", "inconsistent_context"])
def test_not_enough_info_is_unresolvable(tmp_path, texts, label):
    (outcome, _), _ = run(tmp_path, [ev("10-K", date(2020, 2, 20), "k1", text_ref="gc")], texts, reply(label))
    assert outcome == "unresolvable"


def test_unsure_uses_top_label_only_when_confident():
    confident = Verdict.from_reply(reply("supported", status="unsure", p=0.55))
    shaky = Verdict.from_reply(reply("supported", status="unsure", p=0.45))
    assert verdict_to_outcome(confident) == "yes"
    assert verdict_to_outcome(shaky) == "unresolvable"


def test_auditor_change_is_yes_without_sapling(tmp_path, texts):
    (outcome, info), post = run(tmp_path, [ev("8-K", date(2019, 9, 10), "e1", items=["4.01"])], texts)
    assert outcome == "yes" and post.calls == []
    assert info["components"]["auditor_change"]["accessions"] == ["e1"]


def test_no_filing_in_window_is_unresolvable(tmp_path, texts):
    (outcome, _), _ = run(tmp_path, [], texts)
    assert outcome == "unresolvable"


def test_window_ignores_filings_before_as_of_and_after_12_months(tmp_path, texts):
    events = [ev("10-K", date(2019, 3, 1), "old", text_ref="gc"),       # before as_of
              ev("10-K", date(2020, 7, 15), "late", text_ref="gc"),     # after window end
              ev("10-Q", date(2019, 8, 1), "q1", text_ref="clean")]
    (outcome, info), post = run(tmp_path, events, texts, reply("supported"))
    assert outcome == "no" and post.calls == []
    assert [f["accession"] for f in info["components"]["going_concern"]["filings"]] == ["q1"]


def test_missing_text_is_unresolvable(tmp_path, texts):
    (outcome, _), _ = run(tmp_path, [ev("10-K", date(2020, 2, 20), "k1", text_ref="nope")], texts)
    assert outcome == "unresolvable"


def test_grade_sets_resolution_date_and_scores(tmp_path, texts):
    queries.set_backend(InMemoryBackend(events=[ev("10-K", date(2020, 2, 20), "k1", text_ref="gc")]))
    client = SaplingClient(cache_dir=tmp_path, post=FakePost(reply("supported")))
    g = grade(make_call("yes", 0.7), lambda c: resolve_distress(c, client, lambda e: texts.get(e.text_ref)))
    queries.set_backend(InMemoryBackend())
    assert g.outcome == "yes" and g.correct is True
    assert g.resolution_date == date(2020, 6, 30)
    assert g.brier == pytest.approx(0.09)


def test_cache_reuses_verdict_and_replay_only_blocks_misses(tmp_path):
    post = FakePost(reply("supported"))
    live = SaplingClient(cache_dir=tmp_path, post=post)
    live.verify("p", "e", "c")
    replay = SaplingClient(cache_dir=tmp_path, post=post, replay_only=True)
    assert replay.verify("p", "e", "c").raw_label == "supported"
    assert len(post.calls) == 1
    with pytest.raises(CacheMiss):
        replay.verify("p", "e", "other claim")


def test_bad_reply_raises_and_is_not_cached(tmp_path):
    client = SaplingClient(cache_dir=tmp_path, post=FakePost({"error": "Body needs inputs"}))
    with pytest.raises(SaplingError):
        client.verify("p", "e", "c")
    assert list(tmp_path.iterdir()) == []


def test_loader_reads_text_ref_as_ingest_stores_it(tmp_path, monkeypatch):
    """ingest stores text_ref as <cik>/<accession>/<doc>.htm under the raw SEC cache; data/filings/ never
    existed, so before this every going-concern check came back unresolvable."""
    monkeypatch.setenv("RAW_CACHE_DIR", str(tmp_path))
    doc = tmp_path / "sec" / "www.sec.gov" / "Archives" / "edgar" / "data" / "40545" / "000004054518000032"
    doc.mkdir(parents=True)
    (doc / "ge10q.htm").write_text(f"<html><body><p>{CLEAN}</p></body></html>")
    text = risk.file_text_loader()(queries.Event(**ev("10-Q", date(2019, 8, 1), "q1",
                                                      text_ref="40545/000004054518000032/ge10q.htm")))
    assert text is not None and "<" not in text and "well funded" in text


def test_sapling_down_marks_that_filing_unresolvable_without_crashing(tmp_path, texts):
    class Down(SaplingClient):
        def verify(self, *a):
            raise SaplingError("Sapling request failed: timed out")
    queries.set_backend(InMemoryBackend(events=[ev("10-K", date(2020, 2, 20), "k1", text_ref="gc")]))
    outcome, info = resolve_distress(make_call(), sapling=Down(cache_dir=tmp_path),
                                     load_text=lambda e: texts.get(e.text_ref))
    queries.set_backend(InMemoryBackend())
    assert outcome == "unresolvable"
    assert "Sapling unavailable" in info["components"]["going_concern"]["filings"][0]["reason"]
