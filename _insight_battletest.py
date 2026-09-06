# -*- coding: utf-8 -*-
"""Боевой тест «Банка неточностей»: 12 спроектированных решений на реальной модели.

Скрининг effort=low (gemini-3.7-flash), глубокий проход effort=max (deepseek-v4-pro).
AI_INSIGHT_MIN_REASONING_TOKENS=0 — глубина рассуждения не отбраковывает, только логируется.
Сырые JSON-ответы модели пишутся в _insight_battletest_raw.jsonl.
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

os.environ["AI_INSIGHT_MIN_REASONING_TOKENS"] = "0"

from dotenv import load_dotenv
load_dotenv()

from services.insight_runner import run_screen, run_deep

RAW_PATH = "_insight_battletest_raw.jsonl"
raw_f = open(RAW_PATH, "w", encoding="utf-8")


# ── 12 кейсов ─────────────────────────────────────────────────────────────
# Каждый: id, group, expected_has_insight, expected_skip_reason, task, answer,
#         solution_ref, topic, level, time_spent, etalon_time, user_solution

CASES = [
    # ── Группа A — должны попасть в банк ──
    {
        "id": "A1", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Среди чисел от 1 до 20 включительно выбирают одно число, которое не делится ни на 2, ни на 3. Сколько имеется вариантов выбора?",
        "answer": "7",
        "solution_ref": "Исключим чётные: 1,3,5,7,9,11,13,15,17,19 (10 чисел). Из них уберём делящиеся на 3: 3,9,15. Остаются 1,5,7,11,13,17,19 — 7 чисел. Короче: 20 − 10 − 3 + 1 = 7 (по формуле включений-исключений).",
        "topic": "Комбинаторика", "level": 1, "time_spent": 420, "etalon_time": 40,
        "user_solution": "Выпишу все числа от 1 до 20 и отмечу подходящие.\n1 — не делится ни на 2, ни на 3, подходит.\n2 — чётное, нет.\n3 — делится на 3, нет.\n4 — чётное, нет.\n5 — подходит.\n6 — и чётное, и на 3, нет.\n7 — подходит.\n8 — чётное, нет.\n9 — на 3, нет.\n10 — чётное, нет.\n11 — подходит.\n12 — нет.\n13 — подходит.\n14 — чётное, нет.\n15 — на 3, нет.\n16 — чётное, нет.\n17 — подходит.\n18 — нет.\n19 — подходит.\n20 — чётное, нет.\nИтого подошли: 1,5,7,11,13,17,19 — это 7 чисел.\nОтвет: 7.",
    },
    {
        "id": "A2", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Вычислите сумму S = 1 − 2 + 3 − 4 + 5 − 6 + … + 99 − 100.",
        "answer": "−50",
        "solution_ref": "Сгруппируем по два: (1−2)+(3−4)+…+(99−100). Каждая скобка равна −1, всего 50 пар. S = 50·(−1) = −50.",
        "topic": "Алгебра", "level": 1, "time_spent": 380, "etalon_time": 30,
        "user_solution": "Найду эту сумму по частям. Сначала посчитаю отдельно сумму положительных и отрицательных слагаемых.\nПоложительные: 1+3+5+…+99. Это 50 нечётных чисел, среднее (1+99)/2=50, сумма 50·50=2500.\nОтрицательные: 2+4+6+…+100. Это 50 чётных чисел, среднее (2+100)/2=51, сумма 50·51=2550.\nТогда S = 2500 − 2550 = −50.\nОтвет: −50.",
    },
    {
        "id": "A3", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Найдите наименьшее значение выражения x²+y², если x и y — действительные числа, удовлетворяющие равенству x+2y=5.",
        "answer": "5",
        "solution_ref": "По неравенству Коши–Буняковского (x²+y²)(1²+2²) ≥ (x+2y)² = 25, откуда x²+y² ≥ 5. Равенство при (x,y)=(1,2), которое удовлетворяет x+2y=5. Минимум 5.",
        "topic": "Неравенства", "level": 3, "time_spent": 300, "etalon_time": 60,
        "user_solution": "Оценка снизу: по неравенству Коши–Буняковского (x²+y²)(1+4) ≥ (x+2y)² = 25, значит x²+y² ≥ 5.\nЗначит, меньше 5 значение быть не может, поэтому наименьшее значение равно 5.\nОтвет: 5.",
    },
    {
        "id": "A4", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Решите уравнение |x−2|+|x+1|=5 и найдите сумму всех его корней.",
        "answer": "1",
        "solution_ref": "Разбор случаев: (1) x≤−1: −(x−2)−(x+1)=5 → x=−2; (2) −1<x<2: −(x−2)+(x+1)=3≠5; (3) x≥2: (x−2)+(x+1)=5 → x=3. Корни −2 и 3, сумма 1.",
        "topic": "Алгебра", "level": 2, "time_spent": 260, "etalon_time": 50,
        "user_solution": "Разберу случай x ≥ 2: тогда оба модуля раскрываются со знаком плюс.\n|x−2|+|x+1| = (x−2)+(x+1) = 2x−1 = 5, откуда 2x=6, x=3.\nТеперь случай x ≤ −1: |x−2|=2−x, |x+1|=−x−1, сумма (2−x)+(−x−1)=1−2x=5, откуда −2x=4, x=−2.\nПромежуточный случай не рассматривал, там, кажется, решений нет.\nКорни: 3 и −2, сумма 1.\nОтвет: 1.",
    },
    {
        "id": "A5", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Решите уравнение x³ = x.",
        "answer": "−1, 0, 1",
        "solution_ref": "x³−x=0, x(x²−1)=0, x(x−1)(x+1)=0. Корни −1, 0, 1.",
        "topic": "Алгебра", "level": 1, "time_spent": 240, "etalon_time": 20,
        "user_solution": "Разделю обе части на x: x² = 1, откуда x = 1 или x = −1.\nПроверка: 1³=1, верно; (−1)³=−1, верно.\nОтвет: x = 1 или x = −1.",
    },
    {
        "id": "A6", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Выбрали пять целых чисел. Докажите, что среди них найдутся два числа, разность которых делится на 4.",
        "answer": "Для пяти чисел такая пара всегда есть.",
        "solution_ref": "Остатки при делении на 4 — четыре класса: 0,1,2,3. Пять чисел на четыре класса — по принципу Дирихле два попадут в один класс, их разность делится на 4.",
        "topic": "Комбинаторика", "level": 2, "time_spent": 200, "etalon_time": 40,
        "user_solution": "Возьму любые пять чисел. Ясно, что среди любых пяти целых чисел обязательно найдутся два с одинаковой чётностью, а разность двух чисел одинаковой чётности — чётная.\nНо чётная разность не обязана делиться на 4. Однако если рассмотреть остатки по модулю 4, их всего 3 (а не 4): 0, 1 и 2, потому что остаток 3 — это то же самое, что −1.\nЗначит, по принципу Дирихле среди пяти чисел двое имеют одинаковый остаток по модулю 4, и их разность делится на 4.\nДоказано.",
    },
    {
        "id": "A7", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Решите уравнение x⁴ − 5x² + 4 = 0.",
        "answer": "−2, −1, 1, 2",
        "solution_ref": "Замена t=x²: t²−5t+4=0, t=1 или t=4. Тогда x²=1 или x²=4, корни −2,−1,1,2.",
        "topic": "Алгебра", "level": 1, "time_spent": 320, "etalon_time": 30,
        "user_solution": "Попробую разложить на множители. Заметим, что x=1 подходит: 1−5+4=0. x=−1 тоже: 1−5+4=0. x=2: 16−20+4=0. x=−2: 16−20+4=0.\nПокажу, что других корней нет: при x²>4 все члены x⁴ и −5x²+4 дают положительное (x⁴−5x²+4 ≥ 16−20+4=0 при |x|≥2), а при 0≤x²≤1 тоже не ноль, кроме x²=1. Перебирая промежутки, убеждаюсь, что корней ровно четыре.\nОтвет: −2, −1, 1, 2.",
    },
    {
        "id": "A8", "group": "A", "expected_has_insight": True, "expected_skip_reason": None,
        "task": "Последовательность задана условиями x₁=1, x_{n+1}=x_n+2n+1. Найдите x₁₀₀.",
        "answer": "10000",
        "solution_ref": "x_n = 1 + Σ_{k=1}^{n-1}(2k+1) = 1 + (n−1)² = n². Значит x₁₀₀ = 10000.",
        "topic": "Алгебра", "level": 3, "time_spent": 300, "etalon_time": 60,
        "user_solution": "Посчитаю первые члены: x₁=1. x₂=1+3=4. x₃=4+5=9. x₄=9+7=16. x₅=16+9=25.\nВижу закономерность: 1, 4, 9, 16, 25 — это квадраты 1²,2²,3²,4²,5².\nЗначит, x_n = n², и x₁₀₀ = 100² = 10000.\nОтвет: 10000.",
    },

    # ── Группа B — НЕ должны попасть в банк ──
    {
        "id": "B1", "group": "B", "expected_has_insight": False, "expected_skip_reason": "arithmetic_slip",
        "task": "Вычислите сумму S = 1 − 2 + 3 − 4 + … + 99 − 100.",
        "answer": "−50",
        "solution_ref": "50 пар по −1: S = −50.",
        "topic": "Алгебра", "level": 1, "time_spent": 40, "etalon_time": 30,
        "user_solution": "Группирую по два: (1−2)+(3−4)+…+(99−100).\nКаждая скобка равна −1, всего 50 пар.\nСумма = 50·(−1) = −51.\nОтвет: −51.",
    },
    {
        "id": "B2", "group": "B", "expected_has_insight": False, "expected_skip_reason": "arithmetic_slip",
        "task": "Вычислите сумму S = 1 − 2 + 3 − 4 + … + 99 − 100.",
        "answer": "−50",
        "solution_ref": "50 пар по −1: S = −50.",
        "topic": "Алгебра", "level": 1, "time_spent": 45, "etalon_time": 30,
        "user_solution": "Запишу сумму иначе: S = (1+3+5+…+99) − (2+4+6+…+100).\nСумма нечётных 1..99: 50 чисел, среднее 50, сумма 2500.\nСумма чётных 2..100: 50 чисел, среднее 51, сумма 2550.\nВычитаю: 2500 − 2550 = 50. То есть ответ положительный 50.\nОтвет: 50.",
    },
    {
        "id": "B3", "group": "B", "expected_has_insight": False, "expected_skip_reason": "bad_luck",
        "task": "Решите уравнение x⁴ − 5x² + 4 = 0.",
        "answer": "−2, −1, 1, 2",
        "solution_ref": "Замена t=x² → t²−5t+4=0 → x=±1,±2.",
        "topic": "Алгебра", "level": 1, "time_spent": 60, "etalon_time": 30,
        "user_solution": "Сделаю замену t=x², тогда t²−5t+4=0, дискриминант 25−16=9, корни t=(5±3)/2, то есть t=4 или t=1.\nЗначит x²=4 или x²=1, откуда x=±2, ±1.\n(дальше не успел записать проверку)",
    },
    {
        "id": "B4", "group": "B", "expected_has_insight": False, "expected_skip_reason": "no_issue",
        "task": "Решите уравнение x³ = x.",
        "answer": "−1, 0, 1",
        "solution_ref": "x³−x=0 → x(x−1)(x+1)=0.",
        "topic": "Алгебра", "level": 1, "time_spent": 25, "etalon_time": 20,
        "user_solution": "Перенесу всё влево: x³−x=0. Вынесу x: x(x²−1)=0. Разложу: x(x−1)(x+1)=0.\nОтсюда x=0, x=1, x=−1.\nОтвет: −1, 0, 1.",
    },
]


def main():
    results = []
    for case in CASES:
        ctx = {
            "user_id": 0,
            "task_text": case["task"],
            "correct_answer": case["answer"],
            "solution_ref": case["solution_ref"],
            "user_solution": case["user_solution"],
            "topic": case["topic"],
            "difficulty_level": case["level"],
            "time_spent_sec": case["time_spent"],
            "etalon_time_sec": case["etalon_time"],
        }
        rec = {
            "id": case["id"],
            "group": case["group"],
            "expected_has_insight": case["expected_has_insight"],
            "expected_skip_reason": case["expected_skip_reason"],
        }

        # ── Скрининг ──
        t0 = time.time()
        scr = run_screen(ctx)
        screen_ms = int((time.time() - t0) * 1000)
        rec["screen"] = {
            "needs_deep_analysis": scr.needs_deep_analysis,
            "preliminary_type": scr.preliminary_type,
            "skip_reason": scr.skip_reason,
            "reasoning_tokens": scr.meta.get("reasoning_tokens"),
            "model": scr.meta.get("model_id"),
            "provider": scr.meta.get("provider"),
            "cost_usd": scr.meta.get("cost_usd"),
            "latency_ms": screen_ms,
            "raw": scr.raw,
        }
        raw_f.write(json.dumps({"case": case["id"], "stage": "screen", "raw": scr.raw}, ensure_ascii=False) + "\n")
        raw_f.flush()

        # ── Глубокий проход, только если скрининг пропустил ──
        rec["deep"] = None
        if scr.needs_deep_analysis:
            t0 = time.time()
            deep = run_deep(ctx)
            deep_ms = int((time.time() - t0) * 1000)
            rec["deep"] = {
                "has_insight": deep.has_insight,
                "valid": deep.valid,
                "validation_reason": deep.validation_reason,
                "skip_reason": deep.skip_reason,
                "reasoning_short": deep.reasoning_short,
                "reasoning_tokens": deep.meta.get("reasoning_tokens"),
                "model": deep.meta.get("model_id"),
                "provider": deep.meta.get("provider"),
                "cost_usd": deep.meta.get("cost_usd"),
                "latency_ms": deep_ms,
                "raw": deep.raw,
                "insights": deep.insights,
            }
            raw_f.write(json.dumps({"case": case["id"], "stage": "deep", "raw": deep.raw}, ensure_ascii=False) + "\n")
            raw_f.flush()

        results.append(rec)
        print(f"[{case['id']}] screen.needs_deep={scr.needs_deep_analysis} "
              f"screen.skip={scr.skip_reason} "
              f"deep={'has='+str(rec['deep']['has_insight'])+'/valid='+str(rec['deep']['valid']) if rec['deep'] else 'skipped'}",
              flush=True)

    summary_path = "_insight_battletest_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved summary:", summary_path)
    print("Saved raw:", RAW_PATH)


if __name__ == "__main__":
    main()
    raw_f.close()
