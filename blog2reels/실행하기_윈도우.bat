@echo off
chcp 65001 > nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python is not installed. Install it from https://www.python.org/downloads/ and check "Add python.exe to PATH".
  pause
  exit /b
)
echo Installing required packages... (first run only, 1-2 min)
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
python app.py
pause
