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
