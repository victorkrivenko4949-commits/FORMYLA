#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
DEEPSEEK_API_KEY=sk-53d765bfeccd4474bdcb4a7bb2a96013
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_WORKERS = 10
TARGET_FIELDS = ("statement", "answer", "solution")
MAX_RETRIES = 7
HTTP_TIMEOUT = 300

SYSTEM_PROMPT = r"""
Ты — строгий редактор LaTeX для русскоязычной базы олимпиадных задач.
Твоя единственная задача — исправлять и унифицировать LaTeX и типографику в переданных текстовых полях.

КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ:
1. Не исправляй математику, логику, ответ, доказательство и фактические ошибки, даже если они очевидны.
2. Не дописывай объяснения, не сокращай текст, не перефразируй содержательно и не удаляй повторы.
3. Не меняй числа, имена, координаты, последовательности действий и обозначения, кроме чисто LaTeX-нормализации.
4. Верни ровно те же ключи, которые пришли во входном объекте, и только их. Значения всех ключей должны быть строками.
5. Верни только валидный JSON-объект: без Markdown, без ``` и без комментариев.

СТИЛЬ LATEX:
- Встроенная математика: только \\( ... \\). Выключная математика: \\[ ... \\]. Не используй $...$ и $$...$$.
- Исправляй сломанное/лишнее JSON-экранирование LaTeX: например, текстовое \\\\(\\\\times\\\\) приводи к корректной формуле.
- Математические числа, операции, переменные, координаты и состояния сосудов оформляй как математику.
- Используй стандартные команды: \\times, \\cdot, \\le, \\ge, \\ne, \\to, \\Rightarrow, \\ldots и т. п.
- Следи за парностью \\( \\), \\[ \\], фигурных скобок и окружений.
- Ясные перечни шагов можно оформлять через \\begin{enumerate} ... \\end{enumerate}; не меняй порядок и содержание пунктов.
- Не добавляй преамбулу, document, task, problem, answer или solution: редактируй только содержимое поля.
- Сохраняй абзацы через символы новой строки.
- В обычном тексте используй корректное русское тире и «ёлочки». Не применяй команды LaTeX к обычным русским словам без необходимости.

Перед ответом молча проверь JSON и целостность LaTeX.
""".strip()

_thread_local = threading.local()


def parse_args():
    p = argparse.ArgumentParser(
        description="Параллельная нормализация LaTeX в JSONL-базе через DeepSeek V4 Pro."
    )
    p.add_argument("--input", default="paste.txt", help="Исходный JSONL-файл (по умолчанию paste.txt)")
    p.add_argument("--output", default="paste_latex_fixed.txt", help="Результат (по умолчанию paste_latex_fixed.txt)")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Число потоков (по умолчанию 10)")
    p.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL))
    p.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    p.add_argument("--apply", action="store_true", help="После успеха заменить исходник, создав резервную копию")
    p.add_argument("--force", action="store_true", help="Игнорировать checkpoint и обработать всё заново")
    return p.parse_args()


def load_api_key(folder: Path) -> str:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    key_file = folder / "deepseek_api_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8-sig").strip()
    if not key:
        raise RuntimeError(
            "Не найден DEEPSEEK_API_KEY. Задайте переменную окружения либо положите ключ "
            "одной строкой в deepseek_api_key.txt рядом со скриптом."
        )
    return key


def api_request(url: str, api_key: str, payload=None, method="GET", timeout=HTTP_TIMEOUT):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "latex-jsonl-normalizer/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def preflight(base_url: str, api_key: str, model: str):
    url = base_url.rstrip("/") + "/models"
    try:
        response = api_request(url, api_key)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Проверка API завершилась HTTP {e.code}: {body[:1000]}") from e
    ids = {item.get("id") for item in response.get("data", [])}
    if ids and model not in ids:
        raise RuntimeError(
            f"Модель {model!r} отсутствует в /models. Доступны: {', '.join(sorted(x for x in ids if x))}"
        )


def read_jsonl(path: Path):
    records = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Некорректный JSON в строке {line_no}: {e}") from e
            if not isinstance(obj, dict):
                raise RuntimeError(f"Строка {line_no}: ожидался JSON-объект.")
            records.append((line_no, obj))
    if not records:
        raise RuntimeError("Входной файл пуст.")
    return records


def canonical_hash(obj: dict) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_payload(obj: dict) -> dict:
    return {key: obj[key] for key in TARGET_FIELDS if isinstance(obj.get(key), str)}


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_model_json(content: str) -> dict:
    content = strip_code_fence(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start:end + 1])
        raise


def unescaped_dollar_count(text: str) -> int:
    count = 0
    for i, ch in enumerate(text):
        if ch == "$":
            slashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                slashes += 1
                j -= 1
            if slashes % 2 == 0:
                count += 1
    return count


def braces_balanced(text: str) -> bool:
    depth = 0
    for i, ch in enumerate(text):
        escaped = i > 0 and text[i - 1] == "\\"
        if escaped:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def latex_sanity(text: str) -> list[str]:
    errors = []
    if "```" in text:
        errors.append("обнаружена Markdown-ограда ```")
    if unescaped_dollar_count(text):
        errors.append("остались неэкранированные знаки $")
    if text.count(r"\(") != text.count(r"\)"):
        errors.append("не сбалансированы \\( и \\)")
    if text.count(r"\[") != text.count(r"\]"):
        errors.append("не сбалансированы \\[ и \\]")
    if not braces_balanced(text):
        errors.append("не сбалансированы фигурные скобки")
    begins = re.findall(r"\\begin\{([^{}]+)\}", text)
    ends = re.findall(r"\\end\{([^{}]+)\}", text)
    if begins != ends:
        errors.append("не сбалансированы или перепутаны LaTeX-окружения")
    return errors


def validate_result(original: dict, edited: dict):
    if not isinstance(edited, dict):
        raise ValueError("Ответ модели не является JSON-объектом.")
    if set(edited) != set(original):
        raise ValueError(f"Неверные ключи: получено {sorted(edited)}, ожидалось {sorted(original)}")
    for key, old in original.items():
        new = edited[key]
        if not isinstance(new, str):
            raise ValueError(f"Поле {key} не является строкой.")
        if old.strip() and not new.strip():
            raise ValueError(f"Поле {key} стало пустым.")
        old_len = max(len(old), 1)
        ratio = len(new) / old_len
        if len(old) >= 80 and not (0.60 <= ratio <= 1.75):
            raise ValueError(f"Подозрительное изменение длины {key}: {ratio:.2f}x")
        problems = latex_sanity(new)
        if problems:
            raise ValueError(f"Поле {key}: " + "; ".join(problems))


def build_request(payload: dict, model: str, repair_note: str = "") -> dict:
    user_text = (
        "Нормализуй LaTeX в следующем JSON-объекте. Верни объект с точно теми же ключами.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    if repair_note:
        user_text += "\n\nПредыдущий ответ не прошёл валидацию: " + repair_note
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "max_tokens": 16384,
        "stream": False,
    }


def call_deepseek(base_url: str, api_key: str, model: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    last_error = None
    repair_note = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = api_request(
                url, api_key, build_request(payload, model, repair_note), method="POST"
            )
            choices = response.get("choices") or []
            if not choices:
                raise ValueError(f"API не вернул choices: {str(response)[:1000]}")
            content = choices[0].get("message", {}).get("content", "")
            edited = parse_model_json(content)
            validate_result(payload, edited)
            return edited
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {e.code}: {body[:1500]}")
            if e.code in (401, 403, 404):
                raise last_error
            retry_after = e.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            repair_note = str(e)[:700]
            wait = min(60, 2 ** attempt)
        if attempt < MAX_RETRIES:
            time.sleep(wait + random.random())
    raise RuntimeError(f"Не удалось получить валидный ответ за {MAX_RETRIES} попыток: {last_error}")


def init_db(path: Path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS results ("
        "idx INTEGER PRIMARY KEY, input_hash TEXT NOT NULL, result_json TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def load_cached(conn, idx: int, input_hash: str):
    row = conn.execute(
        "SELECT result_json FROM results WHERE idx=? AND input_hash=?", (idx, input_hash)
    ).fetchone()
    return json.loads(row[0]) if row else None


def save_cached(conn, idx: int, input_hash: str, obj: dict):
    conn.execute(
        "INSERT OR REPLACE INTO results(idx,input_hash,result_json,updated_at) VALUES(?,?,?,?)",
        (
            idx,
            input_hash,
            json.dumps(obj, ensure_ascii=False),
            dt.datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()


def merge_result(original_obj: dict, edited_fields: dict) -> dict:
    result = dict(original_obj)
    for key, value in edited_fields.items():
        result[key] = value
    return result


def write_output(path: Path, records, finished: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for idx, (_, original) in enumerate(records):
            obj = merge_result(original, finished[idx])
            f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ": ")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def make_backup_and_apply(input_path: Path, output_path: Path):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = input_path.with_name(f"{input_path.stem}.backup_{stamp}{input_path.suffix}")
    shutil.copy2(input_path, backup)
    os.replace(output_path, input_path)
    return backup


def main():
    args = parse_args()
    if not (1 <= args.workers <= 50):
        raise RuntimeError("--workers должен быть от 1 до 50.")

    script_dir = Path(__file__).resolve().parent
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = script_dir / input_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = script_dir / output_path
    if input_path.resolve() == output_path.resolve():
        raise RuntimeError("Исходный и выходной файлы должны различаться. Для замены используйте --apply.")
    if not input_path.exists():
        raise RuntimeError(f"Не найден входной файл: {input_path}")

    api_key = load_api_key(script_dir)
    print(f"Проверяю API и модель {args.model}...")
    preflight(args.base_url, api_key, args.model)

    records = read_jsonl(input_path)
    checkpoint_path = script_dir / f".{input_path.stem}_latex_checkpoint.sqlite3"
    if args.force and checkpoint_path.exists():
        checkpoint_path.unlink()
    conn = init_db(checkpoint_path)

    finished = {}
    pending = []
    for idx, (line_no, obj) in enumerate(records):
        payload = extract_payload(obj)
        if not payload:
            finished[idx] = {}
            continue
        input_hash = canonical_hash(obj)
        cached = load_cached(conn, idx, input_hash)
        if cached is not None:
            try:
                validate_result(payload, cached)
                finished[idx] = cached
                continue
            except ValueError:
                pass
        pending.append((idx, line_no, input_hash, payload, obj.get("task_uid", "")))

    total = len(records)
    print(
        f"Всего объектов: {total}; уже в checkpoint/без полей: {len(finished)}; "
        f"к обработке: {len(pending)}; потоков: {args.workers}."
    )

    failures = []
    if pending:
        with cf.ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="deepseek") as pool:
            futures = {
                pool.submit(call_deepseek, args.base_url, api_key, args.model, payload):
                (idx, line_no, input_hash, payload, uid)
                for idx, line_no, input_hash, payload, uid in pending
            }
            completed_now = 0
            for future in cf.as_completed(futures):
                idx, line_no, input_hash, payload, uid = futures[future]
                try:
                    edited = future.result()
                    finished[idx] = edited
                    save_cached(conn, idx, input_hash, edited)
                    completed_now += 1
                    print(
                        f"[{len(finished)}/{total}] OK: строка {line_no}"
                        + (f", uid={uid}" if uid else ""),
                        flush=True,
                    )
                except Exception as e:
                    failures.append({"idx": idx, "line": line_no, "task_uid": uid, "error": str(e)})
                    print(f"[ОШИБКА] строка {line_no}, uid={uid}: {e}", file=sys.stderr, flush=True)

    conn.close()

    if failures:
        failure_path = script_dir / "latex_failures.json"
        failure_path.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(
            f"Не обработано объектов: {len(failures)}. Подробности: {failure_path.name}. "
            "Запустите скрипт повторно: готовые объекты возьмутся из checkpoint, ошибки повторятся."
        )

    if len(finished) != total:
        raise RuntimeError(f"Внутренняя ошибка: готово {len(finished)} из {total} объектов.")

    write_output(output_path, records, finished)
    print(f"Готово: {output_path.name}")

    if args.apply:
        backup = make_backup_and_apply(input_path, output_path)
        print(f"Исходник заменён. Резервная копия: {backup.name}")
    else:
        print("Исходный файл не изменён. После проверки можно запустить ещё раз с флагом --apply.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nОстановлено пользователем. Прогресс сохранён в checkpoint.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: {exc}", file=sys.stderr)
        sys.exit(1)
