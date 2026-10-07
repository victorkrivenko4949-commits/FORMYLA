import shutil
from pathlib import Path

auto = Path("auto_run")

for p in auto.glob("queue_retry_*"):
    shutil.rmtree(p, ignore_errors=True)

for p in auto.glob("results_retry_*"):
    shutil.rmtree(p, ignore_errors=True)

print("OK: cleaned interrupted auto retry folders")
