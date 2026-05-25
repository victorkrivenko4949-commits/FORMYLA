# -*- coding: utf-8 -*-
"""Production smoke-test for vsosh-9-2027 release."""
import re
import sys
import time
import urllib.request

BASE = "https://formyla-com.onrender.com"
PROBNIKS = ("topic-6", "topic-8", "topic-9", "topic-10")


def fetch(path, retries=3):
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(BASE + path, headers={"User-Agent": "smoke-test/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(5)
    raise last


def main():
    print(f"=== PROD smoke {BASE} ===")
    rc = 0
    try:
        code, html = fetch("/olympiads/vsosh-9-2027")
        n_packs = len(set(re.findall(r"vsosh-9-2027-topic-\d+", html)))
        print(f"catalog HTTP={code}  len={len(html)}  unique_topic_refs={n_packs}")
        if code != 200:
            rc = 1
    except Exception as e:
        print(f"catalog ERROR: {e!r}")
        return 1

    for slug in PROBNIKS:
        try:
            code, html = fetch(f"/olympiads/probnik/vsosh-9-2027-{slug}")
            task_links = len(set(re.findall(r"/olympiads/task/(\d+)", html)))
            has_otvet = "Ответ" in html
            has_solution = "Решение" in html
            mathjax = ("\\(" in html) or ("\\[" in html) or ("$$" in html)
            print(
                f"{slug:9s} HTTP={code} len={len(html)} task_links={task_links} "
                f"otvet={has_otvet} solution={has_solution} mathjax={mathjax}"
            )
            if code != 200 or task_links == 0:
                rc = 1
        except Exception as e:
            print(f"{slug} ERROR: {e!r}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
