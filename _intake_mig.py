import psycopg2, json, sys
url = 'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require'
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

# Check if curator_state has prep_state column and data
cur.execute("SELECT user_id, prep_state FROM curator_state WHERE prep_state IS NOT NULL")
rows = cur.fetchall()
print(f'curator_state with prep_state: {len(rows)}', flush=True)

# Check what the intake structure should contain
# p9_intake_migration: sets default values for existing users
# class_level: from User.preferred_grade or grade
# goal: "just_grow", experience: "none", daily_tasks: 10
# prior_mu: 2.0, prior_sigma: 1.5

default_intake = {
    "class_level": None,  # will be filled per-user
    "goal": "just_grow",
    "goal_auto": True,
    "experience": "none",
    "daily_tasks": 10,
    "weak_sections": [],
    "weak_priority": False,
    "prior_mu": 2.0,
    "prior_sigma": 1.5
}

# Check existing curator_state rows
cur.execute("SELECT user_id, grade, prep_state FROM curator_state")
states = cur.fetchall()
print(f'Total curator_state rows: {len(states)}', flush=True)

updated = 0
for uid, grade, prep_state in states:
    if prep_state is None:
        prep_state = {}
    elif isinstance(prep_state, str):
        prep_state = json.loads(prep_state)
    
    if 'intake' not in prep_state or prep_state.get('intake', {}).get('goal_auto') == True:
        # Set defaults
        intake = dict(default_intake)
        intake['class_level'] = grade
        prep_state['intake'] = intake
        cur.execute("UPDATE curator_state SET prep_state = %s WHERE user_id = %s",
                   (json.dumps(prep_state, ensure_ascii=False), uid))
        updated += 1

print(f'Updated curator_state rows: {updated}', flush=True)

cur.close(); conn.close()
print('INTAKE MIGRATION DONE', flush=True)
