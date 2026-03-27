from problems import PROBLEMS_DB
total = len(PROBLEMS_DB)
olympiad = [p for p in PROBLEMS_DB if p.get('olympiad') or p.get('olympiad_title') or p.get('round')]
print('Всего задач:', total)
print('Олимпиадных:', len(olympiad))
print('Обычных:', total - len(olympiad))
if olympiad:
    print('Пример олимпиадной:', list(olympiad[0].keys()))



































