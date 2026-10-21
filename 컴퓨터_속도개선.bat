@echo off
chcp 65001 >nul
title 컴퓨터 속도 개선

rem 관리자 권한 확인 - 없으면 관리자 권한으로 다시 실행
net session >nul 2>&1
if %errorlevel% neq 0 goto :elevate
goto :main

:elevate
echo 관리자 권한이 필요합니다. 허용 창이 뜨면 [예]를 눌러주세요.
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b

:main
cls
echo ==============================================
echo   컴퓨터 속도 개선 - 개인 파일은 지우지 않습니다
echo ==============================================
echo.

echo [1/6] 정리 전 C 드라이브 남은 용량
powershell -NoProfile -Command "$d=Get-PSDrive C; '{0:N1} GB 남음' -f ($d.Free/1GB)"
echo.

echo [2/6] 임시 파일 삭제 중... 사용 중인 파일은 자동으로 건너뜁니다
del /f /s /q "%TEMP%\*" >nul 2>&1
for /d %%D in ("%TEMP%\*") do rd /s /q "%%D" >nul 2>&1
del /f /s /q "%SystemRoot%\Temp\*" >nul 2>&1
for /d %%D in ("%SystemRoot%\Temp\*") do rd /s /q "%%D" >nul 2>&1
echo      완료
echo.

echo [3/6] 윈도우 업데이트 찌꺼기 파일 정리 중... 몇 분 걸릴 수 있습니다
net stop wuauserv >nul 2>&1
del /f /s /q "%SystemRoot%\SoftwareDistribution\Download\*" >nul 2>&1
for /d %%D in ("%SystemRoot%\SoftwareDistribution\Download\*") do rd /s /q "%%D" >nul 2>&1
net start wuauserv >nul 2>&1
echo      완료
echo.

echo [4/6] 인터넷 DNS 캐시 초기화
ipconfig /flushdns >nul 2>&1
echo      완료
echo.

echo [5/6] 디스크 최적화 중... SSD는 TRIM, HDD는 조각모음이 자동 선택됩니다
defrag C: /O
echo.

echo [6/6] 정리 후 C 드라이브 남은 용량
powershell -NoProfile -Command "$d=Get-PSDrive C; '{0:N1} GB 남음' -f ($d.Free/1GB)"
echo.

echo ==============================================
echo   메모리를 많이 쓰는 프로그램 TOP 10
echo ==============================================
powershell -NoProfile -Command "Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 @{n='프로그램';e={$_.ProcessName}}, @{n='메모리MB';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize"
echo 위 목록에서 안 쓰는 프로그램은 꺼두면 빨라집니다.
echo.

echo ==============================================
echo   마지막 단계: 시작 프로그램 끄기
echo ==============================================
echo 잠시 후 [시작 앱] 설정 화면이 열립니다.
echo 켤 때 자동 실행이 필요 없는 프로그램의 스위치를 [끔]으로 바꾸세요.
echo 예: 카카오톡, 스팀, 각종 업데이트 도우미 등. 백신 프로그램은 켜두세요.
echo.
pause
start ms-settings:startupapps

echo.
echo 모든 작업이 끝났습니다. 컴퓨터를 한 번 재시작하면 효과가 더 좋습니다.
pause
