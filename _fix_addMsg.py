# -*- coding: utf-8 -*-
"""Insert the missing addMsg() function into templates/prep/coach.html."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = 'templates/prep/coach.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# The marker: we need to find the line after "console.log('[coach] DOMContentLoaded fired');"
# Insert addMsg definition right after that line.
marker = "console.log('[coach] DOMContentLoaded fired');"

addmsg_fn = """console.log('[coach] DOMContentLoaded fired');

// ---- addMsg: add a message bubble to the chat log ----
function addMsg(text, role) {
  var log = document.getElementById('chatLog');
  if (!log) return;
  var div = document.createElement('div');
  div.className = 'chat-msg ' + (role || 'bot');
  div.innerHTML = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
"""

if marker in content:
    # Replace the marker line with marker + addMsg
    content = content.replace(marker, addmsg_fn)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"SUCCESS: addMsg function inserted (len={len(content)})")
else:
    print(f"ERROR: marker not found: {marker}")
