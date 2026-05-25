# -*- coding: utf-8 -*-
import os, sqlite3, sys

DB = os.path.join("instance", "formyla.db")

SECTION_NAMES = {
    "A": "Алгебра и текстовые задачи",
    "B": "Логика и рассуждения",
    "C": "Многочлены и алгебра",
    "D": "Теория чисел",
    "E": "Принципы и идеи",
    "F": "Геометрия",
    "G": "Неравенства и анализ",
    "H": "Дополнительные продвинутые темы",
}

def fetch_example_task(cur, code):
    cur.execute(
        "SELECT number, condition_md, idea_md, solution_md, answer "
        "FROM olympiad_tasks "
        "WHERE method_primary = ? OR method_secondary = ? "
        "ORDER BY id LIMIT 1",
        (code, code),
    )
    return cur.fetchone()

def build_stub(code, name, section, task_row):
    sec_label = SECTION_NAMES.get(section, section)
    definition = (
        "**" + name + "** \u2014 базовый приём из раздела «"
        + sec_label + "».\n\nПодробный конспект готовится. "
        "Ниже приведён один разобранный пример из задач ВсОШ-9, "
        "чтобы можно было сразу увидеть метод в работе."
    )
    if task_row:
        number, cond, idea, sol, ans = task_row
        cond_t = (cond or "_условие готовится_").strip()
        sol_t = (sol or "_разбор готовится_").strip()
        idea_block = ""
        if idea and idea.strip() and not idea.strip().startswith("TODO"):
            idea_block = "**Идея.** " + idea.strip() + "\n\n"
        ans_block = ""
        if ans and ans.strip():
            ans_block = "\n\n**Ответ.** " + ans.strip()
        example = (
            "### Пример (ВсОШ-9, задача " + str(number) + ")\n\n"
            + cond_t + "\n\n" + idea_block
            + "**Решение.**\n" + sol_t + ans_block
        )
    else:
        example = (
            "### Пример\n\nРазобранный пример к методу **" + name + "** "
            "будет добавлен после ревью банка задач ВсОШ-9."
        )
    return definition, example

def main():
    if not os.path.exists(DB):
        print("DB not found:", DB)
        return 2
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT method_code, method_name, section "
        "FROM olympiad_theory "
        "WHERE (definition_md IS NULL OR TRIM(definition_md) = '') "
        "  AND (worked_example_md IS NULL OR TRIM(worked_example_md) = '') "
        "ORDER BY section, sort_order, method_code"
    )
    targets = cur.fetchall()
    print("Empty methods to fill:", len(targets))
    written = 0
    for code, name, section in targets:
        task_row = fetch_example_task(cur, code)
        definition, example = build_stub(code, name, section, task_row)
        cur.execute(
            "UPDATE olympiad_theory "
            "SET definition_md = ?, worked_example_md = ? "
            "WHERE method_code = ?",
            (definition, example, code),
        )
        if cur.rowcount:
            written += 1
            tag = "T" if task_row else "-"
            print("  [" + tag + "] " + code.ljust(6) + " " + (name or ""))
    conn.commit()
    print("Wrote stubs for", written, "methods.")
    conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
