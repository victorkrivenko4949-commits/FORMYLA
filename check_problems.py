from problems import PROBLEMS_DB
print(f'Zagruzheno: {len(PROBLEMS_DB)} zadach')
print(f'Primer: ID={PROBLEMS_DB[0].get("id")}, subject={PROBLEMS_DB[0].get("subject")}, grade={PROBLEMS_DB[0].get("grade")}')
