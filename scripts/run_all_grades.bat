@echo off
REM Автоматическая генерация задач для всех классов
REM Запускается последовательно: 6-7, 8, 9, 10-11

echo ======================================================================
echo FORMYLA AUTOMATIC GENERATION FOR ALL GRADES
echo ======================================================================
echo.
echo This script will generate 504 tasks for each grade:
echo   - Grade 6-7:  504 tasks (~6 hours)
echo   - Grade 8:    504 tasks (~6 hours)
echo   - Grade 9:    504 tasks (~6 hours)
echo   - Grade 10-11: 504 tasks (~6 hours)
echo.
echo Total: 2,016 tasks, ETA: ~24 hours
echo.
echo ======================================================================
echo.

REM Grade 6-7
echo [1/4] Starting generation for Grade 6-7...
python scripts\run_mass_generation.py --output generated_tasks_grade_6_7.json --grades 6-7
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Grade 6-7 generation failed!
    exit /b 1
)
echo.
echo ✅ Grade 6-7 complete!
echo.

REM Grade 8
echo [2/4] Starting generation for Grade 8...
python scripts\run_mass_generation.py --output generated_tasks_grade_8.json --grades 8
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Grade 8 generation failed!
    exit /b 1
)
echo.
echo ✅ Grade 8 complete!
echo.

REM Grade 9
echo [3/4] Starting generation for Grade 9...
python scripts\run_mass_generation.py --output generated_tasks_grade_9.json --grades 9
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Grade 9 generation failed!
    exit /b 1
)
echo.
echo ✅ Grade 9 complete!
echo.

REM Grade 10-11
echo [4/4] Starting generation for Grade 10-11...
python scripts\run_mass_generation.py --output generated_tasks_grade_10_11.json --grades 10-11
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Grade 10-11 generation failed!
    exit /b 1
)
echo.
echo ✅ Grade 10-11 complete!
echo.

echo ======================================================================
echo 🎉 ALL GRADES GENERATION COMPLETE!
echo ======================================================================
echo.
echo Generated files:
echo   - generated_tasks_grade_6_7.json (504 tasks)
echo   - generated_tasks_grade_8.json (504 tasks)
echo   - generated_tasks_grade_9.json (504 tasks)
echo   - generated_tasks_grade_10_11.json (504 tasks)
echo.
echo Total: 2,016 tasks
echo ======================================================================
