@echo off
cd /d "c:\Users\Victor\Desktop\Новая папка (2)"
:loop
echo [%date% %time%] Starting Grade 8 generator...
python _gen_cell_tasks.py --grade 8
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Generator crashed with code %ERRORLEVEL%, restarting in 5s...
    timeout /t 5 /nobreak >nul
    goto loop
)
echo [%date% %time%] Generator completed successfully!
