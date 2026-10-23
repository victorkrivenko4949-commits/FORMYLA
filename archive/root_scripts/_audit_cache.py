#!/usr/bin/env python3
"""Audit the V2 live calibration cache database."""
import sqlite3
import sys

db_path = "C:/Users/Victor/Downloads/FORMYLA_CONDITION_COURT/data/cache.db"
try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print(f"=== TABLES: {len(tables)} found ===")
    for t in tables:
        tn = t[0]
        cur.execute(f'SELECT COUNT(*) FROM "{tn}"')
        cnt = cur.fetchone()[0]
        print(f"\n--- {tn}: {cnt} rows ---")
        
        # Schema
        cur.execute(f'PRAGMA table_info("{tn}")')
        cols = cur.fetchall()
        for c in cols:
            print(f"  COL: {c[1]} ({c[2]})")
        
        # Distinct values for key columns
        for colname in ['role', 'model', 'reasoning_mode', 'mode']:
            try:
                cur.execute(f'SELECT DISTINCT "{colname}" FROM "{tn}" WHERE "{colname}" IS NOT NULL')
                vals = [r[0] for r in cur.fetchall()]
                if vals:
                    print(f"  DISTINCT {colname}: {vals}")
            except:
                pass
        
        # Sample rows
        if cnt > 0:
            cur.execute(f'SELECT * FROM "{tn}" LIMIT 2')
            rows = cur.fetchall()
            for i, r in enumerate(rows):
                print(f"  Sample {i+1}: {str(r)[:300]}")
    
    conn.close()
    print("\n=== DONE ===")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
