"""
cli.py — инструмент командной строки.
Принимает JSON-файл с описанием чертежа, выдаёт SVG.
"""

import sys
import json
import argparse
from pathlib import Path

from .engine import GeometricEngine, EngineSettings


def main():
    parser = argparse.ArgumentParser(
        description="Geometric Engine — построение геометрических чертежей по JSON-описанию в SVG",
    )
    parser.add_argument("input", type=str, help="Путь к JSON-файлу с описанием чертежа")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Путь для сохранения SVG (по умолчанию stdout)")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Семя для генерации (по умолчанию 42)")
    parser.add_argument("--no-retry", action="store_true",
                        help="Отключить повторные попытки при провале проверок")

    args = parser.parse_args()

    # Чтение JSON
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            description = json.load(f)
    except FileNotFoundError:
        print(f"ОШИБКА: файл '{args.input}' не найден", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ОШИБКА: невалидный JSON в '{args.input}': {e}", file=sys.stderr)
        sys.exit(1)

    # Валидация
    engine = GeometricEngine()
    errors = engine.validate_description(description)
    if errors:
        print("ОШИБКИ ВАЛИДАЦИИ:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # Построение
    if args.no_retry:
        svg, ctx = engine.build(description, args.seed)
        attempts = 1
        violations = []
    else:
        svg, ctx, attempts, violations = engine.build_with_retry(description, args.seed)

    if violations:
        print(f"ОТКАЗ после {attempts} попыток. Нарушения:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        sys.exit(1)

    # Вывод
    if args.output:
        Path(args.output).write_text(svg, encoding="utf-8")
        print(f"SVG сохранён в '{args.output}' ({len(svg)} байт, {attempts} попыток)", file=sys.stderr)
    else:
        print(svg)

    sys.exit(0)


if __name__ == "__main__":
    main()
