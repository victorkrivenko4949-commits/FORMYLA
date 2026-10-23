#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Debug why problem 10 isn't being extracted."""
import re

with open('_last_response_11_v4_call2.txt', 'r', encoding='utf-8') as f:
    text = f.read()

print(f"Total chars: {len(text)}")
print(f"Has closing ']': {text.rstrip().endswith(']')}")

# Fix backslashes first
VALID_ESCAPES = set('"\\/bfnrtu')
result = []
i = 0
while i < len(text):
    c = text[i]
    if c == '\\' and i + 1 < len(text):
        nextc = text[i + 1]
        if nextc in VALID_ESCAPES:
            result.append(c); result.append(nextc); i += 2
        else:
            result.append('\\\\'); result.append(nextc); i += 2
    else:
        result.append(c); i += 1
fixed = ''.join(result)

# Find array bounds
start = fixed.find('[')
end = fixed.rfind(']')
print(f"Array: [{start}:{end+1}]")
array_text = fixed[start:end+1]

# Find all { blocks with quote-aware brace matching
i = 1  # skip [
obj_num = 0
while i < len(array_text):
    brace_start = array_text.find('{', i)
    if brace_start < 0 or brace_start >= len(array_text):
        break
    
    depth = 0
    brace_end = -1
    j = brace_start
    in_str = False
    while j < len(array_text):
        c = array_text[j]
        if c == '\\':
            j += 2
            continue
        if c == '"':
            in_str = not in_str
        if not in_str:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    brace_end = j
                    break
        j += 1
    
    if brace_end > brace_start:
        obj_num += 1
        obj_text = array_text[brace_start:brace_end + 1]
        
        # Extract num
        num_match = re.search(r'"num"\s*:\s*(\d+)', obj_text)
        num = num_match.group(1) if num_match else '?'
        
        # Extract text (first 100 chars)
        text_match = re.search(r'"text"\s*:\s*"', obj_text)
        text_preview = ''
        if text_match:
            val_start = text_match.end()
            qpos = val_start
            while qpos < len(obj_text):
                if obj_text[qpos] == '\\':
                    qpos += 2
                elif obj_text[qpos] == '"':
                    break
                else:
                    qpos += 1
            text_preview = obj_text[val_start:qpos][:100]
        
        print(f"\nObject {obj_num}: num={num}, brace range [{brace_start}:{brace_end}], len={len(obj_text)}")
        print(f"  Text preview: {text_preview}")
        
        # Check for unescaped quotes in the text value
        if text_match:
            in_val = False
            unescaped_quote_positions = []
            q = text_match.end()
            while q < len(obj_text):
                c = obj_text[q]
                if c == '\\':
                    q += 1
                elif c == '"':
                    # Check if this is end of value
                    j2 = q + 1
                    while j2 < len(obj_text) and obj_text[j2] in ' \t\n\r':
                        j2 += 1
                    if j2 < len(obj_text) and obj_text[j2] in ',}]':
                        break  # real closing quote
                    else:
                        unescaped_quote_positions.append(q)
                q += 1
            
            if unescaped_quote_positions:
                print(f"  Found {len(unescaped_quote_positions)} unescaped quotes in text value")
        
        # Check for unescaped quotes in solution value
        sol_match = re.search(r'"solution"\s*:\s*"', obj_text)
        if sol_match:
            in_val = False
            unescaped_sol_quotes = []
            q = sol_match.end()
            while q < len(obj_text):
                c = obj_text[q]
                if c == '\\':
                    q += 1
                elif c == '"':
                    j2 = q + 1
                    while j2 < len(obj_text) and obj_text[j2] in ' \t\n\r':
                        j2 += 1
                    if j2 < len(obj_text) and obj_text[j2] in ',}]':
                        break
                    else:
                        unescaped_sol_quotes.append(q)
                q += 1
            
            if unescaped_sol_quotes:
                print(f"  Found {len(unescaped_sol_quotes)} unescaped quotes in solution")
                for pos in unescaped_sol_quotes[:5]:
                    ctx = obj_text[max(0,pos-20):pos+20]
                    print(f"    at {pos}: ...{repr(ctx)}...")
        
        i = brace_end + 1
    else:
        print(f"  Brace not found starting at {brace_start}")
        i = brace_start + 1

print(f"\nTotal objects found: {obj_num}")
