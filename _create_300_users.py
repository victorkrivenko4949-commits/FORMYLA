# -*- coding: utf-8 -*-
import sqlite3, random, sys

DB = 'instance/formyla.db'
db = sqlite3.connect(DB)

# 1. Count users
existing = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
print(f'STEP1: Existing users: {existing}')

need = max(0, 300 - existing)
if need > 0:
    grades = [5,6,7,8,9,10,11]
    for i in range(need):
        grade = random.choice(grades)
        email = f'test{i+10000}@cv.local'
        name = f'Test User {i+1}'
        db.execute(
            "INSERT INTO users(email,name,preferred_grade,is_guest) VALUES(?,?,?,0)",
            (email, name, grade)
        )
        if (i+1) % 100 == 0:
            db.commit()
            print(f'  Created {i+1}/{need} users...')
    db.commit()
    print(f'STEP1: Created {need} new users')

# 2. Count after insert
total = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
print(f'STEP2: Total users: {total}')

# 3. Create curator_state for users without it
users_no_cs = db.execute(
    "SELECT u.id, u.preferred_grade FROM users u "
    "LEFT JOIN curator_state cs ON cs.user_id = u.id "
    "WHERE cs.user_id IS NULL AND u.preferred_grade >= 5"
).fetchall()
print(f'STEP3: Users without curator_state: {len(users_no_cs)}')

for uid, grade in users_no_cs:
    db.execute(
        "INSERT INTO curator_state(user_id, prep_state) VALUES(?, ?)",
        (uid, '{"cycle_started": true}')
    )
db.commit()
print(f'STEP3: Created {len(users_no_cs)} curator_states')

# 4. Count curator_state
cs_count = db.execute('SELECT COUNT(*) FROM curator_state').fetchone()[0]
print(f'STEP4: Total curator_state: {cs_count}')

# 5. Clean conveyor
db.execute('DELETE FROM gen_conveyor')
db.commit()
print(f'STEP5: GenConveyor wiped')

# 6. Check gen_conveyor is empty
gc = db.execute('SELECT COUNT(*) FROM gen_conveyor').fetchone()[0]
print(f'STEP6: GenConveyor rows: {gc}')

db.close()
print('DONE - ready for schedule_all_users()')
