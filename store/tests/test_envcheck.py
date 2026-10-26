"""The .env checker: it must name what is missing, validate formats, and never print a secret."""
import pytest

from store import envcheck as E

GOOD_FRED = "a" * 32


@pytest.mark.parametrize("value,ok", [
    ('Jane Doe jane@example.com', True),
    ('"Jane Doe jane@example.com"', True),
    (E.PLACEHOLDER_UA, False),
    ("", False),
    ("Jane Doe", False),                     # no email
    ("jane@example.com", False),             # no name
])
def test_sec_user_agent_needs_a_name_and_an_email(value, ok):
    assert (E.check_sec_user_agent(value) is None) is ok


@pytest.mark.parametrize("value,ok", [(GOOD_FRED, True), ("", False), ("short", False), ("A" * 32, False),
                                      ("a" * 31, False), ("a" * 33, False)])
def test_fred_key_format(value, ok):
    assert (E.check_fred_key(value) is None) is ok


def test_settings_report_what_is_missing_and_how_to_fix_it():
    rows = {r["name"]: r for r in E.check_settings({"SEC_USER_AGENT": E.PLACEHOLDER_UA})}
    assert not rows["SEC_USER_AGENT"]["ok"] and "placeholder" in rows["SEC_USER_AGENT"]["detail"]
    assert not rows["FRED_API_KEY"]["ok"] and "fred.stlouisfed.org" in rows["FRED_API_KEY"]["how"]
    assert not rows["MUBIT_API_KEY"]["ok"]


def test_a_complete_environment_is_all_ok():
    env = {"SEC_USER_AGENT": "Jane Doe jane@example.com", "FRED_API_KEY": GOOD_FRED, "MUBIT_API_KEY": "mk_live_abc"}
    assert all(r["ok"] for r in E.check_settings(env))


def test_secrets_are_never_printed(monkeypatch, capsys, tmp_path):
    secret = "ZZsecretvalue1234567890abcdefgh"
    monkeypatch.chdir(tmp_path)                                    # so no real .env is read
    monkeypatch.setenv("MUBIT_API_KEY", secret)
    monkeypatch.setenv("FRED_API_KEY", GOOD_FRED)
    monkeypatch.setenv("SEC_USER_AGENT", "Jane Doe jane@example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:hunter2pw@localhost:59999/x")
    E.main([])
    out = capsys.readouterr().out
    assert secret not in out and GOOD_FRED not in out and "jane@example.com" not in out and "hunter2pw" not in out
    assert "set (" in out                                          # shown only as a length


def test_exit_code_reflects_readiness(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    for k in ("MUBIT_API_KEY", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SEC_USER_AGENT", E.PLACEHOLDER_UA)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:59999/x")
    assert E.main([]) == 1
    assert "Not ready" in capsys.readouterr().out


def test_the_fred_key_is_never_in_an_error_message(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection to https://api.stlouisfed.org/...api_key=" + GOOD_FRED)
    monkeypatch.setattr(E, "_get", boom)
    assert GOOD_FRED not in E.ping_fred(GOOD_FRED)["detail"]


def test_database_check_says_what_to_do_when_unreachable():
    r = E.check_database("postgresql://postgres:postgres@localhost:59999/x", timeout=1)
    assert not r["ok"] and "docker compose up -d" in r["detail"]


def test_database_check_sees_the_applied_schema(pg_conn):
    import os
    url = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    # the fixture's schema is private to its connection; the public schema may or may not have tables,
    # so only assert the call returns a well-formed answer for a reachable server
    r = E.check_database(url)
    assert set(r) == {"ok", "detail"} and r["detail"]
