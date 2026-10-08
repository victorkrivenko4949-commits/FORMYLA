"""Export aggregate metrics without importing app.py or running its seeders.

Usage: DATABASE_URL=<read-only connection> python scripts/export_admin_metrics.py
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from admin_metrics.service import collect_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        parser.error("DATABASE_URL must be set to an authorized read-only database.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = None
    try:
        engine = create_engine(url)
        result = collect_metrics(engine, args.date, args.days)
    except (SQLAlchemyError, ValueError):
        print("Metrics unavailable: check connection, schema and date (details omitted).", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
