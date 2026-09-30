@echo off
cd /d "%~dp0"
python server.py
if errorlevel 1 (
    echo.
    echo Dev Panel could not start. See the error above.
    pause
    exit /b 1
)
