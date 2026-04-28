@echo off
cd /d "%~dp0.."
python scripts/fill_class_to_1050.py --grade 5 --batch-size 10
pause
