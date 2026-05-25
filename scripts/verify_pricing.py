# -*- coding: utf-8 -*-
"""Verify pricing changes (strike + 0 RUB) and daily-quest gating."""
import urllib.request as ur
import urllib.error

BASE = "http://127.0.0.1:5001"

def get(path, allow_redirect=True):
    req = ur.Request(BASE + path)
    try:
        opener = ur.build_opener()
        if not allow_redirect:
            class NoRedirect(ur.HTTPRedirectHandler):
                def redirect_request(self, *a, **kw):
                    return None
            opener = ur.build_opener(NoRedirect)
        r = opener.open(req)
        return r.status, r.read().decode("utf-8", "ignore"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore") if e.fp else "", e.headers

print("=== /about ===")
st, body, _ = get("/about")
print("status:", st)
print("has <del>:", "<del>" in body)
print("has '0 \\u20bd':", "0 \u20bd" in body)
print("count <del>:", body.count("<del>"))
# banner phrase 'now all available for free'
phrase_free = "\u0421\u0435\u0439\u0447\u0430\u0441 \u0432\u0441\u0451 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e"
print("has banner phrase:", phrase_free in body)

print()
print("=== /subscribe ===")
st, body, _ = get("/subscribe")
print("status:", st)
print("has <del>:", "<del>" in body)
print("has '0\\u20bd' or '0 \\u20bd':", ("0\u20bd" in body) or ("0 \u20bd" in body))
print("has banner phrase:", phrase_free in body)
print("count <del>:", body.count("<del>"))

print()
print("=== /daily (anon, should redirect to login) ===")
st, body, hdrs = get("/daily", allow_redirect=False)
print("status:", st)
print("Location:", hdrs.get("Location", ""))
