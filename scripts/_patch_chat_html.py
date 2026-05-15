# -*- coding: utf-8 -*-
"""Patch templates/chat.html with WhatsApp-style features.
Reads JS/HTML payload from external base64 file to bypass streaming truncation."""
import os, sys, base64
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "templates", "chat.html")
PAYLOAD = os.path.join(os.path.dirname(__file__), "_chat_html_payload.b64")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

if "CHAT_WA_FE_V1" in src:
    print("[skip] chat.html already patched")
    sys.exit(0)

# Decode payload (JSON dict with two keys: 'composer_html', 'new_js')
with open(PAYLOAD, "r", encoding="ascii") as f:
    blob = f.read().strip()
import json
data = json.loads(base64.b64decode(blob).decode("utf-8"))
COMPOSER_HTML = data["composer_html"]
NEW_JS = data["new_js"]
NEW_CSS = data.get("new_css", "")

# Step 1: Replace the composer block via anchor-based regex.
if '<div class="chat-messages" id="chatMessages"></div>' not in src:
    print("[ERROR] chatMessages anchor not found")
    sys.exit(1)

# Replace from the chatMessages div to the closing /div of chat-composer.
import re
pat = re.compile(
    r'(<div class="chat-messages" id="chatMessages"></div>\s*)'
    r'<div class="chat-composer">.*?</div>',
    re.DOTALL,
)
m = pat.search(src)
if not m:
    print("[ERROR] composer block not found")
    sys.exit(1)
src_new = src[:m.start()] + m.group(1) + COMPOSER_HTML + src[m.end():]

# Step 2: Replace renderMessages function entirely.
pat_rm = re.compile(r'function renderMessages\(msgs\)\{.*?\n\}\n', re.DOTALL)
m2 = pat_rm.search(src_new)
if not m2:
    print("[ERROR] renderMessages not found")
    sys.exit(1)
src_new = src_new[:m2.start()] + NEW_JS + src_new[m2.end():]

# Step 3: Append new CSS at the end of the first <style> block.
if NEW_CSS:
    style_end = src_new.find('</style>')
    if style_end > 0:
        src_new = src_new[:style_end] + NEW_CSS + "\n" + src_new[style_end:]

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src_new)
print("[ok] chat.html patched (CHAT_WA_FE_V1)")
