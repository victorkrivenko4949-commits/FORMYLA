# -*- coding: utf-8 -*-
"""Seed/upsert script for OlympiadPrep calendar (Russian math olympiads).

Usage: python -m scripts.seed_olympiads
Idempotent: matches existing rows by slug and updates them, otherwise inserts.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from models import db, OlympiadPrep

OLYMPIADS_JSON = r"""
[
{"slug": "fiztekh", "name": "Олимпиада «Физтех»", "short_name": "Физтех", "official_url": "https://olymp.mipt.ru", "color_hex": "#3b82f6", "grades": [9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Октябрь 2025 — январь 2026"}, {"name": "Заключительный этап", "date_range": "Февраль — март 2026"}]},
{"slug": "kurchatov", "name": "Олимпиада «Курчатов»", "short_name": "Курчатов", "official_url": "https://olimp.kurchatovedu.ru", "color_hex": "#f59e0b", "grades": [6, 7, 8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Уточняется"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]},
{"slug": "shag-v-budushchee", "name": "Шаг в будущее", "short_name": "Шаг в будущее", "grades": [8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "2025"}, {"name": "Заключ. этап — 11 кл.", "date_range": "7 марта 2026"}, {"name": "Заключ. этап — 8–10 кл.", "date_range": "Весна 2026"}]},
{"slug": "otkrytaya", "name": "Открытая олимпиада школьников", "short_name": "Открытая", "grades": [8, 9, 10, 11], "stages": [{"name": "1-й отборочный онлайн-этап", "date_range": "3 дек 2025 — 19 янв 2026"}, {"name": "Заключительный этап", "date_range": "Уточняется"}]},
{"slug": "vsesibirskaya", "name": "Всесибирская открытая олимпиада", "short_name": "Всесибирская", "grades": [7, 8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Уточняется"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]},
{"slug": "itmo", "name": "Олимпиада ИТМО", "short_name": "ИТМО", "grades": [9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Осень 2025 — зима 2026"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]},
{"slug": "nadezhda-energetiki", "name": "Олимпиада «Надежда энергетики»", "short_name": "Надежда энергетики", "grades": [8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Уточняется"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]},
{"slug": "rosatom", "name": "Олимпиада «Росатом»", "short_name": "Росатом", "grades": [8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Уточняется"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]},
{"slug": "inzhenernaya", "name": "Инженерная олимпиада школьников", "short_name": "Инженерная", "grades": [8, 9, 10, 11], "stages": [{"name": "Отборочный этап", "date_range": "Уточняется"}, {"name": "Заключительный этап", "date_range": "Весна 2026"}]}
]
"""

OLYMPIADS = json.loads(OLYMPIADS_JSON)



def upsert(data):
  row = OlympiadPrep.query.filter_by(slug=data["slug"]).first()
  grades_value = json.dumps(data.get("grades", []), ensure_ascii=False)
  stages_value = json.dumps(data.get("stages", []), ensure_ascii=False)
  payload = {
    "name": data.get("name"),
    "short_name": data.get("short_name"),
    "official_url": data.get("official_url"),
    "color_hex": data.get("color_hex"),
    "grades": grades_value,
    "stages": stages_value,
  }
  if row is not None:
    for key, value in payload.items():
      if hasattr(row, key):
        setattr(row, key, value)
    return "updated"
  fields = {k: v for k, v in payload.items() if hasattr(OlympiadPrep, k)}
  fields["slug"] = data["slug"]
  db.session.add(OlympiadPrep(**fields))
  return "inserted"


def main():
  with app.app_context():
    db.create_all()
    inserted = 0
    updated = 0
    for item in OLYMPIADS:
      result = upsert(item)
      if result == "inserted":
        inserted += 1
      else:
        updated += 1
    db.session.commit()
    print("Done. Inserted:", inserted, "Updated:", updated, "Total:", len(OLYMPIADS))


if __name__ == "__main__":
  main()
