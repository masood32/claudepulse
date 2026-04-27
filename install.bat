@echo off
cd /d "%~dp0"
echo Installing Claude Usage Tracker dependencies...
pip install -r requirements.txt
echo.
echo Done! Run "run.bat" to start the tracker.
pause
