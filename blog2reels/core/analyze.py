"""블로그 내용 분석 → 릴스 기획안(plan) → 스토리보드.

엔진 2가지
- claude : Claude API 가 본문 + 사진을 '직접 보고' 컷마다 [사진 · 자막]을 짝짓는다. (권장)
- rule   : API 키가 없을 때. 사진 바로 앞뒤 문장을 그 사진의 자막 후보로 쓴다. (검수 필수)

어느 엔진이든 결과는 같은 plan 구조이고, plan_to_storyboard() 가
'100만 조회수 문법'(훅 3컷 1.10+1.05+0.90 · 본문 1.9초 · 루프컷 2.0초 · 전환 3회 이하)을 강제한다.
"""
import base64
import io
import json
import os
import re
from collections import Counter

HOOK_DURS = [1.10, 1.05, 0.90]
BODY_DUR = 1.90
LOOP_DUR = 2.00
FLASHY = ["whip", "flash", "glitch", "zoomblur"]

REGULATED = {
    "분양·부동산": r"분양|청약|모델하우스|입주|세대|평형|시행사|시공사|오피스텔|아파트",
    "의료": r"병원|시술|수술|의원|치료|피부과|성형|한의원|처방",
    "금융·투자": r"대출|금리|투자|수익률|보험|주식|코인|적금|펀드",
    "건강기능식품": r"건강기능식품|영양제|다이어트\s*보조|효능",
}


def body_cut_count(length):
    return max(3, round((float(length) - sum(HOOK_DURS) - LOOP_DUR) / BODY_DUR))


# ───────────────────────── 공통: 본문 정리 ─────────────────────────
def usable_images(post):
    return [b for b in post["blocks"] if b["type"] == "image" and b.get("file")]


def post_as_text(post, limit=14000):
    """[사진 n] 표시를 끼운 본문 텍스트 (읽는 순서 유지)."""
    lines = []
    for b in post["blocks"]:
        if b["type"] == "image":
            if b.get("file"):
                cap = f" (캡션: {b['caption']})" if b.get("caption") else ""
                lines.append(f"[사진 {b['idx']}]{cap}")
        elif b["type"] == "heading":
            lines.append(f"## {b['text']}")
        else:
            lines.append(b["text"])
    txt = "\n".join(lines)
    return txt[:limit]


def full_text(post):
    return " ".join(b.get("text", "") + " " + b.get("caption", "") for b in post["blocks"])


def detect_regulated(post):
    txt = (post.get("title", "") + " " + full_text(post))
    hits = []
    for name, pat in REGULATED.items():
        if len(re.findall(pat, txt)) >= 2:
            hits.append(name)
    return hits


# ───────────────────────── Claude 엔진 ─────────────────────────
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "hook": {"type": "array", "items": {
            "type": "object",
            "properties": {"image": {"type": "integer"}, "text": {"type": "string"}},
            "required": ["image", "text"], "additionalProperties": False}},
        "chapters": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "cuts": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"image": {"type": "integer"}, "text": {"type": "string"}},
                    "required": ["image", "text"], "additionalProperties": False}}},
            "required": ["name", "cuts"], "additionalProperties": False}},
        "loop_image": {"type": "integer"},
        "cta": {"type": "string"},
        "cta_sub": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "image_notes": {"type": "array", "items": {
            "type": "object",
            "properties": {"image": {"type": "integer"}, "desc": {"type": "string"}},
            "required": ["image", "desc"], "additionalProperties": False}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["brand", "hook", "chapters", "loop_image", "cta", "cta_sub", "caption",
                 "hashtags", "image_notes", "warnings"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """너는 인스타그램 릴스 100만 조회수 편집 감독이다.
블로그 글 1편과 그 글의 사진들을 받아, 9:16 세로 릴스의 컷 구성(스토리보드)을 만든다.

[가장 중요한 원칙 — 자막과 화면의 일치]
- 각 컷은 [사진 번호 + 자막]의 짝이다. 자막에 쓴 내용이 그 사진에 '실제로 보여야' 한다.
  지도 이야기에는 지도 사진, 외관 이야기에는 외관 사진, 메뉴 이야기에는 그 메뉴 사진.
- 사진을 직접 보고 판단한다. 글 속 [사진 n] 위치와 앞뒤 문장도 참고한다.
- 맞는 사진이 없으면 image 를 0 으로 둔다(텍스트 카드로 처리됨). 억지로 아무 사진이나 붙이지 않는다.
- image_notes 에 사용한 사진마다 '화면에 실제로 보이는 것'을 한 줄로 적는다(검수용).

[사실]
- 숫자·고유명사·가격·날짜는 블로그 본문에 있는 것만 쓴다. 지어내지 않는다.
- 미래 계획은 '예정'·'계획'으로 표기한다. 과장 표현(최고, 1등, 무조건, 100%)은 쓰지 않는다.

[100만 조회수 문법]
- 자막은 1~3어절 조각을 ' / ' 로 구분한다. 한 컷에 조각 1~3개. 조각 하나는 화면에 한 번에 뜬다.
  예: "대전에 / 2,293세대가 / 통째로"
- 훅(hook) 3컷: 0초부터 자막. 3초 안에 [놀라운 사실 or 질문] → [기대치] → [전환]. 결론을 미리 주지 말고 궁금하게.
- 본문은 챕터 2~4개. 챕터 이름은 2~8자(예: 입지·교통, 가격, 메뉴, 꿀팁).
- 본문 컷마다 정보 1개. 구어체로 짧게. 이모지·해시태그 금지.
- loop_image: 마지막 루프 컷(첫 훅 컷으로 자연스럽게 이어지는 사진). 보통 첫 훅 사진과 같게.
- cta: 행동 유도 1줄(예: "저장해두고 / 나중에 보세요"), cta_sub: 작은 보조 문구(12자 내외).
- caption: 인스타 캡션. 첫 줄 훅, 핵심 3줄 요약(블로그 근거), 마지막 줄 행동 유도. 이모지 소량 허용.
- hashtags: 8~15개, '#' 없이 단어만.
- brand: 화면 상단에 작게 들어갈 주제/브랜드명(12자 이내).
- warnings: 분양·의료·금융처럼 광고 심의 대상이거나, 사진과 맞추기 어려운 부분이 있으면 적는다.
"""


def _image_block(path, max_side=768):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    bio = io.BytesIO()
    im.save(bio, "JPEG", quality=80)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(bio.getvalue()).decode()}}


def claude_plan(post, img_dir, length, api_key=None, model="claude-opus-5-5", log=print,
                client=None, max_images=20):
    import anthropic
    if client is None:
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    n_body = body_cut_count(length)
    imgs = usable_images(post)[:max_images]
    content = []
    for b in imgs:
        content.append({"type": "text", "text": f"[사진 {b['idx']}]"})
        content.append(_image_block(os.path.join(img_dir, b["file"])))
    content.append({"type": "text", "text": (
        f"블로그 제목: {post.get('title', '')}\n주소: {post.get('url', '')}\n\n"
        f"=== 블로그 본문 ([사진 n] 은 위 사진의 위치) ===\n{post_as_text(post)}\n\n"
        f"=== 요청 ===\n릴스 길이 약 {length}초. 훅 3컷 + 본문 컷 정확히 {n_body}개(챕터에 나눠 배치) + 루프 컷 1개.\n"
        f"사용 가능한 사진 번호: {[b['idx'] for b in imgs] or '없음(모두 0)'}\n"
        "같은 사진은 되도록 반복하지 말고, 본문 흐름 순서대로 배치하라.")})
    log(f"Claude 분석 요청 (사진 {len(imgs)}장, 본문 컷 {n_body}개)…")
    try:
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("Claude API 키가 올바르지 않습니다.") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Claude API 사용량 한도에 걸렸습니다. 잠시 후 다시 시도하세요.") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API 오류 ({e.status_code}): {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Claude API 에 연결할 수 없습니다. 인터넷 연결을 확인하세요.") from None
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude 가 이 글의 분석을 거절했습니다. 규칙 기반 엔진으로 다시 시도하세요.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude 응답이 길이 제한에 걸렸습니다. 다시 시도하세요.")
    text = next(b.text for b in resp.content if b.type == "text")
    plan = json.loads(text)
    plan["engine"] = "claude"
    return plan


# ───────────────────────── 규칙 기반 엔진 ─────────────────────────
FILLERS = set("""정말 진짜 너무 완전 엄청 그리고 그래서 그런데 근데 하지만 또한 또 오늘은 오늘 제가 저는 저도 우리
일단 사실 약간 살짝 조금 그냥 바로 이렇게 저렇게 그렇게 이번에 이번 아주 꽤 굉장히 역시 다들 여러분
혹시 아무래도 무엇보다 특히""".split())
STOP_TAGS = set("""그리고 그래서 하지만 정말 진짜 너무 오늘 이번 여기 저기 우리 제가 저는 있는 있어요 있습니다 합니다
했어요 입니다 이렇게 그렇게 블로그 포스팅 사진 이웃 공감 댓글 감사합니다 안녕하세요 하는 되는 같아요 같은
보니 보면 해서 에서 으로 하고 그런 이런 저런 위해 대한 통해 정도 가장 함께 모두 다른 많이 다시 한번
제일 솔직 요즘 다녀왔어요 다녀왔습니다 추천해요 추천드려요 좋아요 예뻐요 같이 정말로""".split())
JOSA = ("에서는", "으로는", "에서도", "까지", "부터", "에서", "으로", "에게", "께서", "처럼", "보다",
        "이랑", "하고", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "랑")


def _clean(s):
    s = re.sub(r"[ㅋㅎㅠㅜ]{2,}|[~^♡♥★☆!?.…·]{2,}", " ", s)
    s = re.sub(r"[\U00010000-\U0010ffff]", "", s)  # 이모지
    s = re.sub(r"https?://\S+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _sentences(text):
    text = _clean(text)
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다)\s+(?=[가-힣A-Z0-9])|(?<=요)\s+(?=[가-힣A-Z0-9])", text)
    return [p.strip(" .") for p in parts if len(p.strip()) >= 4]


GREETING = re.compile(r"안녕하세요|여러분|이웃님|포스팅|블로그|구독|댓글|공감")
# 조사·어미로 끝나는 어절 = 자연스러운 끊김 위치
BOUNDARY = re.compile(r"(은|는|이|가|을|를|에서|에서도|으로|로|에|도|만|와|과|랑|이랑|하고|까지|부터|이라|라서|이라서|인데|는데|지만|고|며)[,]?$")
# 절(clause) 경계: 쉼표 또는 '명사+이라/인데'(떼어내도 말이 되는 어미)
CLAUSE_END = re.compile(r"(,|이라서|이라|라서|인데)$")


def _sent_score(s):
    sc = 0.0
    sc += 1.5 * min(2, len(re.findall(r"\d[\d,.]*", s)))
    sc += 1.0 if 8 <= len(s) <= 40 else 0.0
    sc -= 0.04 * max(0, len(s) - 45)
    if GREETING.search(s):
        sc -= 5
    return sc


def _chunk_words(words):
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or w.endswith(",") or (len(cur) >= 2 and BOUNDARY.search(w)):
            chunks.append(cur)
            cur = []
    if cur:
        if chunks and len(cur) == 1 and len(chunks[-1]) < 3:
            chunks[-1] += cur
        else:
            chunks.append(cur)
    return chunks


def _to_chunks(sentence, max_chunks=3):
    """문장 → 1~3어절 조각 최대 3개. 절 단위로 담고, 넘치면 마지막 절의 연결어미를 떼어 마무리."""
    words = [w for w in _clean(sentence).replace("，", ",").split() if w not in FILLERS]
    if not words:
        return []
    clauses, cur = [], []
    for w in words:
        cur.append(w)
        if CLAUSE_END.search(w):
            clauses.append(cur)
            cur = []
    if cur:
        clauses.append(cur)
    out = []
    for k, cl in enumerate(clauses):
        ch = _chunk_words(cl)
        if out and len(out) + len(ch) > max_chunks:
            break
        out += ch
        if len(out) >= max_chunks:
            out = out[:max_chunks]
            break
    taken = sum(len(c) for c in out)
    if taken < len(words) and out:            # 문장이 잘렸으면 마지막 연결어미를 정리
        last = out[-1][-1]
        out[-1][-1] = re.sub(r"(이라서|라서|이라|인데)$", "", last.rstrip(",")) or last
    return [" ".join(c).rstrip(",") for c in out]


def _strip_josa(w):
    for j in JOSA:
        if w.endswith(j) and len(w) - len(j) >= 2:
            return w[: -len(j)]
    return w


def _keywords(post, k=12):
    txt = post.get("title", "") * 3 + " " + full_text(post)
    words = [_strip_josa(w) for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", _clean(txt))]
    words = [w for w in words if w not in STOP_TAGS and not re.search(r"\d", w) and 2 <= len(w) <= 10
             and not re.search(r"(습니다|어요|아요|해요|었|았|겠|니다|세요)$", w)]
    return [w for w, _ in Counter(words).most_common(k)]


def _context_for_image(blocks, i):
    """i번째 블록(이미지)의 설명 후보: 캡션 > 바로 뒤 문단 > 바로 앞 문단."""
    b = blocks[i]
    cands = []
    if b.get("caption"):
        cands.append(b["caption"])
    for j in (i + 1, i - 1, i + 2, i - 2):
        if 0 <= j < len(blocks) and blocks[j]["type"] in ("text", "heading"):
            cands.append(blocks[j]["text"])
    return cands


def rule_plan(post, length, log=print):
    n_body = body_cut_count(length)
    blocks = post["blocks"]
    imgs = [(i, b) for i, b in enumerate(blocks) if b["type"] == "image" and b.get("file")]
    title = _clean(post.get("title", "")) or "오늘의 정보"
    all_sents = [s for b in blocks if b["type"] == "text" for s in _sentences(b["text"])]
    log(f"규칙 기반 분석: 문장 {len(all_sents)}개, 사진 {len(imgs)}장")

    # 사진별 자막 후보: 캡션 > 바로 뒤 문단 > 바로 앞 문단, 한 문장은 한 사진에만
    per_img, used = [], set()
    for i, b in imgs:
        cands = []
        if b.get("caption"):
            cands.append((_clean(b["caption"]), 5.0))
        for j, bonus in ((i + 1, 2.0), (i - 1, 1.0), (i + 2, 0.3)):
            if 0 <= j < len(blocks) and blocks[j]["type"] == "text":
                cands += [(s, bonus) for s in _sentences(blocks[j]["text"])[:3]]
        best, best_sc = None, -1e9
        for s, bonus in cands:
            sc = _sent_score(s) + bonus
            if s and s not in used and sc > best_sc:
                best, best_sc = s, sc
        if best:
            used.add(best)
        per_img.append({"image": b["idx"], "sent": best, "score": best_sc, "pos": i})

    # 챕터: 소제목 기준, 없으면 균등 분할
    heads = [(i, _clean(b["text"])) for i, b in enumerate(blocks) if b["type"] == "heading"]

    def chapter_of(pos):
        name = None
        for i, t in heads:
            if i <= pos:
                name = t
        return name

    # 본문 컷 선택: 사진을 글 흐름대로 고르게 뽑는다
    pool = [p for p in per_img if p["sent"]] or per_img
    body = []
    if pool:
        step = len(pool) / float(n_body)
        picks = sorted({min(len(pool) - 1, int(k * step)) for k in range(n_body)})
        body = [pool[k] for k in picks]
    # 사진이 모자라면 핵심 문장을 텍스트 카드로 채운다
    used_sents = {p["sent"] for p in body}
    extra = sorted([s for s in all_sents if s not in used_sents], key=_sent_score, reverse=True)
    while len(body) < n_body and extra:
        s = extra.pop(0)
        pos = next((i for i, b in enumerate(blocks) if s in _clean(b.get("text", ""))), len(blocks))
        body.append({"image": 0, "sent": s, "score": _sent_score(s), "pos": pos})
    body.sort(key=lambda p: p["pos"])

    n_ch = 1 if len(body) < 4 else (2 if len(body) < 8 else 3)
    chapters = []
    for k, p in enumerate(body):
        hname = chapter_of(p["pos"])
        if heads:
            name = _short_name(hname) if hname else "소개"
        else:
            name = f"핵심 {min(n_ch, k * n_ch // max(1, len(body)) + 1)}"
        if not chapters or chapters[-1]["name"] != name:
            chapters.append({"name": name, "cuts": []})
        chapters[-1]["cuts"].append({"image": p["image"], "text": " / ".join(_to_chunks(p["sent"] or title))})

    # 훅 3컷: ① 제목/핵심 숫자 ② 기대치 ③ 전환
    title = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*", " ", title).strip() or title
    num_sent = max(all_sents, key=_sent_score) if all_sents else title
    first_img = per_img[0]["image"] if per_img else 0
    num_img = next((p["image"] for p in per_img if p["sent"] == num_sent), first_img)
    third_img = per_img[min(2, len(per_img) - 1)]["image"] if per_img else 0
    hook = [
        {"image": first_img, "text": " / ".join(_to_chunks(title))},
        {"image": num_img, "text": " / ".join(_to_chunks(num_sent, 2))},
        {"image": third_img, "text": "핵심만 / 딱 정리했어요"},
    ]
    kws = _keywords(post)
    caption = "\n".join([title, ""] + [f"✔ {s}" for s in sorted(all_sents, key=_sent_score, reverse=True)[:3]]
                        + ["", "저장해두고 필요할 때 꺼내보세요"])
    return {
        "engine": "rule",
        "brand": _short_name(kws[0] if kws else title, 12),
        "hook": hook,
        "chapters": chapters,
        "loop_image": first_img,
        "cta": "저장해두고 / 나중에 보세요",
        "cta_sub": "자세한 내용은 프로필 링크",
        "caption": caption,
        "hashtags": kws[:12],
        "image_notes": [{"image": p["image"], "desc": "(자동 분석: 사진 내용 미확인 — 직접 확인 필요)"}
                        for p in per_img],
        "warnings": ["규칙 기반 분석입니다. 사진 내용을 이해하지 못하므로 컷마다 자막·사진 일치를 직접 확인하세요."],
    }


def _short_name(s, limit=8):
    s = _clean(s or "")
    s = re.sub(r"^\d+[.)]\s*", "", s)
    words = s.split()
    out = ""
    for w in words:
        if len(out) + len(w) + (1 if out else 0) > limit:
            break
        out = (out + " " + w).strip()
    return out or s[:limit]


# ───────────────────────── plan → 스토리보드 ─────────────────────────
def plan_to_storyboard(plan, post, length):
    """기획안을 스토리보드로 변환하면서 형식 규칙을 강제한다."""
    valid = {b["idx"] for b in usable_images(post)}
    files = {b["idx"]: b["file"] for b in usable_images(post)}

    def src(i):
        return str(i) if i in valid else "card"

    cuts = []
    hooks = (plan.get("hook") or [])[:3]
    while len(hooks) < 3:
        hooks.append({"image": 0, "text": plan.get("brand", "")})
    for k, h in enumerate(hooks):
        cuts.append({"src": src(h["image"]), "start": 0, "dur": HOOK_DURS[k],
                     "chunks": _chunks(h["text"]), "hook": True, "trans": "cut"})
    cuts[2]["trans"] = "whip"           # 3초 안의 전환

    n_body = body_cut_count(length)
    body = []
    for ch in plan.get("chapters") or []:
        for j, c in enumerate(ch.get("cuts") or []):
            body.append((ch.get("name", "") if j == 0 else None, c))
    body = body[:n_body]
    flashy_left = [t for t in FLASHY if t != "whip"][:2]   # 훅 whip 포함 총 3회
    zoom = "in"
    for name, c in body:
        cut = {"src": src(c["image"]), "start": 0, "dur": BODY_DUR, "chunks": _chunks(c["text"]),
               "chapter": _short_name(name, 8) if name else None, "trans": "cut", "zoom": zoom}
        if name and flashy_left and len([x for x in cuts if x.get("chapter")]) > 0:
            cut["trans"] = flashy_left.pop(0)   # 챕터 전환에만 화려한 전환 (총 3회 이하)
        zoom = "out" if zoom == "in" else "in"
        cuts.append(cut)
    loop_img = plan.get("loop_image") or (hooks[0]["image"] if hooks else 0)
    cuts.append({"src": src(loop_img), "start": 0, "dur": LOOP_DUR, "chunks": [],
                 "loop": True, "cta": True, "trans": "cut", "zoom": "out"})

    sources = {}
    for c in cuts:
        if c["src"] != "card" and c["src"] not in sources:
            sources[c["src"]] = files[int(c["src"])]
    sources = dict(sorted(sources.items(), key=lambda kv: int(kv[0])))
    sources["card"] = "텍스트카드"
    return {"sources": sources, "cuts": cuts, "meta": {}}


def _chunks(text):
    parts = [p.strip() for p in re.split(r"\s*/\s*", text or "") if p.strip()]
    if len(parts) == 1 and len(parts[0].split()) > 3:
        parts = _to_chunks(parts[0])
    return parts[:3]


def numbers_not_in_source(sb, post):
    """자막 속 숫자가 블로그 원문에 없는 경우를 찾는다(사실 검증 보조)."""
    src = re.sub(r"[\s,]", "", full_text(post) + post.get("title", ""))
    bad = []
    for c in sb["cuts"]:
        for ch in c["chunks"]:
            for num in re.findall(r"\d[\d,.]*", ch):
                n = num.replace(",", "").rstrip(".")
                if n and n not in src:
                    bad.append((c.get("line") or "?", ch, num))
    return bad
