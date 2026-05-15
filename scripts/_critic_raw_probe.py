# raw probe -- prints finish_reason + usage for the Gemini critic call
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from dotenv import load_dotenv

load_dotenv()

from services.drawing_service import _build_critic_messages, MODEL_CRITIC

problem_file = sys.argv[1]
code_file = sys.argv[2]
png_file = sys.argv[3]
out_file = sys.argv[4]

with open(problem_file, "r", encoding="utf-8") as f:
    problem = f.read().strip()
with open(code_file, "r", encoding="utf-8") as f:
    code = f.read()
with open(png_file, "rb") as f:
    png = f.read()

messages = _build_critic_messages(problem, code, png)

payload = dict(
    model=MODEL_CRITIC,
    messages=messages,
    temperature=0.0,
    max_tokens=4000,
)

headers = dict()
headers["Authorization"] = "Bearer " + os.environ["OPENROUTER_API_KEY"].strip()
headers["Content-Type"] = "application/json"
headers["HTTP-Referer"] = "https://formyla.ru"
headers["X-Title"] = "FORMYLA"

print("[probe] calling", MODEL_CRITIC, "...")
sys.stdout.flush()

with httpx.Client(timeout=180.0) as c:
    r = c.post("https://openrouter.ai/api/v1/chat/completions",
               headers=headers, json=payload)

print("[probe] HTTP", r.status_code)
data = r.json()

choice = data["choices"][0]
msg = choice["message"]
content = msg.get("content") or ""

# trim images-style data before dumping
dump = dict(
    finish_reason=choice.get("finish_reason"),
    usage=data.get("usage"),
    content_len=len(content),
    content=content,
    reasoning=msg.get("reasoning"),
    reasoning_details=msg.get("reasoning_details"),
)

with open(out_file, "w", encoding="utf-8") as f:
    json.dump(dump, f, ensure_ascii=False, indent=2)

print("[probe] finish_reason =", choice.get("finish_reason"))
print("[probe] usage         =", data.get("usage"))
print("[probe] content_len   =", len(content))
print("[probe] saved ->", out_file)
