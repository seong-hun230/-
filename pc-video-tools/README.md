# 무료 영상 도구 PC 설치 안내 (Windows 10/11)

`install-video-tools.bat` 파일 하나로 아래 8개를 한 번에 설치합니다.

| # | 도구 | 하는 일 | 설치 방식 |
|---|------|---------|-----------|
| 1 | FFmpeg | 자르기·이어 붙이기·자막 입히기·렌더 | winget (Gyan.FFmpeg) |
| 2 | faster-whisper | 영상/음성 받아쓰기 → 자막(.srt) | Python 패키지 (+ whisper-ctranslate2 명령어) |
| 3 | PySceneDetect | 영상 장면 자동 나누기 | Python 패키지 (scenedetect) |
| 4 | Real-ESRGAN | 사진 화질 4배 키우기 | 공식 Windows 실행 파일 (검증값 확인 후 설치) |
| 5 | ComfyUI | 내 PC에서 AI 이미지 만들기 | winget (Comfy.ComfyUI-Desktop) |
| 6 | Blender | 3D 제작 | winget (BlenderFoundation.Blender) |
| 7 | Remotion | 코드로 모션그래픽 영상 만들기 | Node.js + 빈 프로젝트 생성 |
| 8 | REA | 프로그램 내부 분석 (AI 앱 연결용) | npm (rea-agents) |

## 1. 설치 파일 받기 (PC에서)

1. PC 인터넷 창에서 GitHub에 로그인합니다.
2. 이 저장소의 `pc-video-tools` 폴더로 들어가 **install-video-tools.bat**을 누릅니다.
3. 오른쪽 위의 **다운로드 버튼(↓, "Download raw file")**을 누릅니다.
4. 파일이 **다운로드** 폴더에 저장됩니다.

## 2. 설치 실행

1. **다운로드** 폴더에서 `install-video-tools.bat`을 **더블클릭**합니다.
2. 파란 창 **"Windows의 PC 보호"**가 뜨면 **추가 정보** → **실행**을 누릅니다.
3. 검은 창이 열리고 설치가 차례로 진행됩니다. 30분~1시간쯤 걸립니다. 창을 닫지 마세요.
4. 중간에 **"이 앱이 디바이스를 변경할 수 있도록 허용하시겠어요?"**가 뜨면 **예**를 누릅니다.
5. 끝나면 `[성공]` / `[실패]` 목록이 나옵니다.
6. 마지막에 "REA를 … 연결하는 설정을 지금 할까요?"가 나오면, PC에 Claude Code를 쓰는 경우에만 `Y`를 누르고 Enter를 칩니다. 아니면 `N`을 누릅니다.
7. 모두 끝나면 **PC를 한 번 재시작**합니다.

`[실패]`가 있으면 재시작 후 같은 파일을 한 번 더 실행하세요. 이미 설치된 것은 건너뜁니다.
설치 기록은 `C:\Users\(내 이름)\VideoTools\install-log.txt`에 남습니다.

## 3. PC를 켰을 때 사용하는 법

설치 폴더 `C:\Users\(내 이름)\VideoTools`에 바로 쓰는 파일이 만들어집니다.
(파일 탐색기 주소창에 `%USERPROFILE%\VideoTools`를 입력하고 Enter를 누르면 열립니다.)

| 하고 싶은 일 | 방법 |
|--------------|------|
| 영상 받아쓰기(자막) | 영상 파일을 **받아쓰기_영상끌어놓기.bat** 위로 끌어다 놓기 → 원본 옆에 `.srt` 생성 |
| 장면 나누기 | 영상 파일을 **장면나누기_영상끌어놓기.bat** 위로 끌어다 놓기 → `파일명_scenes` 폴더에 장면별 영상 |
| 사진 화질 키우기 | 사진을 **화질키우기_사진끌어놓기.bat** 위로 끌어다 놓기 → `파일명_x4.png` 생성 |
| Remotion 열기 | **Remotion_스튜디오_열기.bat** 더블클릭 → 인터넷 창에 편집 화면이 열림 |
| ComfyUI / Blender | 시작 메뉴(윈도우 키)에서 **ComfyUI** 또는 **Blender** 검색 후 클릭 |
| FFmpeg | 명령 프롬프트에서 `ffmpeg` 명령으로 사용 (예: `ffmpeg -i 입력.mp4 출력.mp3`) |

## 알아두실 점

- 받아쓰기는 처음 실행할 때 AI 모델(약 500MB)을 한 번 내려받아서 오래 걸립니다.
- ComfyUI와 Real-ESRGAN은 그래픽카드가 있으면 훨씬 빠릅니다. ComfyUI는 처음 실행할 때 나오는 설치 화면에서 내 그래픽카드 종류(NVIDIA 등)를 고르면 됩니다.
- 이 설치 파일은 Windows PC에서 직접 실행해 보지는 못했습니다. 오류가 나면 검은 창의 문구나 `install-log.txt` 내용을 보내 주세요.
- Mac에서는 이 파일이 작동하지 않습니다.
