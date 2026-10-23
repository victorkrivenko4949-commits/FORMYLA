import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    for name, w, h, mobile in [('mobile', 390, 844, True), ('desktop', 1440, 900, False)]:
        ctx = b.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile)
        pg = ctx.new_page()
        pg.goto('http://127.0.0.1:5000/olympiads/methods/atlas.html')
        pg.wait_for_selector('#methods-data', state='attached', timeout=30000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f'qa_shots/{name}_1_catalog.png')
        pg.evaluate("location.hash='#/methods/A1'; window.dispatchEvent(new Event('hashchange'))")
        pg.wait_for_selector('#tutor', timeout=10000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f'qa_shots/{name}_2_method.png')
        ctx.close()
    b.close()
print('DONE')
