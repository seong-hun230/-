@echo off
cd /d "%~dp0"
set "CLAUDE=claude"
where claude >nul 2>nul || set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
if "%~1"=="" goto nofile
echo.
echo  영상: "%~nx1"
echo  받아쓰기와 컷 편집을 시작합니다. 처음 한 번은 오래 걸릴 수 있으니 창을 닫지 마세요.
echo.
"%CLAUDE%" "/video-cut %~1"
goto end
:nofile
echo.
echo  영상 파일을 이 아이콘 위에 마우스로 끌어다 놓으세요.
echo  아이콘을 그냥 두 번 누르면 영상이 선택되지 않습니다.
echo.
pause
:end
