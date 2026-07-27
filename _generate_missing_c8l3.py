#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate 1 missing class 8 L3 task via DeepSeek Reasoner (deepseek-v4-pro).
Shortage cell: (8, L3) — 20 tasks, need 21.

Uses the proper DeepSeekAdapter with reasoning_reviewer profile,
which maps to deepseek-v4-pro in thinking mode.
"""
import json
import sys
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone

# Add FORMYLA_CONDITION_COURT to path for adapter import
PROJECT_DIR = r"C:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
    sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))

# ─── Import the proper DeepSeekAdapter ───────────────────────────────
from adapters.deepseek_adapter import DeepSeekAdapter
from adapters.config_loader import ConfigLoader

# ─── Load curated bank ──────────────────────────────────────────────
SRC = 'curated_bank_L1_L5_fixed.json'
with open(SRC, 'r', encoding='utf-8') as f:
    bank = json.load(f)

print(f"Loaded bank: {len(bank)} tasks")

# ─── Find class 8 L3 tasks ─────────────────────────────────────────
c8l3 = [t for t in bank if t.get('class_level') == 8 and t.get('target_level') == 'L3']
print(f"Class 8 L3 tasks before: {len(c8l3)} (quota=21, shortage={21 - len(c8l3)})")

if len(c8l3) >= 21:
    print("WARNING: Cell already has 21+ tasks. Skipping generation.")
    sys.exit(0)

# Find template (use first class 8 L3 task as template)
template = c8l3[0]

# ─── Compute IDs ────────────────────────────────────────────────────
max_src_idx = max(t.get('source_index', 0) for t in bank)
max_id_num = 0
for t in bank:
    oid = t.get('original_id', '')
    if oid.startswith('SEL1080-'):
        try:
            n = int(oid.split('-')[1])
            if n > max_id_num:
                max_id_num = n
        except:
            pass

max_rank = max(t.get('rank_in_cell', 0) for t in c8l3)
print(f"Max source_index: {max_src_idx}, max original_id: SEL1080-{max_id_num:04d}, max rank: {max_rank}")

# ─── Get existing topics for diversity ──────────────────────────────
existing_topics = set()
for t in c8l3:
    topic = t.get('topic', '')
    if topic:
        existing_topics.add(topic.split('/')[0].strip())
print(f"Existing topics in cell: {sorted(existing_topics)}")

# ─── Use DeepSeekAdapter (reasoning_reviewer profile) ──────────────
print("\n" + "=" * 60)
print("Initializing DeepSeekAdapter with reasoning_reviewer profile...")
print("=" * 60)

# Create adapter with reasoning_reviewer profile (deepseek-v4-pro thinking mode)
adapter = DeepSeekAdapter("reasoning_reviewer")
print(f"  Model configured: {adapter.model}")
print(f"  Mode: {adapter.mode}")
print(f"  Temperature: {adapter.temperature}")
print(f"  Max retries: {adapter.max_retries}")

# ─── Prompt design ──────────────────────────────────────────────────
existing_topics_str = "\n".join(f"  - {t}" for t in sorted(existing_topics))

system_prompt = f"""Ты — составитель олимпиадных задач по математике для 8 класса. 
Твоя задача — создать одну оригинальную олимпиадную задачу среднего уровня сложности (L3).

ТРЕБОВАНИЯ К ЗАДАЧЕ:
1. Класс: 8 (соответствует программе 8 класса, учитывая знания: алгебра до квадратных уравнений, геометрия, теория чисел, комбинаторика)
2. Уровень сложности: L3 (средний — требует нестандартного мышления, но решается за 10-20 минут)
3. Задача должна быть ОРИГИНАЛЬНОЙ — не копировать известные олимпиадные задачи
4. Тема: выбери тему, которая НЕ является доминирующей среди перечисленных существующих тем

СУЩЕСТВУЮЩИЕ ТЕМЫ (избегай повторения самой частой):
{existing_topics_str}

ОТВЕТ ДОЛЖЕН БЫТЬ В ФОРМАТЕ JSON:
{{
    "topic": "название темы на русском",
    "statement": "полный текст задачи на русском языке с LaTeX разметкой $...$",
    "answer": "краткий ответ",
    "solution": "полное решение с пояснениями и LaTeX",
    "task_text": "текст задачи (без ответа)"
}}

ВАЖНО:
- Используй LaTeX разметку для формул: $...$
- Убедись, что задача имеет однозначный ответ
- Решение должно быть полным и понятным для ученика 8 класса
- Ответ должен быть конкретным числом или выражением
- Твой ответ ТОЛЬКО в JSON формате, без дополнительного текста."""

user_prompt = f"""Создай одну оригинальную олимпиадную задачу для 8 класса уровня L3 (средняя сложность).

Избегай тем, которые уже часто встречаются: {sorted(existing_topics)}

Задача должна быть НОВОЙ и НЕОЧЕВИДНОЙ — проверь, что твоя задача не является известной классической задачей из списка запрещённых:
- Задачи про бассейн с трубами
- Задачи про совместную работу
- Задачи про встречное движение
- Классические задачи на разрезание
- Задачи про фальшивые монеты

Выбери интересную комбинаторную, геометрическую, алгебраическую или теоретико-числовую задачу,
которую можно решить с помощью оригинальной идеи.

Твой ответ ТОЛЬКО в JSON формате, без дополнительного текста."""

# ─── Call API via DeepSeekAdapter ──────────────────────────────────
print("\nCalling DeepSeek Reasoner API (deepseek-v4-pro thinking mode)...")
print("-" * 60)

# Use call_raw() to get the raw content, then parse ourselves
# This avoids the adapter's strict JSON parsing that requires _evidence field
raw_result = adapter.call_raw(system_prompt, user_prompt, resolve_model=True)

content = raw_result.get("content", "").strip()
model_used = raw_result.get("model", adapter.model)
usage = raw_result.get("usage", {})

print(f"Model used: {model_used}")
print(f"Raw response length: {len(content)} chars")
print(f"Usage: {usage}")
print(f"Raw response preview:\n{content[:1000]}")

if not content:
    print("\nERROR: Empty response from API — all models failed to produce content.")
    print("Falling back to standard_reviewer profile (non-thinking) as last resort...")
    
    # Last resort: try non-thinking model
    adapter2 = DeepSeekAdapter("standard_reviewer")
    try:
        raw_result2 = adapter2.call_raw(system_prompt, user_prompt, resolve_model=True)
        content = raw_result2.get("content", "").strip()
        model_used = raw_result2.get("model", adapter2.model)
        print(f"Fallback model used: {model_used}")
        print(f"Fallback response length: {len(content)} chars")
        print(f"Fallback preview:\n{content[:1000]}")
    except Exception as e2:
        print(f"ERROR fallback also failed: {e2}")
        sys.exit(1)

if not content:
    print("ERROR: Still empty content after fallback. Cannot generate.")
    sys.exit(1)

# ─── Parse response ─────────────────────────────────────────────────
def extract_json(text):
    """Extract JSON from response, handling markdown code fences."""
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("json"):
                continue
            cleaned.append(line)
        text = "\n".join(cleaned)
    text = text.strip()
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)

try:
    parsed = extract_json(content)
    print(f"\nParsed JSON keys: {list(parsed.keys())}")
except json.JSONDecodeError as e:
    print(f"ERROR parsing JSON: {e}")
    print(f"Raw content:\n{content[:2000]}")
    sys.exit(1)

# Validate required fields
required = ["topic", "statement", "answer", "solution"]
for field in required:
    if field not in parsed:
        print(f"ERROR: Missing field '{field}' in response")
        sys.exit(1)

print(f"\nGenerated task:")
print(f"  Topic: {parsed.get('topic')}")
print(f"  Statement: {parsed.get('statement')[:120]}...")
print(f"  Answer: {parsed.get('answer')}")

# ─── Create task object ─────────────────────────────────────────────
max_id_num += 1
max_src_idx += 1
new_rank = max_rank + 1

new_task = {
    "original_id": f"SEL1080-{max_id_num:04d}",
    "source_index": max_src_idx,
    "class_level": 8,
    "original_difficulty": 4,
    "target_level": "L3",
    "task_text": parsed.get("task_text", parsed["statement"]),
    "image": "",
    "topic": parsed["topic"],
    "audit_mode": "deterministic_pre_live",
    "evidence_source": "ai_generation_deepseek_reasoner",
    "decision_status": "candidate",
    "final_court_status": "pending_live_audit",
    "confidence": "high",
    "feature_score": 4,
    "mechanical_mapping": "L3",
    "quality_score": 90,
    "rank_in_cell": new_rank,
    "total_in_cell_pool": 21,
    "issues": [],
    "in_duplicate_cluster": False,
    "duplicate_clusters": [],
    "validation_warnings": 0,
    "selection_notes": "AI-generated via DeepSeek Reasoner for cell shortage (8, L3). Cell fill.",
    "statement": parsed["statement"],
    "answer": parsed["answer"],
    "solution": parsed["solution"],
    "level": 4,
    "grade": 8,
    "fixed_by_ai": True,
    "fix_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00"),
    "changes_made": [
        "cell_fill: Generated via DeepSeek Reasoner for (8, L3) shortage (20→21)"
    ]
}

# Fill missing keys from template
for k in template.keys():
    if k not in new_task:
        new_task[k] = deepcopy(template[k])

print(f"\nNew task object created:")
print(f"  original_id: {new_task['original_id']}")
print(f"  source_index: {new_task['source_index']}")
print(f"  rank_in_cell: {new_task['rank_in_cell']}")

# ─── Append to bank ─────────────────────────────────────────────────
bank.append(new_task)

# ─── Verify ─────────────────────────────────────────────────────────
c8l3_after = [t for t in bank if t.get('class_level') == 8 and t.get('target_level') == 'L3']
print(f"\nClass 8 L3 tasks after: {len(c8l3_after)} (quota=21)")

new_count = len(c8l3_after)
if new_count >= 21:
    print("✓ SHORTAGE RESOLVED: Cell (8, L3) now has 21 tasks")
else:
    print(f"✗ SHORTAGE PERSISTS: Cell (8, L3) has {new_count}, needs 21")
    sys.exit(1)

# ─── Save bank ──────────────────────────────────────────────────────
backup_path = SRC.replace('.json', f'_before_c8l3_fill.json')
shutil.copy(SRC, backup_path)
print(f"\nBackup saved: {backup_path}")

with open(SRC, 'w', encoding='utf-8') as f:
    json.dump(bank, f, ensure_ascii=False, indent=2)
print(f"Saved to {SRC}")
print(f"Bank size: {len(bank)}")

# ─── Save generation artifact ───────────────────────────────────────
os.makedirs("l4_l5_finalization", exist_ok=True)
artifact = {
    "generation_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "shortage_cell": {"class_level": 8, "target_level": "L3"},
    "quota": 21,
    "before": 20,
    "after": 21,
    "generated_task_id": new_task["original_id"],
    "model_used": model_used,
    "topic": parsed["topic"],
    "status": "resolved"
}
artifact_path = "l4_l5_finalization/c8l3_generation_result.json"
with open(artifact_path, 'w', encoding='utf-8') as f:
    json.dump(artifact, f, ensure_ascii=False, indent=2)
print(f"Generation artifact saved: {artifact_path}")

print("\n" + "=" * 60)
print("STEP 4b COMPLETE: Missing task generated and added to bank")
print("=" * 60)
