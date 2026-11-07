# -*- coding: utf-8 -*-
"""Живая проверка: насколько хорошо DeepSeek vision читает рукописные решения.

Делает настоящие запросы к API (нужен DEEPSEEK_API_KEY), поэтому это не
pytest-тест, а скрипт.

Источники фото:
  * синтетика (по умолчанию): «тетрадные» страницы, нарисованные
    рукописными шрифтами Windows (Ink Free, Segoe Print/Script, Comic)
    с поворотом, шумом и JPEG-сжатием;
  * --dir ПАПКА: настоящие фото. Рядом с каждым photo.jpg кладётся
    photo.txt: в первой строке — ключевые фрагменты через «;»
    (например «D=1; x=2; x=3»), дальше (необязательно) — полный текст.

Для каждого фото: время ответа, найдены ли ключевые фрагменты, похожесть
на эталон. Фото и ответы модели сохраняются в --out.

    python scripts/ocr_handwriting_eval.py
    python scripts/ocr_handwriting_eval.py --dir путь/к/фото --engine gemini
"""

from __future__ import annotations

import argparse
import base64
import difflib
import io
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# (условие, строки решения, ключевые фрагменты)
SAMPLES = [
    ("Решите уравнение x^2 - 5x + 6 = 0",
     ["x² - 5x + 6 = 0", "D = 25 - 24 = 1", "x1 = (5 + 1) / 2 = 3", "x2 = (5 - 1) / 2 = 2",
      "Ответ: x = 2; x = 3"],
     ["25-24=1", "x=2", "x=3"]),
    ("Найдите значение выражения 3/4 + 5/6",
     ["3/4 + 5/6 = 9/12 + 10/12 = 19/12", "19/12 = 1 целая 7/12", "Ответ: 19/12"],
     ["9/12", "10/12", "19/12"]),
    ("Решите неравенство 2x - 7 > 3",
     ["2x - 7 > 3", "2x > 10", "x > 5", "Ответ: x > 5"],
     ["2x>10", "x>5"]),
    ("Скорость лодки 12 км/ч, течение 3 км/ч. За сколько часов лодка пройдёт 45 км против течения?",
     ["Скорость против течения: 12 - 3 = 9 км/ч", "Время: t = 45 / 9 = 5 ч", "Ответ: 5 часов"],
     ["12-3=9", "45/9=5", "5"]),
    ("Докажите, что n^2 + n чётно при любом натуральном n",
     ["n² + n = n(n + 1)", "n и n + 1 — соседние числа,", "одно из них чётное,",
      "значит произведение делится на 2. Ч.т.д."],
     ["n(n+1)", "соседн", "чётн"]),
    ("Найдите площадь прямоугольного треугольника с катетами 6 и 8",
     ["S = a·b / 2", "S = 6·8 / 2 = 24", "Гипотенуза: c² = 36 + 64 = 100, c = 10", "Ответ: S = 24"],
     ["24", "100", "10"]),
]

FONTS = ["Inkfree.ttf", "segoepr.ttf", "segoesc.ttf", "comic.ttf"]


# ── синтетика ───────────────────────────────────────────────────────────

def render_page(lines, font_file, seed):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    rnd = random.Random(seed)
    w, h = 1400, 160 + 120 * len(lines)
    img = Image.new("RGB", (w, h), (250, 248, 240))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 40):  # клетка
        d.line([(x, 0), (x, h)], fill=(200, 215, 235), width=1)
    for y in range(0, h, 40):
        d.line([(0, y), (w, y)], fill=(200, 215, 235), width=1)
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", font_file),
                              rnd.randint(46, 56))
    ink = rnd.choice([(25, 35, 120), (20, 20, 30), (30, 50, 140)])
    y = 70
    for ln in lines:
        x = 60 + rnd.randint(-10, 25)
        for ch in ln:  # «дрожание» каждой буквы
            d.text((x, y + rnd.randint(-3, 3)), ch, font=font, fill=ink)
            x += d.textlength(ch, font=font) + rnd.uniform(-1.0, 2.0)
        y += 120 + rnd.randint(-8, 8)
    img = img.rotate(rnd.uniform(-3, 3), expand=True, fillcolor=(235, 233, 225))
    img = img.filter(ImageFilter.GaussianBlur(rnd.uniform(0.4, 1.1)))
    px = img.load()  # шум
    for _ in range(img.size[0] * img.size[1] // 60):
        i, j = rnd.randrange(img.size[0]), rnd.randrange(img.size[1])
        r, g, b = px[i, j]
        k = rnd.randint(-25, 25)
        px[i, j] = (max(0, min(255, r + k)), max(0, min(255, g + k)), max(0, min(255, b + k)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=rnd.randint(55, 80))
    return buf.getvalue()


# ── оценка ──────────────────────────────────────────────────────────────

_LATEX = [
    (r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2"), (r"\\dfrac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2"),
    (r"\\sqrt\{([^{}]*)\}", r"√(\1)"), (r"\\cdot|\\times|·|×|\*", ""), (r"\\in", "∈"),
    (r"\\infty", "∞"), (r"\\geq?|≥", ">="), (r"\\leq?|≤", "<="), (r"\\gt", ">"), (r"\\lt", "<"),
    (r"\\text\{([^{}]*)\}", r"\1"), (r"\\mathrm\{([^{}]*)\}", r"\1"),
    (r"\\left|\\right|\\[,;:! ]|\\quad|\\qquad", ""), (r"\^\{?2\}?|²", "^2"), (r"_\{?([12])\}?", r"\1"), (r"₁", "1"), (r"₂", "2"),
]


def norm(s):
    s = s or ""
    # вступление модели («Вот текст с изображения…») — не часть решения
    s = re.sub(r"^\s*Вот[^\n]*\n", "", s)
    s = re.sub(r"\\[\[\]()]", "", s)  # \[ \] \( \)
    for a, b in _LATEX:
        s = re.sub(a, b, s)
    s = s.replace("−", "-").replace("–", "-").replace("—", "-").replace("ё", "е").replace("Ё", "Е")
    s = re.sub(r"[\\$`{}\s]", "", s)
    return s.lower()


def score(text, keys, truth):
    n = norm(text)
    hits = [k for k in keys if norm(k) in n]
    sim = difflib.SequenceMatcher(None, norm(truth), n).ratio() if truth else None
    return hits, sim


# ── запуск ──────────────────────────────────────────────────────────────

def load_real(folder):
    out = []
    for f in sorted(os.listdir(folder)):
        base, ext = os.path.splitext(f)
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
            continue
        txt = os.path.join(folder, base + ".txt")
        keys, truth = [], ""
        if os.path.exists(txt):
            with open(txt, encoding="utf-8") as fh:
                first, _, rest = fh.read().partition("\n")
            keys = [k.strip() for k in first.split(";") if k.strip()]
            truth = rest.strip()
        with open(os.path.join(folder, f), "rb") as fh:
            out.append((f, "", fh.read(), keys, truth))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="папка с настоящими фото (+ .txt с ключами)")
    ap.add_argument("--engine", choices=["deepseek", "gemini"], default="deepseek")
    ap.add_argument("--fonts", default=",".join(FONTS))
    ap.add_argument("--out", default=os.path.join("reports", "ocr_handwriting_eval"))
    args = ap.parse_args()

    from services import solution_ocr as so

    fn = so._ocr_deepseek_vision if args.engine == "deepseek" else so._ocr_gemini_vision
    need = "DEEPSEEK_API_KEY" if args.engine == "deepseek" else "GEMINI_API_KEY"
    if not os.environ.get(need):
        sys.exit(f"Нет {need} в окружении")

    if args.dir:
        cases = load_real(args.dir)
    else:
        cases = []
        for fi, font in enumerate(args.fonts.split(",")):
            for si, (task, lines, keys) in enumerate(SAMPLES):
                img = render_page(lines, font, seed=fi * 100 + si)
                cases.append((f"{os.path.splitext(font)[0]}_{si + 1}.jpg", task, img, keys, "\n".join(lines)))

    os.makedirs(args.out, exist_ok=True)
    rows = []
    for name, task, img, keys, truth in cases:
        with open(os.path.join(args.out, name), "wb") as fh:
            fh.write(img)
        b64 = so.ensure_jpeg_images([base64.b64encode(img).decode()])[0]
        t0 = time.time()
        try:
            text = fn(b64, task) or ""
        except Exception as e:  # pragma: no cover
            text = f"<error {e}>"
        dt = time.time() - t0
        hits, sim = score(text, keys, truth)
        rows.append({"file": name, "seconds": round(dt, 1), "keys_found": len(hits), "keys_total": len(keys),
                     "missed": [k for k in keys if k not in hits],
                     "similarity": None if sim is None else round(sim, 2), "text": text})
        print(f"{name:22s} {dt:5.1f}s  ключи {len(hits)}/{len(keys)}  "
              f"похожесть {'-' if sim is None else f'{sim:.2f}'}"
              + (f"  пропущено: {', '.join(rows[-1]['missed'])}" if rows[-1]["missed"] else ""))

    with open(os.path.join(args.out, f"results_{args.engine}.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    tk = sum(r["keys_total"] for r in rows)
    fk = sum(r["keys_found"] for r in rows)
    full = sum(1 for r in rows if r["keys_found"] == r["keys_total"] and r["text"])
    secs = sorted(r["seconds"] for r in rows)
    sims = [r["similarity"] for r in rows if r["similarity"] is not None]
    print("\n── итог ──")
    print(f"фото: {len(rows)}, распознаны полностью: {full}/{len(rows)}")
    print(f"ключевые фрагменты: {fk}/{tk} ({100 * fk / max(1, tk):.0f}%)")
    if sims:
        print(f"средняя похожесть на эталон: {sum(sims) / len(sims):.2f}")
    if secs:
        print(f"время: медиана {secs[len(secs) // 2]:.1f}s, максимум {secs[-1]:.1f}s")
    print(f"фото и ответы: {args.out}")


if __name__ == "__main__":
    main()
