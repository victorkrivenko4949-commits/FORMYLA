#!/usr/bin/env python3
"""Generate a test HTML page with the image embedded as base64 data URI."""
import base64
import os

# Read the image file
img_path = r'C:\Users\Victor\Desktop\Новая папка (2)\olympiad-db\public\images\euler\euler_2009_tasks.pdf\euler_2009_regional_g8_n2_p1_cropde2ac903.png'
with open(img_path, 'rb') as f:
    img_data = f.read()

b64 = base64.b64encode(img_data).decode('ascii')

html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Base64 Embedded Image Test</title>
<style>
  body {{ font-family: sans-serif; margin: 20px; }}
  img {{ max-width: 100%; border: 3px solid green; }}
</style>
</head>
<body>
<h1>Тест: изображение встроено через Data URI (base64)</h1>
<p>Это изображение встроено прямо в HTML. Если вы видите зелёную рамку, но внутри пусто — проблема в браузере/системе.</p>
<p>Размер PNG: {len(img_data)} байт</p>
<img src="data:image/png;base64,{b64}" alt="Base64 embedded Euler image">
<hr>
<h2>Также тест SVG (для проверки отображения графики в целом):</h2>
<svg width="200" height="100" style="border:2px solid blue;">
  <circle cx="50" cy="50" r="40" fill="red" />
  <rect x="100" y="20" width="80" height="60" fill="blue" />
  <text x="100" y="90" fill="black" font-size="14">SVG работает!</text>
</svg>
</body>
</html>'''

out_path = r'C:\Users\Victor\Desktop\Новая папка (2)\olympiad-db\public\diag_base64.html'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Written: {out_path}')
print(f'File size: {os.path.getsize(out_path)} bytes')
print(f'Data URI length: {len(b64)} chars')
