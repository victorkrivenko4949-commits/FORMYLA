#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Шаг 1 пайплайна: спрашиваем у DeepSeek максимальный список чертежей,
необходимых для раздела «Геометрия» в разделе секретов (/secrets).

Вход:  secrets_dump.json  (берём все записи с topic == "Геометрия")
Выход: scripts/_geometry_diagrams_plan.json
        [
          {
            "secret_index":  <int>,                # 1-based индекс среди гео-секретов
            "secret_title":  <str>,                # название секрета
            "diagram_id":    "geom_<NN>_<MM>",     # уникальный id чертежа
            "title":         <str>,                # заголовок чертежа
            "brief":         <str>                 # подробное ТЗ для drawing pipeline
          },
          ...
        ]
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai.deepseek_client import DeepSeekClient  # noqa: E402

SECRETS_FILE = REPO_ROOT / "secrets_dump.json"
OUTPUT_FILE = REPO_ROOT / "scripts" / "_geometry_diagrams_plan.json"


# ─────────────────────────────────────────────────────────────────────
def load_geometry_secrets() -> list[dict]:
    data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    geo = [x for x in data if (x.get("topic") or "").strip() == "Геометрия"]
    return geo


SYSTEM_PROMPT = """Ты — старший методист по олимпиадной геометрии и автор обучающих чертежей.
Тебе предстоит составить ИСЧЕРПЫВАЮЩИЙ план чертежей (диаграмм/иллюстраций) для раздела «Геометрия»
обучающей платформы FORMYLA.

Каждый чертёж будет сгенерирован Python+matplotlib через специальный pipeline
(Claude Opus 4.7 → песочница → критик Gemini Vision). Поэтому ТЗ должно быть техническим:
- никаких рукописных рисунков, всё через matplotlib (линии, окружности, многоугольники, метки точек);
- координаты можно задавать самим (через расчёт);
- метки точек заглавными латинскими буквами;
- допускается LaTeX в подписях.

ПРАВИЛО МАКСИМУМА:
Для КАЖДОГО секрета составь МАКСИМАЛЬНОЕ разумное число чертежей (8–15 на секрет),
чтобы покрыть: главную конструкцию, ключевые теоремы/леммы, типичные конфигурации,
характерные подводные камни. НЕ скупись — нам нужен максимум.

Возвращай СТРОГО валидный JSON-массив объектов следующей формы:
[
  {
    "secret_index": <int>,                 // как передано в инпуте
    "secret_title": "<str>",               // как передано в инпуте
    "diagram_id":   "geom_<NN>_<MM>",      // NN = номер секрета (01..22), MM = порядковый № чертежа в секрете (01..15)
    "title":        "<краткий заголовок>",
    "brief":        "<полное ТЗ для drawing pipeline, 2-5 предложений>"
  },
  ...
]
ЛЮБОЙ текст вне JSON-массива ЗАПРЕЩЁН. Никаких ```json``` обёрток.
"""

USER_TEMPLATE = """Вот список геометрических секретов (раздел /secrets платформы FORMYLA).
Для КАЖДОГО составь максимум чертежей (8–15 на секрет) по правилам из system prompt.
Верни ОДИН большой JSON-массив, охватывающий ВСЕ {n} секретов.

=== Список геометрических секретов ===
{secrets_block}
"""


def build_secrets_block(geo: list[dict]) -> str:
    lines = []
    for i, s in enumerate(geo, 1):
        title = s.get("title", "").strip()
        # Берём кусок контента — достаточно для понимания темы
        content = (s.get("content") or "").strip()
        snippet = content[:800].replace("\n", " ")
        lines.append(f"[{i:02d}] {title}\n     контекст: {snippet}\n")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
def extract_json_array(text: str) -> list:
    """Аккуратно вытаскиваем верхнеуровневый JSON-массив из ответа.

    Поддерживает обрезанные ответы: пытается восстановить, отрезая
    последний неполный объект.
    """
    text = text.strip()
    # Снять обёртку ```...```
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, flags=re.DOTALL)
    if m:
        text = m.group(1).strip()
    # Найти начало массива
    i = text.find("[")
    if i < 0:
        raise ValueError("no '[' in response")
    text = text[i:]
    # 1) Прямой парсинг
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) Попробовать дочитать до последней закрывающей '}' и поставить ']'
    # отрезаем последний неполный объект
    last_obj_end = text.rfind("}")
    if last_obj_end < 0:
        raise ValueError("no '}' in response")
    candidate = text[: last_obj_end + 1]
    # убрать конечную запятую если есть
    candidate = re.sub(r",\s*$", "", candidate.rstrip())
    candidate = candidate + "]"
    return json.loads(candidate)


# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    geo = load_geometry_secrets()
    print(f"[plan] загружено геометрических секретов: {len(geo)}")
    if not geo:
        print("[plan] нет секретов с topic='Геометрия' — выхожу.")
        return 1

    # Бьём по 2 секрета за раз: 2 × ~12 чертежей ≈ ~24 объекта,
    # с запасом помещается в 8000 токенов
    BATCH = 2
    all_items: list[dict] = []
    client = DeepSeekClient()

    for batch_start in range(0, len(geo), BATCH):
        batch = geo[batch_start: batch_start + BATCH]
        # Восстанавливаем оригинальные индексы (1-based в общем списке)
        batch_with_idx = []
        for offset, s in enumerate(batch, 1):
            s2 = dict(s)
            s2["_idx"] = batch_start + offset
            batch_with_idx.append(s2)
        block_lines = []
        for s in batch_with_idx:
            title = s.get("title", "").strip()
            snippet = (s.get("content") or "")[:800].replace("\n", " ")
            block_lines.append(
                f"[{s['_idx']:02d}] {title}\n     контекст: {snippet}\n"
            )
        block = "\n".join(block_lines)

        prompt = USER_TEMPLATE.format(n=len(batch_with_idx), secrets_block=block)
        print(
            f"[plan] batch {batch_start // BATCH + 1}: "
            f"секреты {batch_with_idx[0]['_idx']}..{batch_with_idx[-1]['_idx']}"
        )

        try:
            raw = client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=8000,
            )
            items = extract_json_array(raw)
        except Exception as exc:
            print(f"[plan]   ОШИБКА в батче: {exc}")
            continue

        # Простейшая валидация
        ok_items = []
        for it in items:
            if not isinstance(it, dict):
                continue
            need = ("secret_index", "secret_title", "diagram_id", "title", "brief")
            if not all(k in it for k in need):
                continue
            if len((it.get("brief") or "").strip()) < 30:
                continue
            ok_items.append(it)
        print(f"[plan]   получено {len(items)} → валидных {len(ok_items)}")
        all_items.extend(ok_items)

        # сохраняем после каждой пачки на случай прерывания
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps(all_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Итог
    print()
    print(f"[plan] ВСЕГО запланировано чертежей: {len(all_items)}")
    # Сводка по секретам
    by_secret: dict[int, int] = {}
    for it in all_items:
        by_secret[it["secret_index"]] = by_secret.get(it["secret_index"], 0) + 1
    for idx in sorted(by_secret):
        title = next(
            (s.get("title", "") for i, s in enumerate(geo, 1) if i == idx), ""
        )
        print(f"   [{idx:02d}] {by_secret[idx]:>3} шт  —  {title}")

    print(f"\n[plan] результат: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
