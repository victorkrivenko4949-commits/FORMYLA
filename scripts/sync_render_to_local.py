#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sync: Render PostgreSQL -> local SQLite.
Downloads ALL adaptive_tasks from production and inserts into local DB.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import sqlite3
import os
import time

RENDER_URL = "https://formyla-com.onrender.com"
SECRET = "formyla-migrate-2026"
TABLE = "adaptive_tasks"
PAGE_SIZE = 500  # сколько строк за один запрос
LOCAL_DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'formyla.db')

def fetch_page(offset, limit=PAGE_SIZE):
    """Скачать одну страницу задач с Render."""
    url = f"{RENDER_URL}/api/migrate/export"
    params = {
        'secret': SECRET,
        'table': TABLE,
        'offset': offset,
        'limit': limit
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('rows', []), data.get('columns', [])
            else:
                print(f"  [WARN] HTTP {resp.status_code}: {resp.text[:200]}")
                time.sleep(2)
        except Exception as e:
            print(f"  [WARN] Attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return [], []


def main():
    print("=" * 60)
    print("SYNC: Render PostgreSQL -> Local SQLite")
    print("=" * 60)
    
    # 1. Скачиваем все задачи с Render
    all_rows = []
    columns = []
    offset = 0
    
    while True:
        print(f"  Fetching offset={offset} ...")
        rows, cols = fetch_page(offset)
        if cols and not columns:
            columns = cols
        if not rows:
            break
        all_rows.extend(rows)
        print(f"  Got {len(rows)} rows (total: {len(all_rows)})")
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.5)  # не перегружаем Render
    
    if not all_rows:
        print("ERROR: No rows fetched from Render!")
        return
    
    print(f"\nTotal fetched: {len(all_rows)} tasks")
    print(f"Columns: {columns}")
    
    # 2. Подключаемся к локальной SQLite
    db_path = os.path.abspath(LOCAL_DB)
    print(f"\nLocal DB: {db_path}")
    
    if not os.path.exists(db_path):
        print("ERROR: Local DB not found!")
        return
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 3. Проверяем текущее состояние
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    old_count = cur.fetchone()[0]
    print(f"Current local tasks: {old_count}")
    
    # 4. Очищаем таблицу и вставляем все заново
    print("\nClearing local adaptive_tasks table...")
    cur.execute("DELETE FROM adaptive_tasks")
    conn.commit()
    
    # 5. Вставляем все задачи
    # Определяем какие колонки есть в локальной таблице
    cur.execute("PRAGMA table_info(adaptive_tasks)")
    local_cols = [row[1] for row in cur.fetchall()]
    print(f"Local table columns: {local_cols}")
    
    # Используем только колонки, которые есть и в Render, и в локальной таблице
    common_cols = [c for c in columns if c in local_cols]
    print(f"Common columns: {common_cols}")
    
    inserted = 0
    errors = 0
    
    for row in all_rows:
        try:
            values = []
            for col in common_cols:
                val = row.get(col)
                values.append(val)
            
            placeholders = ', '.join(['?' for _ in common_cols])
            col_names = ', '.join(common_cols)
            
            cur.execute(
                f"INSERT OR REPLACE INTO adaptive_tasks ({col_names}) VALUES ({placeholders})",
                values
            )
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] Row {row.get('id', '?')}: {e}")
    
    conn.commit()
    
    # 6. Проверяем результат
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    new_count = cur.fetchone()[0]
    
    # Проверяем движение
    cur.execute("SELECT topic, COUNT(*) FROM adaptive_tasks WHERE topic LIKE '%движен%' OR topic LIKE '%Движен%' GROUP BY topic")
    movement_rows = cur.fetchall()
    
    # Проверяем по классам
    cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level")
    grade_rows = cur.fetchall()
    
    print(f"\n{'=' * 60}")
    print(f"RESULT:")
    print(f"  Before: {old_count} tasks")
    print(f"  Inserted: {inserted}")
    print(f"  Errors: {errors}")
    print(f"  After: {new_count} tasks")
    print(f"\nBy grade:")
    for g in grade_rows:
        print(f"  Grade {g[0]}: {g[1]}")
    print(f"\nMovement topics:")
    if movement_rows:
        for m in movement_rows:
            print(f"  {m[0]}: {m[1]}")
    else:
        print("  NONE FOUND!")
    
    conn.close()
    print(f"\n{'=' * 60}")
    print("DONE! Restart the local Flask app to see the changes.")


if __name__ == '__main__':
    main()
