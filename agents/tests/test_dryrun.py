from agents import dryrun


def test_dry_run_on_stubs_prints_a_clean_prompt_for_every_agent(capsys):
    assert dryrun.main(["--company", "anon_001", "--as-of", "2019-06-30", "--stubs"]) == 0
    out = capsys.readouterr().out
    assert out.count("leak check: CLEAN") == 3
    assert "fcf_margin_ttm" in out and "interest_coverage" in out and "revenue_growth_yoy" in out
    assert "Q0" in out                                     # relative time, never a calendar date


def test_a_lesson_that_names_a_company_makes_the_dry_run_fail(capsys):
    code = dryrun.main(["--company", "anon_001", "--as-of", "2019-06-30", "--stubs", "--agent", "risk",
                        "--lesson", "Boeing cut its dividend"])
    assert code == 1 and "BLOCKED" in capsys.readouterr().out


def test_unreachable_database_gives_a_clear_message_not_a_traceback(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:59999/nope")
    code = dryrun.main(["--company", "anon_001", "--as-of", "2019-06-30"])
    assert code == 2 and "cannot reach the database" in capsys.readouterr().err
