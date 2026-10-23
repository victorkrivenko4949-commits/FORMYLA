#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2: Deep probe of useful pages and other domains."""
import urllib.request, urllib.error, ssl, re, os

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        return r.status, r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return -1, str(e)

out = []

def report(s):
    out.append(s)
    print(s, flush=True)

BASE = 'https://olymp.mipt.ru'

# 1. Deep scan of /olympiad/stages, /olympiad/preparation, /olympiad/results
report("=== Page analysis ===")
for page in ['/olympiad/stages', '/olympiad/preparation', '/olympiad/results', '/olympiad/about']:
    status, html = fetch(BASE + page)
    if status != 200:
        report(f"  {page}: HTTP {status}")
        continue
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    pdfs = [l for l in links if '.pdf' in l.lower()]
    olympiad_links = [l for l in links if any(x in l.lower() for x in ['olympiad','math','physics','task','problem','upload','fiztekh','phystech'])]
    report(f"\n--- {page} (size={len(html)}b) ---")
    report(f"  Total links: {len(links)}")
    report(f"  PDF links: {len(pdfs)}")
    for p in pdfs[:20]:
        report(f"    PDF: {p}")
    report(f"  Olympiad-related links: {len(olympiad_links)}")
    for l in olympiad_links[:15]:
        report(f"    LINK: {l}")

# 2. Check mipt.ru for olympiad content
report("\n\n=== mipt.ru ===")
for page in ['https://mipt.ru', 'https://mipt.ru/olympiads/', 'https://mipt.ru/olympiads/fizteh/']:
    status, html = fetch(page)
    report(f"\n--- {page} [{status}] ---")
    if status == 200 and len(html) > 500:
        links = re.findall(r'href=["\']([^"\']+)["\']', html)
        pdfs = [l for l in links if '.pdf' in l.lower()]
        olympiad_links = [l for l in links if any(x in l.lower() for x in ['olympiad','fizteh','phystech','upload','math','physics'])]
        report(f"  Links: {len(links)}, PDFs: {len(pdfs)}, Olympiad: {len(olympiad_links)}")
        for l in olympiad_links[:15]:
            report(f"    {l}")

# 3. Check phystech.ru
report("\n\n=== phystech.ru ===")
status, html = fetch('https://phystech.ru')
if status == 200:
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    pdfs = [l for l in links if '.pdf' in l.lower()]
    olympiad_links = [l for l in links if any(x in l.lower() for x in ['olympiad','fizteh','phystech','upload','math','physics','task'])]
    report(f"  Links: {len(links)}, PDFs: {len(pdfs)}, Olympiad: {len(olympiad_links)}")
    for l in olympiad_links[:20]:
        report(f"    {l}")

# 4. Check abitu.net
report("\n\n=== abitu.net ===")
status, html = fetch('https://abitu.net')
if status == 200:
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    pdfs = [l for l in links if '.pdf' in l.lower()]
    olympiad_links = [l for l in links if any(x in l.lower() for x in ['olympiad','fizteh','phystech','upload','math','physics','task','problem'])]
    report(f"  Links: {len(links)}, PDFs: {len(pdfs)}, Olympiad: {len(olympiad_links)}")
    for l in olympiad_links[:20]:
        report(f"    {l}")
    # Also look for events/olympiad links
    event_links = [l for l in links if 'event' in l.lower() or 'olympiad' in l.lower() or 'fizteh' in l.lower() or 'task' in l.lower()]
    report(f"  Event/olympiad links: {len(event_links)}")
    for l in event_links[:20]:
        report(f"    {l}")

# 5. Check pk.mipt.ru
report("\n\n=== pk.mipt.ru ===")
status, html = fetch('https://pk.mipt.ru')
if status == 200:
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    pdfs = [l for l in links if '.pdf' in l.lower()]
    olympiad_links = [l for l in links if any(x in l.lower() for x in ['olympiad','fizteh','phystech','upload','math','physics','task'])]
    report(f"  Links: {len(links)}, PDFs: {len(pdfs)}, Olympiad: {len(olympiad_links)}")
    for l in olympiad_links[:20]:
        report(f"    {l}")

# 6. Read JS bundle looking for API routes
report("\n\n=== JS Bundle Deep Analysis ===")
status, js_text = fetch(BASE + '/build/global.277e25ee.js')
if status == 200:
    # find all path-like strings
    paths = set(re.findall(r'["\'](/[a-zA-Z0-9_/.-]+)["\']', js_text))
    api_paths = [p for p in paths if any(x in p.lower() for x in ['api','fetch','olympiad','math','physics','task','problem','upload','pdf','data','json'])]
    report(f"  Interesting paths in JS bundle: {len(api_paths)}")
    for p in sorted(api_paths)[:30]:
        report(f"    {p}")

# Also search for any URL patterns
    urls = set(re.findall(r'https?://[^"\'\\\s,;)]+', js_text))
    olympiad_urls = [u for u in urls if any(x in u.lower() for x in ['olympiad','mipt','fizteh','phystech','math','physics'])]
    report(f"  URLs in JS bundle: {len(olympiad_urls)}")
    for u in olympiad_urls[:20]:
        report(f"    {u}")

with open('C:/Users/Victor/Desktop/probe2_results.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

report("\n\nDone. Results saved to probe2_results.txt")
