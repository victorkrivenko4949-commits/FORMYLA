"""Test 2: engine.url from _recon."""
import os, sys
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)\_recon')
sys.path.insert(0, r'c:\Users\Redmi\Desktop\Новая папка (2)')
from app import app, db
with app.app_context():
    print(f"FROM _recon: {db.engine.url}")
