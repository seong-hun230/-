"""작업 흐름: ① 수집 → ② 분석/스토리보드 → ③ 렌더 → ④ 검수 · 업로드 세트."""
import datetime as dt
import json
import os

from . import analyze, fetch, render, storyboard, verify
from .util import Logger, ROOT, slugify

OUT_ROOT = os.path.join(ROOT, "output")

DEFAULTS = {"length": 20, "grade": "bright", "bgm": "energetic", "engine": "auto",
            "fx": True, "api_key": "", "model": "claude-opus-5-5"}


def new_job_dir(title_hint="reels"):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(OUT_ROOT, f"{stamp}_{slugify(title_hint, 24)}")
    os.makedirs(d, exist_ok=True)
    return d


def _save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def step_analyze(url, opts, job_dir=None, log=None):
    log = log or Logger()
    o = {**DEFAULTS, **(opts or {})}
    log("블로그 불러오는 중…", 2)
    post = fetch.fetch_blog(url, log=log)
    log(f"제목: {post['title'] or '(없음)'} · 플랫폼: {post['platform']} · 블록 {len(post['blocks'])}개", 8)
    job_dir = job_dir or new_job_dir(post["title"] or "reels")
    img_dir = os.path.join(job_dir, "src")
    log("본문 사진 내려받는 중…", 10)
    n = fetch.download_images(post, img_dir, log=log)
    text_len = sum(len(b.get("text", "")) for b in post["blocks"])
    if n == 0 and text_len < 50:
        raise RuntimeError("본문을 찾지 못했습니다. 비공개 글이거나 지원하지 않는 형식일 수 있습니다.")
    _save_json(os.path.join(job_dir, "post.json"), post)
    verify.blog_contact_sheet(post, img_dir, os.path.join(job_dir, "컨택트시트.jpg"))

    engine = o["engine"]
    if engine == "auto":
        engine = "claude" if (o.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")) else "rule"
    log(f"내용 분석 중… (엔진: {'Claude' if engine == 'claude' else '규칙 기반'})", 20)
    if engine == "claude":
        plan = analyze.claude_plan(post, img_dir, o["length"], api_key=o.get("api_key") or None,
                                   model=o.get("model") or DEFAULTS["model"], log=log)
    else:
        plan = analyze.rule_plan(post, o["length"], log=log)
    plan["regulated"] = analyze.detect_regulated(post)
    _save_json(os.path.join(job_dir, "plan.json"), plan)

    sb = analyze.plan_to_storyboard(plan, post, o["length"])
    notes = {str(n_["image"]): n_["desc"] for n_ in plan.get("image_notes", [])}
    sb_text = storyboard.write(sb, title=plan.get("brand", ""), cta=plan.get("cta", ""),
                               cta_sub=plan.get("cta_sub", ""), notes=notes)
    with open(os.path.join(job_dir, "storyboard.txt"), "w", encoding="utf-8") as f:
        f.write(sb_text)
    _save_json(os.path.join(job_dir, "options.json"), {k: v for k, v in o.items() if k != "api_key"})
    log("스토리보드 완성", 30)
    return job_dir


def step_render(job_dir, opts=None, storyboard_text=None, log=None):
    log = log or Logger()
    saved = {}
    p_opts = os.path.join(job_dir, "options.json")
    if os.path.exists(p_opts):
        saved = _load_json(p_opts)
    o = {**DEFAULTS, **saved, **(opts or {})}
    sb_path = os.path.join(job_dir, "storyboard.txt")
    if storyboard_text is not None:
        with open(sb_path, "w", encoding="utf-8") as f:
            f.write(storyboard_text)
    with open(sb_path, encoding="utf-8") as f:
        sb = storyboard.parse(f.read())
    post = _load_json(os.path.join(job_dir, "post.json"))
    plan = _load_json(os.path.join(job_dir, "plan.json"))
    title = sb["meta"].get("제목", plan.get("brand", ""))
    cta = sb["meta"].get("cta", plan.get("cta", ""))
    cta_sub = sb["meta"].get("cta_sub", plan.get("cta_sub", ""))
    name = slugify(title or post.get("title") or "reels", 30)
    out_mp4 = os.path.join(job_dir, f"{name}.mp4")

    log(f"렌더 시작: 컷 {len(sb['cuts'])}개 · {storyboard.total_duration(sb):.2f}초", 32)

    def prog(f):
        log(f"렌더 중… {f * 100:.0f}%", 32 + f * 55)

    info = render.render(sb, os.path.join(job_dir, "src"), out_mp4, title=title, cta=cta,
                         cta_sub=cta_sub, grade_mode=o["grade"], bgm_style=o["bgm"],
                         fx=bool(o.get("fx", True)), log=log, progress=prog)
    _save_json(os.path.join(job_dir, "_render_info.json"), info)

    log("검수 시트 만드는 중…", 90)
    notes = {str(n_["image"]): n_["desc"] for n_ in plan.get("image_notes", [])}
    issues = verify.verify_sheet(out_mp4, sb, info["starts"], notes, os.path.join(job_dir, "검수시트.jpg"))
    cover = render.make_cover(sb, os.path.join(job_dir, "src"), os.path.join(job_dir, f"{name}_커버.jpg"),
                              title=title, grade_mode=o["grade"], fx=bool(o.get("fx", True)))
    lufs = verify.loudness(out_mp4)
    zero_sub = verify.subtitle_visible_at_zero(out_mp4)

    checks = []

    def chk(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})

    chk(zero_sub, "0초부터 자막이 떠 있다")
    chk(not issues, "검은 띠(레터박스) 없음", "; ".join(issues))
    flashy = info["transitions"]
    chk(len(flashy) <= 3, "화려한 전환 3회 이하", f"{len(flashy)}회: {', '.join(flashy)}")
    chk(len(info["sfx"]) <= 6, "효과음 6개 이하", f"{len(info['sfx'])}개")
    chk(lufs is not None and abs(lufs + 14) <= 1.0, "라우드니스 -14 LUFS 근처",
        f"{lufs:.1f} LUFS" if lufs is not None else "측정 실패")
    target = float(o.get("length") or 0)
    if target:
        chk(abs(info["duration"] - target) <= 2.5, f"목표 길이 {target:g}초 근처",
            f"실제 {info['duration']:.2f}초" + ("" if abs(info["duration"] - target) <= 2.5 else
                                              " — 블로그 사진·문장이 부족하면 짧아집니다. 스토리보드에 컷을 추가하세요."))
    hook_t = sum(c["dur"] for c in sb["cuts"] if c.get("hook"))
    chk(hook_t <= 3.2, "3초 안에 훅", f"훅 {hook_t:.2f}초")
    body = [c for c in sb["cuts"] if not c.get("hook") and not c.get("loop")]
    chk(all(1.5 <= c["dur"] <= 2.1 for c in body), "본문 컷 1.5~2.1초")
    chk(any(c.get("loop") for c in sb["cuts"]) and any(c.get("cta") for c in sb["cuts"]), "루프 + CTA 컷")
    long_chunks = [ch for c in sb["cuts"] for ch in c["chunks"] if len(ch.split()) > 3]
    chk(not long_chunks, "자막 조각 1~3어절", ", ".join(long_chunks[:3]))
    bad_nums = analyze.numbers_not_in_source(sb, post)
    chk(not bad_nums, "자막 숫자가 블로그 원문에 있음",
        "; ".join(f"줄{ln} '{ch}'" for ln, ch, _ in bad_nums[:5]))
    if plan.get("regulated"):
        chk(False, "광고 심의 대상 업종 확인", "·".join(plan["regulated"]) + " → 게시 전 사전 심의/표현 검토 필요")
    if plan.get("engine") == "rule":
        chk(False, "자막↔사진 일치 직접 확인", "규칙 기반 분석은 사진 내용을 모릅니다. 검수시트로 컷마다 확인하세요.")

    # 업로드 세트: 캡션
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in plan.get("hashtags", []) if t.strip())
    caption = (plan.get("caption", "").strip() + "\n\n" + tags).strip()
    guide = ["", "─" * 20, "[업로드 전 체크]",
             "• 인스타 앱에서 트렌드 음원을 20~25% 볼륨으로 덧입히면 노출에 유리합니다.",
             f"• 커버: {os.path.basename(cover)} (훅 프레임)",
             "• 사진 속 인물이 있으면 초상권 동의를 확인하세요(미성년자 실명 포함 금지).",
             f"• 원문: {post.get('url', '')} — 블로그 사진 저작권이 본인 것인지 확인하세요."]
    if plan.get("regulated"):
        guide.append(f"• {'·'.join(plan['regulated'])} 업종: 광고 사전 심의/표현 규정을 확인하세요.")
    with open(os.path.join(job_dir, "캡션_복붙용.txt"), "w", encoding="utf-8") as f:
        f.write(caption + "\n" + "\n".join(guide) + "\n")

    report = {"video": os.path.basename(out_mp4), "cover": os.path.basename(cover),
              "duration": round(info["duration"], 2), "lufs": lufs, "checks": checks,
              "engine": plan.get("engine"), "warnings": plan.get("warnings", []),
              "sfx": [e["type"] for e in info["sfx"]]}
    _save_json(os.path.join(job_dir, "report.json"), report)
    log("완료!", 100)
    return report
