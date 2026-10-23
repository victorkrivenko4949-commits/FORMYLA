import os
import sys
from .jobs import init_db, make_engine

if __name__ == "__main__":
    if sys.argv[1:] != ["init-db"]:
        raise SystemExit("Usage: python -m geoexact.manage init-db")
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://", "postgresql+")):
        raise SystemExit("Set DATABASE_URL to the existing PostgreSQL database")
    init_db(make_engine(url))
    print("GeoExact tables ready. Existing FORMYLA tables unchanged.")
