"""The API tests assert against the 5-company offline demo runs, so pin the source.

Without this, a reachable DATABASE_URL (a loaded Postgres) makes the API read the empty run tables.
data/runs is used when present; a fresh checkout (no data/, which is gitignored) gets the same offline
preview generated into a temp dir, so these tests never depend on local files.
"""
import os

from dashboard.tests.fixtures import demo_runs_dir

os.environ["DASHBOARD_SOURCE"] = str(demo_runs_dir())
