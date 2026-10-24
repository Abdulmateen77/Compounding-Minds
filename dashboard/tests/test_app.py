"""Smoke tests: the Streamlit app renders without exceptions, including empty/missing-data states."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _run(monkeypatch, source):
    monkeypatch.setenv("DASHBOARD_SOURCE", str(source))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def test_app_renders_stored_runs(monkeypatch):
    root = Path(APP).parent.parent / "data" / "runs"
    if not (root / "calls.jsonl").exists():
        pytest.skip("no stored runs")
    at = _run(monkeypatch, root)
    assert not at.exception
    next(b for b in at.sidebar.button if b.label == "Step").click().run()
    assert not at.exception


def test_app_empty_source_is_graceful(monkeypatch, tmp_path):
    at = _run(monkeypatch, tmp_path)
    assert not at.exception
    assert any("No stored runs" in i.value for i in at.info)


def test_app_search_and_run_loop(monkeypatch):
    root = Path(APP).parent.parent / "data" / "runs"
    if not (root / "calls.jsonl").exists():
        pytest.skip("no stored runs")
    at = _run(monkeypatch, root)
    at.sidebar.text_input(key="company_query").set_value("anon_002").run()
    assert not at.exception and at.sidebar.selectbox(key="company").value == "anon_002"
    at.sidebar.text_input(key="company_query").set_value("zzz-no-match").run()
    assert not at.exception and at.sidebar.warning
    at.sidebar.text_input(key="company_query").set_value("").run()
    at.select_slider[0].set_value(3).run()
    next(b for b in at.button if b.label.startswith("Run loop")).click().run()
    assert not at.exception
    assert not at.error
