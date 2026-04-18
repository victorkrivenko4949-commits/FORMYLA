import json
from collections import Counter

# Load data
data = json.load(open('adaptive_175_grade7_COMPLETE.json', encoding='utf-8'))

print(f"Total tasks before cleanup: {len(data)}")

# Find all Dirichle tasks
dirichle_tasks = [t for t in data if 'Дирихле' in t['topic']]
print(f"\nTotal Dirichle tasks: {len(dirichle_tasks)}")

# Show distribution
topics = Counter([t['topic'] for t in dirichle_tasks])
print("\nDirichle topics:")
for topic, count in topics.items():
    print(f"  '{topic}': {count}")

# Show levels for each topic variant
print("\nBy level:")
for t in dirichle_tasks:
    print(f"  Level {t['difficulty_level']}: '{t['topic']}'")

# Fix: Remove tasks with typo "Принцип Дирихле)" and keep only 7 "Принцип Дирихле"
# Strategy: Keep all tasks with correct name, remove those with typo
cleaned_data = []
dirichle_correct = []
dirichle_typo = []

for task in data:
    if task['topic'] == 'Принцип Дирихле)':
        dirichle_typo.append(task)
    elif task['topic'] == 'Принцип Дирихле':
        dirichle_correct.append(task)
    else:
        cleaned_data.append(task)

print(f"\nCorrect 'Принцип Дирихле': {len(dirichle_correct)}")
print(f"Typo 'Принцип Дирихле)': {len(dirichle_typo)}")

# We need exactly 7 Dirichle tasks total
# We have 12 correct + 2 typo = 14 total
# Need to remove 7 tasks

# Check which levels we have
correct_levels = sorted([t['difficulty_level'] for t in dirichle_correct])
typo_levels = sorted([t['difficulty_level'] for t in dirichle_typo])

print(f"\nCorrect levels: {correct_levels}")
print(f"Typo levels: {typo_levels}")

# Strategy: Keep one task per level (1-7), prefer correct topic name
final_dirichle = []
for level in range(1, 8):
    # Try to find in correct tasks first
    found = [t for t in dirichle_correct if t['difficulty_level'] == level]
    if found:
        final_dirichle.append(found[0])  # Take first one
    else:
        # Try typo tasks
        found = [t for t in dirichle_typo if t['difficulty_level'] == level]
        if found:
            # Fix the topic name
            task = found[0].copy()
            task['topic'] = 'Принцип Дирихле'
            final_dirichle.append(task)

print(f"\nFinal Dirichle tasks: {len(final_dirichle)}")
print(f"Levels: {sorted([t['difficulty_level'] for t in final_dirichle])}")

# Combine all
final_data = cleaned_data + final_dirichle

print(f"\nTotal tasks after cleanup: {len(final_data)}")

# Verify distribution
topics = Counter([t['topic'] for t in final_data])
levels = Counter([t['difficulty_level'] for t in final_data])

print("\nBy level:")
for level in sorted(levels.keys()):
    print(f"  Level {level}: {levels[level]}")

print("\nTopics with != 7 tasks:")
for topic, count in sorted(topics.items()):
    if count != 7:
        print(f"  {topic}: {count}")

# Save
json.dump(final_data, open('adaptive_175_grade7_FINAL.json', 'w', encoding='utf-8'), 
          ensure_ascii=False, indent=2)

print("\nSaved to adaptive_175_grade7_FINAL.json")
