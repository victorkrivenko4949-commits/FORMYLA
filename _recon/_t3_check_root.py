"""Test 1: engine.url from root."""
import os, sys
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')
from app import app, db
with app.app_context():
    print(f"FROM ROOT: {db.engine.url}")
