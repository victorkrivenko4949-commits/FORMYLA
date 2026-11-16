"""Read-only payment ledger for admin statistics (amounts in rubles, dates in UTC).

Provider orders take precedence over analytics and subscription snapshots. Resolve
both order and provider IDs before deduplication, then apply date filters: a late
analytics event must not move an old purchase into a new reporting period.
"""
from sqlalchemy import inspect


def ledger_sql():
    from models import db

    inspector = inspect(db.engine)
    pg = db.engine.dialect.name == 'postgresql'
    tables = set(inspector.get_table_names())
    columns = {t: {c['name'] for c in inspector.get_columns(t)} for t in
               tables & {'orders', 'yookassa_payments', 'subscriptions',
                         'analytics_events', 'funnel_events'}}

    def col(table, name, default='NULL'):
        return name if name in columns.get(table, ()) else default

    mappings = []
    if 'yookassa_payments' in tables:
        mappings.append("SELECT order_id, payment_id FROM yookassa_payments")
    if 'orders' in tables:
        mappings.append("SELECT id AS order_id, yookassa_payment_id AS payment_id FROM orders")
    mapping = ' UNION ALL '.join(mappings) or 'SELECT NULL AS order_id, NULL AS payment_id WHERE 1=0'
    parts = []

    def add(table, pid, oid, uid, beneficiary, plan, amount, when, confirmed,
            priority, where='1=1', test='FALSE'):
        if not pg:
            when = f"replace(CAST({when} AS TEXT), 'T', ' ')"
        parts.append(f"""SELECT CAST({pid} AS TEXT) AS payment_id,
            CAST({oid} AS TEXT) AS order_id, {uid} AS user_id,
            {beneficiary} AS beneficiary_user_id, {plan} AS plan,
            {amount} AS amount_rub, {when} AS paid_at,
            CASE WHEN {confirmed} THEN 1 ELSE 0 END AS confirmed,
            CASE WHEN {test} THEN 1 ELSE 0 END AS is_test,
            '{table}' AS source, {priority} AS priority,
            CAST(id AS TEXT) AS row_id FROM {table} WHERE {where}""")

    if 'orders' in tables:
        add('orders', 'yookassa_payment_id', 'id', 'payer_user_id', 'beneficiary_user_id',
            'plan_code', 'amount / 100.0', 'COALESCE(paid_at, created_at)',
            "status = 'paid' AND currency = 'RUB'", 1, test='is_test')
    if 'yookassa_payments' in tables:
        add('yookassa_payments', 'payment_id', 'order_id', 'user_id',
            col('yookassa_payments', 'beneficiary_user_id', 'user_id'), 'item_code',
            'amount_rub', f"COALESCE({col('yookassa_payments', 'paid_at')}, created_at)",
            "status = 'succeeded'", 2, test=col('yookassa_payments', 'is_test', 'FALSE'))
    if 'analytics_events' in tables:
        add('analytics_events', 'NULL', 'order_id', 'user_id', 'user_id', 'plan_code',
            'amount / 100.0', 'created_at', 'TRUE', 3, "event = 'payment_success'", test='is_test')
    if 'subscriptions' in tables and {'payment_id', 'amount_rub'} <= columns['subscriptions']:
        c = columns['subscriptions']
        exclusions = ''.join(f' AND COALESCE({name}, FALSE) = FALSE'
                             for name in ('is_beta_access', 'is_trial') if name in c)
        add('subscriptions', 'payment_id', 'NULL', 'user_id', 'user_id', 'plan',
            'amount_rub', 'created_at', 'TRUE', 4,
            "payment_id IS NOT NULL AND payment_id != '' AND amount_rub > 0" + exclusions)
    if 'funnel_events' in tables:
        def prop(key):
            return f"props->>'{key}'" if pg else f"json_extract(props, '$.{key}')"

        add('funnel_events', prop('payment_id'), prop('order_id'), 'user_id', 'user_id',
            prop('plan'), f"CAST(COALESCE({prop('amount')}, '0') AS NUMERIC)",
            'created_at', 'TRUE', 5, "event = 'payment_success'",
            test=f"lower(COALESCE(CAST({prop('is_test')} AS TEXT), 'false')) IN ('true', '1')")
    raw = ' UNION ALL '.join(parts) or """SELECT NULL AS payment_id, NULL AS order_id,
        NULL AS user_id, NULL AS beneficiary_user_id, NULL AS plan, 0 AS amount_rub,
        NULL AS paid_at, 0 AS confirmed, 0 AS is_test, '' AS source,
        0 AS priority, '' AS row_id WHERE 1=0"""
    return f"""WITH payment_ids AS ({mapping}), raw_payments AS ({raw}),
        normalized AS (
          SELECT *, CASE WHEN payment_id LIKE 'yookassa:%' THEN substr(payment_id, 10)
                         WHEN payment_id LIKE 'order:%' THEN NULL
                         ELSE NULLIF(payment_id, '') END AS provider_id,
                    COALESCE(NULLIF(order_id, ''),
                      CASE WHEN payment_id LIKE 'order:%' THEN substr(payment_id, 7) END) AS local_id
          FROM raw_payments
        ), identified AS (
          SELECT *, COALESCE(provider_id,
            (SELECT MAX(NULLIF(p.payment_id, '')) FROM payment_ids p WHERE p.order_id = local_id)) AS resolved_id
          FROM normalized
        ), ranked AS (
          SELECT *, ROW_NUMBER() OVER (
            PARTITION BY COALESCE('payment:' || resolved_id, 'order:' || local_id, source || ':' || row_id)
            ORDER BY priority, paid_at, row_id) AS payment_rank
          FROM identified
        ) SELECT paid_at, user_id, COALESCE(beneficiary_user_id, user_id) AS beneficiary_user_id,
            plan, amount_rub, COALESCE(resolved_id, local_id) AS payment_id, source
          FROM ranked WHERE payment_rank = 1 AND confirmed = 1 AND is_test = 0
            AND substr(COALESCE(resolved_id, ''), 1, 5) != 'demo_'
            AND substr(COALESCE(local_id, ''), 1, 5) != 'demo_'"""


def payment_query(select, where='1=1', suffix='', **params):
    """Aggregate/filter the canonical ledger; callers supply only static SQL."""
    from models import db
    from sqlalchemy import text

    sql = f'SELECT {select} FROM ({ledger_sql()}) AS payments WHERE {where} {suffix}'
    return db.session.execute(text(sql), params).fetchall()
