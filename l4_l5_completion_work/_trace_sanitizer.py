#!/usr/bin/env python
"""Trace the sanitizer's quote handling for each failing case."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stage6_failed_responses")

# Re-implement sanitize with tracing for specific positions
def traced_sanitize(text, trace_positions):
    """Like sanitize_json_string but with detailed tracing at specific positions."""
    result = []
    in_string = False
    pending_backslash = False
    _VALID_JSON_ESCAPES = frozenset({'"', '\\', '/', 'u'})
    
    for i, ch in enumerate(text):
        if pending_backslash:
            if ch in _VALID_JSON_ESCAPES:
                result.append('\\')
            else:
                result.append('\\\\')
            result.append(ch)
            pending_backslash = False
            continue
        if ch == '\\' and in_string:
            pending_backslash = True
            continue
        if ch == '"':
            if in_string:
                j = i + 1
                while j < len(text) and text[j] in (' ', '\t', '\n', '\r'):
                    j += 1
                is_structural = (j >= len(text) or text[j] in (',', '}', ']', ':'))
                if is_structural:
                    in_string = False
                    result.append('"')
                else:
                    result.append('\\"')
                
                if i in trace_positions:
                    next_peek = text[j] if j < len(text) else 'EOF'
                    print(f"  Pos {i}: inside string, look-ahead->'{next_peek}', structural={is_structural}")
            else:
                in_string = True
                result.append('"')
                if i in trace_positions:
                    print(f"  Pos {i}: opening string")
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            elif ord(ch) < 0x20 and ch not in ('\n', '\r', '\t'):
                result.append(f'\\u{ord(ch):04x}')
            else:
                result.append(ch)
        else:
            result.append(ch)
    
    return ''.join(result)

# The 4 still-failing cases
cases = [
    ("G5|L5|T004|S2", "raw_G5_L5_T004_S2.txt"),
    ("G6|L5|T016|S1", "raw_G6_L5_T016_S1.txt"),
    ("G6|L5|T018|S2", "raw_G6_L5_T018_S2.txt"),
    ("G6|L5|T018|S1", "raw_G6_L5_T018_S1.txt"),
]

for cell_key, raw_file in cases:
    raw_path = os.path.join(FAILED_DIR, raw_file)
    with open(raw_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    print(f"\n{'='*80}")
    print(f"[{cell_key}] ({raw_file}) — {len(text)} bytes")
    print(f"{'='*80}")
    
    # Find all quote positions
    quote_positions = [i for i, ch in enumerate(text) if ch == '"']
    
    # Find unescaped quotes inside what should be strings
    # Try to parse and find the error location
    import re
    
    # Try to find all " inside text fields that might be problematic
    # Let's find all " that are preceded by a letter (Russian or Latin) - these are likely unescaped quotes inside text
    likely_problematic = []
    for pos in quote_positions:
        if pos > 0 and pos < len(text) - 1:
            prev = text[pos-1]
            nxt = text[pos+1]
            # Skip quotes at JSON structural positions
            if prev in ('{', ':', ',', '[', ' ') or text[pos-2:pos] == '\\\\':
                continue
            if nxt in (',', '}', ']', ':', '\n', ' '):
                continue
            # A quote surrounded by text characters might be problematic
            if prev.isalpha() and nxt.isalpha():
                context = text[max(0,pos-30):pos] + f'["]"' + text[pos+1:min(len(text),pos+30)]
                likely_problematic.append((pos, context))
    
    if likely_problematic:
        print(f"\n  Likely problematic quotes (surrounded by text):")
        for pos, ctx in likely_problematic[:10]:
            print(f"    Pos {pos}: ...{repr(ctx[:60])}...")
    else:
        print(f"\n  No quotes surrounded by text found via simple heuristic")
    
    # Let's do a more thorough search: find ALL " and show context around each
    print(f"\n  Finding all quote positions with context:")
    for pos in quote_positions:
        ctx_start = max(0, pos - 20)
        ctx_end = min(len(text), pos + 20)
        ctx = text[ctx_start:ctx_end]
        # Show position, and 10 chars before/after
        escaped_ctx = repr(ctx)
        print(f"    Pos {pos:6d}: ...{repr(text[max(0,pos-15):pos])}[{repr(ch)}]{repr(text[pos+1:min(len(text),pos+15)])}...")

print(f"\n{'='*80}")
print("DONE")
