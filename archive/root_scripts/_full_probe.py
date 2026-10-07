#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full probe of all official sources for Fiztekh olympiad problems."""
import urllib.request, urllib.error, ssl, re, sys, json, os

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

results = []

def probe(url, label=None):
    label = label or url
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        body = r.read()
        status = r.status
        text = body.decode('utf-8', errors='replace')
        results.append((status, label, url, len(text), text[:200].replace('\n',' ').replace('\r','')))
        return status, text, body
    except urllib.error.HTTPError as e:
        results.append((e.code, label, url, 0, str(e)[:200]))
        return e.code, str(e), b''
    except Exception as e:
        results.append((-1, label, url, 0, str(e)[:200]))
        return -1, str(e), b''

# ============ 1. olymp.mipt.ru exhaustive routes ============
print("=== Phase 1: olymp.mipt.ru routes ===", flush=True)
BASE1 = 'https://olymp.mipt.ru'

routes = [
    '/', '/olympiad', '/olympiad/', '/olympiad/samples', '/olympiad/stages',
    '/olympiad/preparation', '/olympiad/archive', '/olympiad/tasks',
    '/olympiad/results', '/olympiad/about',
    '/math', '/math/', '/math/archive',
    '/physics', '/physics/', '/physics/archive',
    '/tasks', '/tasks/', '/problems', '/problems/',
    '/uploads/', '/uploads/media/',
    '/api/', '/api/olympiads', '/api/tasks', '/api/problems',
    '/api/v1/', '/api/v1/olympiads', '/api/v1/tasks',
    '/sitemap.xml', '/robots.txt',
    '/static/', '/build/',
    '/archive/', '/data/',
    '/olympiad/results/2024', '/olympiad/results/2025',
    '/olympiad/tasks/2024', '/olympiad/tasks/2025',
    '/olympiad/archive/2024', '/olympiad/archive/2025',
    '/math/2024', '/math/2025',
    '/math/2024/qualifying_tasks_9.pdf',
    '/math/2025/qualifying_tasks_9.pdf',
    '/math/2025/qualifying_tasks_10.pdf',
    '/math/2025/qualifying_tasks_11.pdf',
    '/math/2025/final_tasks_9.pdf',
    '/math/2025/final_tasks_10.pdf',
    '/math/2025/final_tasks_11.pdf',
    '/api/phystech', '/api/fiztekh',
    '/api/olympiad/phystech', '/api/olympiad/fiztekh',
    '/api/subjects', '/api/math',
    '/api/years', '/api/years/2025',
    '/api/grades', '/api/rounds',
    '/api/olympiads/phystech', '/api/olympiads/fiztekh',
    '/api/tasks/phystech', '/api/problems/phystech',
    '/api/v1/phystech', '/api/v1/fiztekh',
    '/api/v1/olympiads/phystech',
    '/graphql', '/api/graphql',
    '/.env', '/config.json',
    '/wp-admin', '/wp-content',
    '/index.php', '/index.html',
]

for r in routes:
    probe(BASE1 + r, f'olymp.mipt.ru{r}')
    print(f'  {r}', flush=True)

# ============ 2. Check other domains ============
print("\n=== Phase 2: Other domains ===", flush=True)

other_domains = [
    # MIPT official sites
    'https://mipt.ru',
    'https://mipt.ru/olympiads/',
    'https://mipt.ru/olympiads/fizteh/',
    'https://mipt.ru/abitur/olympiads/',
    'https://pk.mipt.ru',
    'https://pk.mipt.ru/olympiads/',
    'https://pk.mipt.ru/olimpiady/',
    # Abitu platform
    'https://abitu.net',
    'https://abitu.net/olympiad',
    'https://abitu.net/tasks',
    'https://abitu.net/event',
    'https://abitu.net/olympiads',
    'https://abitu.net/phystech',
    'https://abitu.net/fiztekh',
    # Phystech olympiad sites
    'https://phystech.ru',
    'https://olymp.phystech.ru',
    'https://olymp.mipt.ru/math/',
    # Archive
    'https://archive.mipt.ru',
    'https://olympiads.mipt.ru',
    # Physics/Math olympiad
    'https://physolymp.ru',
    'https://math.physolymp.ru',
    'https://abitu.net/v-olimpiada-fizteh',
    'https://abitu.net/vi-olimpiada-fizteh',
    'https://abitu.net/vii-olimpiada-fizteh',
]

for domain in other_domains:
    probe(domain, domain)
    print(f'  {domain}', flush=True)

# ============ 3. Try to extract API endpoints from JS bundle ============
print("\n=== Phase 3: JS bundle analysis ===", flush=True)

_, html, _ = probe(BASE1 + '/', 'olymp.mipt.ru main page')

# Find JS bundles
js_urls = set()
if html:
    js_urls.update(re.findall(r'src=["\']([^"\']*\.js[^"\']*)["\']', html))
    js_urls.update(re.findall(r'href=["\']([^"\']*\.js[^"\']*)["\']', html))

print(f"Found {len(js_urls)} JS URLs", flush=True)
for js in sorted(js_urls):
    if js.startswith('//'):
        js_url = 'https:' + js
    elif js.startswith('/'):
        js_url = BASE1 + js
    else:
        js_url = js
    status, text, body = probe(js_url, js)
    if status == 200 and len(text) > 100:
        # Look for API endpoints, fetch calls, PDF references
        endpoints = set(re.findall(r'["\'](/api/[^"\']+)["\']', text))
        fetches = set(re.findall(r'fetch\(["\']([^"\']+)["\']', text))
        pdfs = set(re.findall(r'["\']([^"\']*\.pdf)["\']', text))
        routes_js = set(re.findall(r'["\'](/olympiad[^"\']+)["\']', text))
        routes_js.update(re.findall(r'["\'](/math[^"\']+)["\']', text))
        routes_js.update(re.findall(r'["\'](/physics[^"\']+)["\']', text))
        if endpoints:
            print(f"  API endpoints in {js}: {endpoints}", flush=True)
        if fetches:
            print(f"  fetch() calls in {js}: {fetches}", flush=True)
        if pdfs:
            print(f"  PDF refs in {js}: {pdfs}", flush=True)
        if routes_js:
            print(f"  Routes in {js}: {routes_js}", flush=True)
        if not any([endpoints, fetches, pdfs, routes_js]):
            print(f"  {js}: {len(text)}b (no useful refs found)", flush=True)

# ============ 4. Try to extract links from all olympiad pages ============
print("\n=== Phase 4: Scrape all olympiad pages for PDFs ===", flush=True)

pages_to_check = [
    '/olympiad/samples',
    '/olympiad/stages',
    '/olympiad/preparation',
    '/olympiad/archive',
    '/olympiad/tasks',
    '/olympiad/about',
    '/olympiad',
    '/',
    '/math',
    '/math/archive',
    '/physics',
]

all_pdfs = {}
all_links = {}

for page in pages_to_check:
    status, text, _ = probe(BASE1 + page, page)
    if status == 200 and text:
        pdfs = re.findall(r'href=["\']([^"\']*\.pdf)["\']', text, re.IGNORECASE)
        all_links_local = re.findall(r'href=["\']([^"\']+)["\']', text)
        if pdfs:
            all_pdfs[page] = pdfs
            print(f"  {page}: {len(pdfs)} PDFs", flush=True)
        if all_links_local:
            # filter useful links
            useful = [l for l in all_links_local if any(x in l for x in ['olympiad','math','physics','tasks','archive','upload','pdf'])]
            if useful:
                all_links[page] = useful[:10]
                print(f"  {page}: {len(useful)} useful links", flush=True)

# ============ Print summary ============
print("\n\n========== FULL RESULTS ==========", flush=True)
print(f"{'Status':>6} | {'Label':60s} | Size | Info", flush=True)
print("-"*120, flush=True)
for status, label, url, size, info in results:
    print(f"  [{status:>3}] {label:60s} | {size:>6}b | {info[:80]}", flush=True)
