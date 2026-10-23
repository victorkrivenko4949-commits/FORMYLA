#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3: Probe year-specific olympiad pages found on olymp.mipt.ru."""
import urllib.request, urllib.error, ssl, re, sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE = 'https://olymp.mipt.ru'

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

# 1. Probe year-specific olympiad pages found in /olympiad/results
out.append("=== Year-specific olympiad pages ===")
year_pages = [
    '/olympiad/math2022', '/olympiad/math2021',
    '/olympiad/Phys22', '/olympiad/phys2021',
    '/olympiad/bio2022', '/olympiad/bio2021',
    '/olympiad/math2023', '/olympiad/math2020',
    '/olympiad/math2019', '/olympiad/math2018',
    '/olympiad/math2024', '/olympiad/math2025',
    '/olympiad/phys2022', '/olympiad/phys2020',
    '/olympiad/phys2019',
]

for page in year_pages:
    status, html = fetch(BASE + page)
    if status == 200:
        pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
        links = re.findall(r'href="([^"]+)"', html)
        out.append(f'{page}: HTTP {status} | size={len(html)}b | PDFs={len(pdfs)} | links={len(links)}')
        for p in pdfs[:20]:
            out.append(f'  PDF: {p}')
        for l in links:
            if any(x in l.lower() for x in ['upload', 'file', 'archive', 'download', 'problem', 'task', 'pdf']):
                out.append(f'  LINK: {l}')
    else:
        out.append(f'{page}: HTTP {status}')

# 2. Also check other olympiad sub-pages
out.append("\n=== Other olympiad sub-pages ===")
for page in ['/olympiad/benefits', '/olympiad/ege', '/olympiad/contacts', '/olympiad/organizers']:
    status, html = fetch(BASE + page)
    if status == 200:
        pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
        links = re.findall(r'href="([^"]+)"', html)
        out.append(f'{page}: HTTP {status} | size={len(html)}b | PDFs={len(pdfs)} | links={len(links)}')
        for p in pdfs[:10]:
            out.append(f'  PDF: {p}')
        olymp_links = [l for l in links if any(x in l.lower() for x in ['olympiad','math','physics','task','problem','upload','fiztekh','phystech','pdf'])]
        for l in olymp_links[:15]:
            out.append(f'  LINK: {l}')
    else:
        out.append(f'{page}: HTTP {status}')

# 3. Detailed PDF listing from /olympiad/samples
out.append("\n=== All PDFs from /olympiad/samples ===")
status, html = fetch(BASE + '/olympiad/samples')
if status == 200:
    pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
    out.append(f'Total PDFs: {len(pdfs)}')
    for p in pdfs:
        if p.startswith('http'):
            out.append(f'  {p}')
        else:
            out.append(f'  {BASE}{p}')
    sections = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html)
    out.append(f'\nSections on page: {len(sections)}')
    for s in sections:
        s_clean = re.sub(r'<[^>]+>', '', s)
        out.append(f'  Section: {s_clean}')
else:
    out.append(f'HTTP {status}')

# 4. Deep probe phystech.ru for PDFs
out.append("\n=== phystech.ru deep probe ===")
for url in [
    'https://phystech.ru',
    'https://phystech.ru/olympiads/',
    'https://phystech.ru/obuchenie/olimpiady/',
]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        html = r.read().decode('utf-8', errors='replace')
        pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
        links = re.findall(r'href="([^"]+)"', html)
        olymp_links = [l for l in links if any(x in l.lower() for x in ['olympiad','fizteh','phystech','math','physics','archive','upload'])]
        out.append(f'{url}: HTTP {r.status} | PDFs={len(pdfs)} | olymp_links={len(olymp_links)}')
        for p in pdfs[:10]:
            out.append(f'  PDF: {p}')
        for l in olymp_links[:15]:
            out.append(f'  LINK: {l}')
    except Exception as e:
        out.append(f'{url}: ERROR - {e}')

# 5. Probe abitu.net for Fiztekh events
out.append("\n=== abitu.net olympiad events ===")
for url in ['https://abitu.net/events', 'https://abitu.net/event/4935', 'https://abitu.net/event/4877']:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        html = r.read().decode('utf-8', errors='replace')
        pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
        links = re.findall(r'href="([^"]+)"', html)
        fiztekh_links = [l for l in links if any(x in l.lower() for x in ['fizteh','phystech','mipt','олимп'])]
        out.append(f'{url}: HTTP {r.status} | PDFs={len(pdfs)} | fiztekh_links={len(fiztekh_links)}')
        for p in pdfs[:10]:
            out.append(f'  PDF: {p}')
        for l in fiztekh_links[:10]:
            out.append(f'  LINK: {l}')
    except Exception as e:
        out.append(f'{url}: ERROR - {e}')

# Write results
result = '\n'.join(out)
with open('_probe3_results.txt', 'w', encoding='utf-8') as f:
    f.write(result)
print(f"Written {len(out)} lines to _probe3_results.txt")
