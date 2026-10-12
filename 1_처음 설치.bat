@echo off
cd /d "%~dp0"
set "CLAUDE=claude"
where claude >nul 2>nul || set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
echo.
echo  필요한 프로그램을 설치합니다. 중간에 물어보면 Yes 를 고르세요.
echo.
"%CLAUDE%" "workflow/설치안내.md 대로 설치해줘"
