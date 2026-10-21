@echo off
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$m='#'+'PS-START'; $s=Get-Content -LiteralPath '%~f0' -Encoding UTF8 -Raw; iex $s.Substring($s.IndexOf($m))"
pause
exit /b
#PS-START
$ErrorActionPreference = 'SilentlyContinue'
$report = New-Object System.Collections.Generic.List[string]
function Say($text, $color = 'White') {
    Write-Host $text -ForegroundColor $color
    $report.Add($text)
}
function Ask($question) {
    $a = Read-Host "$question (Y = 예 / N = 아니오)"
    return ($a -eq 'Y' -or $a -eq 'y')
}

Say '========================================' Cyan
Say '  PC 속도 개선 도우미' Cyan
Say '========================================' Cyan

# 1. 현재 상태 진단
Say ''
Say '[1/6] PC 상태 확인' Yellow
$os = Get-CimInstance Win32_OperatingSystem
$ramTotal = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$ramUsedPct = [math]::Round((1 - $os.FreePhysicalMemory / $os.TotalVisibleMemorySize) * 100)
Say "  메모리: 전체 $ramTotal GB, 사용 중 $ramUsedPct%"
$c = Get-PSDrive C
$cFree = [math]::Round($c.Free / 1GB, 1)
$cTotal = [math]::Round(($c.Used + $c.Free) / 1GB, 1)
$cFreePct = [math]::Round($c.Free / ($c.Used + $c.Free) * 100)
Say "  C드라이브: 전체 $cTotal GB 중 남은 공간 $cFree GB ($cFreePct%)"
$disks = Get-PhysicalDisk | Select-Object FriendlyName, MediaType
foreach ($d in $disks) { Say "  저장장치: $($d.FriendlyName) / 종류: $($d.MediaType)" }

Say ''
Say '  메모리를 많이 쓰는 프로그램 TOP 8:'
Get-Process | Group-Object ProcessName | ForEach-Object {
    [pscustomobject]@{ Name = $_.Name; MB = [math]::Round(($_.Group | Measure-Object WorkingSet64 -Sum).Sum / 1MB) }
} | Sort-Object MB -Descending | Select-Object -First 8 | ForEach-Object {
    Say ("    {0,-30} {1,6} MB" -f $_.Name, $_.MB)
}

# 2. 임시 파일 정리
Say ''
Say '[2/6] 임시 파일 정리 (사용 중인 파일은 자동으로 건너뜁니다)' Yellow
$freeBefore = (Get-PSDrive C).Free
$tempDirs = @($env:TEMP, "$env:WINDIR\Temp", "$env:LOCALAPPDATA\Microsoft\Windows\INetCache")
foreach ($t in $tempDirs) {
    if (Test-Path $t) {
        Get-ChildItem -LiteralPath $t -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
}
$freed = [math]::Round(((Get-PSDrive C).Free - $freeBefore) / 1MB)
if ($freed -lt 0) { $freed = 0 }
Say "  정리 완료: 약 $freed MB 확보" Green

# 3. 휴지통 비우기 (확인 후)
Say ''
Say '[3/6] 휴지통 비우기' Yellow
if (Ask '  휴지통을 비울까요? 비우면 휴지통 안 파일은 복구할 수 없습니다') {
    Clear-RecycleBin -Force -ErrorAction SilentlyContinue
    Say '  휴지통을 비웠습니다.' Green
} else { Say '  건너뜀' }

# 4. 시작 프로그램 목록 (끄는 것은 직접 선택)
Say ''
Say '[4/6] 컴퓨터 켤 때 자동 실행되는 프로그램' Yellow
$startup = Get-CimInstance Win32_StartupCommand | Select-Object -ExpandProperty Name -Unique
if ($startup) { foreach ($s in $startup) { Say "    - $s" } } else { Say '    (없음)' }
Say '  안 쓰는 항목은 Ctrl+Shift+Esc > [시작 앱] 에서 [사용 안 함]으로 끄세요.'

# 5. 화면 효과 줄이기 (확인 후)
Say ''
Say '[5/6] 화면 애니메이션 효과 줄이기' Yellow
if (Ask '  애니메이션 효과를 꺼서 성능을 우선할까요? (창이 조금 덜 부드러워 보입니다)') {
    $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects'
    if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
    Set-ItemProperty -Path $k -Name VisualFXSetting -Value 2 -Type DWord
    Say '  설정 완료 (다시 시작하면 완전히 적용됩니다)' Green
} else { Say '  건너뜀' }

# 6. 바이러스 빠른 검사 (확인 후)
Say ''
Say '[6/6] Windows 보안 빠른 검사' Yellow
if (Ask '  빠른 검사를 할까요? (5~15분 걸립니다)') {
    Say '  검사 중입니다. 창을 닫지 마세요...'
    try {
        Start-MpScan -ScanType QuickScan -ErrorAction Stop
        $threats = Get-MpThreatDetection
        if ($threats) { Say "  위협이 발견되었습니다. [Windows 보안] 앱에서 확인하세요." Red }
        else { Say '  발견된 위협 없음' Green }
    } catch {
        Say '  Windows 보안 검사를 실행할 수 없습니다. V3, 알약 같은 다른 백신을 쓰고 있다면 그 백신으로 검사하세요.'
    }
} else { Say '  건너뜀' }

# 진단 결과
Say ''
Say '========================================' Cyan
Say '  진단 결과' Cyan
Say '========================================' Cyan
$advice = 0
if ($ramUsedPct -ge 85) { Say '  - 메모리 사용률이 높습니다. 위 TOP 8에서 안 쓰는 프로그램을 닫으세요.'; $advice++ }
if ($ramTotal -le 8) { Say "  - 메모리가 $ramTotal GB로 적은 편입니다. 램 추가를 고려해 보세요."; $advice++ }
if ($cFreePct -lt 15) { Say '  - C드라이브 공간이 부족합니다. 큰 동영상, PPT 파일을 다른 곳으로 옮기세요.'; $advice++ }
if ($disks | Where-Object { $_.MediaType -eq 'HDD' }) { Say '  - 하드디스크(HDD)를 쓰고 있습니다. SSD로 바꾸면 가장 크게 빨라집니다.'; $advice++ }
if ($advice -eq 0) { Say '  - 큰 문제는 보이지 않습니다. 컴퓨터를 [다시 시작] 해 주세요.' }
Say ''
Say '  마지막으로 [시작] > 전원 > [다시 시작] 을 눌러 주세요.' Green

$path = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PC속도개선_결과.txt'
$report | Out-File -FilePath $path -Encoding UTF8
Write-Host ''
Write-Host "  결과가 바탕화면 'PC속도개선_결과.txt' 에 저장되었습니다." -ForegroundColor Cyan
