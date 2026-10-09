---
name: video-thumbnail
description: STEP 7 썸네일 시안 3개. 후킹 방식이 다른 3개(질문형·숫자형·손해형)를 만들어 사람이 고르게 한다. 유튜브 쇼츠용으로 고른 썸네일을 영상 맨 앞 0.1초에 붙이는 것도 한다. "썸네일 만들어줘", "커버 만들어줘", "표지 3개" 요청에 사용.
---

# STEP 7 썸네일 — 3개 만들고 사람이 고르기

1. 영상 내용으로 문구 3개를 정한다 (문구만 바꾼 3개가 아니라 **후킹 방식이 다르게**):
   - 질문형: "아직도 ○○하세요?"
   - 숫자형: "딱 3개만 보세요"
   - 손해형: "이거 안 하면 반만 씁니다"
   숫자·주장은 영상에서 한 말 안에서만.
2. 배경 장면(얼굴이 잘 나온 시각)을 고르고 `projects/<P>/work/thumbs.json` 작성 (`workflow/templates/thumbs.example.json` 형식). 배경은 꾸미기 전 영상(`cut.mp4`)에서 뽑는다.
3. 만들기:
   ```bash
   python workflow/scripts/thumbnail.py make projects/<P>/work/cut.mp4 projects/<P>/work/thumbs.json -o projects/<P>/out/thumbs
   ```
   만든 3장을 직접 열어 글자 잘림·겹침을 확인한 뒤 사용자에게 보여주고 **고르게 한다** (Claude 가 고르지 않음).
4. 사용자가 고르면, 유튜브 쇼츠용 영상을 만든다:
   ```bash
   python workflow/scripts/thumbnail.py prepend projects/<P>/out/final.mp4 projects/<P>/out/thumbs/<고른것>.jpg -o projects/<P>/out/final_yt.mp4
   ```
   (유튜브는 커버를 자동으로 못 넣어서, 올린 뒤 유튜브 앱에서 맨 앞 장면을 커버로 고르면 됨)
