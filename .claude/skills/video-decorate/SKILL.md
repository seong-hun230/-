---
name: video-decorate
description: STEP 4 꾸미기. 컷 편집된 영상에 상단 고정 제목 2줄, 2~4단어 짧은 자막, 말하는 순간 하나씩 뜨는 번호 배지·키워드 칩·빨간 도장, 검은 터미널 박스 타이핑, 로고, 효과음, 주제 전환 줌을 넣는다. "꾸며줘", "자막 넣어줘", "제목 넣어줘", "효과 넣어줘", "릴스처럼 만들어줘" 요청에 사용.
---

# STEP 4 꾸미기

먼저 `workflow/rules/편집규칙.md` 의 꾸미기 규칙과 피드백 기록을 읽는다.

## 1. decor.json 만들기
`projects/<P>/work/cut.transcript.json`(또는 `.txt`)을 읽고 `workflow/templates/decor.example.json` 형식으로 `projects/<P>/work/decor.json` 을 쓴다.
- **title**: 1줄 '누구에게', 2줄 '무엇을'. 각 15자 안팎. highlight 는 핵심어 1~2개만.
- **pops**: 말하는 순간에 하나씩.
  - 영상에서 "첫 번째/두 번째…"라고 말하는 곳 → `badge` (번호)
  - 그 항목의 핵심 단어 → `chip`
  - 제일 중요한 한 마디 → `stamp` (영상 전체에 1~2개만)
  - 사용자가 말로 읽어 준 명령어·문장 → `terminal` (화면 저장을 부르는 장치)
  - 앱·장소 이름 → `logo` (`workflow/assets/logos/` 에 파일이 있을 때만. 없으면 chip 으로 대신하고 로고 png 를 넣어 달라고 안내)
  - `at` 은 받아쓰기에 적힌 표기 그대로(띄어쓰기는 무시됨). 같은 말이 여러 번 나오면 순서대로 매칭된다.
- **zoom**: 주제가 바뀌는 말("두 번째", "이제", "마지막으로" 등)에 scale 1.08~1.12.
- 글을 많이 띄우지 않는다. 한 화면에 새 요소는 하나씩.

## 2. 미리보기 → 본 렌더링
```bash
python workflow/scripts/decorate.py projects/<P>/work/cut.mp4 projects/<P>/work/cut.transcript.json projects/<P>/work/decor.json -o projects/<P>/work/preview.mp4 --preview
```
미리보기에서 몇 장면을 캡처해 확인한다:
```bash
ffmpeg -y -ss 3 -i projects/<P>/work/preview.mp4 -frames:v 1 projects/<P>/work/check_3s.png
```
캡처를 직접 열어 글자 겹침·잘림·위치를 확인하고, 문제 없으면 본 렌더링:
```bash
python workflow/scripts/decorate.py projects/<P>/work/cut.mp4 projects/<P>/work/cut.transcript.json projects/<P>/work/decor.json -o projects/<P>/out/final.mp4
```

## 3. 피드백
사용자가 "자막이 커요", "도장이 너무 많아요" 등 피드백을 주면 decor.json 이나 스크립트 값을 고치고, 편집규칙.md 의 피드백 기록에 추가한다.
