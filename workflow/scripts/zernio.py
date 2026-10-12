"""STEP 9 제르니오(zernio.com) 예약 발행 + 댓글 키워드 자동 DM.

원칙: 초안(json) → 사람에게 보여주기(show) → 사람이 '승인' → approve → publish.
승인 뒤에 초안이나 영상이 바뀌면 publish 가 거부된다(다시 보여주고 다시 승인받아야 함).

사용법:
  python workflow/scripts/zernio.py set-key                # API 키 저장 (화면에 안 보임, 내 컴퓨터에만 저장)
  python workflow/scripts/zernio.py accounts               # 연결된 계정 목록
  python workflow/scripts/zernio.py audio --account @내계정 --q "piano"   # 인스타 음악 검색
  python workflow/scripts/zernio.py show    초안.json      # 승인용 요약 보기
  python workflow/scripts/zernio.py approve 초안.json      # 사람이 '승인'이라고 한 뒤에만 실행
  python workflow/scripts/zernio.py publish 초안.json [--dry-run]
  python workflow/scripts/zernio.py status  초안.json      # 올라갔는지 확인
  python workflow/scripts/zernio.py cancel  초안.json      # 예약 취소(아직 안 올라간 것만)

초안 형식: workflow/templates/publish_draft.example.json
"""
import argparse
import datetime as dt
import getpass
import hashlib
import json
import mimetypes
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json  # noqa: E402

BASE = os.environ.get("ZERNIO_BASE_URL", "https://zernio.com/api").rstrip("/")
KEY_FILE = Path.home() / ".config" / "zernio" / "api_key"
MAX_HASHTAGS = 5
LIMITS = {"instagram": 2200, "threads": 500, "youtube_title": 100}


# ---------- 키 ----------
def get_key():
    k = os.environ.get("ZERNIO_API_KEY")
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8").strip()
    if not k:
        sys.exit("[오류] API 키가 없습니다. 내 컴퓨터 터미널에서 'python workflow/scripts/zernio.py set-key' 를 먼저 실행하세요.")
    return k


def cmd_set_key(_):
    if sys.stdin.isatty():
        k = getpass.getpass("제르니오 API 키를 붙여넣고 Enter (화면에 표시되지 않음): ").strip()
    else:
        k = sys.stdin.read().strip()
    if not k:
        sys.exit("[오류] 키가 비어 있습니다.")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(k, encoding="utf-8")
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    print(f"저장 완료: {KEY_FILE} (키 끝 4자리: …{k[-4:]})")


# ---------- HTTP ----------
def api(method, path, body=None, params=None, headers=None):
    import requests

    h = {"Authorization": f"Bearer {get_key()}", "Content-Type": "application/json"}
    h.update(headers or {})
    try:
        r = requests.request(method, f"{BASE}/v1{path}", json=body, params=params, headers=h, timeout=120)
    except requests.RequestException as e:
        sys.exit(f"[연결 오류] 제르니오 서버에 연결하지 못했습니다 ({type(e).__name__}). 인터넷 연결을 확인하고 다시 시도하세요.")
    if r.status_code >= 400:
        try:
            msg = r.json()
        except ValueError:
            msg = r.text[:500]
        sys.exit(f"[제르니오 오류 {r.status_code}] {method} {path}\n{json.dumps(msg, ensure_ascii=False, indent=2)}")
    return r.json() if r.content else {}


def upload(path):
    import requests

    p = Path(path)
    if not p.exists():
        sys.exit(f"[오류] 파일이 없습니다: {p}")
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    pre = api("POST", "/media/presign", {"filename": p.name, "contentType": ctype, "size": p.stat().st_size})
    try:
        with open(p, "rb") as f:
            r = requests.put(pre["uploadUrl"], data=f, headers={"Content-Type": ctype}, timeout=1800)
    except requests.RequestException as e:
        sys.exit(f"[연결 오류] 업로드 중 끊겼습니다 ({type(e).__name__}): {p.name}. 다시 publish 하면 이어서 진행합니다.")
    if r.status_code >= 400:
        sys.exit(f"[오류] 업로드 실패 {r.status_code}: {p.name}")
    print(f"  업로드: {p.name} → {pre['publicUrl']}")
    return pre["publicUrl"]


_accounts_cache = None


def accounts():
    global _accounts_cache
    if _accounts_cache is None:
        _accounts_cache = api("GET", "/accounts").get("accounts", [])
    return _accounts_cache


def find_account(platform, ref):
    """'@아이디', 아이디, 또는 계정 ID 로 찾기"""
    ref = str(ref or "").lstrip("@").lower()
    cands = [a for a in accounts() if a.get("platform") == platform]
    for a in cands:
        if ref in (str(a.get("_id", "")).lower(), str(a.get("username", "")).lower(), str(a.get("displayName", "")).lower()):
            return a
    if not ref and len(cands) == 1:
        return cands[0]
    names = ", ".join(f"@{a.get('username')}" for a in cands) or "없음"
    sys.exit(f"[오류] {platform} 계정 '{ref}' 을 찾지 못했습니다. 연결된 {platform} 계정: {names}")


def profile_id(acc):
    p = acc.get("profileId")
    return p.get("_id") if isinstance(p, dict) else p


def cmd_accounts(_):
    for a in accounts():
        state = "" if a.get("isActive", True) else "  (비활성)"
        print(f"{a.get('platform'):<10} @{a.get('username', ''):<24} id={a.get('_id')}{state}")


def cmd_audio(args):
    acc = find_account("instagram", args.account)
    res = api("GET", f"/accounts/{acc['_id']}/instagram/audio", params={"audioType": args.type, **({"q": args.q} if args.q else {})})
    items = res.get("audio", [])
    if not items:
        print("검색 결과 없음 — 다른 단어(영어 추천: piano, calm, lofi)로 다시 찾아보세요.")
    for a in items[:20]:
        sec = (a.get("durationInMs") or 0) / 1000
        print(f"audioId={a.get('audioId')}  {a.get('title')} — {a.get('displayArtist') or a.get('creatorUsername', '')} ({sec:.0f}초)")


# ---------- 초안 ----------
def resolve(draft_path, p):
    q = Path(p)
    if q.is_absolute() or q.exists():
        return q
    return (Path(draft_path).parent / q)


def read_text(draft_path, post, key_text, key_file):
    if post.get(key_file):
        return resolve(draft_path, post[key_file]).read_text(encoding="utf-8").strip()
    return (post.get(key_text) or "").strip()


def media_files(post):
    files = [post.get("video"), post.get("cover")] + list(post.get("images", []))
    for it in post.get("threadItems", []):
        files += it.get("images", [])
    return [f for f in files if f]


def fingerprint(draft_path, draft):
    """승인 후 바뀐 게 없는지 확인용 지문 (초안 내용 + 파일 크기·수정시각)"""
    core = {k: v for k, v in draft.items() if k not in ("approval", "result")}
    h = hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode())
    for post in draft["posts"]:
        for key in ("caption_file", "description_file"):
            if post.get(key):
                h.update(resolve(draft_path, post[key]).read_bytes())
        for f in media_files(post):
            p = resolve(draft_path, f)
            st = p.stat() if p.exists() else None
            h.update(f"{f}:{st.st_size if st else 'X'}:{int(st.st_mtime) if st else 'X'}".encode())
    return h.hexdigest()[:16]


def when_of(draft, post):
    w = str(post.get("when") or draft.get("when") or "").strip()
    tz = draft.get("timezone", "Asia/Seoul")
    if w in ("now", "지금", "바로"):
        from zoneinfo import ZoneInfo

        t = dt.datetime.now(ZoneInfo(tz)) + dt.timedelta(minutes=1)
        return t.strftime("%Y-%m-%dT%H:%M:00"), tz
    if not re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", w):
        sys.exit(f"[오류] '{post.get('label')}' 예약 시각 형식이 이상합니다: '{w}' (예: 2026-10-10 19:23 또는 now)")
    return w.replace(" ", "T")[:16] + ":00", tz


def caption_of(draft_path, post):
    text = read_text(draft_path, post, "content", "caption_file")
    tags = post.get("hashtags", [])
    if tags:
        text = text.rstrip() + "\n\n" + " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    return text


def validate(draft_path, draft):
    errs, warns = [], []
    for i, post in enumerate(draft.get("posts", [])):
        name = post.get("label") or f"posts[{i}]"
        pf = post.get("platform")
        if pf not in ("instagram", "youtube", "threads"):
            errs.append(f"{name}: platform 은 instagram / youtube / threads 중 하나")
            continue
        tags = post.get("hashtags", []) + re.findall(r"#\S+", read_text(draft_path, post, "content", "caption_file"))
        if len(tags) > MAX_HASHTAGS:
            errs.append(f"{name}: 해시태그 {len(tags)}개 — {MAX_HASHTAGS}개까지만 (업로드 규칙)")
        for f in media_files(post):
            if not resolve(draft_path, f).exists():
                errs.append(f"{name}: 파일 없음 {f}")
        if pf == "instagram":
            if not post.get("video"):
                errs.append(f"{name}: 릴스 영상(video)이 없습니다")
            if len(caption_of(draft_path, post)) > LIMITS["instagram"]:
                errs.append(f"{name}: 캡션이 2200자를 넘습니다")
        if pf == "youtube":
            if not post.get("video"):
                errs.append(f"{name}: 영상(video)이 없습니다")
            if len(post.get("title", "")) > LIMITS["youtube_title"]:
                errs.append(f"{name}: 제목이 100자를 넘습니다")
            if not post.get("title"):
                warns.append(f"{name}: 제목이 없으면 설명 첫 줄이 제목이 됩니다")
            if post.get("cover"):
                warns.append(f"{name}: 유튜브 쇼츠는 커버 자동 지정 불가 — thumbnail.py prepend 로 맨 앞에 붙인 영상을 쓰세요")
        if pf == "threads":
            items = post.get("threadItems") or [{"content": post.get("content", ""), "images": post.get("images", [])}]
            for k, it in enumerate(items):
                if len(it.get("content", "")) > LIMITS["threads"]:
                    errs.append(f"{name}: {k + 1}번째 글이 500자를 넘습니다")
                if k > 0 and it.get("images"):
                    errs.append(f"{name}: 사진은 첫 번째 글에만 붙이세요 ({k + 1}번째 글에 있음)")
        w = str(post.get("when") or draft.get("when") or "")
        if re.search(r":00$", w):
            warns.append(f"{name}: 정각({w}) 대신 19:23 처럼 분을 섞는 것을 권장")
        if post.get("automation") and pf != "instagram":
            warns.append(f"{name}: 자동 DM 은 인스타에서만 DM 이 갑니다 (다른 채널은 공개 답글만)")
    return errs, warns


def cmd_show(args):
    draft = load_json(args.draft)
    errs, warns = validate(args.draft, draft)
    print(f"=== 발행 초안: {draft.get('name', Path(args.draft).name)} ===")
    for i, post in enumerate(draft["posts"], 1):
        pf = post["platform"]
        w = post.get("when") or draft.get("when")
        print(f"\n[{i}] {post.get('label', pf)}  ({pf} @{str(post.get('account', '')).lstrip('@')})  예약: {w} {draft.get('timezone', 'Asia/Seoul')}")
        if post.get("video"):
            print(f"    영상: {post['video']}")
        if post.get("cover"):
            print(f"    커버: {post['cover']}")
        if pf == "youtube":
            print(f"    제목: {post.get('title', '')}")
        if pf == "threads" and post.get("threadItems"):
            for k, it in enumerate(post["threadItems"], 1):
                img = f"  [사진 {len(it.get('images', []))}장]" if it.get("images") else ""
                print(f"    ── 글 {k}{img}\n" + "\n".join("      " + l for l in it.get("content", "").splitlines()))
        else:
            cap = caption_of(args.draft, post) if pf != "youtube" else read_text(args.draft, post, "content", "description_file")
            print("    ── 캡션/설명\n" + "\n".join("      " + l for l in cap.splitlines()))
        if post.get("firstComment"):
            print(f"    첫 댓글: {post['firstComment']}")
        m = post.get("music")
        if m:
            print(f"    배경음악: {m.get('title', m.get('audioId'))} (audioId={m.get('audioId')}, 볼륨 {m.get('volume', 10)})")
        a = post.get("automation")
        if a:
            print(f"    자동 DM: 키워드 {a.get('keywords')} → DM '{a.get('dm', '')[:40]}…'"
                  + (f" + 버튼[{a['button']['title']}]" if a.get("button") else "")
                  + (f", 답글 '{a.get('reply')}'" if a.get("reply") else "")
                  + (", 팔로워에게만" if a.get("followersOnly") else ""))
    for w in warns:
        print(f"\n[주의] {w}")
    for e in errs:
        print(f"\n[고쳐야 함] {e}")
    ap = draft.get("approval")
    if ap and ap.get("fingerprint") == fingerprint(args.draft, draft):
        print(f"\n상태: 승인됨 ({ap.get('at')})")
    else:
        print("\n상태: 승인 전 — 위 내용을 확인하고 '승인'이라고 말해 주세요.")
    if errs:
        sys.exit(1)


def cmd_approve(args):
    draft = load_json(args.draft)
    errs, _ = validate(args.draft, draft)
    if errs:
        sys.exit("[오류] 고쳐야 할 항목이 있어 승인할 수 없습니다. show 로 확인하세요.")
    draft["approval"] = {"at": dt.datetime.now().isoformat(timespec="seconds"), "fingerprint": fingerprint(args.draft, draft)}
    save_json(draft, args.draft)
    print(f"승인 기록 완료: {args.draft}")


def build_body(draft_path, draft, post, acc, urls):
    pf = post["platform"]
    when, tz = when_of(draft, post)
    psd = {}
    body = {"platforms": [{"platform": pf, "accountId": acc["_id"]}], "scheduledFor": when, "timezone": tz}
    if pf == "instagram":
        body["content"] = caption_of(draft_path, post)
        item = {"type": "video", "url": urls[post["video"]]}
        if post.get("cover"):
            item["instagramThumbnail"] = urls[post["cover"]]
        body["mediaItems"] = [item]
        if post.get("firstComment"):
            psd["firstComment"] = post["firstComment"]
        m = post.get("music")
        if m and m.get("audioId"):
            psd["audioConfiguration"] = {"audioId": str(m["audioId"]), "audioVolume": int(m.get("volume", 10)),
                                         "videoVolume": int(m.get("videoVolume", 100))}
        if "shareToFeed" in post:
            psd["shareToFeed"] = bool(post["shareToFeed"])
    elif pf == "youtube":
        body["content"] = read_text(draft_path, post, "content", "description_file")
        body["mediaItems"] = [{"type": "video", "url": urls[post["video"]]}]
        psd["title"] = post.get("title", "")
        psd["visibility"] = post.get("visibility", "public")
        psd["madeForKids"] = bool(post.get("madeForKids", False))
        if post.get("firstComment"):
            psd["firstComment"] = post["firstComment"]
        if post.get("tags"):
            body["tags"] = post["tags"]
    elif pf == "threads":
        items = post.get("threadItems")
        if items:
            psd["threadItems"] = [
                {"content": it.get("content", ""), **({"mediaItems": [{"type": "image", "url": urls[f]} for f in it["images"]]} if it.get("images") else {})}
                for it in items
            ]
            body["content"] = items[0].get("content", "")
        else:
            body["content"] = read_text(draft_path, post, "content", "caption_file")
            if post.get("images"):
                body["mediaItems"] = [{"type": "image", "url": urls[f]} for f in post["images"]]
        if post.get("topic"):
            psd["topic_tag"] = post["topic"]
    if psd:
        body["platforms"][0]["platformSpecificData"] = psd
    return body


def automation_body(post, acc, zernio_post_id):
    a = post["automation"]
    body = {
        "profileId": profile_id(acc),
        "accountId": acc["_id"],
        "postId": zernio_post_id,  # 아직 안 올라간 게시물: 올라가는 순간 자동으로 켜짐
        "name": a.get("name") or f"{post.get('label', 'post')} 자동 DM",
        "keywords": a["keywords"],
        "matchMode": a.get("matchMode", "contains"),
        "alsoMatchInDms": bool(a.get("alsoMatchInDms", True)),
    }
    if post["platform"] == "instagram":
        body["dmMessage"] = a["dm"]
        if a.get("button"):
            body["buttons"] = [{"type": "url", "title": a["button"]["title"][:20], "url": a["button"]["url"]}]
    if a.get("reply"):
        body["commentReply"] = a["reply"]
    if a.get("followersOnly") and post["platform"] == "instagram":
        msg = a.get("notFollowingMessage", "팔로우해 주시면 더 많은 정보 드릴게요! 팔로우 후 아래 버튼을 눌러 주세요.")
        body["audience"] = {"followerStatus": "follower", "whenUnknown": "verify"}
        body["followGate"] = {"message": msg, "notFollowingMessage": msg, "buttonLabel": a.get("buttonLabel", "팔로우했어요")}
    return body


def cmd_publish(args):
    draft = load_json(args.draft)
    errs, warns = validate(args.draft, draft)
    if errs:
        sys.exit("[오류] 고쳐야 할 항목이 있습니다. show 로 확인하세요.")
    ap = draft.get("approval") or {}
    if not args.dry_run and ap.get("fingerprint") != fingerprint(args.draft, draft):
        sys.exit("[거부] 승인되지 않았거나, 승인 뒤에 초안·파일이 바뀌었습니다. show 로 다시 보여주고 '승인'을 받은 뒤 approve 하세요.")
    result = draft.get("result", {})
    for i, post in enumerate(draft["posts"]):
        key = post.get("label") or f"posts[{i}]"
        if result.get(key, {}).get("postId") and not args.dry_run:
            print(f"[건너뜀] {key}: 이미 등록됨 (postId={result[key]['postId']})")
            continue
        if args.dry_run:
            acc = {"_id": f"<{post['platform']} 계정 id>", "profileId": "<profile id>"}
            urls = {f: f"<업로드될 URL: {Path(f).name}>" for f in media_files(post)}
        else:
            acc = find_account(post["platform"], post.get("account"))
            urls = {f: upload(resolve(args.draft, f)) for f in media_files(post)}
        body = build_body(args.draft, draft, post, acc, urls)
        if args.dry_run:
            print(f"\n[{key}] POST /v1/posts\n{json.dumps(body, ensure_ascii=False, indent=2)}")
            if post.get("automation"):
                print(f"[{key}] POST /v1/comment-automations\n{json.dumps(automation_body(post, acc, '<postId>'), ensure_ascii=False, indent=2)}")
            continue
        res = api("POST", "/posts", body, headers={"Idempotency-Key": str(uuid.uuid4())})
        pid = (res.get("post") or res).get("_id") or res.get("postId")
        entry = {"postId": pid, "scheduledFor": body["scheduledFor"], "timezone": body["timezone"]}
        print(f"[예약 완료] {key}: {body['scheduledFor']} ({body['timezone']}) postId={pid}")
        if post.get("automation") and pid:
            ar = api("POST", "/comment-automations", automation_body(post, acc, pid))
            entry["automationId"] = (ar.get("automation") or {}).get("id")
            print(f"[자동 DM 설정] {key}: 키워드 {post['automation']['keywords']} — 올라가는 순간 켜집니다")
        result[key] = entry
        draft["result"] = result
        save_json(draft, args.draft)  # 하나 끝날 때마다 저장 (중간에 멈춰도 중복 발행 안 되게)
    if not args.dry_run:
        print("\n알아둘 것: 릴스는 예약 시각 2~3분 뒤에 올라옵니다. 올라간 뒤 다른 계정으로 테스트 댓글을 달아 보세요.")


def cmd_status(args):
    draft = load_json(args.draft)
    for key, r in (draft.get("result") or {}).items():
        p = api("GET", f"/posts/{r['postId']}")
        p = p.get("post", p)
        print(f"{key}: {p.get('status')}  예약 {p.get('scheduledFor')}")
        for pl in p.get("platforms", []):
            print(f"   {pl.get('platform')}: {pl.get('status')} {pl.get('platformPostUrl') or ''} {pl.get('errorMessage') or ''}")


def cmd_cancel(args):
    draft = load_json(args.draft)
    for key, r in list((draft.get("result") or {}).items()):
        if args.only and key != args.only:
            continue
        api("DELETE", f"/posts/{r['postId']}")
        if r.get("automationId"):
            api("DELETE", f"/comment-automations/{r['automationId']}")
        draft["result"].pop(key)
        print(f"취소: {key}")
    save_json(draft, args.draft)


def main():
    ap = argparse.ArgumentParser(description="제르니오 예약 발행")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("set-key")
    sub.add_parser("accounts")
    a = sub.add_parser("audio")
    a.add_argument("--account", default="")
    a.add_argument("--q", default="")
    a.add_argument("--type", default="music", choices=["music", "original_sound"])
    for name in ("show", "approve", "status"):
        sub.add_parser(name).add_argument("draft")
    p = sub.add_parser("publish")
    p.add_argument("draft")
    p.add_argument("--dry-run", action="store_true", help="보내지 않고 보낼 내용만 출력")
    c = sub.add_parser("cancel")
    c.add_argument("draft")
    c.add_argument("--only", help="이 label 하나만 취소")
    args = ap.parse_args()
    {
        "set-key": cmd_set_key, "accounts": cmd_accounts, "audio": cmd_audio, "show": cmd_show,
        "approve": cmd_approve, "publish": cmd_publish, "status": cmd_status, "cancel": cmd_cancel,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
