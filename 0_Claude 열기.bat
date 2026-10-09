@echo off
cd /d "%~dp0"
set "CLAUDE=claude"
where claude >nul 2>nul || set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
echo.
echo  Claude Code 를 엽니다. 아래 입력칸에 하고 싶은 일을 말로 쓰면 됩니다.
echo  끝내려면 /exit 를 입력하거나 창을 닫으세요.
echo.
"%CLAUDE%"
