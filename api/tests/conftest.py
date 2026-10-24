"""The API tests replay the stored demo runs in data/runs. Without this they pick Postgres whenever a
database happens to be reachable, and then see the real 50 companies instead of the demo ones."""
import os

os.environ["DASHBOARD_SOURCE"] = "data/runs"
