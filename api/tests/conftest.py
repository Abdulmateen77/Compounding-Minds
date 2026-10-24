"""The API tests assert against the 5-company demo files in data/runs, so pin the source.

Without this, a reachable DATABASE_URL (a loaded Postgres) makes the API read the empty run tables.
"""
import os

os.environ["DASHBOARD_SOURCE"] = "data/runs"
