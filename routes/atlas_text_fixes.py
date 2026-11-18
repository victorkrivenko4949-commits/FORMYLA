# -*- coding: utf-8 -*-
"""ATLAS_TEXT_FIXES_V1 — точечные текстовые правки атласа методов на лету.

Атлас (static/methods/index.html, ~4 МБ) отдаётся роутом
/olympiads/methods/atlas.html через send_from_directory. Править такой файл
в репозитории неудобно, поэтому исправления из lavrik-bugs применяются
after_request-хуком: ответ материализуется, к HTML применяются замены из
FIXES, результат кэшируется в памяти (ключ — размер файла + mtime).

Каждая правка: (issue, pattern, replacement). pattern — регулярное выражение,
устойчивое к пунктуации, т.к. исходная формулировка известна по пересказу.
Если правка не нашла совпадений — предупреждение в лог, страница не ломается.

Подключение: routes/__init__.py → _install() → install_atlas_text_fixes(app).
Отключить: ATLAS_TEXT_FIXES=0.
"""
from __future__ import annotations

import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

ATLAS_PATH = "/olympiads/methods/atlas.html"

# lavrik-bugs #11 (F3, «Описанный четырёхугольник»): в атласе утверждалось,
# что равенство сумм противоположных сторон — лишь необходимое условие.
# Это неверно: для выпуклого четырёхугольника верна обратная теорема Пито
# (Штейнер, 1846) — условие необходимое и достаточное.
FIXES = [
    (
        11,
        re.compile(
            r"Обратное\s+в\s+общем\s+случае\s+неверно[^.<]{0,120}?"
            r"необходимое,?\s+но\s+не\s+достаточное\s+условие",
            re.S,
        ),
        "Верно и обратное (теорема Штейнера): если у выпуклого четырёхугольника "
        "AB+CD=BC+AD, в него можно вписать окружность. Равенство сумм "
        "противоположных сторон — необходимое и достаточное условие; "
        "выпуклость существенна",
    ),
]

_cache: dict = {"key": None, "body": None}
_lock = threading.Lock()


def apply_fixes(html: str) -> str:
    for issue, pattern, repl in FIXES:
        html, n = pattern.subn(repl, html)
        if n == 0:
            logger.warning("[atlas_text_fixes] lavrik #%s: pattern not found, skipped", issue)
        else:
            logger.info("[atlas_text_fixes] lavrik #%s: %d replacement(s)", issue, n)
    return html


def install_atlas_text_fixes(app) -> None:
    if os.environ.get("ATLAS_TEXT_FIXES", "1") == "0":
        return
    if getattr(app, "_atlas_text_fixes_installed", False):
        return
    app._atlas_text_fixes_installed = True

    @app.after_request
    def _atlas_text_fixes(resp):
        try:
            from flask import request
            if (request.path or "") != ATLAS_PATH or resp.status_code != 200:
                return resp
            ct = (resp.content_type or "").lower()
            if "text/html" not in ct:
                return resp
            # send_from_directory отдаёт файл потоком — читаем его сами по пути,
            # чтобы не тянуть 4 МБ через итератор ответа при каждом запросе.
            path = os.path.join(app.static_folder, "methods", "index.html")
            st = os.stat(path)
            key = (st.st_size, int(st.st_mtime))
            with _lock:
                if _cache["key"] != key:
                    with open(path, "r", encoding="utf-8") as f:
                        _cache["body"] = apply_fixes(f.read()).encode("utf-8")
                    _cache["key"] = key
                body = _cache["body"]
            if resp.direct_passthrough:
                resp.direct_passthrough = False
            resp.set_data(body)
            resp.headers["Content-Length"] = str(len(body))
            resp.headers.pop("ETag", None)
            resp.headers.pop("Last-Modified", None)
        except Exception as e:  # noqa: BLE001
            logger.warning("[atlas_text_fixes] skipped: %r", e)
        return resp

    logger.info("[BP] atlas_text_fixes installed (%s)", ATLAS_PATH)
    print("[BP] atlas_text_fixes installed (%s)" % ATLAS_PATH)
