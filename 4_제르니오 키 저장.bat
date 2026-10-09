@echo off
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py"
echo.
echo  제르니오 대시보드 API Keys 에서 복사한 키를 붙여넣고 Enter 를 누르세요.
echo  붙여넣기는 마우스 오른쪽 클릭입니다. 키가 화면에 안 보이는 게 정상입니다.
echo.
%PY% workflow\scripts\zernio.py set-key
echo.
echo  연결된 계정을 확인합니다...
%PY% workflow\scripts\zernio.py accounts
echo.
pause
