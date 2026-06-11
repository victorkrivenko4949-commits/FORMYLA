# -*- coding: utf-8 -*-
"""Юнит-тест канонизатора корней."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.latex_root_normalizer import normalize_roots

CASES = [
    # (вход, ожидаемый выход)
    # --- уже корректные: НЕ должны меняться ---
    (r"\sqrt[3]{a^2b^2c^2}", r"\sqrt[3]{a^2b^2c^2}"),
    (r"\sqrt[3]{1}", r"\sqrt[3]{1}"),
    (r"\sqrt{2}", r"\sqrt{2}"),
    (r"\sqrt{x^2+y^2}", r"\sqrt{x^2+y^2}"),
    (r"\frac{a^2+b^2+c^2}{3}\ge\sqrt[3]{a^2b^2c^2}=\sqrt[3]{1}=1",
     r"\frac{a^2+b^2+c^2}{3}\ge\sqrt[3]{a^2b^2c^2}=\sqrt[3]{1}=1"),
    # --- битые: \sqrt[n] без скобок ---
    (r"\sqrt[3] X", r"\sqrt[3]{X}"),
    (r"\sqrt[3]abc", r"\sqrt[3]{abc}"),
    (r"\sqrt[3](a^2b^2c^2)", r"\sqrt[3]{a^2b^2c^2}"),
    (r"\sqrt [3]{a^2b^2c^2}", r"\sqrt[3]{a^2b^2c^2}"),
    (r"\sqrt[3]\frac{a}{b}", r"\sqrt[3]{\frac{a}{b}}"),
    # --- КРИТИЧНО: корректные формулы с ^{n} рядом с \sqrt — НЕ трогать ---
    (r"a^2\sqrt{2}", r"a^2\sqrt{2}"),          # a²·√2, НЕ корень 2-й степени
    (r"\(a^2\sqrt{2}\)", r"\(a^2\sqrt{2}\)"),
    (r"x^2 + [2]{y}", r"x^2 + [2]{y}"),          # голый [2]{} — НЕ трогать
    # --- юникод ---
    ("∛(a^2b^2c^2)", r"\sqrt[3]{a^2b^2c^2}"),
    ("∛8", r"\sqrt[3]{8}"),
    ("³√(a^2b^2c^2)", r"\sqrt[3]{a^2b^2c^2}"),
    ("³√27", r"\sqrt[3]{27}"),
    ("√(x+y)", r"\sqrt{x+y}"),
    ("√2", r"\sqrt{2}"),
    # --- \sqrt без скобок ---
    (r"\sqrt(x+1)", r"\sqrt{x+1}"),
    (r"\sqrt 5", r"\sqrt{5}"),
]

def main():
    ok = 0
    fail = 0
    for inp, exp in CASES:
        got = normalize_roots(inp)
        # идемпотентность
        got2 = normalize_roots(got)
        status = "OK" if got == exp else "FAIL"
        idem = "" if got2 == got else "  [NOT IDEMPOTENT]"
        if got == exp and got2 == got:
            ok += 1
        else:
            fail += 1
            print(f"  {status}{idem}")
            print(f"    IN : {inp!r}")
            print(f"    EXP: {exp!r}")
            print(f"    GOT: {got!r}")
            if got2 != got:
                print(f"    2ND: {got2!r}")
    print(f"\nПройдено: {ok}/{len(CASES)}   Провалено: {fail}")
    return 0 if fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
