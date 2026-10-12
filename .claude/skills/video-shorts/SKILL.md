---
name: video-shorts
description: STEP 5 숏폼 자동 분할. 롱폼 영상에서 30~45초짜리 쇼츠·릴스 4~5개를 '한 편 = 정보 하나' 원칙으로 골라 잘라내고 각각 꾸민다. "숏폼 뽑아줘", "쇼츠로 나눠줘", "릴스 4개 만들어줘", "롱폼 잘라줘" 요청에 사용.
---

# STEP 5 숏폼 — 한 편 = 정보 하나

1. 문장 목록 보기:
   ```bash
   python workflow/scripts/shorts.py list projects/<P>/work/cut.transcript.json
   ```
2. 목록을 읽고 4~5개 구간을 고른다.
   - 한 편에 정보는 딱 하나. 30~45초.
   - 앞 맥락 없이 이해되는 구간. `← 앞 문장 필요` 표시 문장으로 시작하면 스크립트가 자동으로 앞 문장을 포함한다. `← 앞 맥락 확인` 표시는 직접 판단.
   - 계획을 `projects/<P>/work/shorts_plan.json` 으로 쓴다 (`workflow/templates/shorts_plan.example.json` 형식).
3. 자르기 (가로 영상이면 `--vertical`):
   ```bash
   python workflow/scripts/shorts.py cut projects/<P>/work/cut.mp4 projects/<P>/work/cut.transcript.json projects/<P>/work/shorts_plan.json -o projects/<P>/work/shorts
   ```
   길이 경고가 나오면 구간을 조정해 다시 자른다.
4. 각 숏폼을 꾸민다 (`video-decorate` 스킬과 같은 방식, 제목 2줄은 숏폼 주제에 맞게 새로):
   ```bash
   python workflow/scripts/decorate.py projects/<P>/work/shorts/<이름>.mp4 projects/<P>/work/shorts/<이름>.transcript.json projects/<P>/work/shorts/<이름>.decor.json -o projects/<P>/out/shorts/<이름>.mp4
   ```
5. 보고: 숏폼마다 제목 · 길이 · 담은 정보 한 줄.
