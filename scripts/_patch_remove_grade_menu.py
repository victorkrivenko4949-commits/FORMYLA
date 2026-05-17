import io, re

p = 'templates/base.html'
with io.open(p, 'r', encoding='utf-8') as fh:
    s = fh.read()

OPEN = chr(123)   # left brace
CLOSE = chr(125)  # right brace
TT = OPEN + OPEN
EE = CLOSE + CLOSE

pat = re.compile(
    r'\s*<a href="' + re.escape(TT) + r" url_for\('grade\.overview_5'\