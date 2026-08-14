import os
import json
import time
import requests

#=== РќР°СЃС‚СЂРѕР№РєРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ ===
# Р’СЃС‚Р°РІСЊС‚Рµ СЃРІРѕР№ РєР»СЋС‡ DeepSeek РІ РїРµСЂРµРјРµРЅРЅСѓСЋ DEEPSEEK_API_KEY РЅРёР¶Рµ
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # TODO: Р·Р°РјРµРЅРёС‚СЊ РЅР° СЂРµР°Р»СЊРЅС‹Р№ РєР»СЋС‡

# РРјСЏ РІС…РѕРґРЅРѕРіРѕ С„Р°Р№Р»Р° СЃ 69 Р·Р°РґР°С‡Р°РјРё РІ С„РѕСЂРјР°С‚Рµ JSONL
INPUT_JSONL = "69_tasks_clean_jsonl.jsonl"  # РєР°Р¶РґР°СЏ СЃС‚СЂРѕРєР° вЂ” РѕР±СЉРµРєС‚ СЃ РїРѕР»СЏРјРё statement, answer, solution Рё РјРµС‚Р°РґР°РЅРЅС‹РјРё

# РРјСЏ РІС‹С…РѕРґРЅРѕРіРѕ С„Р°Р№Р»Р° СЃ LaTeX-РєРѕРґРѕРј
OUTPUT_TEX = "tg_69_tasks.tex"

#=== РљРѕРЅС„РёРіСѓСЂР°С†РёСЏ РІС‹Р·РѕРІР° DeepSeek v4 Pro ===

API_URL = "https://api.deepseek.com/v1/chat/completions"  # РїСЂРё РЅРµРѕР±С…РѕРґРёРјРѕСЃС‚Рё РїРѕРїСЂР°РІСЊС‚Рµ РЅР° Р°РєС‚СѓР°Р»СЊРЅС‹Р№
MODEL_NAME = "deepseek-v4-pro"  # РёР»Рё С‚РѕС‡РЅРѕРµ РёРјСЏ РјРѕРґРµР»Рё, РєРѕС‚РѕСЂРѕРµ РІР°Рј РЅСѓР¶РЅРѕ

SYSTEM_PROMPT = (
    "You are DeepSeek v4 Pro. Your task is to take olympiad math problems "
    "(statement + answer + solution + metadata) and convert them into clean LaTeX snippets. "
    "Output ONLY LaTeX code, no explanations, no surrounding markdown. Use standard LaTeX math "
    "environments (equation, align, itemize, enumerate) and escape special characters. "
    "Do not include preamble (\\documentclass, packages) or \\begin{document}; output just the body."
)

USER_PROMPT_TEMPLATE = (
    "Convert the following olympiad problem record into LaTeX. "
    "Structure it as: \n"
    "\\begin{problem}[metadata]\nstatement\\end{problem}\n"
    "\\begin{answer}answer\\end{answer}\n"
    "\\begin{solution}solution\\end{solution}\n\n"
    "Metadata (grade, level, theme, section, source/year) should go in optional [ ] of problem, "
    "compactly (e.g. [Grade 9, TG, 2017]). Statement/answer/solution should be typeset with proper "
    "math mode where needed. Here is the JSON record:\n\n{json_record}"
)

HEADERS = {
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json",
}


def call_deepseek(messages):
    """Р’С‹Р·РѕРІ DeepSeek Chat Completion СЃ Р·Р°РґР°РЅРЅС‹РјРё СЃРѕРѕР±С‰РµРЅРёСЏРјРё."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
    }
    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def process_jsonl_to_latex(input_path: str, output_path: str):
    """Р§РёС‚Р°РµС‚ JSONL СЃ 69 Р·Р°РґР°С‡Р°РјРё, РїРѕ РѕРґРЅРѕР№ Р·Р°РґР°С‡Рµ РІС‹Р·С‹РІР°РµС‚ DeepSeek, РїРёС€РµС‚ LaTeX РІ РѕРґРёРЅ .tex."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ РІС…РѕРґРЅРѕР№ С„Р°Р№Р» {input_path}")

    with open(input_path, "r", encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
        fout.write("% LaTeX-РІРµСЂСЃРёСЏ 69 Р·Р°РґР°С‡ РўСѓСЂРЅРёСЂР° РіРѕСЂРѕРґРѕРІ / Р’СЃРћРЁ / РґСЂСѓРіРёС… РѕР»РёРјРїРёР°Рґ\n")
        fout.write("% РЎРіРµРЅРµСЂРёСЂРѕРІР°РЅРѕ DeepSeek v4 Pro С‡РµСЂРµР· РґР°РЅРЅС‹Р№ СЃРєСЂРёРїС‚\n\n")

        for idx, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARN] РЎС‚СЂРѕРєР° {idx}: РЅРµ СѓРґР°Р»РѕСЃСЊ СЂР°СЃРїР°СЂСЃРёС‚СЊ JSON, РїСЂРѕРїСѓСЃРєР°СЋ")
                continue

            # Р¤РѕСЂРјРёСЂСѓРµРј JSON-СЃС‚СЂРѕРєСѓ РґР»СЏ РїСЂРѕРјРїС‚Р°
            json_record_str = json.dumps(rec, ensure_ascii=False, indent=2)
            user_prompt = USER_PROMPT_TEMPLATE.replace("{json_record}", json_record_str)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            print(f"[INFO] РћР±СЂР°Р±Р°С‚С‹РІР°СЋ Р·Р°РґР°С‡Сѓ {idx}...")
            try:
                latex_snippet = call_deepseek(messages)
            except Exception as e:
                print(f"[ERROR] Р—Р°РґР°С‡Р° {idx}: РѕС€РёР±РєР° РІС‹Р·РѕРІР° API: {e}")
                continue

            fout.write(f"% ===== Р—Р°РґР°С‡Р° {idx} =====\n")
            fout.write(latex_snippet)
            fout.write("\n\n")
            # РќРµР±РѕР»СЊС€Р°СЏ РїР°СѓР·Р°, С‡С‚РѕР±С‹ РЅРµ СѓРїРµСЂРµС‚СЊСЃСЏ РІ rate-limit
            time.sleep(0.2)

    print(f"[DONE] LaTeX-С„Р°Р№Р» Р·Р°РїРёСЃР°РЅ РІ {output_path}")


if __name__ == "__main__":
    process_jsonl_to_latex(INPUT_JSONL, OUTPUT_TEX)


