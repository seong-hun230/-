---
name: zernio-publish
description: STEP 9 제르니오(zernio.com)로 인스타 릴스·유튜브 쇼츠·쓰레드 예약 발행과 댓글 키워드 자동 DM 설정. 반드시 초안을 보여주고 사용자가 '승인'한 뒤에만 예약한다. "예약해줘", "올려줘", "발행", "릴스 올려줘", "쇼츠 올려줘", "쓰레드 예약", "댓글 자동 DM", "배경음악 넣어줘" 요청에 사용.
---

# STEP 9 제르니오 예약 발행 + 댓글 자동 DM

먼저 `workflow/rules/업로드규칙.md` 를 읽는다. **승인 전에는 절대 publish 하지 않는다.**

## 처음 한 번 (사용자가 직접)
- 제르니오 가입·채널 연결·API 키 만들기는 `workflow/설치안내.md` 의 "제르니오 준비"를 안내한다.
- API 키는 사용자가 **자기 컴퓨터 터미널에서** 직접 저장한다: `python workflow/scripts/zernio.py set-key`
  키를 채팅에 붙여넣으려 하면 말리고 위 방법을 안내한다. 키를 출력·기록하지 않는다.
- 연결 확인: `python workflow/scripts/zernio.py accounts`

## 매번 하는 순서
1. 초안 작성: `projects/<P>/out/publish.json` (`workflow/templates/publish_draft.example.json` 형식, 경로는 out 폴더 기준).
   - 사용자가 말한 시간이 정각이면 그대로 두되 "19:23 처럼 분을 섞는 걸 권장"이라고 한 번 제안.
   - "지금 바로" → `"when": "now"` (1분 뒤 예약).
   - 배경음악을 원하면 곡을 검색해 audioId 를 넣는다:
     `python workflow/scripts/zernio.py audio --account @아이디 --q "piano"` (영어 검색어가 잘 나옴). 결과에 없으면 비슷한 분위기 곡을 제안.
   - 유튜브 쇼츠는 `final_yt.mp4`(썸네일 붙인 영상) 사용.
   - 자동 DM 은 인스타 릴스에 `automation` 으로. 키워드·DM 문구·버튼 링크·답글·팔로우 조건을 사용자에게 확인.
2. 보여주기: `python workflow/scripts/zernio.py show projects/<P>/out/publish.json` 출력 전체를 사용자에게 보여주고 "이대로 예약할까요? '승인'이라고 답해 주세요."
3. 사용자가 **'승인'** 이라고 답한 경우에만:
   ```bash
   python workflow/scripts/zernio.py approve projects/<P>/out/publish.json
   python workflow/scripts/zernio.py publish projects/<P>/out/publish.json
   ```
   승인 뒤에 무엇이든 고치면 2번부터 다시.
4. 보고 + 안내:
   - 예약 시각·채널별 결과.
   - 릴스는 예약 시각 2~3분 뒤에 올라옴.
   - 유튜브 앱에서 맨 앞 장면을 커버로 고르기.
   - **다른 계정으로 테스트 댓글** 달아 보기 (본인 계정 댓글엔 DM 안 감, 팔로우한 계정·안 한 계정 둘 다).
5. 확인·취소: `zernio.py status <초안>` / `zernio.py cancel <초안> [--only 라벨]` (취소도 실제 효력이 있으므로 사용자 확인 후).

## 오류가 날 때
- `instagram_audio_requires_facebook_login`: 인스타가 '인스타 로그인' 방식으로 연결됨 → 설치안내의 "음악 넣으려면" 절차 안내.
- 계정을 못 찾음: `accounts` 결과의 아이디로 초안의 account 를 고친다.
