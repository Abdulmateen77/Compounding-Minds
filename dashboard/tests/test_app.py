"""Smoke tests: the Streamlit app renders without exceptions, including empty/missing-data states."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

from dashboard.tests.fixtures import demo_runs_dir, write_replay_run  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")
DISCLAIMER = "Research tool, not financial advice."


def _run(monkeypatch, source):
    monkeypatch.setenv("DASHBOARD_SOURCE", str(source))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_app_renders_stored_runs(monkeypatch):
    at = _run(monkeypatch, demo_runs_dir())
    assert not at.exception
    assert DISCLAIMER in _text(at)
    next(b for b in at.sidebar.button if b.label == "Step").click().run()
    assert not at.exception


def test_app_empty_source_is_graceful(monkeypatch, tmp_path):
    at = _run(monkeypatch, tmp_path)
    assert not at.exception
    assert any("No stored runs" in i.value for i in at.info)
    assert DISCLAIMER in _text(at)  # the footer is drawn before any st.stop()


def test_app_search_and_run_loop(monkeypatch):
    at = _run(monkeypatch, demo_runs_dir())
    at.sidebar.text_input(key="company_query").set_value("anon_002").run()
    assert not at.exception and at.sidebar.selectbox(key="company").value == "anon_002"
    at.sidebar.text_input(key="company_query").set_value("zzz-no-match").run()
    assert not at.exception and at.sidebar.warning
    at.sidebar.text_input(key="company_query").set_value("").run()
    at.select_slider[0].set_value(3).run()
    next(b for b in at.button if b.label.startswith("Run loop")).click().run()
    assert not at.exception
    assert not at.error


def test_app_replay_in_progress(monkeypatch, tmp_path):
    """grader.replay output while it is still writing: partial quarter, half-written line, baseline arm."""
    at = _run(monkeypatch, write_replay_run(tmp_path / "runs_final"))
    assert not at.exception and not at.error
    text = _text(at)
    assert "Replay in progress" in text and "2018Q3" in text
    assert "These runs use stub metrics" not in text  # a live Mubit replay with no fallback updater
    assert "Fallback updater" not in text
    assert DISCLAIMER in text
    labels = at.sidebar.selectbox(key="company").options
    assert any("anon_002" in o and "held out" in o for o in labels)
    for _ in range(3):  # step past the end without an index error
        next(b for b in at.sidebar.button if b.label == "Step").click().run()
        assert not at.exception
    at.sidebar.radio(key="arm").set_value("frozen").run()
    assert not at.exception
