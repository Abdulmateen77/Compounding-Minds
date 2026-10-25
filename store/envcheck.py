"""Check that .env is ready, and say exactly what is missing.   python -m store.envcheck [--ping]

    python -m store.envcheck             check the settings and the database. No network, no cost
    python -m store.envcheck --ping      also make one tiny real request to SEC and to FRED
    python -m store.envcheck --ping-mubit  also make one 5-token call through Mubit (spends a little credit)

It never prints a secret: a value is shown only as "set (N characters)". Exit code 0 means everything
needed for the next step is in place, 1 means something is missing, so it can gate a script.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request

PLACEHOLDER_UA = "Your Name your.email@example.com"
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
FRED_KEY = re.compile(r"^[a-z0-9]{32}$")

HELP = {
    "SEC_USER_AGENT": 'a real name and email in quotes, for example SEC_USER_AGENT="Jane Doe jane@example.com". '
                      "The SEC needs it to identify who is downloading. No account or key.",
    "FRED_API_KEY": "free and instant: fred.stlouisfed.org/docs/api/api_key.html (make an account, request an API key)",
    "MUBIT_API_KEY": "from your Mubit / Night Shift hackathon account (the starter credit you were given)",
}


def check_sec_user_agent(v: str) -> str | None:
    """A problem description, or None if it looks usable."""
    if not v or v.strip() in ("", PLACEHOLDER_UA):
        return "not set (still the placeholder)"
    if not EMAIL.search(v):
        return "has no email address in it"
    if len(re.sub(EMAIL, "", v).split()) < 1:
        return "has an email but no name"
    return None


def check_fred_key(v: str) -> str | None:
    if not v:
        return "not set"
    if not FRED_KEY.match(v):
        return "does not look like a FRED key (they are 32 lowercase letters and digits)"
    return None


def check_nonblank(v: str) -> str | None:
    return None if v and v.strip() else "not set"


CHECKS = {"SEC_USER_AGENT": check_sec_user_agent, "FRED_API_KEY": check_fred_key, "MUBIT_API_KEY": check_nonblank}
NEEDED_FOR = {"SEC_USER_AGENT": "downloading filings", "FRED_API_KEY": "macro data (GDP, unemployment, rates)",
              "MUBIT_API_KEY": "running the agents on a real model"}


def mask(v: str) -> str:
    return f"set ({len(v)} characters)" if v else "empty"


def check_settings(env=os.environ) -> list[dict]:
    rows = []
    for name, fn in CHECKS.items():
        v = env.get(name, "")
        problem = fn(v)
        rows.append({"name": name, "ok": problem is None, "detail": mask(v) if problem is None else problem,
                     "for": NEEDED_FOR[name], "how": HELP[name]})
    return rows


def check_database(url: str, timeout: int = 3) -> dict:
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=timeout) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()}
            have = len({"companies", "facts", "events", "macro", "calls", "grades"} & tables)
            n = conn.execute("SELECT count(*) FROM facts").fetchone()[0] if "facts" in tables else 0
        if have < 6:
            return {"ok": False, "detail": "reachable, but the schema is not applied: run  python -m store.migrate"}
        return {"ok": True, "detail": f"reachable, schema applied, {n} facts loaded" + ("" if n else " (empty: not downloaded yet)")}
    except Exception as e:  # noqa: BLE001 - one clear line beats a driver traceback
        return {"ok": False, "detail": f"not reachable ({e.__class__.__name__}): start it with  docker compose up -d"}


def _get(url: str, headers: dict, timeout: int = 20) -> int:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read(2048)  # status is what matters: do not pull the whole file
        return r.status


def ping_sec(user_agent: str) -> dict:
    try:
        code = _get("https://data.sec.gov/submissions/CIK0000320193.json", {"User-Agent": user_agent})
        return {"ok": code == 200, "detail": f"SEC answered {code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"SEC request failed: {e.__class__.__name__} {getattr(e, 'code', '')}".strip()}


def ping_fred(key: str) -> dict:
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=UNRATE&limit=1&file_type=json&api_key={key}"
    try:
        code = _get(url, {})
        return {"ok": code == 200, "detail": f"FRED answered {code}"}
    except Exception as e:  # noqa: BLE001  (the key is in the URL: never print the URL)
        return {"ok": False, "detail": f"FRED rejected the request ({e.__class__.__name__} {getattr(e, 'code', '')}): check the key".strip()}


def ping_mubit() -> dict:
    try:
        from agents.gateway import MubitGateway
        out = MubitGateway(max_tokens=5).complete("envcheck", [{"role": "user", "content": "Reply with the word ok."}],
                                                   record=False)  # a probe: not a training example, no junk task
        return {"ok": bool(out), "detail": "Mubit answered a 5-token call"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"Mubit call failed: {e.__class__.__name__}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ping", action="store_true", help="make one tiny request to SEC and to FRED")
    ap.add_argument("--ping-mubit", action="store_true", help="make one 5-token call through Mubit")
    args = ap.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()
    mark = {True: "ok     ", False: "MISSING"}
    all_ok = True

    print("Settings")
    rows = check_settings()
    for r in rows:
        print(f"  {mark[r['ok']]} {r['name']:<15} {r['detail']}")
        if not r["ok"]:
            print(f"           needed for {r['for']}. How: {r['how']}")
        all_ok &= r["ok"]

    print("\nDatabase")
    db = check_database(os.environ.get("DATABASE_URL", "postgresql://localhost:5432/compounding_minds"))
    print(f"  {mark[db['ok']]} DATABASE_URL   {db['detail']}")
    all_ok &= db["ok"]

    mode = "stub metrics (safe default)" if os.environ.get("USE_STUBS") != "0" else "REAL metrics from Postgres"
    print(f"\nMode: USE_STUBS -> {mode}")

    if args.ping:
        print("\nLive checks")
        ok = {r["name"]: r["ok"] for r in rows}
        for label, name, fn in (("SEC ", "SEC_USER_AGENT", lambda: ping_sec(os.environ["SEC_USER_AGENT"])),
                                ("FRED", "FRED_API_KEY", lambda: ping_fred(os.environ["FRED_API_KEY"]))):
            if not ok[name]:
                print(f"  skipped {label}: {name} is not set")
                continue
            res = fn()
            print(f"  {mark[res['ok']]} {label} {res['detail']}")
            all_ok &= res["ok"]
    if args.ping_mubit:
        if not os.environ.get("MUBIT_API_KEY"):
            print("  skipped Mubit: MUBIT_API_KEY is not set")
        else:
            res = ping_mubit()
            print(f"  {mark[res['ok']]} Mubit {res['detail']}")
            all_ok &= res["ok"]

    print("\n" + ("Ready." if all_ok else "Not ready: fix the MISSING lines above, then run this again."))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
