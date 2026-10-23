"""Download KaTeX fonts to static/katex/fonts/"""
import os, urllib.request, sys

BASE = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/fonts/'
DEST = os.path.join(os.path.dirname(__file__), 'static', 'katex', 'fonts')
os.makedirs(DEST, exist_ok=True)

FONTS = [
    'KaTeX_AMS-Regular.woff2',
    'KaTeX_Caligraphic-Bold.woff2',
    'KaTeX_Caligraphic-Regular.woff2',
    'KaTeX_Fraktur-Bold.woff2',
    'KaTeX_Fraktur-Regular.woff2',
    'KaTeX_Main-Bold.woff2',
    'KaTeX_Main-BoldItalic.woff2',
    'KaTeX_Main-Italic.woff2',
    'KaTeX_Main-Regular.woff2',
    'KaTeX_Math-BoldItalic.woff2',
    'KaTeX_Math-Italic.woff2',
    'KaTeX_SansSerif-Bold.woff2',
    'KaTeX_SansSerif-Italic.woff2',
    'KaTeX_SansSerif-Regular.woff2',
    'KaTeX_Script-Regular.woff2',
    'KaTeX_Size1-Regular.woff2',
    'KaTeX_Size2-Regular.woff2',
    'KaTeX_Size3-Regular.woff2',
    'KaTeX_Size4-Regular.woff2',
    'KaTeX_Typewriter-Regular.woff2',
]

for fname in FONTS:
    url = BASE + fname
    local = os.path.join(DEST, fname)
    if os.path.exists(local):
        print(f'Already exists: {fname}')
        continue
    print(f'Downloading {fname}...', end=' ', flush=True)
    try:
        urllib.request.urlretrieve(url, local)
        print('OK')
    except Exception as e:
        print(f'FAILED: {e}')
        sys.exit(1)

print(f'\nAll {len(FONTS)} fonts downloaded to {DEST}')
