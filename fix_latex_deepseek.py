#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# ============================================================
# НАСТРОЙКИ
# ============================================================

# Вставь настоящий ключ DeepSeek между кавычками.
DEEPSEEK_API_KEY = "sk-53d765bfeccd4474bdcb4a7bb2a96013"

# Точный рабочий адрес из твоего другого скрипта.
API_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = "deepseek-v4-pro"

# Файлы должны лежать рядом со скриптом.
INPUT_FILE = "6767.txt"
OUTPUT_FILE = "6767_latex_fixed"

# Одновременные запросы.
WORKERS = 3

# 0 — обработать весь файл.
# Для теста можно поставить, например, 5.
LIMIT = 0

MAX_TOKENS = 32000
HTTP_TIMEOUT = 900
MAX_RETRIES = 7

TARGET_FIELDS = (
    "statement",
    "answer",
    "solution",
)

PROMPT_VERSION = "latex_normalizer_v3"


# ============================================================
# ПРОМПТ
# ============================================================

SYSTEM_PROMPT = r"""
Ты — строгий редактор LaTeX для русскоязычной базы олимпиадных задач.

Твоя единственная задача — исправить и унифицировать LaTeX и типографику
в переданных текстовых полях.

КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ:

1. Не исправляй математику, логику, ответ, доказательство и фактические
   ошибки, даже если они очевидны.

2. Не дописывай новые объяснения, не сокращай текст, не удаляй повторы
   и не перефразируй содержание.

3. Не меняй числа, имена, координаты, последовательности действий,
   математические утверждения и обозначения, кроме чистой нормализации LaTeX.

4. Верни ровно те же ключи, которые находились во входном JSON-объекте.

5. Значение каждого возвращённого ключа должно быть строкой.

6. Верни только один валидный JSON-объект:
   без Markdown, без тройных обратных кавычек и без комментариев.

ПРАВИЛА LATEX:

1. Встроенные формулы оформляй только так:

   \( ... \)

2. Выключные формулы оформляй только так:

   \[ ... \]

3. Не используй $...$ и $$...$$.

4. Исправляй лишнее или сломанное экранирование обратных слешей.

5. Математические переменные, числа в вычислениях, операции, координаты,
   состояния сосудов, множества, степени, неравенства и формулы оформляй
   как математику.

6. Используй стандартные команды:

   \times
   \cdot
   \le
   \ge
   \ne
   \to
   \Rightarrow
   \ldots
   \frac
   \sqrt

7. Следи за балансом:

   \( и \)
   \[ и \]
   { и }
   \begin и \end

8. Явные нумерованные перечни разрешается оформлять через:

   \begin{enumerate}
   \item ...
   \end{enumerate}

   При этом нельзя менять порядок и содержание пунктов.

9. Явные ненумерованные перечни разрешается оформлять через:

   \begin{itemize}
   \item ...
   \end{itemize}

10. Не добавляй:

   \documentclass
   \begin{document}
   \end{document}
   \begin{task}
   \begin{problem}
   \begin{solution}
   \begin{answer}

11. Редактируй только содержимое переданных полей.

12. Сохраняй смысловые абзацы и переносы строк.

13. В русском тексте используй «ёлочки» и корректное тире.

14. Не превращай весь обычный текст в LaTeX-команды.

Перед выдачей результата молча проверь:

- валидность JSON;
- наличие всех исходных ключей;
- отсутствие дополнительных ключей;
- баланс LaTeX;
- сохранность исходного содержания.
""".strip()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def validate_api_key():
    key = DEEPSEEK_API_KEY.strip()

    invalid_values = {
        "",
        "СЮДА_ВСТАВЬ_КЛЮЧ",
        "потом вставлю",
        "YOUR_API_KEY",
        "sk-вставь_сюда_свой_ключ",
    }

    if key in invalid_values:
        raise RuntimeError(
            "Вставь настоящий API-ключ в DEEPSEEK_API_KEY "
            "в начале скрипта."
        )

    if "\n" in key or "\r" in key:
        raise RuntimeError(
            "API-ключ должен находиться на одной строке."
        )

    return key


def read_jsonl(path: Path):
    """
    Поддерживает:
    1. JSONL — один объект на строке.
    2. Многострочные JSON-объекты.
    3. Несколько JSON-объектов подряд.
    4. JSON-массив объектов.
    5. Файл, случайно обёрнутый в ```json ... ```.
    """

    text = path.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not text:
        raise RuntimeError("Входной файл пуст.")

    # Удаляем Markdown-ограду, если файл был скопирован из чата.
    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json|jsonl|txt)?\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
            count=1,
        )

        text = text.strip()

    # Сначала пытаемся прочитать весь файл как обычный JSON.
    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return [(1, parsed)]

        if isinstance(parsed, list):
            records = []

            for index, obj in enumerate(parsed, 1):
                if not isinstance(obj, dict):
                    raise RuntimeError(
                        f"Элемент JSON-массива №{index} "
                        "не является объектом."
                    )

                records.append((index, obj))

            if not records:
                raise RuntimeError(
                    "JSON-массив во входном файле пуст."
                )

            return records

    except json.JSONDecodeError:
        pass

    # Если весь файл не является одним JSON-документом,
    # последовательно извлекаем объекты.
    decoder = json.JSONDecoder()
    records = []
    position = 0
    text_length = len(text)

    while position < text_length:
        # Пропускаем пробелы и переносы строк.
        while (
            position < text_length
            and text[position].isspace()
        ):
            position += 1

        # Дополнительно разрешаем запятые между объектами.
        if (
            position < text_length
            and text[position] == ","
        ):
            position += 1
            continue

        if position >= text_length:
            break

        line_number = (
            text.count("\n", 0, position) + 1
        )

        try:
            obj, end_position = decoder.raw_decode(
                text,
                position,
            )

        except json.JSONDecodeError as error:
            fragment = text[
                position:position + 250
            ].replace("\n", "\\n")

            raise RuntimeError(
                f"Не удалось разобрать JSON около "
                f"строки {line_number}.\n"
                f"Ошибка: {error}\n"
                f"Начало проблемного фрагмента:\n"
                f"{fragment}"
            ) from error

        if isinstance(obj, list):
            for nested_index, nested_obj in enumerate(
                obj,
                1,
            ):
                if not isinstance(nested_obj, dict):
                    raise RuntimeError(
                        f"Строка {line_number}: "
                        f"элемент массива №{nested_index} "
                        "не является JSON-объектом."
                    )

                records.append(
                    (line_number, nested_obj)
                )

        elif isinstance(obj, dict):
            records.append(
                (line_number, obj)
            )

        else:
            raise RuntimeError(
                f"Строка {line_number}: ожидался "
                "JSON-объект или массив объектов."
            )

        position = end_position

    if not records:
        raise RuntimeError(
            "Во входном файле не найдено JSON-объектов."
        )

    return records


def extract_payload(obj: dict):
    payload = {}

    for field in TARGET_FIELDS:
        value = obj.get(field)

        if isinstance(value, str):
            payload[field] = value

    return payload


def canonical_hash(obj: dict):
    source = {
        "prompt_version": PROMPT_VERSION,
        "object": obj,
    }

    serialized = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def strip_code_fence(text: str):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    return text.strip()


def parse_model_json(content: str):
    content = strip_code_fence(content)

    try:
        return json.loads(content)

    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")

        if start >= 0 and end > start:
            return json.loads(content[start:end + 1])

        raise


def is_escaped(text: str, position: int):
    slash_count = 0
    index = position - 1

    while index >= 0 and text[index] == "\\":
        slash_count += 1
        index -= 1

    return slash_count % 2 == 1


def count_unescaped_dollars(text: str):
    count = 0

    for position, char in enumerate(text):
        if char == "$" and not is_escaped(text, position):
            count += 1

    return count


def braces_balanced(text: str):
    depth = 0

    for position, char in enumerate(text):
        if is_escaped(text, position):
            continue

        if char == "{":
            depth += 1

        elif char == "}":
            depth -= 1

            if depth < 0:
                return False

    return depth == 0


def environments_balanced(text: str):
    pattern = re.compile(
        r"\\(begin|end)\{([^{}]+)\}"
    )

    stack = []

    for match in pattern.finditer(text):
        action = match.group(1)
        environment = match.group(2)

        if action == "begin":
            stack.append(environment)

        else:
            if not stack:
                return False

            if stack[-1] != environment:
                return False

            stack.pop()

    return not stack


def latex_sanity(text: str):
    errors = []

    if "```" in text:
        errors.append("обнаружена Markdown-ограда ```")

    if count_unescaped_dollars(text):
        errors.append("остались неэкранированные знаки $")

    if text.count(r"\(") != text.count(r"\)"):
        errors.append("не сбалансированы \\( и \\)")

    if text.count(r"\[") != text.count(r"\]"):
        errors.append("не сбалансированы \\[ и \\]")

    if not braces_balanced(text):
        errors.append("не сбалансированы фигурные скобки")

    if not environments_balanced(text):
        errors.append("не сбалансированы LaTeX-окружения")

    return errors


def validate_result(original: dict, edited: dict):
    if not isinstance(edited, dict):
        raise ValueError(
            "Ответ модели не является JSON-объектом."
        )

    if set(edited.keys()) != set(original.keys()):
        raise ValueError(
            "Модель изменила набор ключей. "
            f"Получено: {sorted(edited.keys())}; "
            f"ожидалось: {sorted(original.keys())}"
        )

    for field, old_text in original.items():
        new_text = edited[field]

        if not isinstance(new_text, str):
            raise ValueError(
                f"Поле {field} не является строкой."
            )

        if old_text.strip() and not new_text.strip():
            raise ValueError(
                f"Поле {field} стало пустым."
            )

        old_length = max(len(old_text), 1)
        length_ratio = len(new_text) / old_length

        if len(old_text) >= 80:
            if not 0.55 <= length_ratio <= 1.85:
                raise ValueError(
                    f"Подозрительное изменение длины поля {field}: "
                    f"{length_ratio:.2f}x"
                )

        problems = latex_sanity(new_text)

        if problems:
            raise ValueError(
                f"Поле {field}: " + "; ".join(problems)
            )


# ============================================================
# DEEPSEEK API
# ============================================================

def build_request(payload: dict, repair_note: str = ""):
    user_message = (
        "Нормализуй LaTeX в следующем JSON-объекте. "
        "Верни JSON-объект с точно такими же ключами.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    if repair_note:
        user_message += (
            "\n\nПредыдущий ответ не прошёл автоматическую проверку. "
            "Исправь только указанную техническую ошибку:\n"
            + repair_note
        )

    return {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
        "temperature": 0.0,
        "response_format": {
            "type": "json_object",
        },
        "max_tokens": MAX_TOKENS,
        "stream": False,
    }


def api_request(api_key: str, payload: dict):
    encoded_payload = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=encoded_payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": "latex-jsonl-normalizer/3.0",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT,
    ) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def call_deepseek(api_key: str, payload: dict):
    last_error = None
    repair_note = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request_payload = build_request(
                payload,
                repair_note,
            )

            response = api_request(
                api_key,
                request_payload,
            )

            choices = response.get("choices") or []

            if not choices:
                raise ValueError(
                    "API не вернул choices: "
                    + str(response)[:1000]
                )

            message = choices[0].get("message") or {}
            content = message.get("content") or ""

            if not content:
                raise ValueError(
                    "API вернул пустой message.content."
                )

            edited = parse_model_json(content)
            validate_result(payload, edited)

            return edited

        except urllib.error.HTTPError as error:
            body = error.read().decode(
                "utf-8",
                errors="replace",
            )

            last_error = RuntimeError(
                f"HTTP {error.code}: {body[:2000]}"
            )

            if error.code in (401, 403, 404):
                raise last_error

            retry_after = error.headers.get("Retry-After")

            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    wait_seconds = min(60, 2 ** attempt)
            else:
                wait_seconds = min(60, 2 ** attempt)

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as error:
            last_error = error
            repair_note = str(error)[:1000]
            wait_seconds = min(60, 2 ** attempt)

        if attempt < MAX_RETRIES:
            time.sleep(
                wait_seconds + random.random()
            )

    raise RuntimeError(
        f"Не удалось получить валидный результат "
        f"за {MAX_RETRIES} попыток: {last_error}"
    )


# ============================================================
# CHECKPOINT
# ============================================================

def initialize_checkpoint(path: Path):
    connection = sqlite3.connect(path)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            idx INTEGER PRIMARY KEY,
            input_hash TEXT NOT NULL,
            result_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    connection.commit()
    return connection


def load_cached_result(
    connection,
    index: int,
    input_hash: str,
):
    row = connection.execute(
        """
        SELECT result_json
        FROM results
        WHERE idx = ? AND input_hash = ?
        """,
        (index, input_hash),
    ).fetchone()

    if not row:
        return None

    return json.loads(row[0])


def save_cached_result(
    connection,
    index: int,
    input_hash: str,
    result: dict,
):
    connection.execute(
        """
        INSERT OR REPLACE INTO results (
            idx,
            input_hash,
            result_json,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            index,
            input_hash,
            json.dumps(
                result,
                ensure_ascii=False,
            ),
            dt.datetime.now().isoformat(
                timespec="seconds"
            ),
        ),
    )

    connection.commit()


# ============================================================
# СОХРАНЕНИЕ РЕЗУЛЬТАТА
# ============================================================

def merge_result(
    original_object: dict,
    edited_fields: dict,
):
    result = dict(original_object)

    for field, value in edited_fields.items():
        result[field] = value

    return result


def write_output(
    output_path: Path,
    records,
    finished: dict,
):
    temporary_path = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        for index, (_, original_object) in enumerate(records):
            final_object = merge_result(
                original_object,
                finished[index],
            )

            file.write(
                json.dumps(
                    final_object,
                    ensure_ascii=False,
                    separators=(",", ": "),
                )
                + "\n"
            )

        file.flush()
        os.fsync(file.fileno())

    os.replace(
        temporary_path,
        output_path,
    )


# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================

def main():
    script_directory = Path(__file__).resolve().parent

    input_path = script_directory / INPUT_FILE
    output_path = script_directory / OUTPUT_FILE

    checkpoint_path = (
        script_directory
        / f".{Path(INPUT_FILE).stem}_latex_checkpoint.sqlite3"
    )

    failure_path = (
        script_directory
        / "latex_failures.json"
    )

    if not input_path.exists():
        raise RuntimeError(
            f"Не найден входной файл:\n{input_path}"
        )

    if input_path.resolve() == output_path.resolve():
        raise RuntimeError(
            "INPUT_FILE и OUTPUT_FILE не должны совпадать."
        )

    api_key = validate_api_key()

    print("=" * 60)
    print("DeepSeek LaTeX Normalizer")
    print(f"Модель: {MODEL_NAME}")
    print(f"API: {API_URL}")
    print(f"Потоков: {WORKERS}")
    print(f"Входной файл: {input_path.name}")
    print(f"Выходной файл: {output_path.name}")
    print("=" * 60)

    records = read_jsonl(input_path)

    if LIMIT > 0:
        records = records[:LIMIT]

    total = len(records)

    connection = initialize_checkpoint(
        checkpoint_path
    )

    finished = {}
    pending = []

    for index, (line_number, obj) in enumerate(records):
        payload = extract_payload(obj)

        if not payload:
            finished[index] = {}
            continue

        input_hash = canonical_hash(obj)

        cached = load_cached_result(
            connection,
            index,
            input_hash,
        )

        if cached is not None:
            try:
                validate_result(
                    payload,
                    cached,
                )

                finished[index] = cached
                continue

            except ValueError:
                pass

        pending.append(
            (
                index,
                line_number,
                input_hash,
                payload,
                obj.get("task_uid", ""),
            )
        )

    print(
        f"Всего объектов: {total}; "
        f"готово из checkpoint: {len(finished)}; "
        f"нужно обработать: {len(pending)}."
    )

    failures = []

    if pending:
        with cf.ThreadPoolExecutor(
            max_workers=WORKERS,
            thread_name_prefix="deepseek",
        ) as executor:

            futures = {}

            for (
                index,
                line_number,
                input_hash,
                payload,
                task_uid,
            ) in pending:

                future = executor.submit(
                    call_deepseek,
                    api_key,
                    payload,
                )

                futures[future] = (
                    index,
                    line_number,
                    input_hash,
                    payload,
                    task_uid,
                )

            for future in cf.as_completed(futures):
                (
                    index,
                    line_number,
                    input_hash,
                    payload,
                    task_uid,
                ) = futures[future]

                try:
                    edited = future.result()

                    finished[index] = edited

                    save_cached_result(
                        connection,
                        index,
                        input_hash,
                        edited,
                    )

                    print(
                        f"[{len(finished)}/{total}] OK: "
                        f"строка {line_number}"
                        + (
                            f", uid={task_uid}"
                            if task_uid
                            else ""
                        ),
                        flush=True,
                    )

                except Exception as error:
                    failure = {
                        "idx": index,
                        "line": line_number,
                        "task_uid": task_uid,
                        "error": str(error),
                    }

                    failures.append(failure)

                    print(
                        f"[ОШИБКА] строка {line_number}, "
                        f"uid={task_uid}: {error}",
                        file=sys.stderr,
                        flush=True,
                    )

    connection.close()

    if failures:
        failure_path.write_text(
            json.dumps(
                failures,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        raise RuntimeError(
            f"Не обработано объектов: {len(failures)}.\n"
            f"Ошибки записаны в {failure_path.name}.\n"
            "Запусти скрипт повторно: успешно обработанные "
            "объекты загрузятся из checkpoint."
        )

    if len(finished) != total:
        raise RuntimeError(
            f"Внутренняя ошибка: готово "
            f"{len(finished)} из {total} объектов."
        )

    write_output(
        output_path,
        records,
        finished,
    )

    print("=" * 60)
    print("ГОТОВО")
    print(f"Результат: {output_path}")
    print(f"Checkpoint: {checkpoint_path}")
    print("Исходный файл не изменён.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\nОстановлено пользователем. "
            "Уже обработанные результаты сохранены.",
            file=sys.stderr,
        )

        sys.exit(130)

    except Exception as error:
        print(
            f"\nКРИТИЧЕСКАЯ ОШИБКА:\n{error}",
            file=sys.stderr,
        )

        sys.exit(1)