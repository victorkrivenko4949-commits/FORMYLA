#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'c:\Users\Victor\Desktop\Новая папка (2)\templates\prep\coach.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# R1: Add console.log and DOMContentLoaded after <script>
# Exact content from file uses U+2500 BOX DRAWINGS LIGHT HORIZONTAL
old_open = '<script>\n\n// \u2500\u2500\u2500 Dynamic greeting via API \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500'
new_open = '<script>\nconsole.log(\'[coach] inline script loaded...\');\ndocument.addEventListener(\'DOMContentLoaded\', function() {\nconsole.log(\'[coach] DOMContentLoaded fired\');\n\n// \u2500\u2500\u2500 Dynamic greeting via API \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500'

if old_open in html:
    html = html.replace(old_open, new_open, 1)
    print('OK - replaced script open block')
else:
    print('FAIL - could not find script open block')

# R2: Add cache-busting (already done by previous run)
# Check if already done
if 'greetingUrl' in html:
    print('OK - fetch already has cache-busting')
else:
    old_fetch = 'fetch(\'{{ url_for("prep.coach_greeting") }}\''
    new_fetch = "var greetingUrl = '{{ url_for(\"prep.coach_greeting\") }}' + '?_t=' + Date.now();\nconsole.log('[coach] fetching greeting from:', greetingUrl);\nvar greetingController = new AbortController();\nvar greetingTimeout = setTimeout(function () { greetingController.abort(); }, 10000);\nvar greetingUrl = '{{ url_for(\"prep.coach_greeting\") }}' + '?_t=' + Date.now();\nconsole.log('[coach] fetching greeting from:', greetingUrl);\nfetch(greetingUrl, { signal: greetingController.signal })"
    # Actually this was already done, skip

# R3: Close DOMContentLoaded before chat history
old_history = '  });\n\n// \u2500\u2500\u2500 Load chat history \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500'
new_history = '  });\n\n}); // end DOMContentLoaded\n\n// \u2500\u2500\u2500 Load chat history \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500'

if old_history in html:
    html = html.replace(old_history, new_history, 1)
    print('OK - added DOMContentLoaded close before chat history')
else:
    print('FAIL - could not find history section marker')
    idx = html.find('Load chat history')
    if idx >= 0:
        print(f'Found at {idx}, context: {repr(html[idx-30:idx+60])}')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print('OK - File saved')
