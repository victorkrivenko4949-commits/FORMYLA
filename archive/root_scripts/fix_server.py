"""Установить все нужные пакеты и запустить сервер."""
import subprocess, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Читаем requirements
reqs = []
with open("requirements.txt", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            reqs.append(line)

# Устанавливаем
print("Устанавливаю пакеты...")
subprocess.run([sys.executable, "-m", "pip", "install", *reqs], check=True)
print("\nГотово! Пакеты установлены.")
print(f"Используй: {sys.executable} app.py")
