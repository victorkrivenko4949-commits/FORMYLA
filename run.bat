@echo off
chcp 65001 >nul
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

:loop
python -u formyla_3level.py
set RC=%ERRORLEVEL%
if "%RC%"=="0" (
  echo.
  echo ========================================
  echo ALL 3 STEPS DONE. EXIT.
  echo ========================================
  goto end
)
echo.
echo ========================================
echo Exit code %RC% - restart in 10s (progress saved)
echo ========================================
timeout /t 10 >nul
goto loop

:end
pause
