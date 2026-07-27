# -*- coding: utf-8 -*-
"""Diagnose: compare parsed 'text' values against raw file content.
Uses OLYMPIADS_DB (not PROBLEMS_DB) to match the main script."""
import sys, re, json

sys.path.insert(0, '.')
# Clear any cached import
for key in list(sys.modules.keys()):
    if 'olympiads' in key:
        del sys.modules[key]
from olympiads import OLYMPIADS_DB

def _escape_py_string(text: str) -> str:
    result = []
    for ch in text:
        if ch == '\\':
            result.append('\\\\')
        elif ch == "'":
            result.append("\\'")
        elif ch == '\n':
            result.append('\\n')
        elif ch == '\r':
            result.append('\\r')
        elif ch == '\t':
            result.append('\\t')
        elif ord(ch) < 32:
            result.append(f'\\x{ord(ch):02x}')
        else:
            result.append(ch)
    return ''.join(result)

with open('olympiads.py', 'r', encoding='utf-8') as f:
    content = f.read()

results = []
examined = 0

# Check ALL entries for any that use implicit string concatenation in 'text'
for idx, entry in enumerate(OLYMPIADS_DB):
    eid = entry.get('id', '')
    olympiad = entry.get('olympiad', '')
    for prob in entry.get('problems', []):
        text = prob.get('text', '')
        pnum = prob.get('num', '?')
        
        if not text or len(text) < 20:
            continue
        
        file_old = _escape_py_string(text)
        pos = content.find(file_old)
        
        if pos < 0:
            # FAILED TO FIND - investigate why
            examined += 1
            if examined > 25:
                break
            
            # Look for 'text': near this problem
            # First find a unique substring
            # Try to find the first 40 chars of the text
            prefix = text[:40]
            file_prefix = _escape_py_string(prefix)
            prefix_pos = content.find(file_prefix)
            
            results.append(f"\n=== FAIL #{examined}: set#{eid} {olympiad} prob#{pnum} ===")
            results.append(f"  text len: {len(text)}")
            results.append(f"  text[:80]: {repr(text[:80])}")
            
            if prefix_pos >= 0:
                # Show context around the match
                ctx_start = max(0, prefix_pos - 50)
                ctx_end = min(len(content), prefix_pos + len(file_prefix) + 200)
                ctx = content[ctx_start:ctx_end]
                results.append(f"  Prefix found at pos {prefix_pos}!")
                results.append(f"  Raw ctx: {repr(ctx)}")
            else:
                results.append(f"  Prefix NOT found either!")
                # Try even shorter prefix - just first 20 chars
                shorter = text[:20]
                file_shorter = _escape_py_string(shorter)
                sp = content.find(file_shorter)
                if sp >= 0:
                    ctx = content[max(0,sp-30):sp+len(file_shorter)+100]
                    results.append(f"  Shorter prefix ({shorter[:20]}) found at {sp}: {repr(ctx)}")
                else:
                    # Maybe the file has '\\n' but text has actual newlines?
                    # Try looking for the text without newline escaping
                    alt = file_old.replace('\\n', '\\\\n').replace('\\n', '\\\\n')
                    # Hmm that's wrong. Let me think...
                    # Actually maybe the file uses implicit concatenation
                    results.append(f"  file_old[:60]: {repr(file_old[:60])}")
                    
                    # Search for each word in the text
                    words = text.split()[:5]
                    for w in words:
                        if len(w) < 3:
                            continue
                        w_esc = _escape_py_string(w)
                        wp = content.find(w_esc)
                        if wp >= 0:
                            ctx = content[max(0,wp-20):wp+len(w_esc)+60]
                            results.append(f"  Word '{w}' found at {wp}: {repr(ctx)}")
                            break
                    else:
                        results.append(f"  No words found in file either!")
            
            # Check if this entry has implicit concatenation around 'text'
            # Find the 'num' key for this problem
            num_pattern = f"'num': {pnum}"
            num_pos = content.find(num_pattern)
            if num_pos >= 0:
                # Look around for 'text': 
                search_start = max(0, num_pos - 5)
                search_end = min(len(content), num_pos + 500)
                region = content[search_start:search_end]
                if "'text'" in region:
                    # Find where text value starts
                    text_marker_pos = region.find("'text'")
                    after_marker = region[text_marker_pos:]
                    results.append(f"  Found 'text' near 'num': {pnum}")
                    results.append(f"  Region: {repr(after_marker[:300])}")
                    
                    # Check for implicit concatenation
                    if "' '" in after_marker:
                        results.append(f"  >>> HAS IMPLICIT CONCATENATION! <<<")
        else:
            # Found! Show context
            ctx = content[max(0,pos-30):pos+len(file_old)+30]
            # Only show first few
            if examined == 0:
                results.append(f"\n=== SUCCESS (example) set#{eid} prob#{pnum} ===")
                results.append(f"  Found at pos {pos}")
                results.append(f"  Raw ctx: {repr(ctx[:200])}")

    if examined > 25:
        break

results.append(f"\n\nTotal failed searches examined: {examined}")

with open('_diag_results3.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print(f"Written {examined} failed cases to _diag_results3.txt")
