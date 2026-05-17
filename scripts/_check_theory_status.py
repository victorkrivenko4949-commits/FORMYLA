# -*- coding: utf-8 -*-
"""Показать состояние теории по всем 89 методам."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import app
from models import db
from models_olympiad import TheoryBlock


def main():
    with app.app_context():
        total = TheoryBlock.query.count()
        with_def = TheoryBlock.query.filter(
            TheoryBlock.definition_md.isnot(None),
            TheoryBlock.definition_md != ''
        ).count()
        without = total - with_def

        print('Всего методов в БД :', total)
        print('С теорией (def_md) :', with_def)
        print('Без теории         :', without)
        print()

        if without:
            print('Методы БЕЗ теории:')
            rows = TheoryBlock.query.order_by(TheoryBlock.method_code).all()
            for r in rows:
                if not r.definition_md:
                    print(f'  {r.method_code:<8}  {r.method_name or ""}')


if __name__ == '__main__':
    main()
