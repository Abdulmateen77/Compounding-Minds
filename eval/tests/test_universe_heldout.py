"""One source of truth for which companies are held out (found while merging A's and B's work).

ingest/universe.json carries `held_out`, the `companies` table stores it, and the replay and the
held-out report must use the same set. Otherwise the replay could learn from a company the database
calls held out, which silently invalidates the held-out result."""
from ingest.universe import held_out_ids, load_universe, train_ids
from eval import split as S


def _ids():
    return [c["company_id"] for c in load_universe()]


def test_a_universe_run_uses_the_universe_flags():
    assert set(S.pick_held_out(_ids())) == held_out_ids()


def test_make_split_over_the_universe_agrees_with_the_database_flags():
    sp = S.make_split(_ids())
    assert set(sp.held_out_companies) == held_out_ids()
    assert set(sp.train_companies) == train_ids()
    assert len(sp.held_out_companies) == 10 and not set(sp.held_out_companies) & set(sp.train_companies)


def test_the_replay_and_the_held_out_report_pick_the_same_companies():
    from grader import replay
    assert replay.pick_held_out is S.pick_held_out
    assert set(replay.pick_held_out(_ids(), 10)) == held_out_ids()


def test_the_requested_count_is_ignored_for_the_universe_because_the_flags_decide():
    assert S.pick_held_out(_ids(), 3) == S.pick_held_out(_ids(), 10)


def test_stub_runs_and_small_lists_still_use_the_hash():
    stubs = [f"anon_{i:03d}" for i in range(1, 6)]            # the 5 stub companies: ids exist in the universe
    assert S.universe_held_out(stubs) is None
    assert len(S.pick_held_out(stubs, 1)) == 1
    foreign = [f"c{i:02d}" for i in range(40)]
    assert S.universe_held_out(foreign) is None
    assert S.pick_held_out(foreign, 10) == S.pick_held_out(foreign, 10) and len(S.pick_held_out(foreign, 10)) == 10


def test_a_universe_sized_list_with_a_foreign_id_falls_back_to_the_hash():
    mixed = _ids()[:-1] + ["not_in_universe"]
    assert S.universe_held_out(mixed) is None
