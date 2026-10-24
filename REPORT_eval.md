Workstream: H2   Branch: hermes/eval   Commits: 1

Done:
- `eval/frozen.py`: `FrozenUpdater(ModelUpdater)` (version is always `<base>-frozen`, corrections ignored, `lessons()` is `[]`, nothing written to disk) and `run_frozen(...)`, which passes `lessons=[]` explicitly, so even an updater that holds lessons cannot leak them into the control.
- `eval/baselines.py`: `always_yes` and `base_rate`, scored with `grader.scoring` (the same maths as the agents). `base_rate` is fitted on the training cell only, and a test proves that changing a held-out outcome does not change it.
- `eval/split.py`: `unseen_years`, `unseen_companies`, `unseen_both` and `slice_of(call, held_out_ids)`. The boundary tests pass: 2022-12-31 is training, 2023-01-01 is held out, and a held-out company in 2021 is only in `unseen_companies`.
- `eval/metrics.py`: `accuracy`, `mean_brier`, `calibration_bins`, `overconfidence_gap`, `valid_json_rate`, `evidence_match_rate`. `unresolvable` is excluded from accuracy and Brier and counted separately. Empty input gives `None`, never NaN.
- `eval/report.py`: writes `heldout.json` with exactly the documented keys, and `quality.md` with one section per agent. A "learned does not beat frozen on <agent>/<slice>" note is added plainly, with the numbers behind it. The critique sentence comes from fixed rules, not an LLM.
- `eval/load.py` and `eval/cli.py`: `load_scored(conn, run_ids)` reads `calls JOIN grades JOIN runs`. `python -m eval.cli --out eval/out` reads `DATABASE_URL`, and `--demo` needs no database.

Files:
  eval/__init__.py, frozen.py, baselines.py, split.py, metrics.py, report.py, load.py, cli.py, demo.py
  eval/tests/__init__.py, helpers.py, test_metrics.py, test_split.py, test_baselines.py, test_frozen.py, test_report.py, test_load.py
  eval/out/.gitkeep   (deleted eval/.gitkeep)

Tests: 94 new, 221 passing, 1 skipped when Postgres is reachable.
  Without Postgres (how it runs by default): 203 passed, 19 skipped. The skipped ones are the 18 database tests plus 1 `pglast` skip.
  Baseline before this branch was 115 passed and 13 skipped without Postgres (128 in all), so 128 + 94 = 222.
  The 1 skip with Postgres up is `store/tests/test_schema.py`: `pglast` is a dev-only package that is not installed. It is not mine.
  The 6 new database tests in `test_load.py` pass against a real Postgres (checked). They use the `pg_conn` fixture and skip by themselves when no database is reachable.
  I mutation-checked the tests that matter most. Each of these breakages makes a test fail:
    - base_rate fitting on ALL data, held-out company and year included
    - base_rate using outcomes settled by filings after the training window
    - the same case being double-counted across learned and frozen
    - the training window running a year too long
    - `unseen_years` also containing held-out companies
    - unresolvable counted in accuracy and Brier
    - a tie being reported as a win
    - the frozen twin picking up lessons
    - NaN allowed into `heldout.json`
  The NaN mutation was missed on the first pass, which exposed a missing test. I added `test_a_corrupt_nan_grade_fails_loudly_and_writes_no_file` and re-checked that it is caught.

Deviations from this brief:
1. **base_rate is stricter than "training window only".** The brief says it must not look at held-out data. I read that as: a training company, in a training year, AND an outcome settled inside the training window. A Q4 2022 call about the next four quarters resolves in 2023 to 2024, so its outcome is held-out-window information even though the call is dated 2022. Such calls are left out and counted in a note. If you meant only the call's `as_of`, delete the `resolves_after_training` check in `baselines.py`; one test will then fail on purpose.
2. **`resolution_date` is read from `grades.evidence`.** The `grades` table has no such column, but `grader/grade.py` writes `evidence=[info]` with `info["resolution_date"]`, so `load_scored` reads it back from there. Where it is missing, the case is still used but a note says the baseline cannot prove it was settled in the training window.
3. **Rules I chose where the brief was silent:**
   - "Learned beats frozen" means strictly lower Brier on the same cases. A tie is reported as "does not beat". Accuracy is quoted in the note but does not decide it.
   - Learned and frozen are compared only on cases BOTH resolved, so the columns compare like with like. One-sided cases are counted in a note.
   - The same (variant, agent, company, quarter) in more than one run is counted once, keeping the latest graded record, with a note.
   - Variants other than learned or frozen (the schema also allows `baseline`) are ignored, with a note.
   - The `unresolvable` count in `heldout.json` is per case, not per variant.
4. `run_frozen` takes optional `run_id` and `updater` arguments in addition to the brief's signature.
5. The CLI connects with `psycopg.connect(connect_timeout=5)` instead of `store.db.connect()`. On this Windows machine a refused connection through `db.connect()` hung for about 130 seconds before failing, which looks like a freeze. The CLI now fails in about 5 seconds with a clear message and exit code 2, and writes no file.

Requests (changes needed in files I may not edit):
- `store/schema.sql`: a `resolution_date DATE` column on `grades` would be cleaner than reading it out of the `evidence` JSON. Nothing breaks without it.
- `grader/` or the replay (Person B): `runs.config` needs a `variant` key (`learned` or `frozen`) on every frozen-twin run. If it is missing everything defaults to `learned`, and the frozen column will silently stay empty.
- `grader/` or the replay (Person B): record how many calls were attempted per agent (for example in `runs.config`). The runner drops invalid replies, so the valid-JSON rate cannot be recovered from the database. Until then the CLI takes `--attempted fundamentals=2400` and otherwise prints n/a.
- `requirements.txt`: nothing new needed.

Dependencies: none.

Open questions / things I did not verify:
- **Evidence match is n/a in every real CLI run.** It needs the metric bundle each call was shown, and the CLI has no way to fetch those. `build_quality(..., bundles=...)` supports it, and the function is tested, but nobody passes bundles yet. Someone has to feed it either the stored bundles or `get_metrics` at each call's `as_of`.
- **I have never run this against real agent output.** No real calls or grades exist yet. The report code is tested on hand-built records and on synthetic data. I do not know how the real numbers will look.
- **`--demo` output is synthetic by construction.** It comes from a seeded random generator, and I picked three arbitrary skill levels on purpose so that the three code paths (learned wins, ties, loses) all get exercised. Every report built from it says "SYNTHETIC DEMO DATA" in its notes and in `quality.md`. That the demo contains a loss is a property of the generator, not a finding about the agents. Never quote a demo number.
- The generated `eval/out/heldout.json` and `eval/out/quality.md` are left in the working tree untracked, as the brief says not to commit them. They are demo output.
- In `quality.md`, the baselines table scores `base_rate` over ALL of the learned agent's resolved calls, so on the training years it is scored in-sample. The report says so. `heldout.json` is the honest comparison: every held-out slice is out-of-sample for `base_rate`.
- `quality.md` shows each variant on its own resolved calls, while `heldout.json` compares them on the shared cases. Their numbers can differ slightly for that reason.
