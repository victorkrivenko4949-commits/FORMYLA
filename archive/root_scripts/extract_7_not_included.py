import json
from pathlib import Path

EXTENSIONS = {".txt", ".json", ".jsonl"}


def parse_concatenated_json(path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return []
    decoder = json.JSONDecoder()
    pos = 0
    records = []
    n = len(text)
    while pos < n:
        while pos < n and (text[pos].isspace() or text[pos] == ","):
            pos += 1
        if pos >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            return []
        records.append(obj)
        pos = end
    return records


def find_files():
    full_candidates = []
    cache_candidates = []
    for path in Path(".").iterdir():
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        records = parse_concatenated_json(path)
        if len(records) == 69 and all(isinstance(x, dict) and "task_uid" in x for x in records):
            full_candidates.append((path, records))
        if len(records) == 62 and all(isinstance(x, dict) and "idx" in x and "result_json" in x for x in records):
            cache_candidates.append((path, records))
    return full_candidates, cache_candidates


def main():
    full_candidates, cache_candidates = find_files()
    if len(full_candidates) != 1:
        print("Не удалось однозначно найти полный файл из 69 задач.")
        print("Кандидаты:", [str(x[0]) for x in full_candidates])
        print("Положите в эту папку ровно один полный файл с 69 объектами JSON.")
        return
    if len(cache_candidates) != 1:
        print("Не удалось однозначно найти кэш из 62 результатов.")
        print("Кандидаты:", [str(x[0]) for x in cache_candidates])
        print("Положите в эту папку ровно один файл кэша с 62 объектами idx/result_json.")
        return

    full_path, full_records = full_candidates[0]
    cache_path, cache_records = cache_candidates[0]
    completed = {int(x["idx"]) for x in cache_records}
    expected = set(range(69))
    missing = sorted(expected - completed)

    if len(missing) != 7:
        print(f"Ожидалось 7 пропущенных индексов, найдено {len(missing)}: {missing}")
        return

    missing_records = [full_records[i] for i in missing]
    out_path = Path("7_not_included.jsonl")
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for record in missing_records:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    report = {
        "full_file": str(full_path),
        "cache_file": str(cache_path),
        "completed_count": len(completed),
        "missing_count": len(missing),
        "missing_indices_zero_based": missing,
        "missing_task_numbers_one_based": [i + 1 for i in missing],
        "missing_task_uids": [full_records[i]["task_uid"] for i in missing],
    }
    Path("7_not_included_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Полный файл:", full_path)
    print("Кэш:", cache_path)
    print("Пропущенные индексы (с 0):", missing)
    print("Номера задач (с 1):", [i + 1 for i in missing])
    print("task_uid:")
    for record in missing_records:
        print(" -", record["task_uid"])
    print("Создан файл:", out_path)
    print("Создан отчёт: 7_not_included_report.json")


if __name__ == "__main__":
    main()
