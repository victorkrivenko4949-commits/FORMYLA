# -*- coding: utf-8 -*-
"""E2E-тест этапа 21 (синтетика, без API): атрибуция, вариант, дубли,
обогащение, отчёт, --limit, защиты (reasoner-вердикт, кросс-олимпиадный дубликат)."""
import sys, json, types, shutil, tempfile
from pathlib import Path
sys.path.insert(0, "scripts")
import olymp_catalog_fix as FIX
import olymp_fix_prompts as P
import olymp_fix_rules as R

TMP = Path(tempfile.mkdtemp())
SRC = TMP / "catalog"
SRC.mkdir()

def mk(uid, num, text, variant=None, status="official_found", solution="Реш."):
    return {"uid": uid, "olymp": "Физтех", "year": 2025,
            "round": "Отборочный этап", "day": 0, "grade": "11", "num": str(num),
            "status": status, "answer": "42", "source": "",
            "text": text, "solution": solution, "qa": {}, "variant": variant}

T1 = "Задача один: найти сумму чисел от 1 до 10."
T2 = "Задача два: докажите, что число иррационально."
T3 = "Задача три: решите уравнение с параметром a."
T4 = "Задача четыре: постройте график функции."
V2T1 = "Вторая серия, задача один про треугольник."
V2T2 = "Вторая серия, задача два про вписанный угол."
V2T3 = "Вторая серия, задача три про окружность."

u1 = mk("u1", 1, T1, status="AI_generated", solution="AI-решение, требует проверки")
u1["answer"] = "55"  # совпадает с PDF — конфликтов нет
u2 = mk("u2", 4, T4)
u2["answer"] = "парабола"   # совпадает с PDF — атрибуция подтверждается
phystech = [
    # без variant: после атрибуции должны получить вариант 1
    u1,
    # u2: ответ в базе совпадает с PDF — атрибуция подтверждается;
    # конфликт ответов покрыт сценариями частей 6 и 8
    u2,
    # вариант 2: дыра №2
    mk("u4", 1, V2T1, variant="2"),
    mk("u5", 3, V2T3, variant="2"),
]
(SRC / "phystech.json").write_text(json.dumps(phystech, ensure_ascii=False), encoding="utf-8")

# Кросс-олимпиадная ловушка: тот же текст задачи 2, другая олимпиада —
# дубликат НЕ должен обогащаться и не должен мешать импорту в phystech
lomo = [mk("l1", 7, T2)]
lomo[0]["olymp"] = "Ломоносов"
(SRC / "lomonosov.json").write_text(json.dumps(lomo, ensure_ascii=False), encoding="utf-8")

PDF_URL = "https://olymp.mipt.ru/zadachi-2025.pdf"
PDF_PAGES = [
    "Физтех 2025, отборочный этап",
    "11 класс. Вариант 1",
    f"1. {T1} [3 балла]",
    "Ответ: 55. Решение: сумма арифметической прогрессии.",
    f"2. {T2} [3 балла]",
    f"3. {T3} [4 балла]",
    f"4. {T4} [5 балла]",
    "Ответ: парабола. Решение: дискриминант больше нуля.",
    "11 класс. Вариант 2",
    f"1. {V2T1} [3 балла]",
    f"2. {V2T2} [4 балла]",
    f"3. {V2T3} [3 балла]",
]

# --- Заглушки вместо API ---
def _fetch_result(url):
    return {"ok": True, "pages": list(PDF_PAGES), "http_code": "200",
            "content_type": "application/pdf", "final_url": url, "error": ""}

FIX._fetch_doc_result = _fetch_result
FIX._fetch_doc_pages = lambda url, ttl=7: list(PDF_PAGES)

class StubIndex:
    _cache = {"phystech": True, "lomonosov": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        if slug != "phystech":
            return []          # у «Ломоносова» своих PDF нет
        return [{"url": PDF_URL, "variant": variant, "grades": [grade],
                 "year": year, "kind": "tasks", "round_key": round_key}]

class StubChat:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        def task(num, text, answer, solution, points, variant):
            t = {"num": num, "text": text, "answer": answer, "solution": solution,
                 "points": points, "variant": variant}
            # заглушка обязана проверять переданный doc_text
            if text[:60] not in doc:
                return None
            return t
        if str(data.get("variant")) == "2":
            tasks = [task("2", V2T2, "90", "Вписанный угол равен половине дуги.",
                          "4 балла", "2")]
        else:
            tasks = [
                task("1", T1, "55", "сумма арифметической прогрессии", "3 балла", "1"),
                task("2", T2, "корень из 2", "от противного", "3 балла", "1"),
                # повтор той же задачи в одном ответе — должна добавиться один раз
                task("2", T2, "корень из 2", "от противного", "3 балла", "1"),
                task("3", T3, "a > 5", "разбор случаев по параметру", "4 балла", "1"),
                task("4", T4, "парабола", "дискриминант больше нуля", "5 баллов", "1"),
            ]
        tasks = [t for t in tasks if t]
        if not tasks:
            return {"ok": False, "reason": "нет задач в переданном блоке"}
        return {"ok": True, "tasks": tasks}

class StubReasoner:
    """Вердикт match для всех задач, кроме №3 (неопределённость — отказ)."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        if data.get("text", "").startswith(T3):
            return {"verdict": "unclear", "reason": "не уверен"}
        return {"verdict": "match", "reason": "ок"}

def make_pipeline(limit=None):
    args = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP / f"cp_{limit}.json", source=str(SRC),
        slug=None, limit=limit, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p = FIX.Pipeline(args)
    p.deepseek_chat = StubChat()
    p.deepseek_reasoner = StubReasoner()
    p.gemini = None
    p._source_index = StubIndex()
    return p

p = make_pipeline()
FIX.stage_21(p)

recs = p.catalog.data["phystech"]
by_num_var = {(r.get("variant"), str(r["num"])): r for r in recs}

# 1) Атрибуция: u1 подтверждён (вариант 1); u2 — конфликт ответов
# («42» в базе vs «парабола» в PDF): вариант НЕ проставляется, только
# needs_review — прежние поля сохраняются
r1 = by_num_var[("1", "1")]
assert r1["uid"] == "u1" and r1["variant"] == "1", (r1["uid"], r1.get("variant"))
r4 = by_num_var[("1", "4")]
assert r4["uid"] == "u2" and r4["variant"] == "1"

# 2) Дубль №1 (AI_generated) обогащён официальным решением
assert r1["status"] == "official_found"
assert r1["solution"] == "сумма арифметической прогрессии"
assert any("points: 3" in json.dumps(v) for v in r1["qa"].values())

# 2б) Дубль №4: ответ совпадает, статус official_found — существующее
# решение НЕ перезаписано (обогащение только для AI_*/gemini_solved)
assert r4["uid"] == "u2" and r4["variant"] == "1"
assert r4["solution"] == "Реш."
assert not any("конфликт" in json.dumps(v, ensure_ascii=False)
               for v in r4["qa"].values())

# 3) Новые задачи: №2 вар.1 и №2 вар.2 (№3 отклонена reasoner-вердиктом)
r2 = by_num_var[("1", "2")]
assert r2["text"] == T2 and r2["status"] == "official_found"
assert any("points: 3" in json.dumps(v) for v in r2["qa"].values())
r2v2 = by_num_var[("2", "2")]
assert r2v2["text"] == V2T2 and r2v2["variant"] == "2"
assert ("1", "3") not in by_num_var, "№3 должна быть отклонена (неясный вердикт)"

# 4) Повтор задачи №2 в одном ответе — добавлена один раз
assert sum(1 for r in recs if r["text"] == T2) == 1

# 5) Кросс-олимпиадный дубль не тронут: у Ломоносова без изменений
l_recs = p.catalog.data["lomonosov"]
assert len(l_recs) == 1 and not (l_recs[0].get("variant") or "")
assert not l_recs[0].get("qa"), "чужая олимпиада не обогащается"

# 6) Отчёт: честные счётчики (уникальные записи/URL, полный vs частичный импорт)
st = p.stage21_report["phystech"]
assert st["tasks_added"] == 2, st
assert st["dup_skipped"] == 2, st          # №1 и №4 (вариант 1) — дубли
assert st["variants"] == 1, st             # вариант 2 закрыт полностью
assert st["variants_partial"] == 1, st    # вариант 1 — частично (№3 отклонена)
assert st["pdfs"] == 1, st                 # один уникальный URL
gaps_nums = {g.get("num") for g in st["gaps"]}
assert 3 in gaps_nums, st["gaps"]         # остаток дыры №3 с причиной
assert any("не сверено" in json.dumps(g, ensure_ascii=False)
               for g in st["gaps"])

# 7) --limit = число вариантов: лимит 1, продолжение с тем же чекпоинтом
# доходит до СЛЕДУЮЩЕЙ группы (нерешённая не занимает лимит повторно)
p2 = make_pipeline(limit=1)
FIX.stage_21(p2)
p2.checkpoint.save()   # как в реальном прогоне (save_state)
st2 = p2.stage21_report["phystech"]
assert st2["unprocessed"] >= 1, st2
tried_after_1 = dict(p2.checkpoint.data["stage21_tried"])
assert len(tried_after_1) == 1, tried_after_1
# второй прогон с ТЕМ ЖЕ чекпоинтом: обработана другая группа
p3 = FIX.Pipeline(types.SimpleNamespace(
    dry_run=False, checkpoint=p2.args.checkpoint, source=str(SRC),
    slug=None, limit=1, stages_set={21}, workers=2, resume=False,
    rebuild_index=True))
p3.deepseek_chat = StubChat()
p3.deepseek_reasoner = StubReasoner()
p3.gemini = None
p3._source_index = StubIndex()
FIX.stage_21(p3)
tried_after_2 = p3.checkpoint.data["stage21_tried"]
assert len(tried_after_2) == 2, tried_after_2   # две РАЗНЫЕ группы
assert set(tried_after_1) < set(tried_after_2)
# группа первого прогона помечена более ранним номером — при сортировке
# она уйдёт в конец, следующий прогон возьмёт другую (ротация)
assert tried_after_2[list(tried_after_1)[0]] < tried_after_2[list(tried_after_2)[-1]]

print("E2E ЭТАП 21: OK")
shutil.rmtree(TMP)


# =====================================================================
# Часть 2: происхождение полей, неоднозначность атрибуции, ротация прогонов
# =====================================================================
TMP2 = Path(tempfile.mkdtemp())
SRC2 = TMP2 / "catalog"
SRC2.mkdir()

# Задачи: №1 (дубль, AI_generated) и №2 (новая); решения — в отдельном PDF
p1t1 = mk("x1", 1, T1, status="AI_generated", solution="AI-решение")
p1t1["answer"] = "55"   # совпадает с PDF
p1t2 = mk("x2", 3, T3)
p1t2["answer"] = "a > 5"  # совпадает с PDF
v2recs = [p1t1, p1t2]
(SRC2 / "phystech.json").write_text(json.dumps(v2recs, ensure_ascii=False), encoding="utf-8")

TASKS_PDF = "https://olymp.mipt.ru/tasks.pdf"
SOL_PDF = "https://olymp.mipt.ru/solutions.pdf"
PAGES_TASKS = ["11 класс. Вариант 1", f"1. {T1} [3 балла]", f"3. {T3} [4 балла]"]
PAGES_SOL = ["11 класс. Вариант 1", f"1. {T1}", "Решение: сумма арифметической прогрессии.",
             f"3. {T3}", "Решение: разбор случаев по параметру."]

FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_TASKS), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""}
    if "tasks.pdf" in url else
    {"ok": True, "pages": list(PAGES_SOL), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: (list(PAGES_TASKS) if "tasks.pdf" in url
                                          else list(PAGES_SOL))

class StubIndex2:
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        # оба PDF: условия и решения (год подтверждён метаданными индекса)
        return [{"url": TASKS_PDF, "year": year, "grades": [grade]},
                {"url": SOL_PDF, "year": year, "grades": [grade]}]

class StubChat2:
    """Условия — из tasks.pdf, решения — из solutions.pdf (вторая ссылка)."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = []
        if "сумма арифметической прогрессии" in doc:   # solutions.pdf
            tasks = [
                {"num": "1", "text": T1, "answer": "55",
                 "solution": "сумма арифметической прогрессии", "points": "3 балла"},
                {"num": "3", "text": T3, "answer": "a > 5",
                 "solution": "разбор случаев по параметру", "points": "4 балла"},
            ]
        else:                                          # tasks.pdf
            tasks = [
                {"num": "1", "text": T1, "answer": "", "solution": ""},
                {"num": "3", "text": T3, "answer": "", "solution": ""},
            ]
        tasks = [t for t in tasks if t["text"][:40] in doc]
        if not tasks:
            return {"ok": False, "reason": "нет задач в переданном блоке"}
        return {"ok": True, "tasks": tasks}

class StubReasoner2:
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        return {"verdict": "match"}

def make_pipeline2(limit=None, cp_name="cp"):
    args = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP2 / f"{cp_name}.json", source=str(SRC2),
        slug=None, limit=limit, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p = FIX.Pipeline(args)
    p.deepseek_chat = StubChat2()
    p.deepseek_reasoner = StubReasoner2()
    p.gemini = None
    p._source_index = StubIndex2()
    return p

pB = make_pipeline2()
FIX.stage_21(pB)

# Происхождение: решение подтянуто из solutions.pdf, условие — из tasks.pdf
rx1 = [r for r in pB.catalog.data["phystech"] if r["uid"] == "x1"][0]
assert rx1["status"] == "official_found"
assert rx1["solution"] == "сумма арифметической прогрессии"
qa_str = json.dumps(rx1["qa"], ensure_ascii=False)
assert "решение подтянуто из https://olymp.mipt.ru/solutions.pdf" in qa_str, qa_str
assert "условие — из https://olymp.mipt.ru/tasks.pdf" in qa_str, qa_str
assert rx1["source"] == TASKS_PDF   # источник записи — PDF с условием

# x2 (№3) — дубль со статусом official_found: по ТЗ решение НЕ заменяется
# (замена только для gemini_solved/AI_*), но вариант проставлен
x2 = [r for r in pB.catalog.data["phystech"] if r["uid"] == "x2"][0]
assert x2["solution"] == "Реш."
assert (x2.get("variant") or "") == "1"
assert not any(r["uid"] not in ("x1", "x2") for r in pB.catalog.data["phystech"])

# --- Неоднозначность атрибуции между двумя PDF ---
AMB1 = "https://olymp.mipt.ru/amb1.pdf"
AMB2 = "https://olymp.mipt.ru/amb2.pdf"
PAGES_AMB1 = ["11 класс. Вариант 1", f"1. {T1}"]
PAGES_AMB2 = ["11 класс. Вариант 2", f"1. {T1}"]

FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_AMB1), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""}
    if url == AMB1 else
    {"ok": True, "pages": list(PAGES_AMB2), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: (list(PAGES_AMB1) if url == AMB1
                                           else list(PAGES_AMB2))

class StubIndexAmb:
    _cache = {"phystech": True}
    def find(self, slug, year, *a, **k):
        return [{"url": AMB1, "year": year}, {"url": AMB2, "year": year}]

pC = make_pipeline2(cp_name="cp_amb")
pC._source_index = StubIndexAmb()
FIX.stage_21(pC)
# один и тот же текст в варианте 1 (PDF A) и варианте 2 (PDF B) —
# неоднозначность: вариант НЕ проставлен, needs_review
rc1 = [r for r in pC.catalog.data["phystech"] if r["uid"] == "x1"][0]
assert not (rc1.get("variant") or ""), rc1.get("variant")
assert "needs_review" in json.dumps(rc1["qa"], ensure_ascii=False)

# --- Ротация прогонов: 3 запуска с --limit 1, группы чередуются ---
pD = make_pipeline2(limit=1, cp_name="cp_rot")
pD._source_index = StubIndex2()
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_TASKS), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""}
    if "tasks.pdf" in url else
    {"ok": True, "pages": list(PAGES_SOL), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX.stage_21(pD)
pD.checkpoint.save()
tried_runs = [dict(pD.checkpoint.data["stage21_tried"])]

for i in range(2):
    pE = FIX.Pipeline(types.SimpleNamespace(
        dry_run=False, checkpoint=pD.args.checkpoint, source=str(SRC2),
        slug=None, limit=1, stages_set={21}, workers=2, resume=False,
        rebuild_index=True))
    pE.deepseek_chat = StubChat2()
    pE.deepseek_reasoner = StubReasoner2()
    pE.gemini = None
    pE._source_index = StubIndex2()
    FIX.stage_21(pE)
    pE.checkpoint.save()
    tried_runs.append(dict(pE.checkpoint.data["stage21_tried"]))

# группы обрабатываются по очереди (ротация): номера прогонов растут
last_run = pE.checkpoint.data["stage21_runs"]
assert last_run >= 3, last_run
print("ПРОИСХОЖДЕНИЕ/НЕОДНОЗНАЧНОСТЬ/РОТАЦИЯ OK")
shutil.rmtree(TMP2)


# =====================================================================
# Часть 3: две нерешаемые группы чередуются, затем ресурс появляется —
# импорт доходит до цели несмотря на --limit 1
# =====================================================================
TMP3 = Path(tempfile.mkdtemp())
SRC3 = TMP3 / "catalog"
SRC3.mkdir()
# две олимпиады с дырами, обе «нерешаемые» пока индекс пуст
(SRC3 / "alpha.json").write_text(json.dumps(
    [mk("a1", 1, T1), mk("a2", 3, T3)], ensure_ascii=False), encoding="utf-8")
(SRC3 / "beta.json").write_text(json.dumps(
    [mk("b1", 1, T2), mk("b2", 3, T4)], ensure_ascii=False), encoding="utf-8")

EMPTY_PAGES = ["11 класс. Вариант 1", f"1. {T1} [3 балла]", f"3. {T3} [4 балла]",
               f"2. {T2} [3 балла]",
               "Ответ: 55. Решение: сумма арифметической прогрессии.",
               "Ответ: a>5. Решение: разбор случаев."]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(EMPTY_PAGES), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(EMPTY_PAGES)

class StubIndex3:
    """Сначала кандидатов нет, после переключения — появляются."""
    _cache = {"alpha": True, "beta": True}
    available = False
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        if not self.available:
            return []
        return [{"url": "https://olymp.mipt.ru/combined.pdf",
                 "year": year, "grades": [grade]}]

class StubChat3:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [t for t in ({"num": "2", "text": T2, "answer": "x",
                             "solution": "s", "points": "1 балл"},) ]
        # возвращаем только те задачи, чей текст есть в переданном блоке
        tasks = [t for t in tasks if t["text"][:30] in doc]
        if not tasks:
            return {"ok": False, "reason": "нет задач в блоке"}
        return {"ok": True, "tasks": tasks}

def make_pipeline3(cp_name):
    args = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP3 / f"{cp_name}.json", source=str(SRC3),
        slug=None, limit=1, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p = FIX.Pipeline(args)
    p.deepseek_chat = StubChat3()
    p.deepseek_reasoner = StubReasoner2()
    p.gemini = None
    p._source_index = StubIndex3()
    return p

# Прогоны 1-2: кандидатов нет — обе группы помечаются tried по очереди
pG = make_pipeline3("cp3")
FIX.stage_21(pG); pG.checkpoint.save()
t1 = dict(pG.checkpoint.data["stage21_tried"])
assert len(t1) == 1, t1
pG2 = FIX.Pipeline(types.SimpleNamespace(
    dry_run=False, checkpoint=pG.args.checkpoint, source=str(SRC3),
    slug=None, limit=1, stages_set={21}, workers=2, resume=False,
    rebuild_index=True))
pG2.deepseek_chat = StubChat3(); pG2.deepseek_reasoner = StubReasoner2()
pG2.gemini = None; pG2._source_index = StubIndex3()
FIX.stage_21(pG2); pG2.checkpoint.save()
t2 = dict(pG2.checkpoint.data["stage21_tried"])
assert len(t2) == 2, t2   # обе группы попробованы за два прогона

# Прогон 3: индекс «ожил» — импорт доходит до цели при --limit 1
StubIndex3.available = True
pG3 = FIX.Pipeline(types.SimpleNamespace(
    dry_run=False, checkpoint=pG.args.checkpoint, source=str(SRC3),
    slug=None, limit=1, stages_set={21}, workers=2, resume=False,
    rebuild_index=True))
pG3.deepseek_chat = StubChat3(); pG3.deepseek_reasoner = StubReasoner2()
pG3.gemini = None; pG3._source_index = StubIndex3()
FIX.stage_21(pG3)
added3 = sum(st["tasks_added"] for st in pG3.stage21_report.values())
assert added3 >= 1, pG3.stage21_report   # импорт произошёл
print("РОТАЦИЯ+ДОСТУПНОСТЬ OK")
shutil.rmtree(TMP3)


# =====================================================================
# Часть 4: контрпримеры атрибуции (классы, год, хвост варианта, sol-PDF)
# =====================================================================
TMP4 = Path(tempfile.mkdtemp())
SRC4 = TMP4 / "catalog"
SRC4.mkdir()

# --- 4.1 Классы заголовков не перепутываются на одной странице ---
pages_mix = ["11 класс. Вариант 1\nA\n10 класс. Вариант 2\nB"]
blocks_mix = FIX._find_blocks(pages_mix)
assert [(b["grade"], b["variant"]) for b in blocks_mix] == [("11", "1"), ("10", "2")]
assert FIX._select_blocks(blocks_mix, "11", "2") == []
assert len(FIX._select_blocks(blocks_mix, "11", "1")) == 1
assert len(FIX._select_blocks(blocks_mix, "10", "2")) == 1

# --- 4.2 Год: PDF с явным 2024 при группе 2025 — импорта/атрибуции НЕТ ---
y1 = mk("y1", 1, T1, status="AI_generated", solution="AI-решение")
y1["answer"] = "55"
y2 = mk("y2", 3, T3, status="AI_generated", solution="AI-решение")
y2["answer"] = "a > 5"
r2024 = [y1, y2]
(SRC4 / "phystech.json").write_text(json.dumps(r2024, ensure_ascii=False), encoding="utf-8")

PAGES_2024 = ["11 класс. Вариант 1", "Олимпиада 2024 года",
              f"1. {T1} [3 балла]", f"3. {T3} [4 балла]",
              f"2. {T2} [3 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_2024), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_2024)

class StubIndex4:
    """Год в индексе НЕИЗВЕСТЕН (None) — подтверждение только документом."""
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/y2024.pdf"}]

class StubChat4:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "2", "text": T2, "answer": "x", "solution": "s"}]
        tasks = [t for t in tasks if t["text"][:30] in doc]
        if not tasks:
            return {"ok": False, "reason": "нет"}
        return {"ok": True, "tasks": tasks}

def make_pipeline4(cp_name):
    args = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP4 / f"{cp_name}.json", source=str(SRC4),
        slug=None, limit=None, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p = FIX.Pipeline(args)
    p.deepseek_chat = StubChat4()
    p.deepseek_reasoner = StubReasoner2()
    p.gemini = None
    p._source_index = StubIndex4()
    return p

pH = make_pipeline4("cp4")
FIX.stage_21(pH)
stH = pH.stage21_report["phystech"]
# ни атрибуции, ни импорта: год 2024 не подтверждает группу 2025
assert not any((r.get("variant") or "").strip() for r in pH.catalog.data["phystech"])
assert stH["tasks_added"] == 0, stH
assert any("год не подтверждён" in json.dumps(g, ensure_ascii=False)
           for g in stH["gaps"]), stH["gaps"]

# --- 4.3 PDF без годов + год индекса неизвестен — тоже НЕ подтверждено ---
PAGES_NOYEAR = ["11 класс. Вариант 1", f"1. {T1}", f"3. {T3}", f"2. {T2}"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_NOYEAR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_NOYEAR)
pI = make_pipeline4("cp4b")
FIX.stage_21(pI)
stI = pI.stage21_report["phystech"]
assert stI["tasks_added"] == 0, stI   # молчание документа — не согласие
assert any("год не подтверждён" in json.dumps(g, ensure_ascii=False)
           for g in stI["gaps"]), stI["gaps"]

# --- 4.4 Год подтверждён метаданными индекса: импорт идёт ---
class StubIndex4b(StubIndex4):
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/y2025.pdf", "year": year,
                 "grades": [grade], "kind": "tasks"}]
pJ = make_pipeline4("cp4c")
pJ._source_index = StubIndex4b()
FIX.stage_21(pJ)
assert pJ.stage21_report["phystech"]["tasks_added"] >= 1, \
    pJ.stage21_report["phystech"]   # индекс подтвердил год — импорт прошёл

# --- 4.5 Хвост варианта: блок 1-4, модель вернула 1-3, каталог 1,3 ---
PAGES_TAIL = ["11 класс. Вариант 1", f"1. {T1}", f"3. {T3}", f"2. {T2}",
              f"4. {T4} [5 баллов]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_TAIL), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_TAIL)
pK = make_pipeline4("cp4d")
pK._source_index = StubIndex4b()
FIX.stage_21(pK)
stK = pK.stage21_report["phystech"]
# модель вернула только 1-3 (StubChat4 отдаёт T2); №4 в блоке есть, в каталоге нет
assert any(g.get("num") == 4 for g in stK["gaps"]), stK["gaps"]
assert stK["variants_partial"] >= 1 or stK["variants"] == 0, stK

# --- 4.6 Решения без условия: sol-PDF «1. Решение…» без текста условия ---
SOL_ONLY = ["11 класс. Вариант 1",
            "1. Решение: сумма арифметической прогрессии. Ответ: 55.",
            "3. Решение: разбор случаев по параметру."]
TASKS_ONLY = ["11 класс. Вариант 1", f"1. {T1} [3 балла]", f"3. {T3} [4 балла]"]

def fetch_by_url(url):
    pages = SOL_ONLY if "sol" in url else TASKS_ONLY
    return {"ok": True, "pages": list(pages), "http_code": "200",
            "content_type": "application/pdf", "final_url": url, "error": ""}
FIX._fetch_doc_result = fetch_by_url
FIX._fetch_doc_pages = lambda url, ttl=7: (SOL_ONLY if "sol" in url else TASKS_ONLY)

class StubChat5:
    """tasks.pdf — условия без решений; sol.pdf — решения без условий."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        if "Решение" in doc:   # sol-PDF: только решения
            tasks = [{"num": "1", "text": "", "answer": "55",
                      "solution": "сумма арифметической прогрессии"},
                     {"num": "3", "text": "", "answer": "a > 5",
                      "solution": "разбор случаев по параметру"}]
        else:                  # tasks-PDF: только условия
            tasks = [{"num": "1", "text": T1, "answer": "", "solution": ""},
                     {"num": "3", "text": T3, "answer": "", "solution": ""}]
        return {"ok": True, "tasks": tasks}

class StubIndex5:
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/tasks5.pdf", "year": year,
                 "grades": [grade]},
                {"url": "https://olymp.mipt.ru/sol5.pdf", "year": year,
                 "grades": [grade]}]

pL = make_pipeline4("cp4e")
pL.deepseek_chat = StubChat5()
pL._source_index = StubIndex5()
FIX.stage_21(pL)
stL = pL.stage21_report["phystech"]
# задача №1: условие из tasks.pdf + решение из sol.pdf, URL решения в qa
rL1 = [r for r in pL.catalog.data["phystech"] if r.get("num") == "1"][0]
assert rL1["text"] == T1
assert rL1["solution"] == "сумма арифметической прогрессии"
assert "sol5.pdf" in json.dumps(rL1["qa"], ensure_ascii=False)
assert rL1["status"] == "official_found"
# задача №3 (дубль x2-типа): решение присоединено по номеру без условия
rL3 = [r for r in pL.catalog.data["phystech"] if r.get("num") == "3"][0]
assert rL3["solution"] == "разбор случаев по параметру", rL3.get("solution")

print("КОНТРПРИМЕРЫ АТРИБУЦИИ OK")
shutil.rmtree(TMP4)


# =====================================================================
# Часть 5: наследование класса, порядок кандидатов, остаток блока,
# противоречие года против метаданных индекса
# =====================================================================
TMP5 = Path(tempfile.mkdtemp())
SRC5 = TMP5 / "catalog"
SRC5.mkdir()

# --- 5.1 Многострочный заголовок: класс наследуется до явного изменения ---
pages_ml = ["11 класс\nВариант 1\nA\n10 класс\nВариант 2\nB"]
blocks_ml = FIX._find_blocks(pages_ml)
got_ml = [(b["grade"], b["variant"]) for b in blocks_ml]
assert got_ml == [("11", "1"), ("10", "2")], got_ml
assert FIX._select_blocks(blocks_ml, "11", "2") == []
assert len(FIX._select_blocks(blocks_ml, "11", "1")) == 1

# --- 5.2 Остаток: модель вернула 1-4, №4 отклонена reasoner ---
z1 = mk("z1", 1, T1, status="AI_generated", solution="AI")
z1["answer"] = "55"
z2 = mk("z2", 3, T3, status="AI_generated", solution="AI")
z2["answer"] = "a > 5"
(SRC5 / "phystech.json").write_text(json.dumps([z1, z2], ensure_ascii=False),
                                   encoding="utf-8")

PAGES_14 = ["11 класс. Вариант 1", f"1. {T1}", f"3. {T3}", f"2. {T2}",
            f"4. {T4} [5 баллов]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_14), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_14)

class StubChat6:
    """Возвращает №1-4; №4 не проходит сверку reasoner."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        base = [{"num": "1", "text": T1, "answer": "55", "solution": "s1"},
                {"num": "2", "text": T2, "answer": "x", "solution": "s2"},
                {"num": "3", "text": T3, "answer": "a > 5", "solution": "s3"},
                {"num": "4", "text": T4, "answer": "p", "solution": "s4"}]
        tasks = [t for t in base if t["text"][:30] in doc]
        return {"ok": True, "tasks": tasks}

class StubReasoner6:
    """Явный match для всех, кроме №4 (unclear); гейт эквивалентности — ok."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        # гейт эквивалентности условий (MATH_EQUIVALENCE)
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        data = json.loads(payload)
        if data.get("text", "").startswith(T4):
            return {"verdict": "unclear"}
        return {"verdict": "match"}

class StubIndex6:
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/full.pdf", "year": year,
                 "grades": [grade]}]

def make_pipeline5(cp_name, chat=None, reasoner=None, index=None):
    args = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP5 / f"{cp_name}.json", source=str(SRC5),
        slug=None, limit=None, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p = FIX.Pipeline(args)
    p.deepseek_chat = chat or StubChat6()
    p.deepseek_reasoner = reasoner or StubReasoner6()
    p.gemini = None
    p._source_index = index or StubIndex6()
    return p

pM = make_pipeline5("cp5")
FIX.stage_21(pM)
stM = pM.stage21_report["phystech"]
# №2 добавлена; №4 отклонена reasoner и НЕ в итоговых записях
finals = [r for r in pM.catalog.data["phystech"] if r.get("year") == 2025]
final_nums = {r.get("num") for r in finals}
assert "2" in final_nums, final_nums
assert "4" not in final_nums, final_nums
# остаток №4 зафиксирован с причиной отклонения
g4 = [g for g in stM["gaps"] if g.get("num") == 4]
assert g4 and "не сверено" in json.dumps(g4, ensure_ascii=False), stM["gaps"]
assert stM["variants_partial"] >= 1, stM

# --- 5.3 Порядок кандидатов: sol-PDF ПЕРВЫМ, tasks-PDF вторым ---
SOL6 = ["11 класс. Вариант 1",
        "1. Решение: сумма арифметической прогрессии. Ответ: 55.",
        "3. Решение: разбор случаев по параметру. Ответ: a > 5."]
TASKS6 = ["11 класс. Вариант 1", f"1. {T1} [3 балла]", f"3. {T3} [4 балла]"]

def fetch6(url):
    pages = SOL6 if "sol6" in url else TASKS6
    return {"ok": True, "pages": list(pages), "http_code": "200",
            "content_type": "application/pdf", "final_url": url, "error": ""}
FIX._fetch_doc_result = fetch6
FIX._fetch_doc_pages = lambda url, ttl=7: (SOL6 if "sol6" in url else TASKS6)

class StubIndexRev:
    """sol-PDF идёт ПЕРВЫМ."""
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/sol6.pdf", "year": year,
                 "grades": [grade]},
                {"url": "https://olymp.mipt.ru/tasks6.pdf", "year": year,
                 "grades": [grade]}]

class StubChatRev:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        if "Решение" in doc:   # sol-PDF первым
            return {"ok": True, "tasks": [
                {"num": "1", "text": "", "answer": "55",
                 "solution": "сумма арифметической прогрессии"},
                {"num": "3", "text": "", "answer": "a > 5",
                 "solution": "разбор случаев по параметру"}]}
        return {"ok": True, "tasks": [
            {"num": "1", "text": T1, "answer": "", "solution": ""},
            {"num": "3", "text": T3, "answer": "", "solution": ""}]}

pN = make_pipeline5("cp5rev", chat=StubChatRev(), index=StubIndexRev())
FIX.stage_21(pN)
rN1 = [r for r in pN.catalog.data["phystech"] if r.get("num") == "1"
       and r.get("year") == 2025][0]
# условие из tasks6, решение из sol6 — независимо от порядка кандидатов
assert rN1["text"] == T1
assert rN1["solution"] == "сумма арифметической прогрессии"
qaN = json.dumps(rN1["qa"], ensure_ascii=False)
assert "sol6.pdf" in qaN, qaN
assert rN1["source"] == "https://olymp.mipt.ru/tasks6.pdf"
rN3 = [r for r in pN.catalog.data["phystech"] if r.get("num") == "3"
       and r.get("year") == 2025][0]
assert rN3["solution"] == "разбор случаев по параметру"

# --- 5.4 Явная датировка документа сильнее метаданных индекса ---
PAGES_2024HDR = ["Заключительный этап 2024 года", "11 класс. Вариант 1",
                 f"1. {T1}", f"3. {T3}", f"2. {T2}"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_2024HDR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_2024HDR)

class StubIndexDated:
    """Индекс «знает» год 2025 — но документ явно датирован 2024."""
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/dated.pdf", "year": 2025,
                 "grades": [grade]}]

pO = make_pipeline5("cp5dated", index=StubIndexDated())
FIX.stage_21(pO)
stO = pO.stage21_report["phystech"]
assert stO["tasks_added"] == 0, stO   # противоречие документа блокирует импорт
assert any("год не подтверждён" in json.dumps(g, ensure_ascii=False)
           for g in stO["gaps"]), stO["gaps"]

print("НАСЛЕДОВАНИЕ/ПОРЯДОК/ОСТАТОК/ДАТИРОВКА OK")
shutil.rmtree(TMP5)


# =====================================================================
# Часть 6: остатки разных вариантов не подавляют друг друга
# =====================================================================
TMP6 = Path(tempfile.mkdtemp())
SRC6 = TMP6 / "catalog"
SRC6.mkdir()
# два варианта, в каждом каталог имеет №1 и №3 (макс 3), №4 — хвост блока
v1a = mk("w1", 1, T1, status="AI_generated", solution="AI"); v1a["answer"] = "55"
v1b = mk("w2", 3, T3, status="AI_generated", solution="AI"); v1b["answer"] = "a > 5"
v2a = mk("w3", 1, V2T1, variant="2", status="AI_generated", solution="AI")
v2a["answer"] = "55"
v2b = mk("w4", 3, V2T3, variant="2", status="AI_generated", solution="AI")
v2b["answer"] = "a > 5"
(SRC6 / "phystech.json").write_text(
    json.dumps([v1a, v1b, v2a, v2b], ensure_ascii=False), encoding="utf-8")

PAGES_2VAR = ["11 класс. Вариант 1", f"1. {T1}", f"3. {T3}", f"4. {T4}",
             "11 класс. Вариант 2", f"1. {V2T1}", f"3. {V2T3}", f"4. {V2T3}x"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_2VAR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_2VAR)

class StubChat7:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        # задачи №1 и №3 — для подтверждения атрибуции w1/w2 (ответы совпадают)
        tasks = [{"num": "1", "text": T1, "answer": "55", "solution": "s1"},
                 {"num": "3", "text": T3, "answer": "a > 5", "solution": "s3"},
                 {"num": "4", "text": T4, "answer": "p", "solution": "s4"},
                 {"num": "4", "text": V2T3 + "x", "answer": "q", "solution": "s5"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": True, "tasks": tasks}

class StubIndex7:
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/two-vars.pdf", "year": year,
                 "grades": [grade], "variant": variant}]

args6 = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP6 / "cp6.json", source=str(SRC6),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pP = FIX.Pipeline(args6)
pP.deepseek_chat = StubChat7()
pP.deepseek_reasoner = StubReasoner6()   # №4 всегда unclear
pP.gemini = None
pP._source_index = StubIndex7()
FIX.stage_21(pP)
stP = pP.stage21_report["phystech"]
# ДВЕ записи остатка №4 — по одной на вариант, каждая со своей причиной
g4s = [g for g in stP["gaps"] if g.get("num") == 4]
assert len(g4s) == 2, g4s
assert {g.get("variant") for g in g4s} == {"1", "2"}, g4s
assert all(("не сверено" in json.dumps(g, ensure_ascii=False))
           or ("конфликт" in json.dumps(g, ensure_ascii=False)) for g in g4s), g4s
print("ОСТАТКИ ДВУХ ВАРИАНТОВ OK")
shutil.rmtree(TMP6)


# =====================================================================
# Часть 7: дробь-не-сезон, вариант без заголовков, гейт эквивалентности
# =====================================================================
# 7.1 «24/25» в условии — не сезон
assert not FIX._year_ok({}, ["11 класс", "Задача 1. Вычислите 24/25."], 2025)
assert FIX._year_ok({}, ["Отборочный этап 2024/25", "11 класс"], 2025)

TMP7 = Path(tempfile.mkdtemp())
SRC7 = TMP7 / "catalog"
SRC7.mkdir()
# почти одинаковые условия, но математика разная (знак)
T1_MINUS = "Задача один: найти сумму чисел от 1 до -10."
q1 = mk("q1", 1, T1_MINUS, status="AI_generated", solution="AI-решение")
q1["answer"] = "55"
(SRC7 / "phystech.json").write_text(json.dumps([q1], ensure_ascii=False), encoding="utf-8")

# 7.2 Беззаголовочный PDF + запрошенный вариант без подтверждения индексом
NOHDR = [f"1. {T1_MINUS}", f"2. {T2} [3 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(NOHDR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(NOHDR)

class StubIndexNoVar:
    """Индекс не подтверждает вариант (variant нет в метаданных)."""
    _cache = {"phystech": True}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return [{"url": "https://olymp.mipt.ru/nohdr.pdf", "year": year,
                 "grades": [grade]}]   # variant не указан

class StubChat8:
    """Задача №1 из PDF (та же формулировка, что в записи)."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "1", "text": T1_NO_SIGN, "answer": "55",
                  "solution": "сумма прогрессии"},
                 {"num": "2", "text": T2, "answer": "x", "solution": "s"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasoner8:
    """Отрицательный вердикт эквивалентности (другая математика)."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": False,
                    "reason": "знак отличается"}
        return {"verdict": "match"}

# вариант 2 у записи q1 — беззаголовочный PDF не должен ничего enrich-ить
q1v = dict(q1); q1v["variant"] = "2"
(SRC7 / "phystech.json").write_text(
    json.dumps([q1v, mk("q9", 3, T3, variant="2")], ensure_ascii=False),
    encoding="utf-8")

args7 = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP7 / "cp7.json", source=str(SRC7),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pQ = FIX.Pipeline(args7)
pQ.deepseek_chat = StubChat8()
pQ.deepseek_reasoner = StubReasoner8()
pQ.gemini = None
pQ._source_index = StubIndexNoVar()
FIX.stage_21(pQ)
stQ = pQ.stage21_report["phystech"]
assert stQ["tasks_added"] == 0, stQ
assert any("вариант не подтверждён" in json.dumps(g, ensure_ascii=False)
           for g in stQ["gaps"]), stQ["gaps"]

# 7.3 Гейт эквивалентности: другая математика — никакого обогащения дубля
T1_PLUS = "Задача один: найти сумму чисел от 1 до 10."   # без «со знаком минус»
HDR = ["11 класс. Вариант 2", f"1. {T1_PLUS} [3 балла]", f"3. {T3} [4 балла]",
       f"2. {T2} [3 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(HDR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(HDR)

class StubChat9:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "1", "text": T1_PLUS, "answer": "55",
                  "solution": "сумма арифметической прогрессии"},
                 {"num": "2", "text": T2, "answer": "x", "solution": "s2"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

args7b = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP7 / "cp7b.json", source=str(SRC7),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pR = FIX.Pipeline(args7b)
pR.deepseek_chat = StubChat9()
pR.deepseek_reasoner = StubReasoner8()   # эквивалентность = False
pR.gemini = None
pR._source_index = StubIndexNoVar()
FIX.stage_21(pR)
q_after = [r for r in pR.catalog.data["phystech"] if r.get("uid") == "q1"][0]
# ничего не изменилось: вариант, источник, решение, статус — прежние
assert q_after["variant"] == "2"
assert not (q_after.get("source") or "")
assert q_after["solution"] == "AI-решение"
assert q_after["status"] == "AI_generated"
# но needs_review от гейта зафиксирован
assert "needs_review" in json.dumps(q_after["qa"], ensure_ascii=False)

print("ДРОБЬ/ВАРИАНТ/ГЕЙТ OK")
shutil.rmtree(TMP7)


# =====================================================================
# Часть 8: атрибуция только при дословном совпадении (фаза А),
#          конфликт ответов с сохранением знаков
# =====================================================================
# 8.1 Фаза А: похожий текст с другой математикой — гейт эквивалентности
#             отклоняет, вариант НЕ проставляется (непрерывная нумерация →
#             фазы Б нет); сохранены все прежние поля, только needs_review
TMP8 = Path(tempfile.mkdtemp())
SRC8 = TMP8 / "catalog"
SRC8.mkdir()
T1_SIGN = "Задача один: найти сумму чисел от 1 до -10."     # знак минус
z1 = mk("z1", 1, T1_SIGN, status="AI_generated", solution="AI-решение")
z1["answer"] = "55"    # ответ совпадает — проверяем именно гейт условий
(SRC8 / "phystech.json").write_text(json.dumps([z1], ensure_ascii=False), encoding="utf-8")
T1_NO_SIGN = "Задача один: найти сумму чисел от 1 до 10."   # без минуса
PDF_SIGN = ["11 класс. Вариант 1", f"1. {T1_NO_SIGN} [3 балла]"]   # в PDF знака нет
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PDF_SIGN), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PDF_SIGN)

args8 = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP8 / "cp8.json", source=str(SRC8),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pS = FIX.Pipeline(args8)
pS.deepseek_chat = StubChat8()   # фаза Б не запустится (нумерация полная)
pS.deepseek_reasoner = StubReasoner8()   # эквивалентность = False
pS.gemini = None
pS._source_index = StubIndexNoVar()
FIX.stage_21(pS)
z_after = pS.catalog.data["phystech"][0]
assert not (z_after.get("variant") or ""), z_after
assert z_after["solution"] == "AI-решение"          # прежние поля целы
assert z_after["status"] == "AI_generated"
assert "правка отклонена гейтом эквивалентности" in \
    json.dumps(z_after["qa"], ensure_ascii=False), z_after["qa"]
print("ФАЗА А: ДОСЛОВНОСТЬ OK")

# 8.2 Конфликт ответов: Unicode-минус «−1» и «1» — РАЗНЫЕ ответы
#     (структурное сравнение, знаки сохраняются)
z2 = mk("z2", 1, T1_NO_SIGN, status="AI_generated", solution="AI-решение")
z2["answer"] = "\u22121"      # Unicode-минус (−1)
(SRC8 / "phystech.json").write_text(json.dumps([z2], ensure_ascii=False), encoding="utf-8")
args8b = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP8 / "cp8b.json", source=str(SRC8),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pT = FIX.Pipeline(args8b)
pT.deepseek_chat = StubChat8()
pT.deepseek_reasoner = StubReasoner6()   # эквивалентность = ok
pT.gemini = None
pT._source_index = StubIndexNoVar()
FIX.stage_21(pT)
z2_after = pT.catalog.data["phystech"][0]
assert not (z2_after.get("variant") or ""), z2_after
assert "конфликт ответов" in json.dumps(z2_after["qa"], ensure_ascii=False), \
    z2_after["qa"]
assert z2_after["solution"] == "AI-решение"

# 8.3 Конфликт: в PDF «1», в базе «-1» — различие знака теперь ВИДИМО
class StubChat10:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "2", "text": T2, "answer": "1", "solution": "s"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

z3 = mk("z3", 2, T2, status="AI_generated", solution="AI-решение")
z3["answer"] = "-1"          # в PDF ответ «1» — конфликт знака
(SRC8 / "phystech.json").write_text(json.dumps([z3], ensure_ascii=False), encoding="utf-8")
PDF3 = ["11 класс. Вариант 1", f"1. {T1_NO_SIGN}", f"2. {T2} [3 балла]",
        f"3. {T3} [4 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PDF3), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PDF3)
args8c = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP8 / "cp8c.json", source=str(SRC8),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pU = FIX.Pipeline(args8c)
pU.deepseek_chat = StubChat10()
pU.deepseek_reasoner = StubReasoner6()
pU.gemini = None
pU._source_index = StubIndexNoVar()
FIX.stage_21(pU)
z3_after = [r for r in pU.catalog.data["phystech"] if r.get("uid") == "z3"][0]
assert "конфликт ответов" in json.dumps(z3_after["qa"], ensure_ascii=False), \
    z3_after["qa"]
print("КОНФЛИКТ ОТВЕТОВ СО ЗНАКАМИ OK")
shutil.rmtree(TMP8)


# =====================================================================
# Часть 9: дроби не «склеиваются», хвост условия за 300-м символом
# =====================================================================
# структурные проверки нормализации ответов
assert FIX._answer_norm_strict("\\frac{1}{23}") != FIX._answer_norm_strict("\\frac{12}{3}")
assert FIX._answer_norm_strict("−1") == FIX._answer_norm_strict("-1")   # U+2212 == дефис
assert FIX._answer_norm_strict("−1") != FIX._answer_norm_strict("1")
# схожесть без удаления математики: дроби различаются
assert FIX._raw_similarity("\\frac{1}{23}", "\\frac{12}{3}") < 1.0

TMP9 = Path(tempfile.mkdtemp())
SRC9 = TMP9 / "catalog"
SRC9.mkdir()

# 9.1 Разные дроби: \frac{1}{23} в базе против \frac{12}{3} в PDF.
#     Нормализация «склеивает» их (frac123 == frac123) — предложение
#     создаётся, но подтверждение обязано его отклонить.
FRAC_BASE = "Вычислите сумму всех дробей вида \\frac{1}{23} в первых членах."
FRAC_PDF = "Вычислите сумму всех дробей вида \\frac{12}{3} в первых членах."
f1 = mk("f1", 1, FRAC_BASE, status="AI_generated", solution="AI-решение")
f1["answer"] = "7"
(SRC9 / "phystech.json").write_text(json.dumps([f1], ensure_ascii=False), encoding="utf-8")
PDF_FRAC = ["11 класс. Вариант 1", f"1. {FRAC_PDF} [3 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PDF_FRAC), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PDF_FRAC)

class StubChatFrac:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "1", "text": FRAC_PDF, "answer": "7",
                  "solution": "решение с дробью"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasonerFrac:
    """Дроби \frac{1}{23} и \frac{12}{3} математически РАЗНЫЕ."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            data = json.loads(payload)
            if "\\frac{1}{23}" in str(data.get("old", "")) and \
               "\\frac{12}{3}" in str(data.get("new", "")):
                return {"ok": True, "equivalent": False,
                        "reason": "разные дроби: 1/23 и 12/3"}
            return {"ok": True, "equivalent": True}
        return {"verdict": "match"}

args9 = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP9 / "cp9.json", source=str(SRC9),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pF = FIX.Pipeline(args9)
pF.deepseek_chat = StubChatFrac()
pF.deepseek_reasoner = StubReasonerFrac()
pF.gemini = None
pF._source_index = StubIndexNoVar()
FIX.stage_21(pF)
f_after = pF.catalog.data["phystech"][0]
assert not (f_after.get("variant") or ""), f_after.get("variant")
assert f_after["solution"] == "AI-решение" and f_after["status"] == "AI_generated"
assert "needs_review" in json.dumps(f_after["qa"], ensure_ascii=False)
print("ДРОБИ НЕ СКЛЕИВАЮТСЯ OK")

# 9.2 Различие условия ЗА 300-м символом: голова совпадает, хвост другой.
#     Совпадение по первым 300 символам — НЕ подтверждение.
HEAD = "Дана последовательность чисел, в которой каждый член больше "  \
       "предыдущего. Известно, что первый член равен единице, а "  \
       "разность прогрессии положительна и составляет менее десятой "  \
       "доли первого члена. Требуется определить, при каких значениях "  \
       "параметра сумма первых членов не превысит заданного числа, "  \
       "если известно, что всего в последовательности ровно двадцать "
TAIL_BASE = "членов и все они являются целыми числами."
TAIL_PDF = "членов и ровно половина из них делится на три."
t_base = mk("t1", 1, HEAD + TAIL_BASE, status="AI_generated", solution="AI-решение")
t_base["answer"] = "20"
(SRC9 / "phystech.json").write_text(
    json.dumps([t_base], ensure_ascii=False), encoding="utf-8")
assert len(HEAD + TAIL_BASE) > 320, "хвост должен быть за 300-м символом"
PDF_TAIL = ["11 класс. Вариант 1", f"1. {HEAD}{TAIL_PDF} [3 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PDF_TAIL), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PDF_TAIL)

class StubChatTail:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "1", "text": HEAD + TAIL_PDF, "answer": "20",
                  "solution": "решение"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasonerTail:
    """Хвост условия отличается — условия не эквивалентны."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            data = json.loads(payload)
            if TAIL_BASE in str(data.get("old", "")) and \
               TAIL_PDF in str(data.get("new", "")):
                return {"ok": True, "equivalent": False,
                        "reason": "хвост условия отличается"}
            return {"ok": True, "equivalent": True}
        return {"verdict": "match"}

args9b = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP9 / "cp9b.json", source=str(SRC9),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pV = FIX.Pipeline(args9b)
pV.deepseek_chat = StubChatTail()
pV.deepseek_reasoner = StubReasonerTail()
pV.gemini = None
pV._source_index = StubIndexNoVar()
FIX.stage_21(pV)
t_after = pV.catalog.data["phystech"][0]
assert not (t_after.get("variant") or ""), t_after.get("variant")
assert "needs_review" in json.dumps(t_after["qa"], ensure_ascii=False)
assert t_after["text"] == HEAD + TAIL_BASE   # условие записи не искажено
print("ХВОСТ ЗА 300-М СИМВОЛОМ OK")
shutil.rmtree(TMP9)


# =====================================================================
# Часть 10: разные условия одного номера в разных вариантах; \Gamma ≠ \gamma
# =====================================================================
TMP10 = Path(tempfile.mkdtemp())
SRC10 = TMP10 / "catalog"
SRC10.mkdir()

TA1 = "Вариант один, задача первый про прогрессии."
TB1 = "Вариант один, задача второй про неравенства."
TB2 = "Вариант два, задача второй про треугольники."   # ДРУГОЕ условие №2
g1 = mk("g1", 1, TA1, status="AI_generated", solution="AI")
g1["answer"] = "10"
(SRC10 / "phystech.json").write_text(json.dumps([g1], ensure_ascii=False), encoding="utf-8")

TC1 = "Вариант один, задача третий про функции."
g2 = mk("g2", 3, TC1, status="AI_generated", solution="AI")
g2["answer"] = "40"
(SRC10 / "phystech.json").write_text(
    json.dumps([g1, g2], ensure_ascii=False), encoding="utf-8")
# блоки ЦЕЛИКОМ, порядок вариантов разный (реалистичная перестановка)
PAGES_2V = ["11 класс. Вариант 1", f"1. {TA1} [3 балла]", f"2. {TB1} [4 балла]",
           "11 класс. Вариант 2", f"2. {TB2} [4 балла]"]

class StubChat10:
    """Возвращает задачи того блока, чьи тексты есть в doc_text."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "1", "text": TA1, "answer": "10", "solution": "s1"},
                    {"num": "2", "text": TB1, "answer": "20", "solution": "s2"},
                    {"num": "2", "text": TB2, "answer": "30", "solution": "s3"},
                    {"num": "3", "text": TC1, "answer": "40", "solution": "s4"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasoner10:
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        return {"verdict": "match"}

def run10(pages):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(pages), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args10 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP10 / f"cp10_{abs(hash(tuple(pages))) % 1000}.json",
        source=str(SRC10), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p10 = FIX.Pipeline(args10)
    p10.deepseek_chat = StubChat10()
    p10.deepseek_reasoner = StubReasoner10()
    p10.gemini = None
    p10._source_index = StubIndexNoVar()
    FIX.stage_21(p10)
    return p10

# прямой порядок блоков и переставленный (блоки целиком) — результат одинаков
PAGES_2V_SWAP = ["11 класс. Вариант 2", f"2. {TB2} [4 балла]",
                 "11 класс. Вариант 1", f"1. {TA1} [3 балла]",
                 f"2. {TB1} [4 балла]"]
pA1 = run10(PAGES_2V)
pA2 = run10(PAGES_2V_SWAP)
def snapshot(pipeline):
    return sorted((str(r.get("variant") or ""), str(r.get("num")), r["text"][:20])
                  for r in pipeline.catalog.data["phystech"])
assert snapshot(pA1) == snapshot(pA2), (snapshot(pA1), snapshot(pA2))
snap = snapshot(pA1)
# обе задачи №2 импортированы, КАЖДАЯ со своим вариантом
assert ("1", "2", TB1[:20]) in snap, snap
assert ("2", "2", TB2[:20]) in snap, snap
# g1 атрибуцирован вариантом 1 (дубль задачи №1 блока 1)
g1_after = [r for r in pA1.catalog.data["phystech"] if r["uid"] == "g1"][0]
assert g1_after.get("variant") == "1", g1_after.get("variant")
# дыра №2 не осталась висеть в группе без варианта
gaps_v2 = [g for g in pA1.stage21_report["phystech"]["gaps"]]
assert not any(g.get("num") == 2 for g in gaps_v2), gaps_v2
print("ДВА ВАРИАНТА ОДНОГО НОМЕРА OK")

# 10.2 \Gamma и \gamma — РАЗНЫЕ ответы (регистр не склеивается)
assert FIX._answer_norm_strict("\\Gamma") != FIX._answer_norm_strict("\\gamma")
assert FIX._answer_norm_strict("\\Delta") != FIX._answer_norm_strict("\\delta")
gam = mk("gam", 1, TA1, status="AI_generated", solution="AI")
gam["answer"] = "\\Gamma"     # в PDF ответ \gamma — конфликт
(SRC10 / "phystech.json").write_text(
    json.dumps([gam], ensure_ascii=False), encoding="utf-8")

class StubChatGamma:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        tasks = [{"num": "1", "text": TA1, "answer": "\\gamma",
                  "solution": "s"}]
        tasks = [t for t in tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

argsG = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP10 / "cp10g.json", source=str(SRC10),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pG = FIX.Pipeline(argsG)
pG.deepseek_chat = StubChatGamma()
pG.deepseek_reasoner = StubReasoner10()
pG.gemini = None
pG._source_index = StubIndexNoVar()
FIX.stage_21(pG)
gam_after = pG.catalog.data["phystech"][0]
assert not (gam_after.get("variant") or ""), gam_after.get("variant")
assert "конфликт ответов" in json.dumps(gam_after["qa"], ensure_ascii=False), \
    gam_after["qa"]
print("\\Gamma НЕ РАВНО \\gamma OK")
shutil.rmtree(TMP10)

# =====================================================================
# Часть 11: остатки ПО ВАРИАНТАМ; неоднозначность не «заражает» другие
# =====================================================================
TMP11 = Path(tempfile.mkdtemp())
SRC11 = TMP11 / "catalog"
SRC11.mkdir()

RX = "Задача два из варианта один про векторы."
RY = "Задача два из варианта два про комбинации."   # ДРУГОЕ условие №2
H1 = "Задача один про треугольник Паскаля."          # в PDF отсутствует
H3 = "Задача три про матрицы и определители."        # в PDF отсутствует
h1 = mk("h1", 1, H1, status="AI_generated", solution="AI")
h1["answer"] = "11"
h3 = mk("h3", 3, H3, status="AI_generated", solution="AI")
h3["answer"] = "31"
(SRC11 / "phystech.json").write_text(json.dumps([h1, h3], ensure_ascii=False), encoding="utf-8")

PAGES_RV = ["11 класс. Вариант 1", f"2. {RX} [4 балла]",
           "11 класс. Вариант 2", f"2. {RY} [4 балла]"]

class StubChat11:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "2", "text": RX, "answer": "x", "solution": "s-векторы"},
                     {"num": "2", "text": RY, "answer": "y", "solution": "s-комбинации"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasoner11:
    """№2 варианта 1 (RX) — неопределённый вердикт → отказ; RY — match."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        data = json.loads(payload)
        if data.get("text", "").startswith(RX):
            return {"verdict": "unclear", "reason": "не уверен"}
        return {"verdict": "match"}

def run11(pages):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(pages), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args11 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP11 / f"cp11_{abs(hash(tuple(pages))) % 997}.json",
        source=str(SRC11), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p11 = FIX.Pipeline(args11)
    p11.deepseek_chat = StubChat11()
    p11.deepseek_reasoner = StubReasoner11()
    p11.gemini = None
    p11._source_index = StubIndexNoVar()
    FIX.stage_21(p11)
    return p11

PAGES_RV_SWAP = ["11 класс. Вариант 2", f"2. {RY} [4 балла]",
                 "11 класс. Вариант 1", f"2. {RX} [4 балла]"]
pR1 = run11(PAGES_RV)
pR2 = run11(PAGES_RV_SWAP)

def snap11(pipeline):
    return sorted((str(r.get("variant") or ""), str(r.get("num")), r["text"][:20])
                  for r in pipeline.catalog.data["phystech"])
assert snap11(pR1) == snap11(pR2), (snap11(pR1), snap11(pR2))
# №2 варианта 2 импортирована со своим вариантом
assert ("2", "2", RY[:20]) in snap11(pR1), snap11(pR1)
# отклонённая №2 варианта 1 — ДЫРА со своим вариантом и причиной
g11 = pR1.stage21_report["phystech"]["gaps"]
assert any(g.get("variant") == "1" and g.get("num") == 2 and
           "не сверено" in json.dumps(g, ensure_ascii=False) for g in g11), g11
# принятая №2 варианта 2 НЕ скрыла дыру варианта 1 — и наоборот
assert not any(g.get("variant") == "2" and g.get("num") == 2 for g in g11), g11
# в смешанной группе не осталось «общей» дыры №2
assert not any((g.get("variant") or "") == "" and g.get("num") == 2
               for g in g11), g11
print("ОСТАТКИ ПО ВАРИАНТАМ OK")

# 11.2 Неоднозначность не «заражает» другие варианты: одинаковое условие
#     №2 в вариантах 1/2 — needs_review без варианта; ДРУГОЕ условие №2
#     варианта 3 сохраняет вариант 3
SAME2 = "Общая задача два про делимость чисел."
OTHER2 = "Задача два варианта три про графы."
(SRC11 / "phystech.json").write_text(json.dumps([h1, h3], ensure_ascii=False),
                                     encoding="utf-8")
PAGES_3V = ["11 класс. Вариант 1", f"2. {SAME2} [3 балла]",
           "11 класс. Вариант 2", f"2. {SAME2} [3 балла]",
           "11 класс. Вариант 3", f"2. {OTHER2} [3 балла]"]

class StubChat12:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "2", "text": SAME2, "answer": "d", "solution": "s"},
                     {"num": "2", "text": OTHER2, "answer": "g", "solution": "s"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasoner12:
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        return {"verdict": "match"}

def run12(pages):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(pages), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args12 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP11 / f"cp12_{abs(hash(tuple(pages))) % 991}.json",
        source=str(SRC11), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p12 = FIX.Pipeline(args12)
    p12.deepseek_chat = StubChat12()
    p12.deepseek_reasoner = StubReasoner12()
    p12.gemini = None
    p12._source_index = StubIndexNoVar()
    FIX.stage_21(p12)
    return p12

PAGES_3V_SWAP = ["11 класс. Вариант 3", f"2. {OTHER2} [3 балла]",
                 "11 класс. Вариант 1", f"2. {SAME2} [3 балла]",
                 "11 класс. Вариант 2", f"2. {SAME2} [3 балла]"]
pW1 = run12(PAGES_3V)
pW2 = run12(PAGES_3V_SWAP)
assert snap11(pW1) == snap11(pW2), (snap11(pW1), snap11(pW2))
w_snap = snap11(pW1)
# задача №2 варианта 3 сохраняет вариант 3 (не «заражена» неоднозначностью)
assert ("3", "2", OTHER2[:20]) in w_snap, w_snap
# общая задача №2 вариантов 1/2 — без варианта, с needs_review
same_rec = [r for r in pW1.catalog.data["phystech"] if r["text"] == SAME2]
assert len(same_rec) == 1 and not (same_rec[0].get("variant") or ""), same_rec
assert "needs_review" in json.dumps(same_rec[0]["qa"], ensure_ascii=False)
assert any("неоднозначно" in json.dumps(g, ensure_ascii=False)
           for g in pW1.stage21_report["phystech"]["gaps"])
# 11.3 счётчики: вариант 3 закрыт независимо; варианты 1/2 НЕ считаются
# закрытыми (неоднозначная задача не закрывает конкретный вариант)
st11 = pW1.stage21_report["phystech"]
assert st11["variants"] == 1 and st11["variants_partial"] == 0, st11
g11_2 = st11["gaps"]
assert {g.get("variant") for g in g11_2 if g.get("num") == 2} == {"1", "2"}, g11_2
assert not any(g.get("variant") == "3" for g in g11_2), g11_2
print("НЕОДНОЗНАЧНОСТЬ НЕ ЗАРАЖАЕТ OK")
shutil.rmtree(TMP11)

# =====================================================================
# Часть 12: хвост подтверждённого блока; безвариантный блок; единый остаток
# =====================================================================
TMP12 = Path(tempfile.mkdtemp())
SRC12 = TMP12 / "catalog"
SRC12.mkdir()

K1 = "Задача первый про арифметику."
K2 = "Задача второй про геометрию."
K3 = "Задача третий про теорию чисел."
K4 = "Задача четвёртый про комбинаторику."

# --- 12.1 Непрерывная нумерация: найденный в фазе А блок №1–4 ---
#     импортируется ЦЕЛИКОМ (хвост за пределами каталога)
k1 = mk("k1", 1, K1, status="AI_generated", solution="AI")
k1["answer"] = "5"
(SRC12 / "phystech.json").write_text(json.dumps([k1], ensure_ascii=False), encoding="utf-8")

PAGES_K = ["11 класс. Вариант 1", f"1. {K1} [3 балла]", f"2. {K2} [3 балла]",
           f"3. {K3} [4 балла]", f"4. {K4} [5 балла]"]

class StubChatK:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "1", "text": K1, "answer": "5", "solution": "s1"},
                     {"num": "2", "text": K2, "answer": "6", "solution": "s2"},
                     {"num": "3", "text": K3, "answer": "7", "solution": "s3"},
                     {"num": "4", "text": K4, "answer": "8", "solution": "s4"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

class StubReasonerK:
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        return {"verdict": "match"}

def run12p(pages):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(pages), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args12 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP12 / f"cp12x_{abs(hash(tuple(pages))) % 983}.json",
        source=str(SRC12), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p12 = FIX.Pipeline(args12)
    p12.deepseek_chat = StubChatK()
    p12.deepseek_reasoner = StubReasonerK()
    p12.gemini = None
    p12._source_index = StubIndexNoVar()
    FIX.stage_21(p12)
    return p12

pK = run12p(PAGES_K)
k_recs = pK.catalog.data["phystech"]
# №1 атрибуцирован и обогащён; №2–4 импортированы (хвост блока целиком)
k1_after = [r for r in k_recs if r["uid"] == "k1"][0]
assert k1_after.get("variant") == "1", k1_after.get("variant")
assert k1_after["status"] == "official_found" and k1_after["solution"] == "s1"
assert sorted(str(r["num"]) for r in k_recs) == ["1", "2", "3", "4"], k_recs
assert all(r.get("variant") == "1" for r in k_recs), k_recs
stK = pK.stage21_report["phystech"]
assert stK["tasks_added"] == 3, stK
assert stK["variants"] == 1 and stK["variants_partial"] == 0, stK
assert not [g for g in stK["gaps"]], stK["gaps"]
print("ХВОСТ ПОДТВЕРЖДЁННОГО БЛОКА OK")

# --- 12.2 Безвариантный блок: отклонённый хвост остаётся в отчёте ---
n1 = mk("n1", 1, K1, status="AI_generated", solution="AI")
n1["answer"] = "5"
n3 = mk("n3", 3, K3, status="AI_generated", solution="AI")
n3["answer"] = "7"
(SRC12 / "phystech.json").write_text(
    json.dumps([n1, n3], ensure_ascii=False), encoding="utf-8")

class StubReasonerK4:
    """№4 — неопределённый вердикт (отказ)."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        data = json.loads(payload)
        if data.get("text", "").startswith(K4):
            return {"verdict": "unclear", "reason": "не уверен"}
        return {"verdict": "match"}

PAGES_NOVAR = [f"1. {K1} [3 балла]", f"2. {K2} [3 балла]",
              f"3. {K3} [4 балла]", f"4. {K4} [5 балла]"]
FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_NOVAR), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_NOVAR)
argsN = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP12 / "cp12n.json", source=str(SRC12),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pN2 = FIX.Pipeline(argsN)
pN2.deepseek_chat = StubChatK()
pN2.deepseek_reasoner = StubReasonerK4()
pN2.gemini = None
pN2._source_index = StubIndexNoVar()
FIX.stage_21(pN2)
stN = pN2.stage21_report["phystech"]
# №2 импортирована; диапазон 1–3 непрерывен, но отклонённая №4 — в отчёте
n_recs = pN2.catalog.data["phystech"]
assert sorted(str(r["num"]) for r in n_recs) == ["1", "2", "3"], n_recs
assert stN["tasks_added"] == 1, stN
assert any(g.get("num") == 4 and "не сверено" in json.dumps(g, ensure_ascii=False)
           for g in stN["gaps"]), stN["gaps"]
# счётчик: вариант (здесь безымянный блок) ЧАСТИЧНЫЙ — есть отклонённая №4
assert stN["variants_partial"] == 1 and stN["variants"] == 0, stN
print("БЕЗВАРИАНТНЫЙ ХВОСТ OK")
shutil.rmtree(TMP12)


# =====================================================================
# Часть 13: продолжение хвоста между запусками; variant модели vs заголовок
# =====================================================================
TMP13 = Path(tempfile.mkdtemp())
SRC13 = TMP13 / "catalog"
SRC13.mkdir()

# --- 13.1 Отклонённая задача хвоста доступна для повтора ПОСЛЕ
#     перезагрузки каталога и checkpoint (variant уже установлен,
#     нумерация непрерывна — только pending из checkpoint возвращает группу)
c1 = mk("c1", 1, K1, status="AI_generated", solution="AI")
c1["answer"] = "5"
(SRC13 / "phystech.json").write_text(json.dumps([c1], ensure_ascii=False), encoding="utf-8")

class StubReasonerRun1:
    """№4 — неопределённый вердикт (первый запуск)."""
    name, model = "deepseek-reasoner", "deepseek-reasoner"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        if "equivalent" in prompt or "эквивалент" in prompt:
            return {"ok": True, "equivalent": True}
        data = json.loads(payload)
        if data.get("text", "").startswith(K4):
            return {"verdict": "unclear", "reason": "не уверен"}
        return {"verdict": "match"}

def run13(reasoner, cp_name):
    args13 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP13 / cp_name, source=str(SRC13),
        slug=None, limit=None, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p13 = FIX.Pipeline(args13)
    p13.deepseek_chat = StubChatK()
    p13.deepseek_reasoner = reasoner
    p13.gemini = None
    p13._source_index = StubIndexNoVar()
    FIX.stage_21(p13)
    return p13

FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_K), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_K)

# запуск 1: №2–3 импортированы, №4 отклонена
pR = run13(StubReasonerRun1(), "cp13.json")
assert sorted(str(r["num"]) for r in pR.catalog.data["phystech"]) == ["1", "2", "3"]
# сохраняем каталог и checkpoint (как в реальном прогоне)
(SRC13 / "phystech.json").write_text(
    json.dumps(pR.catalog.data["phystech"], ensure_ascii=False), encoding="utf-8")
pR.checkpoint.save()
pend = pR.checkpoint.data.get("stage21_pending", {})
assert any((pr[1] if isinstance(pr, (list, tuple)) else pr) == 4
           for prs in pend.values() for pr in prs), pend   # №4 в очереди

# запуск 2: ПЕРЕЗАГРУЗКА (новый Pipeline, тот же checkpoint и каталог);
# №4 теперь подтверждена reasoner — импортирована
pR2 = run13(StubReasonerK(), "cp13.json")
recs13 = pR2.catalog.data["phystech"]
assert sorted(str(r["num"]) for r in recs13) == ["1", "2", "3", "4"], recs13
assert all(r.get("variant") == "1" for r in recs13), recs13
r4 = [r for r in recs13 if str(r["num"]) == "4"][0]
assert r4["status"] == "official_found" and r4["solution"] == "s4"
# очередь повтора очищена
assert not pR2.checkpoint.data.get("stage21_pending"), \
    pR2.checkpoint.data.get("stage21_pending")
print("ПРОДОЛЖЕНИЕ ХВОСТА МЕЖДУ ЗАПУСКАМИ OK")

# --- 13.2 Поле variant модели противоречит заголовку блока ---
#     («Вариант 1» в PDF, модель возвращает "variant": "2"):
#     приоритет у заголовка; противоречие — отметка, НЕ атрибуция
m1 = mk("m1", 1, K1, status="AI_generated", solution="AI")
m1["answer"] = "5"
m3 = mk("m3", 3, K3, status="AI_generated", solution="AI")
m3["answer"] = "7"
(SRC13 / "phystech.json").write_text(
    json.dumps([m1, m3], ensure_ascii=False), encoding="utf-8")

PAGES_V1 = ["11 класс. Вариант 1", f"1. {K1} [3 балла]", f"2. {K2} [3 балла]",
            f"3. {K3} [4 балла]"]

class StubChatV:
    """Верное условие/ответ/решение, но variant модели = «2» (конфликт)."""
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "1", "text": K1, "answer": "5", "solution": "s1",
                      "variant": "2"},
                     {"num": "2", "text": K2, "answer": "6", "solution": "s2",
                      "variant": "2"},
                     {"num": "3", "text": K3, "answer": "7", "solution": "s3",
                      "variant": "2"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

FIX._fetch_doc_result = lambda url: (
    {"ok": True, "pages": list(PAGES_V1), "http_code": "200",
     "content_type": "application/pdf", "final_url": url, "error": ""})
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_V1)
argsV = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP13 / "cp13v.json", source=str(SRC13),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pV = FIX.Pipeline(argsV)
pV.deepseek_chat = StubChatV()
pV.deepseek_reasoner = StubReasonerK()
pV.gemini = None
pV._source_index = StubIndexNoVar()
FIX.stage_21(pV)
v_recs = pV.catalog.data["phystech"]
# ВСЕ записи — вариант 1 (заголовок блока), вариант «2» нигде не записан
assert all(r.get("variant") == "1" for r in v_recs), v_recs
assert not any(r.get("variant") == "2" for r in v_recs)
# противоречие зафиксировано отметкой
assert any("противоречит заголовку блока" in json.dumps(r["qa"], ensure_ascii=False)
           for r in v_recs)
# вариант 1 закрыт (№2 импортирована с вариантом 1, а не 2)
stV = pV.stage21_report["phystech"]
assert stV["tasks_added"] == 1 and stV["variants"] == 1, stV
assert not [g for g in stV["gaps"]], stV["gaps"]
print("VARIANT МОДЕЛИ НЕ ПЕРЕКРЫВАЕТ ЗАГОЛОВОК OK")
shutil.rmtree(TMP13)


# =====================================================================
# Часть 14: очередь переживает «пустой» кандидат, ранний выход, --limit=варианты
# =====================================================================
TMP14 = Path(tempfile.mkdtemp())
SRC14 = TMP14 / "catalog"
SRC14.mkdir()

# --- 14.1 Задача из очереди не «закрывается» отсутствием в новом
#     кандидате: pending сохраняется до подтверждённого закрытия
q1 = mk("q1", 1, K1, status="AI_generated", solution="AI")
q1["answer"] = "5"
(SRC14 / "phystech.json").write_text(json.dumps([q1], ensure_ascii=False), encoding="utf-8")

PAGES_K123 = ["11 класс. Вариант 1", f"1. {K1} [3 балла]", f"2. {K2} [3 балла]",
              f"3. {K3} [4 балла]"]          # №4 в этом PDF нет

class StubChatK123:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "1", "text": K1, "answer": "5", "solution": "s1"},
                     {"num": "2", "text": K2, "answer": "6", "solution": "s2"},
                     {"num": "3", "text": K3, "answer": "7", "solution": "s3"},
                     {"num": "4", "text": K4, "answer": "8", "solution": "s4"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

def run14(pages, chat, reasoner, cp_name):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(pages), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args14 = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP14 / cp_name, source=str(SRC14),
        slug=None, limit=None, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    p14 = FIX.Pipeline(args14)
    p14.deepseek_chat = chat
    p14.deepseek_reasoner = reasoner
    p14.gemini = None
    p14._source_index = StubIndexNoVar()
    FIX.stage_21(p14)
    return p14

# запуск 1: полный блок, №4 отклонена → каталог 1–3, pending (1, 4)
pX1 = run14(PAGES_K, StubChatK(), StubReasonerRun1(), "cp14.json")
assert sorted(str(r["num"]) for r in pX1.catalog.data["phystech"]) == ["1", "2", "3"]
(SRC14 / "phystech.json").write_text(
    json.dumps(pX1.catalog.data["phystech"], ensure_ascii=False), encoding="utf-8")
pX1.checkpoint.save()

# запуск 2 (перезагрузка): PDF только №1–3 — №4 НЕ импортирована,
# но и НЕ «закрыта»: остаётся в очереди с причиной
pX2 = run14(PAGES_K123, StubChatK123(), StubReasonerK(), "cp14.json")
assert not [r for r in pX2.catalog.data["phystech"] if str(r["num"]) == "4"]
pend2 = pX2.checkpoint.data.get("stage21_pending", {})
assert any(pr[1] == 4 for prs in pend2.values() for pr in prs), pend2
gX2 = pX2.stage21_report["phystech"]["gaps"]
assert any(g.get("num") == 4 and "не найдена в новом кандидате"
           in json.dumps(g, ensure_ascii=False) for g in gX2), gX2
(SRC14 / "phystech.json").write_text(
    json.dumps(pX2.catalog.data["phystech"], ensure_ascii=False), encoding="utf-8")
pX2.checkpoint.save()

# запуск 3 (перезагрузка): полный PDF — №4 импортирована, очередь очищена
pX3 = run14(PAGES_K, StubChatK(), StubReasonerK(), "cp14.json")
assert sorted(str(r["num"]) for r in pX3.catalog.data["phystech"]) == \
    ["1", "2", "3", "4"]
assert not pX3.checkpoint.data.get("stage21_pending")
print("ОЧЕРЕДЬ ПЕРЕЖИВАЕТ ПУСТОЙ КАНДИДАТ OK")

# --- 14.2 Ранний выход: хвост обнаружен в фазе А, но фаза Б не получила
#     кандидатов — очередь сохраняется и обрабатывается после перезагрузки
e1 = mk("e1", 1, K1, status="AI_generated", solution="AI")
e1["answer"] = "5"   # совпадает с PDF — атрибуция подтверждается
(SRC14 / "phystech.json").write_text(json.dumps([e1], ensure_ascii=False),
                                     encoding="utf-8")

class StubIndexOnce:
    """Первая выборка (фаза А) даёт PDF, дальнейшие (фаза Б) — пусто."""
    _cache = {"phystech": True}
    def __init__(self):
        self.calls = 0
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        self.calls += 1
        if self.calls <= 1:
            return [{"url": "https://olymp.mipt.ru/x.pdf", "year": year,
                     "grades": [grade]}]
        return []

argsE = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP14 / "cp14e.json", source=str(SRC14),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pE1 = FIX.Pipeline(argsE)
pE1.deepseek_chat = StubChatK()
pE1.deepseek_reasoner = StubReasonerK()
pE1.gemini = None
pE1._source_index = StubIndexOnce()
FIX.stage_21(pE1)
# №2–4 НЕ импортированы (кандидатов в фазе Б не было), но хвост в очереди
assert sorted(str(r["num"]) for r in pE1.catalog.data["phystech"]) == ["1"]
pendE = pE1.checkpoint.data.get("stage21_pending", {})
assert pendE, "хвост обязан сохраниться даже без кандидатов в фазе Б"
(SRC14 / "phystech.json").write_text(
    json.dumps(pE1.catalog.data["phystech"], ensure_ascii=False), encoding="utf-8")
pE1.checkpoint.save()

# перезагрузка: индекс снова даёт PDF — хвост обработан
argsE2 = types.SimpleNamespace(
    dry_run=False, checkpoint=TMP14 / "cp14e.json", source=str(SRC14),
    slug=None, limit=None, stages_set={21}, workers=2, resume=False,
    rebuild_index=True)
pE2 = FIX.Pipeline(argsE2)
pE2.deepseek_chat = StubChatK()
pE2.deepseek_reasoner = StubReasonerK()
pE2.gemini = None
pE2._source_index = StubIndexNoVar()
FIX.stage_21(pE2)
assert sorted(str(r["num"]) for r in pE2.catalog.data["phystech"]) == \
    ["1", "2", "3", "4"]
assert not pE2.checkpoint.data.get("stage21_pending")
print("РАННИЙ ВЫХОД СОХРАНЯЕТ ОЧЕРЕДЬ OK")

# --- 14.3 --limit — число ВАРИАНТОВ: безвариантная группа с блоками
#     двух вариантов обрабатывает один, второй — в очередь и после
#     перезагрузки
PA1 = "Задача один из варианта один про прогрессии."
PA2 = "Задача два из варианта один про неравенства."
PB2 = "Задача два из варианта два про треугольники."
P3X = "Задача третий про матрицы."   # в PDF отсутствует
s1v = mk("s1", 1, PA1, status="AI_generated", solution="AI")
s1v["answer"] = "5"
(SRC14 / "phystech.json").write_text(
    json.dumps([mk("s3", 3, P3X), s1v], ensure_ascii=False),
    encoding="utf-8")
PAGES_2VAR2 = ["11 класс. Вариант 1", f"1. {PA1} [3 балла]", f"2. {PA2} [3 балла]",
              "11 класс. Вариант 2", f"2. {PB2} [4 балла]"]

class StubChatL:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        data = json.loads(payload)
        doc = data.get("doc_text", "")
        all_tasks = [{"num": "1", "text": PA1, "answer": "5", "solution": "sa1"},
                     {"num": "2", "text": PA2, "answer": "6", "solution": "sa2"},
                     {"num": "2", "text": PB2, "answer": "7", "solution": "sb2"}]
        tasks = [t for t in all_tasks if t["text"][:25] in doc]
        return {"ok": bool(tasks), "tasks": tasks}

def run14l(limit, cp_name):
    FIX._fetch_doc_result = lambda url: (
        {"ok": True, "pages": list(PAGES_2VAR2), "http_code": "200",
         "content_type": "application/pdf", "final_url": url, "error": ""})
    FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_2VAR2)
    argsL = types.SimpleNamespace(
        dry_run=False, checkpoint=TMP14 / cp_name, source=str(SRC14),
        slug=None, limit=limit, stages_set={21}, workers=2, resume=False,
        rebuild_index=True)
    pL = FIX.Pipeline(argsL)
    pL.deepseek_chat = StubChatL()
    pL.deepseek_reasoner = StubReasonerK()
    pL.gemini = None
    pL._source_index = StubIndexNoVar()
    FIX.stage_21(pL)
    return pL

# запуск 1 (--limit 1): обработан ТОЛЬКО вариант 1; вариант 2 — в очереди
pL1 = run14l(1, "cp14l.json")
l_recs = pL1.catalog.data["phystech"]
assert sorted(str(r["num"]) for r in l_recs) == ["1", "2", "3"], l_recs
assert all(r.get("variant") == "1" for r in l_recs if str(r["num"]) != "3")
assert not any(r["text"] == PB2 for r in l_recs)   # №2 варианта 2 НЕ импортирована
pendL = pL1.checkpoint.data.get("stage21_pending", {})
assert any(pr[1] == 2 and pr[0] == "2" for prs in pendL.values() for pr in prs), pendL
assert any(g.get("variant") == "2" and "--limit" in json.dumps(g, ensure_ascii=False)
           for g in pL1.stage21_report["phystech"]["gaps"])
(SRC14 / "phystech.json").write_text(
    json.dumps(l_recs, ensure_ascii=False), encoding="utf-8")
pL1.checkpoint.save()

# запуск 2 (перезагрузка, тот же checkpoint): вариант 2 обработан
pL2 = run14l(None, "cp14l.json")
l2 = pL2.catalog.data["phystech"]
pb = [r for r in l2 if r["text"] == PB2]
assert len(pb) == 1 and pb[0].get("variant") == "2", l2
assert not pL2.checkpoint.data.get("stage21_pending")
print("--LIMIT СЧИТАЕТ ВАРИАНТЫ OK")
shutil.rmtree(TMP14)

# Часть 15: порог атрибуции 0.9, честный отчёт, третий запуск очереди
print("\nЧасть 15: порог 0.9 / честный отчёт / третий запуск")

# --- 15.1: сходство 0.6-0.9 НЕ атрибутирует (порог финальной атрибуции 0.9)
K1v = "Задача первый про арифметику и прогрессии с целыми числами"
# разный регистр: нормализация его стирает (предложение проходит,
# contained = 1.0), но raw-схожесть 0.62 — ниже порога 0.9
K1cat = "ЗаДаЧа пЕрВый ПрО аРиФмЕтИкУ и ПрОгРеСсИи с ЦеЛыМи чИсЛаМи"
assert 0.6 <= FIX._raw_similarity(K1cat, K1v) < 0.9   # кандидат, но не атрибуция
assert FIX._text_contained(K1cat, "11 класс. Вариант 1\n1. " + K1v) >= 0.9

class StubChatSim:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        doc = json.loads(payload).get("doc_text", "")
        tasks = [{"num": "1", "text": K1v, "answer": "5", "solution": "s1"}]
        return {"ok": True, "tasks": [t for t in tasks if t["text"][:20] in doc]}

TMP15 = Path(tempfile.mkdtemp()); SRC15 = TMP15 / "catalog"; SRC15.mkdir()
sim1 = mk("sim1", 1, K1cat, status="AI_generated", solution="AI")
sim1["answer"] = "5"
(SRC15 / "phystech.json").write_text(json.dumps([sim1], ensure_ascii=False),
                                     encoding="utf-8")

def run15(pages, cp_name):
    FIX._fetch_doc_result = lambda url: {"ok": True, "pages": list(pages),
        "http_code": "200", "content_type": "application/pdf",
        "final_url": url, "error": ""}
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args = types.SimpleNamespace(dry_run=False, checkpoint=TMP15 / cp_name,
        source=str(SRC15), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p15 = FIX.Pipeline(args)
    p15.deepseek_chat = StubChatSim(); p15.deepseek_reasoner = StubReasonerK()
    p15.gemini = None; p15._source_index = StubIndexNoVar()
    FIX.stage_21(p15)
    return p15

PAGES_151 = ["11 класс. Вариант 1", f"1. {K1v} [3 балла]"]
pS1 = run15(PAGES_151, "cp15.json")
assert pS1.catalog.data["phystech"][0].get("variant") is None, \
    "сходство 0.6-0.9 не должно атрибутировать"
assert "needs_review" in json.dumps(pS1.catalog.data["phystech"][0]["qa"],
                                   ensure_ascii=False)
assert pS1.stage21_report["phystech"]["needs_review"] >= 1
assert not pS1.stage21_report["phystech"]["gaps"]
print("ПОРОГ 0.9 OK")

# --- 15.2: пустое извлечение — отчёт не заявляет «все дыры закрыты»
class StubChatEmpty:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        return {"ok": False, "tasks": [], "error": "пустой ответ"}

def run15e(cp_name):
    args = types.SimpleNamespace(dry_run=False, checkpoint=TMP15 / cp_name,
        source=str(SRC15), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p15 = FIX.Pipeline(args)
    p15.deepseek_chat = StubChatEmpty(); p15.deepseek_reasoner = StubReasonerK()
    p15.gemini = None; p15._source_index = StubIndexNoVar()
    FIX.stage_21(p15)
    return p15

pE = run15e("cp15e.json")
FIX._write_report(pE, [], "")
rep15 = (FIX.REPORTS_DIR / "olymp_catalog_fix.md").read_text(encoding="utf-8")
assert "все дыры закрыты" not in rep15, "ложное заявление о полноте"
assert "полнота НЕ подтверждена" in rep15
assert "needs_review) — 1" in rep15
print("ЧЕСТНЫЙ ОТЧЁТ OK")

# --- 15.3: три запуска с СОХРАНЕНИЕМ каталога и чекпоинта между ними
TMP16 = Path(tempfile.mkdtemp()); SRC16 = TMP16 / "catalog"; SRC16.mkdir()
PA1 = "Задача один из варианта один про прогрессии."
PA2 = "Задача два из варианта один про неравенства."
PB2 = "Задача два из варианта два про треугольники."
P3X = "Задача третий про матрицы."
s1w = mk("s1w", 1, PA1, status="AI_generated", solution="AI")
s1w["answer"] = "5"
(SRC16 / "phystech.json").write_text(
    json.dumps([mk("s3w", 3, P3X), s1w], ensure_ascii=False), encoding="utf-8")

PAGES_2VAR3 = ["11 класс. Вариант 1", f"1. {PA1} [3 балла]",
               f"2. {PA2} [3 балла]", "11 класс. Вариант 2", f"2. {PB2} [4 балла]"]

def run16(pages, cp_name, limit=None):
    FIX._fetch_doc_result = lambda url: {"ok": True, "pages": list(pages),
        "http_code": "200", "content_type": "application/pdf",
        "final_url": url, "error": ""}
    FIX._fetch_doc_pages = lambda url, ttl=7: list(pages)
    args = types.SimpleNamespace(dry_run=False, checkpoint=TMP16 / cp_name,
        source=str(SRC16), slug=None, limit=limit, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p16 = FIX.Pipeline(args)
    p16.deepseek_chat = StubChatL(); p16.deepseek_reasoner = StubReasonerK()
    p16.gemini = None; p16._source_index = StubIndexNoVar()
    return p16

# запуск 1: --limit 1 — вариант 2 отложен в очередь; СОХРАНЯЕМ состояние
q1r = run16(PAGES_2VAR3, "cp16.json", limit=1)
FIX.stage_21(q1r)
q1r.checkpoint.save()
q1r.catalog.save(SRC16)
# запуск 2: без лимита — PB2 импортирована, очередь очищена; СОХРАНЯЕМ
q2r = run16(PAGES_2VAR3, "cp16.json", limit=None)
FIX.stage_21(q2r)
q2r.checkpoint.save()
q2r.catalog.save(SRC16)
assert not q2r.checkpoint.data.get("stage21_pending")
# запуск 3: группа варианта 2 УЖЕ материализована на диске — PB2 загружена
q3r = run16(PAGES_2VAR3, "cp16.json", limit=None)
pb2_pre = [r for r in q3r.catalog.data["phystech"]
           if r.get("text") == PB2]
assert pb2_pre, "PB2 должна быть загружена с диска перед запуском 3"
assert (pb2_pre[0].get("qa") or {}).get("stage21", {}).get("imported"), \
    "у PB2 должен стоять флаг импорта"
uids_before = sorted(r["uid"] for r in q3r.catalog.data["phystech"])
FIX.stage_21(q3r)
gaps_v2 = [g for g in q3r.stage21_report["phystech"]["gaps"]
           if g.get("variant") == "2"]
assert not gaps_v2, f"фантомные дыры варианта 2: {gaps_v2}"
assert not q3r.checkpoint.data.get("stage21_pending"), \
    q3r.checkpoint.data.get("stage21_pending")
assert q3r.stage21_report["phystech"]["tasks_added"] == 0, \
    "повторный импорт уже существующей задачи"
uids_after = sorted(r["uid"] for r in q3r.catalog.data["phystech"])
assert uids_before == uids_after, "UID должны быть стабильны"
recs3 = q3r.catalog.data["phystech"]
assert sorted(str(r["num"]) for r in recs3) == ["1", "2", "2", "3"]
print("ТРЕТИЙ ЗАПУСК БЕЗ ФАНТОМОВ OK")

# --- 15.4: нет предложения атрибуции — отчёт не заявляет полного закрытия
TMP17 = Path(tempfile.mkdtemp()); SRC17 = TMP17 / "catalog"; SRC17.mkdir()
# текст записи вообще не совпадает с PDF (contained < 0.9) — предложения нет
k17 = "Задача про совсем другую тему про графы."
(SRC17 / "phystech.json").write_text(
    json.dumps([mk("n1", 1, k17, status="AI_generated", solution="AI")],
              ensure_ascii=False), encoding="utf-8")
FIX._fetch_doc_result = lambda url: {"ok": True, "pages": list(PAGES_151),
    "http_code": "200", "content_type": "application/pdf",
    "final_url": url, "error": ""}
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_151)
args = types.SimpleNamespace(dry_run=False, checkpoint=TMP17 / "cp17.json",
    source=str(SRC17), slug=None, limit=None, stages_set={21}, workers=2,
    resume=False, rebuild_index=True)
pN = FIX.Pipeline(args)
pN.deepseek_chat = StubChatSim(); pN.deepseek_reasoner = StubReasonerK()
pN.gemini = None; pN._source_index = StubIndexNoVar()
FIX.stage_21(pN)
assert pN.stage21_report["phystech"]["gaps"] == []
FIX._write_report(pN, [], "")
rep17 = (FIX.REPORTS_DIR / "olymp_catalog_fix.md").read_text(encoding="utf-8")
assert "все дыры закрыты" not in rep17
assert "Зарегистрированных дыр нет" in rep17
print("ОТЧЁТ БЕЗ ПРЕДЛОЖЕНИЯ OK")

# --- 15.5: смешанная группа — импорт №4 не создаёт ожиданий №2-3
TMP18 = Path(tempfile.mkdtemp()); SRC18 = TMP18 / "catalog"; SRC18.mkdir()
MA1 = "Задача один смешанной группы про прогрессии."
MA4 = "Задача четыре смешанной группы про графы."
m1 = mk("m1", 1, MA1, status="AI_generated", solution="AI")
m1["answer"] = "5"
(SRC18 / "phystech.json").write_text(json.dumps([m1], ensure_ascii=False),
                                     encoding="utf-8")
# блок содержит только №1 и №4 (нумерация не сплошная)
PAGES_MIX = ["11 класс. Вариант 1", f"1. {MA1} [3 балла]",
             f"4. {MA4} [5 балла]"]

class StubChatMix:
    name, model = "deepseek-chat", "deepseek-chat"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "errors": 0}
    def chat_json(self, prompt, payload, **kw):
        doc = json.loads(payload).get("doc_text", "")
        all_tasks = [{"num": "1", "text": MA1, "answer": "5", "solution": "sm1"},
                     {"num": "4", "text": MA4, "answer": "8", "solution": "sm4"}]
        return {"ok": True, "tasks": [t for t in all_tasks
                                      if t["text"][:20] in doc]}

FIX._fetch_doc_result = lambda url: {"ok": True, "pages": list(PAGES_MIX),
    "http_code": "200", "content_type": "application/pdf",
    "final_url": url, "error": ""}
FIX._fetch_doc_pages = lambda url, ttl=7: list(PAGES_MIX)
args = types.SimpleNamespace(dry_run=False, checkpoint=TMP18 / "cp18.json",
    source=str(SRC18), slug=None, limit=None, stages_set={21}, workers=2,
    resume=False, rebuild_index=True)
pM = FIX.Pipeline(args)
pM.deepseek_chat = StubChatMix(); pM.deepseek_reasoner = StubReasonerK()
pM.gemini = None; pM._source_index = StubIndexNoVar()
FIX.stage_21(pM)
FIX.stage_21(pM)   # второй прогон: №4 уже импортирована (imported=True)
recsM = pM.catalog.data["phystech"]
numsM = sorted(str(r["num"]) for r in recsM)
assert numsM == ["1", "4"], numsM
# фантомных дыр №2-3 у варианта 1 быть не должно
gapsM = [g for g in pM.stage21_report["phystech"]["gaps"]
         if g.get("num") in (2, 3)]
assert not gapsM, f"фантомные дыры №2-3: {gapsM}"
assert pM.stage21_report["phystech"]["tasks_added"] == 1  # №4 — один раз
print("СМЕШАННАЯ ГРУППА OK")

# --- 15.6: контрпример — ранний выход не создаёт фантомных дыр из импорта
# каталог: исходная №1 (вариант 1) + импортированная №4 (вариант 1); индекс пуст
TMP19 = Path(tempfile.mkdtemp()); SRC19 = TMP19 / "catalog"; SRC19.mkdir()
imp4 = mk("imp4", 4, MA4, variant="1")
imp4["qa"] = {"stage21": {"stage": 21, "model": "index+deepseek",
                          "imported": True, "changes": {},
                          "notes": ["добавлена задача №4"]}}
m1b = mk("m1b", 1, MA1, variant="1", status="AI_generated", solution="AI")
m1b["answer"] = "5"
(SRC19 / "phystech.json").write_text(
    json.dumps([m1b, imp4], ensure_ascii=False), encoding="utf-8")

class StubIndexEmpty:
    _cache = {}
    def find(self, slug, year, round_key, grade, kinds=None, variant=None):
        return []

def run19(src_dir, tmp_dir, cp_name):
    args = types.SimpleNamespace(dry_run=False, checkpoint=tmp_dir / cp_name,
        source=str(src_dir), slug=None, limit=None, stages_set={21}, workers=2,
        resume=False, rebuild_index=True)
    p19 = FIX.Pipeline(args)
    p19.deepseek_chat = StubChatMix(); p19.deepseek_reasoner = StubReasonerK()
    p19.gemini = None; p19._source_index = StubIndexEmpty()
    FIX.stage_21(p19)
    return p19

pF = run19(SRC19, TMP19, "cp19.json")
# проверка ДО запуска: обе записи в одной группе варианта 1
assert m1b.get("variant") == "1" == imp4.get("variant")
assert pF.stage21_report["phystech"]["gaps"] == [], \
    pF.stage21_report["phystech"]["gaps"]
assert not pF.checkpoint.data.get("stage21_pending")
print("РАННИЙ ВЫХОД БЕЗ ФАНТОМОВ OK")

# --- 15.7: импортированная №2 ЗАКРЫВАЕТ дыру — не «нет PDF»
TMP20 = Path(tempfile.mkdtemp()); SRC20 = TMP20 / "catalog"; SRC20.mkdir()
MA2 = "Задача два смешанной группы про неравенства."
imp2 = mk("imp2", 2, MA2, variant="1")
imp2["qa"] = {"stage21": {"stage": 21, "model": "index+deepseek",
                          "imported": True, "changes": {},
                          "notes": ["добавлена задача №2"]}}
o1 = mk("o1", 1, MA1, variant="1", status="AI_generated", solution="AI")
o1["answer"] = "5"
o3 = mk("o3", 3, "Задача три смешанной группы про функции.", variant="1")
(SRC20 / "phystech.json").write_text(
    json.dumps([o1, o3, imp2], ensure_ascii=False), encoding="utf-8")
pF2 = run19(SRC20, TMP20, "cp20.json")
assert pF2.stage21_report["phystech"]["gaps"] == [], \
    f"импортированная №2 должна закрывать дыру: {pF2.stage21_report['phystech']['gaps']}"
assert not pF2.checkpoint.data.get("stage21_pending")
print("ИМПОРТ ЗАКРЫВАЕТ ДЫРУ OK")
shutil.rmtree(TMP19, ignore_errors=True)
shutil.rmtree(TMP20, ignore_errors=True)

# =====================================================================
# Часть 16: улучшения v3.3 (MAX_TOKENS=8192, блок 12000, спасение JSON,
#           PUA/T2A, _index.json массив, 10-11 не сезон, 12 олимпиад)
# =====================================================================
assert FIX.MAX_TOKENS == 8192, FIX.MAX_TOKENS
assert FIX.PDF_BLOCK_CHUNK_SIZE == 12000, FIX.PDF_BLOCK_CHUNK_SIZE

# 16.1 Спасение закрытых задач из обрезанного JSON-ответа
trunc_raw = (
    '{"ok": true, "tasks": ['
    '{"num": "1", "text": "Задача 1 про числа.", "answer": "5", "solution": "Решение 1."}, '
    '{"num": "2", "text": "Задача 2 про скобки {a+b}.", "answer": "6", "solution": "Решение 2."}, '
    '{"num": "3", "text": "Незакрытая задача 3 про граф'
)
salv = FIX._salvage_truncated_tasks_json(trunc_raw)
assert salv is not None and salv.get("ok") is True, salv
assert len(salv["tasks"]) == 2 and [t["num"] for t in salv["tasks"]] == ["1", "2"], salv
print("СПАСЕНИЕ ОБРЕЗАННОГО JSON OK")

# 16.2 Нормализация PUA Symbol + T2A-артефактов PDF
norm_pua = FIX.R.normalize_unicode_math("В \uf044ABC \uf0d0A = 90\uf0b0, x \uf0b3 2 \uf0d7 3, привед¼н пример ¾Ломоносов¿, (¼)^n.")
assert "△ABC" in norm_pua and "∠A = 90°" in norm_pua and "x ≥ 2 ⋅ 3" in norm_pua, norm_pua
assert "приведён" in norm_pua and "«Ломоносов»" in norm_pua and "(¼)^n" in norm_pua, norm_pua
print("PUA SYMBOL И T2A PDF OK")

# 16.3 BROKEN_FORMULA_HINTS не срабатывает на русские предлоги перед \(...\)
assert not any(rx.search(r"Точка лежит в \(ABC\) и на \(Ox\), в 2 раза больше.") for rx in FIX.R.BROKEN_FORMULA_HINTS)
assert any(rx.search(r"Вычислите co \(s^2 x\) + \(a\) + \(b\).") for rx in FIX.R.BROKEN_FORMULA_HINTS)
print("ЭВРИСТИКА ПОРЕЗАННЫХ ФОРМУЛ БЕЗ ЛОЖНЫХ СРАБАТЫВАНИЙ OK")

# 16.4 Сезон в URL: «10-11» (классы) НЕ считается сезоном 2010–2011
from olymp_source_index import season_year_from_url, year_from_url, KNOWN_ACTIVITY_IDS, catalog_index_records
assert season_year_from_url("https://olymp.hse.ru/mirror/pubs/share/Math-10-11-2023.pdf") is None
assert year_from_url("https://olymp.hse.ru/mirror/pubs/share/Math-10-11-2023.pdf") == 2023
assert season_year_from_url("https://olymp.msu.ru/2023-2024/tasks.pdf") == 2024
assert season_year_from_url("https://olymp.mipt.ru/math_2019-20.pdf") == 2020
assert season_year_from_url("https://tasks.olimpiada.ru/upload/files/tasks/72/2018/sol-math-11-reg-18-9.pdf") == 2019
assert len(KNOWN_ACTIVITY_IDS) == 12 and KNOWN_ACTIVITY_IDS["vsosh"] == "72" and KNOWN_ACTIVITY_IDS["lomonosov"] == "348"
# Чужой activity_id (74 — физика ВсОШ) отфильтровывается из vsosh
cat_r, aid_v = catalog_index_records("vsosh", [
    {"source": "https://tasks.olimpiada.ru/upload/files/tasks/74/2021/phys.pdf", "year": 2021, "grade": 11, "round": "Заключительный этап"},
    {"source": "https://tasks.olimpiada.ru/upload/files/tasks/72/2021/math.pdf", "year": 2021, "grade": 11, "round": "Заключительный этап"},
])
assert aid_v == "72" and len(cat_r) == 1 and "tasks/72/" in cat_r[0]["url"], (aid_v, cat_r)
print("СЕЗОН 10-11 И ACTIVITY_ID 12 ОЛИМПИАД OK")

# 16.5 Формат _index.json в Catalog.save — список словарей [{"slug", "name", "count", "with_figs", "years"}]
TMP21 = Path(tempfile.mkdtemp())
cat_test = FIX.Catalog()
cat_test.data["phystech"] = [{**mk("u1", 1, "Задача 1"), "year": 2023}, {**mk("u2", 2, "Задача 2"), "year": 2025}]
cat_test.save(TMP21)
idx_saved = json.loads((TMP21 / "_index.json").read_text(encoding="utf-8"))
assert isinstance(idx_saved, list), type(idx_saved)
ph_idx = next(x for x in idx_saved if x.get("slug") == "phystech")
assert ph_idx["count"] == 2 and ph_idx["years"] == [2023, 2025] and "Физтех" in ph_idx["name"], ph_idx
shutil.rmtree(TMP21, ignore_errors=True)
print("ФОРМАТ _INDEX.JSON OK")

