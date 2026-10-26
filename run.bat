@echo off
cd /d "%~dp0"
echo Starting CampusShare from: %CD%
py -m pip install -r requirements.txt
if errorlevel 1 (
  python -m pip install -r requirements.txt
  if errorlevel 1 pause & exit /b 1
)
py app.py
if errorlevel 1 python app.py
pause
