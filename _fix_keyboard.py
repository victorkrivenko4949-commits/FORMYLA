# -*- coding: utf-8 -*-
"""Add keyboard helper functions (toggleKeyboard, kbInsert, switchKbTab) 
to templates/prep/coach.html."""
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = 'templates/prep/coach.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# We'll insert the keyboard functions right after the first <script> tag opens,
# BEFORE the DOMContentLoaded wrapper.
# The keyboard functions need to be global (not inside DOMContentLoaded) 
# because they're called from inline onclick handlers.

insertion = """
// ---- Keyboard helpers (global, called from inline onclick handlers) ----
var _kbActiveField = null;
function kbInsert(text) {
    var el = _kbActiveField || document.getElementById('chatInput');
    if (!el) return;
    var start = el.selectionStart;
    var end = el.selectionEnd;
    el.value = el.value.substring(0, start) + text + el.value.substring(end);
    el.selectionStart = el.selectionEnd = start + text.length;
    el.focus();
}
function toggleKeyboard() {
    var kb = document.getElementById('unifiedKeyboard');
    var btn = document.getElementById('kbToggleBtn');
    if (!kb || !btn) return;
    var active = kb.style.display !== 'none';
    kb.style.display = active ? 'none' : 'block';
    btn.textContent = active ? '⌨️ Клавиатура' : ' Скрыть';
}
function switchKbTab(tabName) {
    document.querySelectorAll('.kb-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.kb-layout').forEach(function(l) { l.classList.remove('active'); });
    var tab = document.querySelector('.kb-tab[data-layout="' + tabName + '"]');
    var layout = document.getElementById('kbLayout' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    if (tab) tab.classList.add('active');
    if (layout) layout.classList.add('active');
}
// ---- End keyboard helpers ----
"""

# Insert after the opening <script> tag but before the console.log
marker = "console.log('[coach] inline script loaded...');"
if marker in content:
    content = content.replace(marker, marker + insertion)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"SUCCESS: keyboard helpers inserted (len={len(content)})")
else:
    print(f"ERROR: marker not found: {marker}")
