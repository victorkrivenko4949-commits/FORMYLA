from PIL import Image
import os

FOLDER = "static/images/problems/"

for filename in os.listdir(FOLDER):
    if not filename.startswith("vsosh_") or not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        continue
    if "копия" in filename: continue
        
    filepath = os.path.join(FOLDER, filename)
    try:
        img = Image.open(filepath)
        gray = img.convert("L")
        pixels = gray.load()
        w, h = gray.size
        
        top, bottom, left, right = h, 0, w, 0
        for y in range(h):
            for x in range(w):
                if pixels[x, y] < 240:
                    if y < top: top = y
                    if y > bottom: bottom = y
                    if x < left: left = x
                    if x > right: right = x
        
        if top < bottom and left < right:
            pad = 20
            top, bottom = max(0, top - pad), min(h, bottom + pad)
            left, right = max(0, left - pad), min(w, right + pad)
            cropped = img.crop((left, top, right, bottom))
            cropped.save(filepath, quality=95)
            print(f"Обрезан: {filename}")
    except Exception as e:
        print(f"Ошибка с {filename}: {e}")
