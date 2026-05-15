"""Quick test for the math-equivalent helper from app.py."""
import re as _re


def _math_equivalent(user, canon):
    if not user or not canon:
        return False
    u = user.strip()
    c = canon.strip()
    if not u or not c:
        return False
    _norm = lambda s: _re.sub(r"\s+", "", s).lower().replace(",", ".")
    if _norm(u) == _norm(c):
        return True
    num_re = _re.compile(r"-?\d+(?:[.,]\d+)?(?:/\d+)?")

    def _to_floats(s):
        out = []
        for m in num_re.findall(s):
            t = m.replace(",", ".")
            try:
                if "/" in t:
                    a, b = t.split("/", 1)
                    out.append(float(a) / float(b))
                else:
                    out.append(float(t))
            except Exception:
                pass
        return out

    uns = _to_floats(u)
    cns = _to_floats(c)
    if not uns or not cns:
        return False
    if len(uns) == len(cns):
        if all(abs(a - b) <= max(1e-4, 1e-3 * max(abs(a), abs(b)))
               for a, b in zip(sorted(uns), sorted(cns))):
            return True
    if len(cns) == 1 and any(
        abs(x - cns[0]) <= max(1e-4, 1e-3 * max(abs(x), abs(cns[0])))
        for x in uns
    ):
        return True
    return False


cases = [
    ("30", "30 см²", True),
    ("30 см", "30 см²", True),
    ("30,0", "30", True),
    ("1/2", "0.5", True),
    ("0.5", "1/2", True),
    ("15", "x = 15", True),
    ("answer is 7", "7", True),
    ("7", "answer is 7", True),
    ("100", "50", False),
    ("", "5", False),
    ("абв", "5", False),
    ("12.5", "12,5", True),
    ("3 см", "5 см", False),
    ("(2, 3)", "(2, 3)", True),
    ("2; 3", "(2, 3)", True),
]

ok = 0
fail = 0
for u, c, expected in cases:
    r = _math_equivalent(u, c)
    mark = "OK  " if r == expected else "FAIL"
    if r == expected:
        ok += 1
    else:
        fail += 1
    print(f"{mark}: _math_equivalent({u!r}, {c!r}) = {r}, expected {expected}")
print(f"\n{ok}/{ok+fail} passed")
