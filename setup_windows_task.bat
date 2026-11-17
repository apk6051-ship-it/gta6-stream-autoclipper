@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   GTA 6 Auto-Clipper - Windows Task Scheduler Setup
echo ========================================================
echo.
echo This will schedule the auto-clipper to run automatically every 2 hours.
echo.

set TASK_NAME=GTA6_AutoClipper
set BATCH_PATH=%~dp0run_clipper.bat

:: Create scheduled task running every 2 hours
schtasks /create /tn "%TASK_NAME%" /tr "\"%BATCH_PATH%\"" /sc hourly /mo 2 /f

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Scheduled task "%TASK_NAME%" created successfully!
    echo It will trigger every 2 hours automatically in the background.
    echo You can manage it anytime in Windows "Task Scheduler".
) else (
    echo.
    echo [NOTE] If permission denied, please right-click this .bat and "Run as administrator".
)

echo.
pause
