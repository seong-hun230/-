<# :
@echo off
setlocal
echo Video tools installer is starting...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%~f0'; iex ([IO.File]::ReadAllText($f, [Text.Encoding]::UTF8))"
echo.
pause
exit /b
#>

# ============================================================
#  무료 영상 도구 일괄 설치 (Windows 10/11)
#  FFmpeg, faster-whisper, PySceneDetect, Real-ESRGAN,
#  ComfyUI, Blender, Remotion, REA
#  설치 위치: C:\Users\(사용자)\VideoTools
# ============================================================

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Join-Path $env:USERPROFILE 'VideoTools'
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Start-Transcript -Path (Join-Path $Root 'install-log.txt') -Append | Out-Null

function Say($msg) { Write-Host ''; Write-Host "==== $msg ====" -ForegroundColor Cyan }

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Add-UserPath($dir) {
    $cur = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $cur) { $cur = '' }
    if (($cur -split ';') -notcontains $dir) {
        [Environment]::SetEnvironmentVariable('Path', ($cur.TrimEnd(';') + ';' + $dir).TrimStart(';'), 'User')
    }
    Refresh-Path
}

function Winget-Install($id, $name, $extra = @()) {
    Say "$name 설치"
    winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements --disable-interactivity @extra
    if ($LASTEXITCODE -ne 0) {
        # 이미 설치돼 있으면 최신 버전으로 업데이트만 시도
        winget upgrade -e --id $id --silent --accept-package-agreements --accept-source-agreements --disable-interactivity @extra | Out-Null
    }
    Refresh-Path
}

function Winget-Has($id) {
    winget list -e --id $id --accept-source-agreements --disable-interactivity | Out-Null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host ''
    Write-Host 'winget(앱 설치 관리자)이 없습니다.' -ForegroundColor Red
    Write-Host 'Microsoft Store에서 "앱 설치 관리자"를 검색해 설치(또는 업데이트)한 뒤 이 파일을 다시 실행하세요.'
    Stop-Transcript | Out-Null
    return
}

# ---------- 1. FFmpeg ----------
Winget-Install 'Gyan.FFmpeg' 'FFmpeg (편집·렌더)'

# ---------- 2~3. Python + faster-whisper + PySceneDetect ----------
Winget-Install 'Python.Python.3.12' 'Python 3.12 (faster-whisper, PySceneDetect용)' @('--scope', 'user')

$py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $py)) { $py = 'C:\Program Files\Python312\python.exe' }
if (-not (Test-Path $py)) {
    try { $py = (& py -3.12 -c "import sys; print(sys.executable)") } catch { $py = $null }
}

$venv = Join-Path $Root 'python-env'
if ($py -and (Test-Path $py)) {
    Say 'faster-whisper (받아쓰기) + PySceneDetect (장면 나누기) 설치'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { & $py -m venv $venv }
    $vpy = Join-Path $venv 'Scripts\python.exe'
    & $vpy -m pip install --upgrade pip
    & $vpy -m pip install --upgrade faster-whisper whisper-ctranslate2 'scenedetect[opencv]'
    Add-UserPath (Join-Path $venv 'Scripts')
} else {
    Write-Host 'Python을 찾지 못해 faster-whisper / PySceneDetect 설치를 건너뜁니다. PC를 재시작한 뒤 이 파일을 다시 실행하세요.' -ForegroundColor Yellow
}

# ---------- 4. Real-ESRGAN (공식 Windows 실행 파일) ----------
Say 'Real-ESRGAN (화질 키우기) 설치'
$esr = Join-Path $Root 'Real-ESRGAN'
if (-not (Test-Path (Join-Path $esr 'realesrgan-ncnn-vulkan.exe'))) {
    $url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip'
    $zip = Join-Path $env:TEMP 'realesrgan-ncnn-vulkan.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($hash -eq 'ABC02804E17982A3BE33675E4D471E91EA374E65B70167ABC09E31ACB412802D') {
        Expand-Archive -Force -Path $zip -DestinationPath $esr
    } else {
        Write-Host "다운로드한 파일의 검증값이 달라 설치하지 않았습니다. ($hash)" -ForegroundColor Red
    }
    Remove-Item $zip -ErrorAction SilentlyContinue
}
Add-UserPath $esr

# ---------- 5. ComfyUI ----------
Winget-Install 'Comfy.ComfyUI-Desktop' 'ComfyUI (내 PC AI 이미지)'

# ---------- 6. Blender ----------
Winget-Install 'BlenderFoundation.Blender' 'Blender (3D)'

# ---------- 7. Node.js + Remotion ----------
Winget-Install 'OpenJS.NodeJS.LTS' 'Node.js LTS (Remotion, REA용)'

$rp = Join-Path $Root 'remotion-project'
if (Get-Command npx.cmd -ErrorAction SilentlyContinue) {
    if (-not (Test-Path (Join-Path $rp 'package.json'))) {
        Say 'Remotion (코드 모션그래픽) 프로젝트 만들기'
        Push-Location $Root
        npx.cmd --yes create-video@latest --yes --blank remotion-project
        Pop-Location
    }
} else {
    Write-Host 'Node.js를 찾지 못해 Remotion 설치를 건너뜁니다. PC를 재시작한 뒤 다시 실행하세요.' -ForegroundColor Yellow
}

# ---------- 8. REA (Reverse Engineer Anything) ----------
if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    Say 'REA 설치'
    npm.cmd install -g rea-agents@latest
    Refresh-Path
}

# ---------- 바로 쓰는 파일 만들기 (영상/사진을 끌어다 놓으면 실행) ----------
Say '바로 쓰는 파일 만들기'
Set-Content -Encoding Default -Path (Join-Path $Root '받아쓰기_영상끌어놓기.bat') -Value @'
@echo off
if "%~1"=="" (echo Drag a video or audio file onto this file. & pause & exit /b)
whisper-ctranslate2 "%~1" --model small --language ko --output_format srt --output_dir "%~dp1"
echo.
echo Done. The .srt subtitle file is next to the original file.
pause
'@
Set-Content -Encoding Default -Path (Join-Path $Root '장면나누기_영상끌어놓기.bat') -Value @'
@echo off
if "%~1"=="" (echo Drag a video file onto this file. & pause & exit /b)
scenedetect -i "%~1" -o "%~dp1%~n1_scenes" detect-adaptive split-video
echo.
echo Done. Clips are in the "%~n1_scenes" folder next to the original file.
pause
'@
Set-Content -Encoding Default -Path (Join-Path $Root '화질키우기_사진끌어놓기.bat') -Value @'
@echo off
if "%~1"=="" (echo Drag an image file onto this file. & pause & exit /b)
"%USERPROFILE%\VideoTools\Real-ESRGAN\realesrgan-ncnn-vulkan.exe" -i "%~1" -o "%~dpn1_x4.png" -n realesrgan-x4plus
echo.
echo Done. Saved as "%~n1_x4.png" next to the original file.
pause
'@
Set-Content -Encoding Default -Path (Join-Path $Root 'Remotion_스튜디오_열기.bat') -Value @'
@echo off
cd /d "%USERPROFILE%\VideoTools\remotion-project"
npm run dev
pause
'@

# ---------- 설치 결과 확인 ----------
Say '설치 결과'
Refresh-Path
$results = [ordered]@{
    'FFmpeg'         = [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
    'faster-whisper' = (Test-Path (Join-Path $venv 'Scripts\whisper-ctranslate2.exe'))
    'PySceneDetect'  = (Test-Path (Join-Path $venv 'Scripts\scenedetect.exe'))
    'Real-ESRGAN'    = (Test-Path (Join-Path $esr 'realesrgan-ncnn-vulkan.exe'))
    'ComfyUI'        = (Winget-Has 'Comfy.ComfyUI-Desktop')
    'Blender'        = (Winget-Has 'BlenderFoundation.Blender')
    'Remotion'       = (Test-Path (Join-Path $rp 'package.json'))
    'REA'            = [bool](Get-Command rea.cmd -ErrorAction SilentlyContinue)
}
$fail = 0
foreach ($k in $results.Keys) {
    if ($results[$k]) { Write-Host ("  [성공] " + $k) -ForegroundColor Green }
    else { Write-Host ("  [실패] " + $k) -ForegroundColor Red; $fail++ }
}
Write-Host ''
Write-Host "설치 폴더: $Root"
Write-Host "설치 기록: $(Join-Path $Root 'install-log.txt')"
if ($fail -gt 0) {
    Write-Host '실패한 항목이 있으면 PC를 재시작한 뒤 이 파일을 한 번 더 실행하세요. 이미 설치된 것은 건너뜁니다.' -ForegroundColor Yellow
}

# ---------- REA를 AI 앱에 연결 (선택) ----------
if ($results['REA']) {
    Write-Host ''
    $ans = Read-Host 'REA를 Claude Code 등 AI 앱에 연결하는 설정을 지금 할까요? (Y/N)'
    if ($ans -match '^[Yy]') { rea.cmd setup }
}

Stop-Transcript | Out-Null
