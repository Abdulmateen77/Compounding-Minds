"""Apply the schema to DATABASE_URL:  python -m store.migrate   (safe to re-run)"""
from dotenv import load_dotenv

from . import db

if __name__ == "__main__":
    load_dotenv()
    with db.connect() as conn:
        db.apply_schema(conn)
    print("schema applied to", db.database_url())
