"""The replay committed in demo_data/ is what a clean clone shows, so it must load as real results."""
import json

from dashboard import data as D


def test_committed_replay_loads_as_real_results():
    b = D.load(str(D.SNAPSHOT_DIR))
    assert not b.empty
    assert b.provenance()["real_results"] is True
    assert not b.uses_fallback_updater()
    assert set(b.calls["arm"]) == {"learned", "frozen", "baseline"}
    assert b.calls["company_id"].nunique() == 50


def test_default_source_falls_back_to_the_snapshot(monkeypatch, tmp_path):
    monkeypatch.delenv("DASHBOARD_SOURCE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(D, "DEFAULT_JSONL_DIR", tmp_path / "no_runs")
    assert D.resolve_source() == str(D.SNAPSHOT_DIR)


def test_heldout_report_is_the_official_one():
    report = json.loads((D.ROOT / "eval" / "reports" / "heldout_report.json").read_text())
    assert report["provenance"]["real_results"] is True
