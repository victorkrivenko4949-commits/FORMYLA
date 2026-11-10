"""GeoExact — пакет генерации чертежей (blueprint в web.py).

ARTICLES_BRIDGE_V1: при регистрации blueprint'а GeoExact в приложение
добавляются маршруты статей раздела «Статьи», которые ещё не описаны в app.py
(app.py очень большой и правится только вручную). Маршрут добавляется один раз,
до первого запроса, и пропускается, если такой rule/endpoint уже есть в app.py.
Когда маршрут переедет в app.py, запись из ARTICLE_ROUTES можно просто удалить.
"""
from flask import render_template

# rule -> (endpoint, шаблон в templates/ приложения)
ARTICLE_ROUTES = {
    "/articles/fiztech": ("article_fiztech", "articles/fiztech.html"),
    "/articles/kalendar-olimpiad-2026-2027": (
        "article_calendar_2026_2027", "articles/calendar_2026_2027.html"
    ),
    "/articles/vsosh-etapy": ("article_vsosh_etapy", "articles/vsosh_etapy.html"),
    "/articles/olimpiady-9-klass": (
        "article_olimpiady_9_klass", "articles/olimpiady_9_klass.html"
    ),
    "/articles/olimpiady-5-6-klass": (
        "article_olimpiady_5_6_klass", "articles/olimpiady_5_6_klass.html"
    ),
    "/articles/perechnievye-olimpiady": (
        "article_perechnevye_olimpiady", "articles/perechnevye_olimpiady.html"
    ),
    "/articles/olimpiada-eilera": (
        "article_olimpiada_eilera", "articles/olimpiada_eilera.html"
    ),
    "/articles/turnir-gorodov": ("article_turnir_gorodov", "articles/turnir_gorodov.html"),
    "/articles/plan-podgotovki": (
        "article_plan_podgotovki", "articles/plan_podgotovki.html"
    ),
}


def _make_view(template):
    def view():
        return render_template(template)
    view.__name__ = "article_view_" + template.rsplit("/", 1)[-1].split(".")[0]
    return view


def _attach_article_routes(state):
    app = state.app
    existing = {r.rule for r in app.url_map.iter_rules()}
    for rule, (endpoint, template) in ARTICLE_ROUTES.items():
        if rule in existing or endpoint in app.view_functions:
            continue
        app.add_url_rule(rule, endpoint=endpoint, view_func=_make_view(template))


try:
    from . import web as _web
    _web.bp.record_once(_attach_article_routes)
except Exception:  # мост не должен ломать GeoExact при любой ошибке
    pass
