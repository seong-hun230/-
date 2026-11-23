<# :
@echo off
setlocal
set "DS_ARG=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; iex ([IO.File]::ReadAllText($f, [Text.Encoding]::UTF8))"
echo.
pause
exit /b
#>

# ============================================================
#  드라마 쇼츠 만들기 (Windows 10/11)
#  - 영상 파일을 이 파일 위로 끌어다 놓거나
#  - 더블클릭한 뒤 유튜브 링크를 붙여넣으면
#  3분 이하 세로 쇼츠(mp4)를 자동으로 만든다.
#  먼저 install-video-tools.bat 으로 FFmpeg, Python 을 설치해 두어야 한다.
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONUTF8 = '1'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

$Root = Join-Path $env:USERPROFILE 'VideoTools'
New-Item -ItemType Directory -Force -Path $Root | Out-Null

function Stop-With($msg) {
    Write-Host ''
    Write-Host $msg -ForegroundColor Red
}

# ---------- FFmpeg ----------
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Stop-With 'FFmpeg가 없습니다. install-video-tools.bat 을 먼저 실행하고 PC를 재시작한 뒤 다시 해 주세요.'
    return
}

# ---------- Python 가상환경 ----------
$venv = Join-Path $Root 'python-env'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
    $py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path $py)) { $py = 'C:\Program Files\Python312\python.exe' }
    if (-not (Test-Path $py)) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike '*WindowsApps*') { $py = $cmd.Source } else { $py = $null }
    }
    if (-not $py) {
        Stop-With 'Python이 없습니다. install-video-tools.bat 을 먼저 실행하고 PC를 재시작한 뒤 다시 해 주세요.'
        return
    }
    Write-Host '처음 실행이라 준비 작업을 합니다...' -ForegroundColor Cyan
    & $py -m venv $venv
}

# ---------- 필요한 패키지 ----------
& $vpy -c "import faster_whisper, scenedetect, cv2, yt_dlp, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '필요한 프로그램을 설치합니다 (처음 한 번, 몇 분 걸립니다)...' -ForegroundColor Cyan
    & $vpy -m pip install --upgrade pip
    & $vpy -m pip install --upgrade faster-whisper scenedetect opencv-python-headless 'yt-dlp[default]' numpy
} else {
    # 유튜브는 자주 바뀌므로 내려받기 도구만 매번 최신으로 맞춘다
    & $vpy -m pip install --quiet --upgrade 'yt-dlp[default]'
}

# ---------- 쇼츠 제작 프로그램 받기 (항상 최신으로) ----------
$script = Join-Path $Root 'drama_shorts.py'
$urls = @(
    'https://raw.githubusercontent.com/seong-hun230/-/claude/wizardly-franklin-m7erx3/.claude/skills/drama-shorts/scripts/drama_shorts.py',
    'https://raw.githubusercontent.com/seong-hun230/-/main/.claude/skills/drama-shorts/scripts/drama_shorts.py'
)
foreach ($u in $urls) {
    try {
        $tmp = "$script.new"
        Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $tmp
        if ((Get-Item $tmp).Length -gt 5000) { Move-Item -Force $tmp $script; break }
    } catch {}
}
Remove-Item "$script.new" -ErrorAction SilentlyContinue
if (-not (Test-Path $script)) {
    Stop-With '쇼츠 제작 프로그램을 내려받지 못했습니다. 인터넷 연결을 확인한 뒤 다시 실행해 주세요.'
    return
}

# ---------- 입력 ----------
$src = $env:DS_ARG
if (-not $src) {
    Write-Host ''
    Write-Host '유튜브 링크를 붙여넣거나(마우스 오른쪽 클릭), 영상 파일을 이 창으로 끌어다 놓은 뒤 Enter를 누르세요.' -ForegroundColor Yellow
    $src = Read-Host '링크 또는 파일'
}
$src = "$src".Trim().Trim('"')
if (-not $src) { Stop-With '입력이 없어 종료합니다.'; return }

$title = Read-Host '영상 위에 넣을 제목 (그냥 Enter를 누르면 자동으로 정합니다)'

$a = @($script, 'auto', $src, '--open')
if ($title) { $a += @('--title', $title) }

Write-Host ''
Write-Host '쇼츠를 만드는 중입니다. 원본 길이에 따라 10분~1시간 걸립니다. 창을 닫지 마세요.' -ForegroundColor Cyan
& $vpy @a
if ($LASTEXITCODE -eq 0) {
    Write-Host ''
    Write-Host '완성됐습니다. 방금 열린 폴더에서 "_쇼츠.mp4" 파일을 확인하세요.' -ForegroundColor Green
} else {
    Stop-With '쇼츠를 만들지 못했습니다. 위에 나온 [오류] 문구를 Claude에게 그대로 보내 주세요.'
}
