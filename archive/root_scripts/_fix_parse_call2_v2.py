#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test a properly fixed version of fix_unescaped_quotes that tracks
whether we're in a JSON key or value context.
"""
import json
import os

os.chdir(r'C:\Users\Victor\Desktop\Новая папка (2)')

def fix_json_escapes(text):
    """Fix invalid backslash escapes in JSON string content."""
    VALID_ESCAPES = set('"\\/bfnrtu')
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            nextc = text[i + 1]
            if nextc in VALID_ESCAPES:
                result.append(c)
                result.append(nextc)
                i += 2
            else:
                result.append('\\\\')
                result.append(nextc)
                i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def fix_unescaped_quotes_v2(text):
    """
    Fix unescaped double quotes inside JSON string VALUES only.
    
    State machine tracks JSON structure:
    - OUTSIDE: not in any string
    - BEFORE_VALUE: just saw ':' followed by optional whitespace, next '"' starts a VALUE
    - IN_VALUE: inside a string VALUE (content that may contain unescaped quotes)
    - IN_KEY: inside a string KEY (simple names, no escaping needed)
    
    For IN_VALUE state: any '"' that is NOT followed by ',', ']', '}' (after optional whitespace)
    is treated as an unescaped content quote and escaped as \".
    """
    # First fix backslash escapes
    text = fix_json_escapes(text)
    
    result = []
    i = 0
    state = 'OUTSIDE'  # OUTSIDE, BEFORE_VALUE, IN_VALUE, IN_KEY
    
    while i < len(text):
        c = text[i]
        
        if c == '\\' and i + 1 < len(text) and state in ('IN_VALUE', 'IN_KEY'):
            # Escape sequence - copy verbatim
            result.append(c)
            result.append(text[i+1])
            i += 2
            continue
        
        if c == '"':
            if state == 'OUTSIDE':
                # A " starts something - is it a key or a value?
                # Look backwards past whitespace for the last non-whitespace char
                j = len(result) - 1
                while j >= 0 and result[j] in ' \t\n\r':
                    j -= 1
                if j >= 0 and result[j] == ':':
                    # Preceded by : -> this starts a VALUE
                    state = 'IN_VALUE'
                else:
                    # Preceded by {, [, ,, or start of text -> this starts a KEY
                    state = 'IN_KEY'
                result.append(c)
            elif state == 'IN_KEY':
                # End of key name
                state = 'OUTSIDE'
                result.append(c)
            elif state == 'IN_VALUE':
                # Potentially end of value string
                # Look ahead past whitespace for structural char
                j = i + 1
                while j < len(text) and text[j] in ' \t\n\r':
                    j += 1
                if j < len(text) and text[j] in ',]}':
                    # Structural char follows -> this " closes the string
                    state = 'OUTSIDE'
                    result.append(c)
                else:
                    # Not at structural boundary -> unescaped quote inside value
                    result.append('\\"')
            i += 1
        elif c == ':' and state == 'OUTSIDE':
            # Colon in OUTSIDE state -> after this, if we see a " it starts a value
            result.append(c)
            # Check if next non-ws is "
            j = i + 1
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1
            if j < len(text) and text[j] == '"':
                state = 'BEFORE_VALUE'
            i += 1
        elif c in ' \t\n\r' and state == 'BEFORE_VALUE':
            # Still in whitespace before value
            result.append(c)
            i += 1
        elif c == '"' and state == 'BEFORE_VALUE':
            # The " that starts the value
            state = 'IN_VALUE'
            result.append(c)
            i += 1
        else:
            # Non-quote, non-structural character
            if state == 'BEFORE_VALUE':
                # We saw : but then a non-" started the value (number/bool/null)
                state = 'OUTSIDE'
            result.append(c)
            i += 1
    
    return ''.join(result)


# Load and test with Call 1 response
print("=== Testing with Call 1 response ===")
with open('_last_response_11_v4_call1.txt', 'r', encoding='utf-8') as f:
    call1 = f.read()

fixed1 = fix_unescaped_quotes_v2(call1)
try:
    data = json.loads(fixed1)
    print(f"SUCCESS! Got {len(data)} items")
    for p in data:
        print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    print(f"  Position: {e.pos}")
    ctx = fixed1[max(0,e.pos-50):e.pos+50]
    print(f"  Context: {repr(ctx)}")

print()
print("=== Testing with Call 2 response (old) ===")
with open('_last_response_11_v4_call2.txt', 'r', encoding='utf-8') as f:
    call2 = f.read()

fixed2 = fix_unescaped_quotes_v2(call2)
try:
    data = json.loads(fixed2)
    print(f"SUCCESS! Got {len(data)} items")
    for p in data:
        print(f"  Problem {p.get('num')}: text={p.get('text','')[:80]}")
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    print(f"  Position: {e.pos}")
    ctx = fixed2[max(0,e.pos-100):e.pos+100]
    print(f"  Context: {repr(ctx)}")
