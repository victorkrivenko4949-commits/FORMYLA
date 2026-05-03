import sys
sys.path.insert(0, '.')
from olympiads import OLYMPIADS_DB

slugs = set()
rounds_info = {}

for c in OLYMPIADS_DB:
    slug = c.get('olympiad', '')
    rnd = c.get('round', '')
    rnd_title = c.get('round_title', '')
    grade = c.get('grade', 0)
    n_problems = len(c.get('problems', []))
    slugs.add((slug, c.get('olympiad_title', '')))
    key = (slug, rnd, rnd_title)
    if key not in rounds_info:
        rounds_info[key] = {}
    if grade not in rounds_info[key]:
        rounds_info[key][grade] = []
    rounds_info[key][grade].append(n_problems)

print('=== SLUGS ===')
for s in sorted(slugs):
    {
