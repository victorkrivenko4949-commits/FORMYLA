import json

with open('data/adaptive_full_db.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

all_topics = sorted(set(t['topic'] for t in data))
print('Все темы в БД:')
for i, topic in enumerate(all_topics, 1):
    print(f'{i}. {topic}')
