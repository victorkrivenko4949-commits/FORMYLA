#!/usr/bin/env python
"""Quick exploration of topics in the curated bank, focusing on AI-fixed tasks."""
import json

with open("curated_bank_L1_L5_fixed.json", "r", encoding="utf-8") as f:
    bank = json.load(f)

print(f"Total tasks: {len(bank)}")

# Count by topic
from collections import Counter
topic_counts = Counter()
for t in bank:
    topic_counts[t.get("topic", "N/A")] += 1

print(f"\nUnique topics: {len(topic_counts)}")
print("\nTopic distribution:")
for topic, count in topic_counts.most_common():
    print(f"  {topic}: {count}")

# Focus on AI-fixed tasks
fixed = [t for t in bank if t.get("fixed_by_ai")]
print(f"\n\nAI-fixed tasks: {len(fixed)}")

# Fixed tasks by topic
fixed_topic_counts = Counter()
for t in fixed:
    fixed_topic_counts[t.get("topic", "N/A")] += 1

print("\nFixed tasks by topic:")
for topic, count in fixed_topic_counts.most_common():
    print(f"  {topic}: {count}")

# Show a few examples with statement + topic
print("\n\n=== Sample fixed tasks (statement + topic) ===")
for i, t in enumerate(fixed[:15]):
    stmt = t.get("statement", t.get("task_text", "NO STATEMENT"))[:120]
    print(f"\n[{i+1}] Topic: {t.get('topic', '?')}")
    print(f"    original_id: {t.get('original_id', '?')}")
    print(f"    Statement: {stmt}...")
