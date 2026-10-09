# -*- coding: utf-8 -*-
"""Clean the extraction cache: strip code blocks, fix 692_1, remove bad entries."""
import json
import re

path = "pipeline/output/phystech_stub_extractions.json"
data = json.load(open(path, 'r', encoding='utf-8'))

def _clean_entry(text: str) -> str:
    """Strip ```json ... ``` wrappers and extract the actual text."""
    if not text:
        return text
    # Pattern 1: ```json\n{ "extracted_text": "..." }\n```
    m = re.search(r'```json\s*\n?(\{.*?\})\s*\n?```', text, re.DOTALL)
    if m:
        try:
            j = json.loads(m.group(1))
            extracted = j.get('extracted_text', '')
            if extracted:
                return extracted
        except (json.JSONDecodeError, Exception):
            pass
    # Pattern 2: standalone ```json prefix
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    # Pattern 3: try to parse whole thing as JSON
    try:
        j = json.loads(text)
        extracted = j.get('extracted_text', '')
        if extracted:
            return extracted
    except (json.JSONDecodeError, Exception):
        pass
    return text.strip()

def _strip_trailing_answer(text: str) -> str:
    """Remove trailing **Ответ:** ... or Ответ: ... from the end."""
    # Remove trailing **Ответ:** ... possibly multi-line
    text = re.sub(r'\s*\*\*Ответ:\*\*\s*.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*Ответ:\s*.*$', '', text, flags=re.DOTALL)
    return text.strip()

# Fix 693_1 and 693_3 - strip code blocks
for key in ['693_1', '693_3']:
    if key in data:
        cleaned = _clean_entry(data[key])
        if cleaned and len(cleaned) > 30:
            print(f"[FIX] {key}: stripped code block, now {len(cleaned)} chars")
            print(f"  First 80: {cleaned[:80]}")
            data[key] = cleaned
        else:
            print(f"[WARN] {key}: cleanup produced empty/short result, marking for re-extraction")
            del data[key]

# Fix 692_1 - strip trailing answer
if '692_1' in data:
    cleaned = _strip_trailing_answer(data['692_1'])
    if cleaned != data['692_1']:
        print(f"[FIX] 692_1: stripped trailing answer")
        print(f"  Was: {data['692_1'][:80]}...")
        print(f"  Now: {cleaned[:80]}...")
        data['692_1'] = cleaned

# Remove 692_4 and 692_5 - they need re-extraction (wrong content)
for key in ['692_4', '692_5']:
    if key in data:
        val = data[key]
        print(f"[REMOVE] {key}: removing from cache (got wrong content)")
        print(f"  Content: {val[:80]}...")
        del data[key]

# Save
json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f"\n[SAVED] Cache updated. {len(data)} entries remaining.")
print(f"Keys: {sorted(data.keys())}")
