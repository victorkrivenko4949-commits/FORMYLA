@echo off
REM Запуск ночной регенерации в отдельном окне cmd.
REM Окно остаётся открытым — закрывать его НЕ нужно до утра.
REM Логи: logs\full_regen_*.log
REM Прогресс: logs\regen_progress.json
REM
REM Использование:
REM   scripts\start_overnight_regen.bat
REM
REM Утром:
REM   python scripts\morning_report.py

cd /d "%~dp0\.."
echo Starting overnight regeneration in a new window...
echo Logs: %CD%\logs\
echo Press Ctrl+C in the new window to stop early. Progress is saved after each cell.
echo.

start "FORMYLA Overnight Regen" cmd /k "chcp 65001 >nul && python scripts\regenerate_full.py --count-per-cell 25 --max-cost-per-cell 4.0"

echo.
echo OK — окно с регенерацией запущено в фоне.
echo Утром запусти: python scripts\morning_report.py
