# -*- coding: utf-8 -*-
"""
Photo recognizer - LOCAL only. No API, no VPN, no registration.

Pipeline:
    photo.png -> Tesseract OCR (rus+eng) -> DeepSeek cleanup

Requires: Tesseract (winget install UB-Mannheim.TesseractOCR)
          rus.traineddata auto-downloaded to ~/tessdata_both/

Speed: OCR <1s, DeepSeek <3s, total <5s.

Usage:
    python _photo_ocr.py [path_to_photo]
"""
import io
import os
import shutil
import subprocess
import sys
import time

# Windows console: force UTF-8
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ----- config ------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__)) or "."
TESSCACHE = os.path.join(os.path.expanduser("~"), "tessdata_both")
os.makedirs(TESSCACHE, exist_ok=True)

# Load .env
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

# ----- find Tesseract ----------------------------------------------
def _find_tesseract():
    for p in [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Tesseract-OCR", "tesseract.exe"),
    ]:
        if os.path.exists(p):
            return p
    f = shutil.which("tesseract")
    if f:
        return f
    raise FileNotFoundError("Tesseract not found. Run: winget install UB-Mannheim.TesseractOCR")

TESSERACT = os.environ.get("TESSERACT_CMD", "").strip() or _find_tesseract()
assert os.path.exists(TESSERACT), f"Tesseract not found at {TESSERACT}"

# ----- language packs ----------------------------------------------
SYSTEM_TESSDATA = os.path.join(os.path.dirname(TESSERACT), "tessdata")
ENG_SRC = os.path.join(SYSTEM_TESSDATA, "eng.traineddata")
ENG_DST = os.path.join(TESSCACHE, "eng.traineddata")
if os.path.exists(ENG_SRC) and not os.path.exists(ENG_DST):
    shutil.copy2(ENG_SRC, ENG_DST)

# Copy rus from project (if downloaded) or system
RUS_DST = os.path.join(TESSCACHE, "rus.traineddata")
if not os.path.exists(RUS_DST):
    for src in [
        os.path.join(PROJECT_DIR, "rus.traineddata"),
        os.path.join(PROJECT_DIR, "tessdata", "rus.traineddata"),
        os.path.join(SYSTEM_TESSDATA, "rus.traineddata"),
    ]:
        if os.path.exists(src):
            shutil.copy2(src, RUS_DST)
            break

USE_RUS = os.path.exists(RUS_DST)
print(f"[OK] Tesseract ready (eng{'+rus' if USE_RUS else ''})")

# ----- OCR ---------------------------------------------------------
def _ocr(image_path):
    """Tesseract OCR. Copies image to clean path (no Cyrillic in path)."""
    lang = "rus+eng" if USE_RUS else "eng"
    temp_img = os.path.join(TESSCACHE, "_ocr_work.png")
    shutil.copy2(image_path, temp_img)

    t0 = time.time()
    cmd = [TESSERACT, temp_img, "stdout", "-l", lang, "--psm", "3",
           "--tessdata-dir", TESSCACHE]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8",
                            errors="replace", timeout=30)
    elapsed = time.time() - t0
    text = (result.stdout or "").strip()

    try:
        os.remove(temp_img)
    except OSError:
        pass

    if not text and USE_RUS:
        # Fallback eng
        result = subprocess.run(
            [TESSERACT, image_path if not any(ord(c)>127 for c in image_path) else temp_img,
             "stdout", "-l", "eng", "--psm", "3", "--tessdata-dir", TESSCACHE],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        text = (result.stdout or "").strip()

    return text, elapsed


# ----- DeepSeek cleanup --------------------------------------------
def _refine(raw_text):
    import requests
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return raw_text

    prompt = (
        "You received OCR output from a photo of a Russian math problem. "
        "OCR may have errors (letters/digits mixed, '3' vs 'Z', '4' vs 'ch'). "
        "Reconstruct the EXACT task statement in Russian:\n"
        "1. Fix OCR errors, restore proper Russian text.\n"
        "2. Math formulas as plain text: x^2, a/b, sqrt(...), <=, >=.\n"
        "3. Return ONLY the clean task statement, nothing else.\n\n"
        f"OCR text:\n{raw_text}"
    )

    t0 = time.time()
    try:
        r = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 800},
            timeout=20,
        )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            return text.strip(), time.time() - t0
    except Exception as e:
        print(f"[DeepSeek] Error: {e}")
    return raw_text, 0


# ----- Public API --------------------------------------------------
def recognize(image_path, refine=True):
    t_start = time.time()
    if not os.path.exists(image_path):
        return {"error": f"File not found: {image_path}"}

    raw, ocr_time = _ocr(image_path)
    if not raw:
        return {"error": "OCR returned empty text (image may have no text)", "raw": "", "clean": ""}

    if refine:
        clean, ds_time = _refine(raw)
    else:
        clean, ds_time = raw, 0

    return {
        "raw": raw,
        "clean": clean,
        "ocr_seconds": round(ocr_time, 1),
        "deepseek_seconds": round(ds_time, 1),
        "total_seconds": round(time.time() - t_start, 1),
    }


# ----- CLI ---------------------------------------------------------
if __name__ == "__main__":
    import glob

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        # Auto-pick last screenshot
        screens = glob.glob(os.path.join(os.path.expanduser("~"),
                                         "Pictures", "Screenshots", "*.png"))
        if screens:
            path = screens[-1]
            print(f"[AUTO] Using last screenshot: {os.path.basename(path)}")
        else:
            # Fallback to bundled image
            path = os.path.join(PROJECT_DIR, "data", "images",
                                "Lom2024Math10", "Lom2024Math10_p1_img0.png")

    print(f"\n{'='*60}\n  PHOTO RECOGNIZER\n  {os.path.basename(path)}\n{'='*60}\n")

    result = recognize(path)

    if result.get("error") and not result.get("raw"):
        print(f"[FAIL] {result['error']}")
        sys.exit(1)

    if result.get("error"):
        print(f"[WARN] {result['error']}")

    print(f"  OCR:       {result['ocr_seconds']}s  ({len(result['raw'])} chars)")
    print(f"  DeepSeek:  {result['deepseek_seconds']}s")
    print(f"  TOTAL:     {result['total_seconds']}s")
    print(f"\n{'='*60}\n  RAW OCR:\n{result['raw'][:500]}")
    print(f"\n{'='*60}\n  CLEAN (DeepSeek):\n{result['clean'][:800]}")
    print(f"{'='*60}")
