#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Шаг 3 пайплайна: вшиваем сгенерированные PNG-чертежи в content
геометрических секретов в secrets_dump.json.

Алгоритм:
1. Читаем scripts/_geometry_diagrams_done.json — список успешных чертежей.
2. Группируем по secret_index → список чертежей этого секрета.
3. Для каждого геометрического секрета:
   - убираем старую секцию "## 📐 Чертежи" (если осталась от прошлых запусков);
   - добавляем новую секцию со всеми чертежами секрета (markdown-формат).
4. Сохраняем secrets_dump.json + бэкап.
5. ОПЦИОНАЛЬНО: загружаем в локальную БД через seed_secrets_from_json(force=True).

Запуск:
    python scripts/link_geometry_diagrams_to_secrets.py
    python scripts/link_geometry_diagrams_to_secrets.py --no-db    # только JSON, без загрузки в БД
    python scripts/link_geometry_diagrams_to_secrets.py --reload   # принудительно перезалить БД
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SECRETS_FILE = REPO_ROOT / "secrets_dump.json"
DONE_FILE = REPO_ROOT / "scripts" / "_geometry_diagrams_done.json"
BACKUP_FILE = REPO_ROOT / "secrets_dump.backup_pre_diagrams.json"
PNG_DIR = REPO_ROOT / "static" / "generated" / "secrets"

# Маркеры начала/конца блока чертежей внутри content (HTML-комменты в md
# не рендерятся marked.js, поэтому используем их как разделители).
MARK_START = "<!-- DIAGRAMS_BLOCK_START -->"
MARK_END = "<!-- DIAGRAMS_BLOCK_END -->"


# ─────────────────────────────────────────────────────────────────────
def strip_old_block(content: str) -> str:
    """Удалить ранее вставленный блок чертежей, если он есть."""
    pattern = re.compile(
        re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\s*",
        flags=re.DOTALL,
    )
    return pattern.sub("", content).rstrip()


def build_diagrams_md(diagrams: list[dict]) -> str:
    """Собрать markdown-блок «Чертежи» для одного секрета.

    Каждый чертёж — заголовок ### + картинка.
    URL'ы — абсолютные от корня сайта (/static/...).
    """
    lines: list[str] = []
    lines.append(MARK_START)
    lines.append("")
    lines.append("## 📐 Чертежи и иллюстрации")
    lines.append("")
    lines.append(
        f"*Автоматически сгенерировано через FORMYLA Drawing Pipeline "
        f"(Claude Opus 4.7 + Gemini 3.1 Pro Vision). Всего: {len(diagrams)}.*"
    )
    lines.append("")
    # Стабильная сортировка по diagram_id
    for d in sorted(diagrams, key=lambda x: x.get("diagram_id", "")):
        title = (d.get("title") or "").strip() or d["diagram_id"]
        url = "/" + d["png"].lstrip("/")  # /static/generated/secrets/geom_NN_MM.png
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"![{title}]({url})")
        lines.append("")
    lines.append(MARK_END)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-db", action="store_true",
                    help="Не перезагружать локальную БД (только JSON).")
    ap.add_argument("--reload", action="store_true",
                    help="Принудительно перезалить БД (seed_secrets force=True).")
    args = ap.parse_args()

    if not DONE_FILE.exists():
        print(f"[link] нет файла {DONE_FILE} — запустите gen_geometry_diagrams.py")
        return 1

    done = json.loads(DONE_FILE.read_text(encoding="utf-8"))
    ok_diagrams = [r for r in done if r.get("ok") and r.get("png")]
    print(f"[link] успешных чертежей: {len(ok_diagrams)} / всего записей {len(done)}")

    # 0) Проверим, что PNG-файлы действительно существуют
    missing = [r for r in ok_diagrams if not (REPO_ROOT / r["png"]).exists()]
    if missing:
        print(f"[link] !!! {len(missing)} записей помечены OK, но PNG нет на диске")
        for r in missing[:5]:
            print(f"    {r['diagram_id']}: {r['png']}")
        ok_diagrams = [r for r in ok_diagrams if (REPO_ROOT / r["png"]).exists()]
        print(f"[link] фильтруем — остаётся {len(ok_diagrams)}")

    # 1) Группировка по secret_index
    by_secret: dict[int, list[dict]] = {}
    for r in ok_diagrams:
        idx = r.get("secret_index")
        if not isinstance(idx, int):
            continue
        by_secret.setdefault(idx, []).append(r)
    print(f"[link] секретов с чертежами: {len(by_secret)}")

    # 2) Загружаем secrets_dump.json и бэкапим
    secrets = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
    BACKUP_FILE.write_text(
        json.dumps(secrets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[link] backup: {BACKUP_FILE}")

    # 3) Идём по геометрическим секретам в том же порядке,
    # что использовал gen_geometry_diagrams_plan.py (фильтр topic == 'Геометрия').
    geo_positions = [
        i for i, s in enumerate(secrets)
        if (s.get("topic") or "").strip() == "Геометрия"
    ]
    print(f"[link] геом. секретов в dump'е: {len(geo_positions)}")

    touched = 0
    for geo_idx_1based, dump_pos in enumerate(geo_positions, 1):
        diagrams = by_secret.get(geo_idx_1based) or []
        if not diagrams:
            continue
        s = secrets[dump_pos]
        old_content = s.get("content") or ""
        cleaned = strip_old_block(old_content)
        new_block = build_diagrams_md(diagrams)
        new_content = cleaned.rstrip() + "\n\n" + new_block + "\n"
        s["content"] = new_content
        touched += 1
        print(
            f"   [{geo_idx_1based:02d}] {s.get('title','')[:50]}  "
            f"→  +{len(diagrams)} чертежей  ({len(new_content)} ch)"
        )

    # 4) Сохраняем
    SECRETS_FILE.write_text(
        json.dumps(secrets, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[link] сохранено: {SECRETS_FILE}  (обновлено секретов: {touched})")

    # 5) Опционально: загружаем в БД
    if not args.no_db:
        try:
            # Подтянуть .env
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except Exception:
                pass
            from app import app, db  # noqa: F401
            from utils.seed_secrets_utils import seed_secrets_from_json
            with app.app_context():
                res = seed_secrets_from_json(
                    json_file=str(SECRETS_FILE),
                    force=True if args.reload else False,
                )
                print(f"[link] seed_secrets_from_json → {res}")
        except Exception as exc:
            print(f"[link] !! загрузка в БД пропущена: {exc}")
            print("[link]    запустите вручную если нужно:")
            print("[link]    python -c \"from app import app, db; "
                  "from utils.seed_secrets_utils import seed_secrets_from_json; "
                  "import sys\\nwith app.app_context(): "
                  "print(seed_secrets_from_json(force=True))\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())
