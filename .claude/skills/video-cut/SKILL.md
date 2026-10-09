---
name: video-cut
description: STEP 2~3 받아쓰기와 컷 편집. 영상을 단어별 시각까지 받아쓰고, 말 없는 구간을 자르고, 같은 문장을 두 번 읽은 곳은 뒤에 읽은 쪽만 남긴 뒤 완성본을 다시 받아써서 잘림·중복을 검증한다. "받아쓰기 해줘", "컷 편집", "말 없는 구간 잘라줘", "무음 제거", "다시 읽은 곳 정리" 요청에 사용.
---

# STEP 2~3 받아쓰기 + 컷 편집

먼저 `workflow/rules/편집규칙.md` 를 읽는다.

## 0. 영상 경로를 받았을 때 (실행 버튼으로 시작한 경우)
인자로 영상 파일 경로가 오면 묻지 말고 바로 시작한다.
1. `projects/YYYY-MM-DD_파일이름/{raw,work,out}` 폴더를 만들고 영상을 `raw/` 로 **복사**한다 (원본은 그대로 둠).
2. 사용자는 컴퓨터 초보다. 진행 상황은 한두 줄로 쉽게 알리고, 끝나면 결과 영상 위치(`projects/.../work/cut.mp4`)를 알려 "두 번 눌러서 직접 보세요"라고 안내한다.

## STEP 2 받아쓰기
```bash
python workflow/scripts/transcribe.py projects/<P>/raw/<원본>.mp4 -o projects/<P>/work/transcript.json --prompt "<고유명사들>"
```
- 처음 실행 시 모델 다운로드로 몇 분 걸린다. 너무 느리면 `--model medium`.
- 결과 `transcript.txt` 를 훑어보고 고유명사가 틀렸으면 `--prompt` 로 힌트를 주고 다시 받는다.

## STEP 3 컷 편집
1. 계획 먼저 보기:
   ```bash
   python workflow/scripts/cut.py projects/<P>/raw/<원본>.mp4 projects/<P>/work/transcript.json -o projects/<P>/work/cut.mp4 --dry-run
   ```
2. `✂ 뺌` 표시된 문장이 맞는지 직접 판단한다. 다시 읽은 게 아닌데 비슷해서 빠진 문장(예: 일부러 반복한 강조)은 `--keep 번호`, 빠졌어야 하는데 남은 실수는 `--drop 번호`.
3. 실제 편집: 같은 명령에서 `--dry-run` 을 빼고 실행. 결과: `cut.mp4`, `cut.transcript.json`, `cut_report.txt`.
4. **반드시 검증**: 완성본을 다시 받아쓰고 비교한다.
   ```bash
   python workflow/scripts/transcribe.py projects/<P>/work/cut.mp4 -o projects/<P>/work/cut.recheck.json
   python workflow/scripts/verify.py projects/<P>/work/cut.transcript.json projects/<P>/work/cut.recheck.json
   ```
   - '잘림?'이 나온 곳: 끝 음절이 잘렸으면 `--gap` 을 0.08~0.1 로 늘리거나 `--max-inner` 를 0.4 로 늘려 다시 자른다.
   - '중복?'이 나온 곳: 해당 문장 번호를 `--drop` 으로 빼고 다시 자른다.
   - 받아쓰기 오차일 수도 있으니, 확실하지 않은 곳은 시각을 알려주고 사용자에게 들어보라고 한다.
5. 보고: "원본 N초 → 편집본 M초, 뺀 문장 K개(목록), 검증 결과". 숫자는 스크립트 출력 그대로.
