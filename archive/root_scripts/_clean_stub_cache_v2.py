# -*- coding: utf-8 -*-
"""Clean cache v2: remove entries with malformed JSON wrappers, keep only good ones."""
import json
import re

path = "pipeline/output/phystech_stub_extractions.json"
data = json.load(open(path, 'r', encoding='utf-8'))

def extract_from_wrapped_json(text: str) -> str | None:
    """Try to extract actual text from a JSON-wrapped response where json.loads failed."""
    # Pattern: {"extracted_text": "THE_ACTUAL_TEXT"}
    m = re.search(r'"extracted_text"\s*:\s*"(.+?)"\s*}', text, re.DOTALL)
    if m:
        candidate = m.group(1)
        # Unescape common LaTeX sequences that the AI might have left single-escaped
        # The issue is \t, \a, \f, \n, \r in LaTeX are interpreted as JSON escapes
        # So we need to replace literal \t with \\t etc.
        # But we can't just blindly do this...
        # Let's just check if this looks like a reasonable problem statement
        if len(candidate) > 30 and any(kw in candidate for kw in 
                ['\\', '$', 'Найдите', 'Решите', 'Пусть', 'Вычислите']):
            return candidate
    return None

# Clean 692_4 and 692_5
for key in ['692_4', '692_5']:
    if key in data:
        val = data[key]
        # Try to extract from wrapped JSON
        extracted = extract_from_wrapped_json(val)
        if extracted and len(extracted) > 30:
            print(f"[FIX] {key}: extracted from JSON wrapper")
            print(f"  Text: {extracted[:80]}...")
            data[key] = extracted
        else:
            print(f"[REMOVE] {key}: cannot extract, removing for re-extraction")
            print(f"  Content: {val[:100]}...")
            del data[key]

# Save
json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n[SAVED] Cache updated. {len(data)} entries remaining.")
print(f"Keys: {sorted(data.keys())}")
