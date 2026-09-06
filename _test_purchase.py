# -*- coding: utf-8 -*-
"""Проверка бизнес-логики покупки кредитов напрямую (без auth-обёртки)."""
import io

import app as app_module
from app import app, db
from models import User, FigureCreditTransaction
from routes.figures import _get_figure_credits, FIGURE_PACKAGES

out = io.open('_purchase_test.txt', 'w', encoding='utf-8')

with app.app_context():
    user = User.query.first()
    before = _get_figure_credits(user)
    out.write('user_id=%s before=%s\n' % (user.id, before))

    pkg = next(p for p in FIGURE_PACKAGES if p['id'] == 'p30')
    amount = int(pkg['amount'])

    user.figure_credits = before + amount
    txn = FigureCreditTransaction(user_id=user.id, amount=amount, reason='purchase', reference='p30')
    db.session.add(txn)
    db.session.commit()

    after = _get_figure_credits(user)
    out.write('after=%s (added %d)\n' % (after, amount))

    # проверить транзакцию
    last = (FigureCreditTransaction.query
            .filter_by(user_id=user.id, reason='purchase')
            .order_by(FigureCreditTransaction.created_at.desc())
            .first())
    out.write('txn amount=%s reference=%s\n' % (last.amount, last.reference))

out.close()
print('test done')
