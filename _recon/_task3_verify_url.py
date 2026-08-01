"""Test: engine.url must be the same absolute path regardless of cwd."""
import os, sys

# Run from root
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
from app import app
with app.app_context():
    from app import db
    url_root = str(db.engine.url)
print(f"FROM ROOT:   {url_root}")

# Run from _recon
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)\_recon')
sys.path.insert(0, r'c:\Users\Redmi\Desktop\Новая папка (2)')
# Force reimport
for k in list(sys.modules.keys()):
    if 'app' in k.lower() or 'models' in k.lower():
        del sys.modules[k]
import importlib
import app as app_mod
importlib.reload(app_mod)
from app import app as app2
with app2.app_context():
    from app import db as db2
    url_recon = str(db2.engine.url)
print(f"FROM _recon: {url_recon}")

print(f"\nMatch: {url_root == url_recon}")
print(f"Both point to: {url_root}")
