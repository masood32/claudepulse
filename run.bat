@echo off
cd /d "%~dp0"

:: Install deps if missing
pip show pystray >nul 2>&1 || (
    echo Installing dependencies...
    pip install -r requirements.txt
)

:: Check if already running
netstat -an | find "47291" | find "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo Claude Usage Tracker is already running.
    echo Check the system tray arrow ^(^) near your clock.
    timeout /t 3 >nul
    exit /b
)

echo Starting Claude Usage Tracker...
echo Look for the icon in your system tray ^(click the ^ arrow near the clock^)

:: Run silently, log errors to file
pythonw main.py 2>app.log

:: If pythonw fails immediately, show the log
if %errorlevel% neq 0 (
    echo Error starting app. Check app.log for details.
    type app.log
    pause
)
