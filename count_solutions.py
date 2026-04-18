from olympiads import OLYMPIADS_DB

total = 0
with_solution = 0

for combo in OLYMPIADS_DB:
    for problem in combo.get('problems', []):
        total += 1
        solution = problem.get('solution', '')
        if solution and len(solution) > 50:
            with_solution += 1

print(f'Vsego zadach: {total}')
print(f'S reshenijami (>50 simvolov): {with_solution}')
print(f'Bez reshenij: {total - with_solution}')
