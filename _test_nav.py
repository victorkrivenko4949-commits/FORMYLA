"""
N1_NAV acceptance test — Местная навигация
Запускать как: python _test_nav.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
import re

def main():
    client = app.test_client()
    report_lines = []
    all_ok = [True]

    def ok(msg):
        report_lines.append(f"PASS  {msg}")
        print(f"PASS  {msg}")
    def fail(msg):
        all_ok[0] = False
        report_lines.append(f"FAIL  {msg}")
        print(f"FAIL  {msg}")

    # ---------- 1) HTML fragments ----------
    print("\n=== 1) HTML fragments of menus ===")

    resp = client.get("/daily_tasks", follow_redirects=True)
    html = resp.data.decode("utf-8")
    ok(f"GET /daily_tasks -> {resp.status_code}")

    # Desktop nav
    m_desktop = re.search(r'<nav class="nav" id="navLinks">(.*?)</nav>', html, re.DOTALL)
    if m_desktop:
        desktop_fragment = m_desktop.group(0)
        ok(f"Desktop nav fragment: {len(desktop_fragment)} chars")
        report_lines.append(f"\n### DESKTOP NAV\n```html\n{desktop_fragment}\n```\n")
        for term in ["Задачи дня", "Олимпиады", "Куратор подготовки", "Прочее"]:
            if term in desktop_fragment:
                ok(f"  Desktop nav contains: {term}")
            else:
                fail(f"  Desktop nav MISSING: {term}")
        for old in ["Тренировка", "Доска", "Сообщество", "О сайте", "Тьютор", "Написать отзыв"]:
            if old in desktop_fragment:
                fail(f"  Desktop nav still has OLD item: {old}")
    else:
        fail("Desktop nav not found")

    # Mobile drawer
    m_drawer = re.search(r'<aside class="mobile-drawer".*?</aside>', html, re.DOTALL)
    if m_drawer:
        drawer_fragment = m_drawer.group(0)
        ok(f"Drawer fragment: {len(drawer_fragment)} chars")
        report_lines.append(f"\n### DRAWER NAV\n```html\n{drawer_fragment[:2000]}\n```\n")
        for term in ["Задачи дня", "Олимпиады", "Куратор подготовки", "Прочее"]:
            if term in drawer_fragment:
                ok(f"  Drawer contains: {term}")
            else:
                fail(f"  Drawer MISSING: {term}")
    else:
        fail("Drawer not found")

    # Bottom nav
    m_bottom = re.search(r'<nav class="mobile-bottom-nav".*?</nav>', html, re.DOTALL)
    if m_bottom:
        bottom_fragment = m_bottom.group(0)
        ok(f"Bottom nav fragment: {len(bottom_fragment)} chars")
        report_lines.append(f"\n### BOTTOM NAV\n```html\n{bottom_fragment}\n```\n")
        for term in ["Задачи дня", "Олимпиады", "Куратор", "Прочее"]:
            if term in bottom_fragment:
                ok(f"  Bottom nav contains: {term}")
            else:
                fail(f"  Bottom nav MISSING: {term}")
    else:
        fail("Bottom nav not found")

    # ---------- 2) misc page ----------
    print("\n=== 2) /misc page ===")
    resp = client.get("/misc", follow_redirects=True)
    ok(f"/misc status: {resp.status_code}")
    html_misc = resp.data.decode("utf-8")
    m_content = re.search(r'<div class="misc-page">(.*?)</div>\s*</main>', html_misc, re.DOTALL)
    if m_content:
        misc_html = m_content.group(0)
        ok(f"Misc page content: {len(misc_html)} chars")
        report_lines.append(f"\n### MISC PAGE HTML\n```html\n{misc_html[:4000]}\n```\n")
        for group_title in ["Тренировка", "Доска и чертежи", "Сообщество", "Инструменты", "Информация"]:
            if group_title in misc_html:
                ok(f"  Misc group present: {group_title}")
            else:
                fail(f"  Misc group MISSING: {group_title}")
        for title in re.findall(r'<div class="misc-group-title">(.*?)</div>', misc_html):
            if re.search(r'[\U0001F000-\U0001FFFF]', title):
                fail(f"  Emoji found in group title: {title}")
            else:
                ok(f"  Group title clean (no emoji): {title}")
    else:
        fail("Misc page content block not found")

    # ---------- 3) walk all links from misc page ----------
    print("\n=== 3) Walk all links from /misc ===")
    resp = client.get("/misc", follow_redirects=True)
    html_misc2 = resp.data.decode("utf-8")
    m_block = re.search(r'<div class="misc-page">(.*?)</div>\s*</main>', html_misc2, re.DOTALL)
    if m_block:
        links = re.findall(r'href="([^"]+)"', m_block.group(0))
        links = [l for l in links if l and not l.startswith("javascript:") and l != "#" and not l.startswith("http")]
        unique_links = list(dict.fromkeys(links))
        ok(f"Found {len(unique_links)} unique internal links on /misc")
        report_lines.append(f"\n### LINK WALK ({len(unique_links)} links)\n")
        for link in unique_links:
            r = client.get(link, follow_redirects=True)
            status = r.status_code
            if status == 500:
                fail(f"  {link} -> 500")
            elif status >= 400:
                fail(f"  {link} -> {status}")
            else:
                ok(f"  {link} -> {status}")
            report_lines.append(f"  {link} -> {status}")

    # ---------- 4) profile page: «Прочее» active ----------
    print("\n=== 4) Profile page active state ===")
    resp = client.get("/misc", follow_redirects=True)
    html_check = resp.data.decode("utf-8")
    # Check that nav.js is referenced
    if 'nav.js' in html_check:
        ok("nav.js referenced on /misc page")
    else:
        fail("nav.js not referenced on /misc page")
    # Check /misc link in nav
    if '/misc' in html_check:
        ok("'/misc' found in rendered HTML")
    else:
        fail("'/misc' NOT found in rendered HTML")
    # Check logo leads to daily_tasks
    m_logo = re.search(r'<a href="([^"]+)" class="logo"', html_check)
    if m_logo:
        logo_href = m_logo.group(1)
        if 'daily_tasks' in logo_href or 'daily' in logo_href:
            ok(f"Logo links to daily_tasks: {logo_href}")
        else:
            fail(f"Logo links to wrong page: {logo_href}")
    else:
        fail("Logo link not found in page")

    # ---------- 5) route count ----------
    print("\n=== 5) Route count ===")
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            routes.append(rule.rule)
    ok(f"Total non-static routes: {len(routes)}")
    report_lines.append(f"\n### ROUTES ({len(routes)} total)\n")
    for r in sorted(routes):
        report_lines.append(f"  {r}")

    # ---------- Write report ----------
    os.makedirs("_recon", exist_ok=True)
    report_path = "_recon/N1_NAV.md"
    header = "# N1_NAV — Приёмочный отчёт по навигации\n\n"
    report_content = header + "\n".join(report_lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"\nReport written to {report_path} (all_ok={all_ok[0]})")

    return all_ok[0]

if __name__ == "__main__":
    success = main()
    print(f"\nFinal result: {'ALL OK' if success else 'SOME FAILURES'}")
