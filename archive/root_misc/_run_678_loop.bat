@echo off
chcp 65001 >nul
cd /d "c:\Users\Victor\Desktop\Новая папка (2)"
echo [%date% %time%] Starting gen_678 loop (90 min sessions)...
:loop
echo [%date% %time%] ===== LAUNCH =====
python _gen_678.py --max-concurrent 60 --max-duration 90 >> gen_678_run.log 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] ===== CRASHED with exit code %EXIT_CODE%, restarting in 10s... ===== >> gen_678_run.log
timeout /t 10 /nobreak >nul
goto loop
