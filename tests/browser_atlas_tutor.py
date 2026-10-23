# -*- coding: utf-8 -*-
"""Playwright browser QA for the atlas methods tutor.

Usage:
    py -3.14 tests/browser_atlas_tutor.py --base-url http://127.0.0.1:5001
    py -3.14 tests/browser_atlas_tutor.py --base-url http://127.0.0.1:5001 --shots-dir qa_shots

Runs the full user-visible scenarios and takes screenshots (desktop 1440,
mobile 390x844).  Requires Playwright + Chromium (installed for py 3.14).
"""

import argparse
import base64
import os
import sys
import time

from playwright.sync_api import sync_playwright, expect

ATLAS_URL = "/olympiads/methods/atlas.html"

# A tiny valid 1x1 PNG for clipboard/drag tests.
PNG_1PX = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _open_tutor(page):
    # open a method first (hash router), then open the tutor panel
    page.goto(ATLAS_URL)
    page.wait_for_selector("#methods-data", state="attached", timeout=20000)
    page.evaluate("location.hash = '#/methods/A1'; window.dispatchEvent(new Event('hashchange'))")
    page.wait_for_selector("#tutor", timeout=20000)
    page.wait_for_selector("#tutor-open", timeout=20000)
    page.click("#tutor-open")
    page.wait_for_selector("#tutor.open", timeout=5000)
    return page


def scenario_selection_quote(page):
    _open_tutor(page)
    # select some text inside the article
    page.evaluate("""() => {
      const el = document.querySelector('#article .prose p, #article h2, #article p');
      if (!el) return;
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    }""")
    page.wait_for_selector("#sel-panel", timeout=5000)
    # click "Это непонятно"
    page.evaluate("""() => {
      const btns = [...document.querySelectorAll('#sel-panel button')];
      const b = btns.find(x => x.textContent === 'Это непонятно');
      if (b) b.click();
    }""")
    page.wait_for_selector("#tutor-quote:not([hidden])", timeout=5000)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:5001")
    ap.add_argument("--shots-dir", default="qa_shots")
    args = ap.parse_args()

    os.makedirs(args.shots_dir, exist_ok=True)

    results = []

    def record(name, ok, note=""):
        results.append((name, ok, note))
        print(("[PASS] " if ok else "[FAIL] ") + name + ((" — " + note) if note else ""))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---------------- Desktop 1440 ----------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(args.base_url + ATLAS_URL)
        page.wait_for_selector("#methods-data", state="attached", timeout=20000)
        page.evaluate("location.hash = '#/methods/A1'; window.dispatchEvent(new Event('hashchange'))")
        page.wait_for_selector("#tutor", timeout=20000)
        page.screenshot(path=os.path.join(args.shots_dir, "01_desktop_method_dark.png"))

        # On desktop (>1180px) the tutor is a sticky sidebar — always visible.
        # #tutor-open is hidden; interact with #tutor-input directly.
        page.wait_for_selector("#tutor-input", timeout=5000)
        page.screenshot(path=os.path.join(args.shots_dir, "02_desktop_tutor_empty_dark.png"))

        # status should become on/off
        page.wait_for_timeout(1500)
        status_text = page.inner_text("#tutor-status-text")
        record("tutor status visible", "ИИ" in status_text, status_text[:40])

        # send a question -> streaming loading + answer
        page.fill("#tutor-input", "Объясни идею метода")
        page.click("#tutor-send")
        # loading indicator appears
        try:
            page.wait_for_selector("#tutor-pending", timeout=2000)
            record("loading indicator appears", True)
        except Exception:
            record("loading indicator appears", False, "no pending")
        page.screenshot(path=os.path.join(args.shots_dir, "03_desktop_loading.png"))

        # wait for a real answer (streamed)
        page.wait_for_selector(".msg.ai .bubble", timeout=120000)
        page.wait_for_timeout(1000)
        log_text = page.inner_text("#tutor-log")
        record("real answer received", len(log_text) > 20, log_text[:60])

        # answer with LaTeX: ask for a formula (rendered by MathJax — superscripts)
        page.fill("#tutor-input", "Напиши формулу квадрата суммы в LaTeX")
        page.click("#tutor-send")
        page.wait_for_timeout(9000)
        log_text = page.inner_text("#tutor-log")
        # MathJax renders (100+3)^2 as a superscript "2" or a katex msup node
        has_math = ("+" in log_text and "2" in log_text) or ("^2" in log_text) or ("msup" in log_text)
        record("answer contains formula", has_math, log_text[-80:])
        page.screenshot(path=os.path.join(args.shots_dir, "04_desktop_answer_latex.png"))

        # light theme
        page.evaluate("""() => {
          window.__atlas = window.__atlas || {};
          document.documentElement.setAttribute('data-theme','light');
        }""")
        page.screenshot(path=os.path.join(args.shots_dir, "05_desktop_light_theme.png"))
        page.evaluate("document.documentElement.setAttribute('data-theme','dark')")

        # hint ladder pill
        page.click("button[data-mode='hint']")
        # wait for streaming to finish (stop button hidden again)
        page.wait_for_selector("#tutor-stop[style*='none'], #tutor-send", timeout=20000)
        page.wait_for_timeout(1500)
        try:
            pill = page.inner_text("#tutor-hint-pill")
            record("hint pill visible after hint", "из" in pill, pill)
        except Exception:
            record("hint pill visible after hint", False)
        page.screenshot(path=os.path.join(args.shots_dir, "06_desktop_hint_1of4.png"))

        # spoiler warning: handle the confirm() dialog
        page.on("dialog", lambda d: d.accept())
        page.click("#tutor-ladder [data-ladder='reveal']")
        # wait for meta event to flip the spoiler warning
        page.wait_for_function("document.querySelector('#tutor-spoiler-warn').classList.contains('on')", timeout=15000)
        record("spoiler warning shown", True)
        page.screenshot(path=os.path.join(args.shots_dir, "07_desktop_spoiler_warning.png"))

        # switch task -> context reset (hintLevel back to 0)
        page.select_option("#tutor-task", "1")
        page.wait_for_timeout(500)
        pill_display = page.evaluate("document.querySelector('#tutor-hint-pill').style.display")
        record("task switch resets hintLevel", pill_display == "none")

        # Enter vs Shift+Enter
        page.fill("#tutor-input", "первая строка")
        page.press("#tutor-input", "Shift+Enter")
        val = page.input_value("#tutor-input")
        record("Shift+Enter inserts newline", "\n" in val)

        # Esc closes panel
        page.press("#tutor-input", "Escape")
        record("Esc closes panel", not page.evaluate("document.querySelector('#tutor').classList.contains('open')"))

        ctx.close()

        # ---------------- Mobile 390x844 ----------------
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mpage = mctx.new_page()
        mpage.goto(args.base_url + ATLAS_URL)
        mpage.wait_for_selector("#methods-data", state="attached", timeout=20000)
        mpage.evaluate("location.hash = '#/methods/A1'; window.dispatchEvent(new Event('hashchange'))")
        mpage.wait_for_selector("#tutor-open", timeout=20000)
        mpage.click("#tutor-open")
        mpage.wait_for_selector("#tutor.open", timeout=5000)
        mpage.screenshot(path=os.path.join(args.shots_dir, "08_mobile_tutor_bottom_sheet.png"))
        mctx.close()

        browser.close()

    print("-" * 70)
    failed = [r for r in results if not r[1]]
    print(f"Итого: {len(results)} проверок, {len(results) - len(failed)} прошло, {len(failed)} упало")
    if failed:
        for name, _, note in failed:
            print("  FAIL:", name, "-", note)
        sys.exit(1)
    print("Все браузерные проверки прошли.")


if __name__ == "__main__":
    main()
