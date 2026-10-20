@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (py -3 receiver.py) else (python receiver.py)
if errorlevel 1 pause
