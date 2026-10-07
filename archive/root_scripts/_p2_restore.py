"""Restore adaptive_tasks from backup, filling default values for new columns"""
import sqlite3

BACKUP = 'instance/formyla.db.bak_before_sync_adaptive_20260611_032504'
DB = 'instance/formyla.db'

src = sqlite3.connect(BACKUP)
src.row_factory = sqlite3.Row
dst = sqlite3.connect(DB)

# Get destination columns with defaults
dst_cols_info = dst.execute('PRAGMA table_info(adaptive_tasks)').fetchall()
dst_col_names = [c[1] for c in dst_cols_info]
dst_col_defaults = {c[1]: c[4] for c in dst_cols_info if c[4] is not None}
dst_notnull = {c[1] for c in dst_cols_info if c[3] == 1}

print(f"DST columns: {len(dst_col_names)}")
print(f"NOT NULL: {dst_notnull}")

src_col_names = [c[1] for c in src.execute('PRAGMA table_info(adaptive_tasks)').fetchall()]
print(f"SRC columns: {len(src_col_names)}")

# Hardcoded defaults for NOT NULL columns that don't exist in source
extra_defaults = {
    'figure_status': 'pending',
    'has_aux': 0,
    'is_calibration': 0,
    'needs_reclassification': 0,
    'actual_solve_rate': 0.0,
    'suggested_level': 1,
    'attempts_count': 0,
    'solves_count': 0,
    'task_type': 'adaptive',
    'source': 'legacy',
    'origin': 'import',
    'agent_type': 'imported',
    'subtopic': '',
    'theme_id': None,
    'theme_title': '',
    'methods_json': '[]',
    'figure_json': None,
    'aux_svg_path': None,
    'aux_reason': None,
    'last_calibrated_at': None,
}

dst.execute('DELETE FROM adaptive_tasks')
cols_str = ', '.join(dst_col_names)
ph = ', '.join(['?'] * len(dst_col_names))
sql = f"INSERT INTO adaptive_tasks ({cols_str}) VALUES ({ph})"

src_rows = src.execute('SELECT * FROM adaptive_tasks').fetchall()
print(f"Source rows: {len(src_rows)}")

count = 0
for src_row in src_rows:
    row_dict = {k: src_row[k] for k in src_row.keys()}
    # Build destination row
    dst_row = []
    for col in dst_col_names:
        if col in row_dict:
            dst_row.append(row_dict[col])
        elif col in extra_defaults:
            dst_row.append(extra_defaults[col])
        elif col in dst_col_defaults:
            dst_row.append(dst_col_defaults[col])
        else:
            dst_row.append(None)
    dst.execute(sql, dst_row)
    count += 1

dst.commit()
print(f"Inserted {count} rows")
print(f"Verify: {dst.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()[0]}")

# Copy users
src_u_rows = src.execute('SELECT * FROM users').fetchall()
dst_u_cols = [c[1] for c in dst.execute('PRAGMA table_info(users)').fetchall()]
existing_ids = {r[0] for r in dst.execute('SELECT id FROM users').fetchall()}

u_cols_str = ', '.join(dst_u_cols)
u_ph = ', '.join(['?'] * len(dst_u_cols))
u_sql = f"INSERT INTO users ({u_cols_str}) VALUES ({u_ph})"

copied = 0
for row in src_u_rows:
    if row['id'] not in existing_ids:
        dst_row = [row[k] if k in row.keys() else None for k in dst_u_cols]
        try:
            dst.execute(u_sql, dst_row)
            copied += 1
        except Exception as e:
            print(f"Skip user {row['id']}: {e}")

dst.commit()
print(f"Users copied: {copied}")
print(f"Users total: {dst.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")

src.close()
dst.close()
print("DONE")
