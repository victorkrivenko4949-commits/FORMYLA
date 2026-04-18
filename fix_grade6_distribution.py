import json
from collections import Counter

# Load data
data = json.load(open('adaptive_grade6_COMPLETE.json', encoding='utf-8'))

print(f"Total tasks before cleanup: {len(data)}")

# Analyze distribution
topics = Counter([t['topic'] for t in data])
levels = Counter([t['difficulty_level'] for t in data])

print("\nBy level:")
for level in sorted(levels.keys()):
    print(f"  Level {level}: {levels[level]}")

print("\nTopics with != 7 tasks:")
for topic, count in sorted(topics.items()):
    if count != 7:
        print(f"  '{topic}': {count}")

# Strategy: Keep exactly 7 tasks per topic and 25 per level
# We need 25 topics × 7 levels = 175 tasks total

# Group by topic
by_topic = {}
for task in data:
    topic = task['topic']
    if topic not in by_topic:
        by_topic[topic] = []
    by_topic[topic].append(task)

print(f"\nTotal topics: {len(by_topic)}")

# For each topic, keep exactly 7 tasks (one per level 1-7)
final_data = []
for topic, tasks in sorted(by_topic.items()):
    # Group by level
    by_level = {}
    for task in tasks:
        level = task['difficulty_level']
        if level not in by_level:
            by_level[level] = []
        by_level[level].append(task)
    
    # Keep one task per level (1-7)
    for level in range(1, 8):
        if level in by_level:
            # Take the first task for this level
            final_data.append(by_level[level][0])
            if len(by_level[level]) > 1:
                print(f"  {topic} level {level}: keeping 1 of {len(by_level[level])} tasks")
        else:
            print(f"  WARNING: {topic} missing level {level}")

print(f"\nTotal tasks after cleanup: {len(final_data)}")

# Verify distribution
topics_final = Counter([t['topic'] for t in final_data])
levels_final = Counter([t['difficulty_level'] for t in final_data])

print("\nFinal distribution by level:")
for level in sorted(levels_final.keys()):
    print(f"  Level {level}: {levels_final[level]}")

print("\nFinal topics with != 7 tasks:")
for topic, count in sorted(topics_final.items()):
    if count != 7:
        print(f"  '{topic}': {count}")

# Save
json.dump(final_data, open('adaptive_175_grade6_FIXED.json', 'w', encoding='utf-8'), 
          ensure_ascii=False, indent=2)

print(f"\nSaved {len(final_data)} tasks to adaptive_175_grade6_FIXED.json")
