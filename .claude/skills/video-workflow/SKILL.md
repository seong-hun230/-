---
name: video-workflow
description: 영상 하나로 4개 채널(인스타 릴스·유튜브 쇼츠·네이버 블로그·쓰레드) 콘텐츠를 만드는 전체 워크플로우. "영상 하나로 4개 채널", "이 영상으로 콘텐츠 만들어줘", "워크플로우 시작", "새 영상 작업", "대본 써줘" 같은 요청이나 촬영본(mp4/mov)을 주며 전체 진행을 원할 때 사용. 단계별 스킬(video-cut, video-decorate, video-shorts, content-write, video-thumbnail, content-review, zernio-publish)을 순서대로 이어 준다.
---

# 영상 하나로 4개 채널 — 전체 워크플로우

사람이 하는 일은 두 군데뿐: 🎥 촬영(STEP 1) 과 👀 검토(STEP 8). 나머지는 Claude 가 한다.

## 0. 시작할 때
1. `workflow/rules/` 의 규칙 문서 3개를 읽는다 (편집규칙·글쓰기규칙·업로드규칙). 피드백 기록까지 전부 적용.
2. 프로젝트 폴더를 만든다: `projects/YYYY-MM-DD_짧은제목/` 아래 `raw/`(원본), `work/`(중간 파일), `out/`(완성본).
3. 사용자가 준 촬영본을 `raw/` 로 복사(원본은 절대 수정·삭제하지 않음).
4. 아래 진행표를 `projects/.../진행.md` 로 만들고, 단계가 끝날 때마다 체크한다.

```
- [ ] STEP 2 받아쓰기        → work/transcript.json
- [ ] STEP 3 컷 편집 + 검증  → work/cut.mp4, cut_report.txt, verify 결과
- [ ] STEP 4 꾸미기          → out/final.mp4
- [ ] STEP 5 숏폼 분할       → out/shorts/*.mp4   (롱폼일 때만)
- [ ] STEP 6 글 쓰기         → out/blog.md, out/threads.md, out/caption_reels.txt, out/youtube_description.txt
- [ ] STEP 7 썸네일 3개      → out/thumbs/
- [ ] STEP 8 검토 (사람)     → 검토_체크리스트.md
- [ ] STEP 9 발행 초안→승인→예약 → out/publish.json
```

## STEP 1. 촬영 도움 (요청 시)
대본을 부탁받으면 `workflow/templates/대본_템플릿.md` 형식으로 쓴다: 한 문장 한 줄, 첫 3초에 "○○하시는 분들께…", 본론은 "첫 번째는…"처럼 번호로 끊기(나중에 배지·줌을 걸기 좋음). 사용자가 말하지 않은 사실·숫자는 넣지 않고 `(○○)` 빈칸으로 둔다.

## 진행 순서
- STEP 2~3 → `video-cut` 스킬
- STEP 4 → `video-decorate` 스킬
- STEP 5 → `video-shorts` 스킬 (롱폼일 때)
- STEP 6 → `content-write` 스킬
- STEP 7 → `video-thumbnail` 스킬
- STEP 8 → `content-review` 스킬 (사람이 검토)
- STEP 9 → `zernio-publish` 스킬 (승인 후에만)

처음 하는 사용자에게는 "STEP 2~3(받아쓰기+컷 편집)만 먼저 해 보시죠"라고 권한다.

## 공통 원칙
- 각 단계가 끝나면 결과를 검증하고(파일 존재·길이·미리보기 프레임) 짧게 보고한 뒤 다음 단계로.
- 사용자가 피드백을 주면 해당 규칙 문서의 "피드백 기록"에 날짜와 함께 한 줄 추가하고, "규칙 문서에 적어 뒀습니다"라고 알린다.
- 무거운 작업(받아쓰기·렌더링)은 몇 분 걸릴 수 있다고 미리 알린다.
