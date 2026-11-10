"""Public article integration: real templates, the official GeoExact bridge."""
from pathlib import Path
from html.parser import HTMLParser
import re
from xml.etree import ElementTree

import pytest

from app import app as real_app
from geoexact import ARTICLE_ROUTES
from geoexact.web import bp as geoexact_bp

# Register during collection, before any test sends the first app request.
# The production bridge is otherwise disabled with GEOEXACT_ENABLED=0 locally.
if "geoexact" not in real_app.blueprints:
    real_app.register_blueprint(geoexact_bp)


class Element:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find(self, tag=None, cls=None, **attrs):
        found = []
        for child in self.children:
            if isinstance(child, str):
                continue
            if ((tag is None or child.tag == tag)
                    and (cls is None or cls in child.attrs.get("class", "").split())
                    and all(child.attrs.get(key) == value for key, value in attrs.items())):
                found.append(child)
            found.extend(child.find(tag, cls, **attrs))
        return found


class Page(HTMLParser):
    """Small stdlib DOM for the assertions; no new test dependencies."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]
        self.feed(body.decode("utf-8"))

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def find(self, *args, **kwargs):
        return self.root.find(*args, **kwargs)


CASES = [
    ("kalendar-olimpiad-2026-2027", "calendar-2026-2027", "Календарь олимпиад", 7, 0),
    ("vsosh-etapy", "vsosh-etapy", "Всероссийская олимпиада", 6, 0),
    ("olimpiady-9-klass", "olimpiady-9-klass", "для 9 класса", 4, 0),
    ("olimpiady-5-6-klass", "olimpiady-5-6-klass", "для 5–6 классов", 5, 0),
    ("perechnievye-olimpiady", "perechnevye-olimpiady", "Перечневые олимпиады", 6, 0),
    ("olimpiada-eilera", "olimpiada-eilera", "Олимпиада Эйлера", 7, 0),
    ("turnir-gorodov", "turnir-gorodov", "Турнир городов", 8, 0),
    ("plan-podgotovki", "plan-podgotovki", "Как подготовиться", 8, 0),
]


@pytest.fixture(scope="module")
def article_client():
    # Production registers GeoExact with its PostgreSQL queue. The local test
    # environment intentionally disables that queue; registering the same bp
    # runs the real record_once article bridge without an external service.
    # Do not mock _attach_article_routes or render_template.
    with real_app.test_client() as client:
        yield client


@pytest.mark.parametrize("slug,cover,phrase,chapters,markers", CASES)
def test_seo_article_routes(article_client, slug, cover, phrase, chapters, markers):
    route = "/articles/" + slug
    assert route in ARTICLE_ROUTES
    response = article_client.get(route)
    assert response.status_code == 200
    page = Page(response.data)
    assert len(page.find("h1")) == 1
    assert phrase in page.find("h1")[0].text()
    assert phrase in page.find("title")[0].text()
    assert page.find("meta", name="description")[0].attrs["content"].strip()
    assert page.find(cls="fa-hero__lead")
    assert len(page.find(cls="fa-kpi")[0].find("li")) == 4
    links = page.find(id="faHud")[0].find("a")
    article = page.find(id="faArticle")[0]
    sections = article.find("section", cls="fa-chapter")
    assert len(links) == len(sections) == chapters
    for step, (link, section) in enumerate(zip(links, sections)):
        assert link.attrs["data-step"] == section.attrs["data-step"] == str(step)
        assert link.attrs["href"] == "#" + section.attrs["id"]
        assert section.find("h2")
    assert len(page.find(cls="fa-chip--review")) == markers
    assert len(re.findall(r"\[УТОЧНИТЬ[^\]]*\]", article.text())) == markers
    assert any(a.attrs.get("href", "").startswith("https://formyla.net/olympiad-prep/")
               for a in article.find("a"))
    for table in article.find("table"):
        assert "fa-table-scroll" in table.parent.attrs.get("class", "").split()
        assert all(th.attrs.get("scope") == "col" for th in table.find("th"))
    assert "{{" not in page.find(cls="fa")[0].text()
    image_url = page.find(cls="fa-hero__img")[0].attrs["src"]
    assert image_url.endswith("cover-" + cover + ".svg")
    image = article_client.get(image_url)
    assert image.status_code == 200
    assert ElementTree.fromstring(image.data).attrib["viewBox"] == "0 0 800 800"


def test_article_index_keeps_existing_cards_first(article_client):
    response = article_client.get("/articles")
    assert response.status_code == 200
    page = Page(response.data)
    cards = page.find("a", cls="art-card")
    expected = ["/articles/fiztech", "/articles/ot-shkoly-k-olimpiadam"]
    expected += ["/articles/" + row[0] for row in CASES]
    assert [card.attrs["href"] for card in cards] == expected
    assert all(card.find("img")[0].attrs.get("alt") and card.find("h2") and card.find("p")
               for card in cards)


@pytest.mark.parametrize(
    "route,phrase",
    [
        ("/articles/fiztech", "Физтех"),
        ("/articles/ot-shkoly-k-olimpiadam", "Пятёрка"),
    ],
)
def test_existing_articles_still_render(article_client, route, phrase):
    response = article_client.get(route)
    assert response.status_code == 200
    page = Page(response.data)
    assert phrase in page.find("h1")[0].text()
    assert page.find(id="faHud")[0].find("a")


def test_new_guides_reuse_reference_hud_not_tracker_script():
    templates = Path(__file__).resolve().parents[1] / "templates" / "articles"
    reference = (templates / "fiztech.html").read_text(encoding="utf-8")
    reference_script = reference.split("{% block extra_js %}", 1)[1].split("{% endblock %}", 1)[0]
    script = (templates / "_seo_scripts.html").read_text(encoding="utf-8")
    assert script.strip() == reference_script.strip()
    assert "trackerGrid" not in script
