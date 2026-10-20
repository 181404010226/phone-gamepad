@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 app.py
) else (
    python app.py
)
if errorlevel 1 (
    echo.
    echo Startup failed. Check app.log. Python 3.10+ with tkinter is required.
    pause
)
