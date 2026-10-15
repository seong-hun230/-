"""스토리보드 → 9:16 릴스 mp4.

프레임마다 Pillow 로 합성해 ffmpeg 로 바로 인코딩한다.
켄번즈 + 줌 펀치 · 1~3어절 워드팝 자막 · 챕터 칩 · 진행바 · 전환(whip/flash/glitch/zoomblur) · 루프 · CTA.
가로 사진은 잘라내지 않고 흐린 배경 위에 올린다 → 검은 띠(레터박스)가 생기지 않는다.
"""
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import music, text_fx
from .util import FPS, H, W, ffmpeg_exe, run_ffmpeg

CANVAS_SCALE = 1.16
CW, CH = int(W * CANVAS_SCALE), int(H * CANVAS_SCALE)
TRANS_FRAMES = {"whip": 7, "flash": 5, "glitch": 6, "zoomblur": 8}

# 자막 세로 위치(화면 비율) — 레이아웃별
SUB_Y = {"full": 0.60, "wide": 0.745, "card": 0.50}
HOOK_Y = {"full": 0.50, "wide": 0.745, "card": 0.48}
WIDE_CENTER = 0.40    # 가로 사진은 위로 올리고 자막은 사진 아래에
WIDE_MAX_H = 0.52
SAFE_CX = 520         # 오른쪽 버튼 영역을 피해 살짝 왼쪽 중심


# ───────────────────────── 컬러 그레이딩 ─────────────────────────
def grade(im, mode):
    a = np.asarray(im).astype(np.float32) / 255.0
    if mode == "warm":
        a = a * np.array([1.05, 1.0, 0.92])
        a = (a - 0.5) * 1.06 + 0.5
    elif mode == "cine":
        lum = a.mean(axis=2, keepdims=True)
        shadow = np.clip(1 - lum * 2, 0, 1)
        high = np.clip(lum * 2 - 1, 0, 1)
        a = a + shadow * np.array([-0.04, 0.02, 0.05]) + high * np.array([0.05, 0.02, -0.04])
        a = (a - 0.5) * 1.12 + 0.5
        g = a.mean(axis=2, keepdims=True)
        a = g + (a - g) * 0.92
    elif mode == "punch":
        a = (a - 0.5) * 1.16 + 0.5
        g = a.mean(axis=2, keepdims=True)
        a = g + (a - g) * 1.28
    elif mode == "bright":
        a = np.clip(a * 1.07, 0, 1) ** 0.9
        a = (a - 0.5) * 1.04 + 0.5
        g = a.mean(axis=2, keepdims=True)
        a = g + (a - g) * 1.12
    else:  # clean
        a = (a - 0.5) * 1.05 + 0.5
        g = a.mean(axis=2, keepdims=True)
        a = g + (a - g) * 1.06
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def vignette_mask(size, strength=0.28):
    w, h = size
    y, x = np.ogrid[-1:1:complex(0, h), -1:1:complex(0, w)]
    r = np.sqrt(x ** 2 * 0.8 + y ** 2)
    m = 1 - strength * np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6
    return m[..., None].astype(np.float32)


# ───────────────────────── 소스 → 캔버스 ─────────────────────────
def cover(im, size):
    tw, th = size
    s = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, int(im.width * s + 0.5)), max(th, int(im.height * s + 0.5))), Image.LANCZOS)
    x, y = (im.width - tw) // 2, (im.height - th) // 2
    return im.crop((x, y, x + tw, y + th))


def build_canvas(img_path, grade_mode, fx=True):
    """→ (캔버스, 레이아웃) · full: 꽉 채움 / wide: 흐린 배경 위 사진(자막은 사진 아래)."""
    im = Image.open(img_path).convert("RGB")
    ar = im.width / im.height
    layout = "full"
    if ar <= 0.68:                    # 세로 사진: 꽉 채운다
        canvas = cover(im, (CW, CH))
    else:                             # 3:4 ~ 가로: 흐린 배경 + 원본 전체
        tall = ar <= 0.9
        layout = "full" if tall else "wide"
        center = 0.46 if tall else WIDE_CENTER
        max_h = 0.80 if tall else WIDE_MAX_H
        bg = cover(im, (CW // 4, CH // 4)).filter(ImageFilter.GaussianBlur(10))
        bg = ImageEnhance.Brightness(bg.resize((CW, CH), Image.BILINEAR)).enhance(0.55)
        fw = int(CW * 0.98)
        fh = int(fw / ar)
        if fh > CH * max_h:
            fh = int(CH * max_h)
            fw = int(fh * ar)
        fg = im.resize((fw, fh), Image.LANCZOS)
        canvas = bg
        y = int(CH * center - fh / 2)
        sh = Image.new("L", (CW, CH), 0)
        ImageDraw.Draw(sh).rectangle(((CW - fw) // 2, y + 14, (CW + fw) // 2, y + fh + 26), fill=150)
        canvas = Image.composite(Image.new("RGB", (CW, CH)), canvas, sh.filter(ImageFilter.GaussianBlur(22)))
        canvas.paste(fg, ((CW - fw) // 2, y))
    canvas = grade(canvas, grade_mode)
    if fx:
        a = np.asarray(canvas).astype(np.float32) * vignette_mask((CW, CH))
        canvas = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return canvas, layout


def card_canvas(seed=0):
    """사진이 없는 컷용 텍스트 카드 배경(진한 그라데이션 + 그레인)."""
    palettes = [((24, 24, 36), (70, 40, 110)), ((15, 32, 39), (44, 83, 100)),
                ((40, 18, 30), (120, 40, 60)), ((20, 30, 20), (50, 90, 60))]
    c1, c2 = palettes[seed % len(palettes)]
    y = np.linspace(0, 1, CH)[:, None, None]
    x = np.linspace(0, 1, CW)[None, :, None]
    t = np.clip(0.65 * y + 0.35 * x, 0, 1)
    a = np.array(c1) * (1 - t) + np.array(c2) * t
    a = a + np.random.default_rng(seed).normal(0, 4, (CH, CW, 1))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# ───────────────────────── 이징 ─────────────────────────
def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def pop_scale(u):
    """워드팝: 0.55 → 1.12 → 1.0 (약 0.16초)."""
    if u >= 0.16:
        return 1.0
    if u < 0.09:
        return 0.55 + (1.12 - 0.55) * ease_out(u / 0.09)
    return 1.12 - 0.12 * ease_out((u - 0.09) / 0.07)


# ───────────────────────── 전환 ─────────────────────────
def h_blur(im, k=14):
    return im.resize((max(1, W // k), H), Image.BILINEAR).resize((W, H), Image.BILINEAR)


def apply_transition(kind, prev, cur, i):
    n = TRANS_FRAMES.get(kind, 0)
    p = (i + 1) / (n + 1)
    if kind == "whip":
        off = int(W * ease_out(p))
        out = Image.new("RGB", (W, H))
        out.paste(h_blur(prev), (-off, 0))
        out.paste(h_blur(cur, 10 if p < 0.7 else 4), (W - off, 0))
        return out
    if kind == "flash":
        return Image.blend(cur, Image.new("RGB", (W, H), (255, 255, 255)), max(0.0, 1 - p * 1.1))
    if kind == "glitch":
        a = np.asarray(cur).copy()
        rng = np.random.default_rng(i)
        dx = int(40 * (1 - p)) + 6
        a[..., 0] = np.roll(a[..., 0], dx, axis=1)
        a[..., 2] = np.roll(a[..., 2], -dx, axis=1)
        for _ in range(6):
            y0 = rng.integers(0, H - 80)
            hh = rng.integers(20, 120)
            a[y0:y0 + hh] = np.roll(a[y0:y0 + hh], rng.integers(-90, 90), axis=1)
        return Image.fromarray(a)
    if kind == "zoomblur":
        s = 1 + 0.35 * (1 - ease_out(p))
        layers = []
        for k in (1.0, 1.06, 1.12):
            ss = s * k
            cw, ch = W / ss, H / ss
            box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
            layers.append(np.asarray(cur.resize((W, H), Image.BILINEAR, box=box)).astype(np.float32))
        return Image.fromarray(np.mean(layers, axis=0).astype(np.uint8))
    return cur


# ───────────────────────── 메인 렌더 ─────────────────────────
def chunk_times(chunks, dur, lead=0.0):
    if not chunks:
        return []
    w = [max(2, len(c)) for c in chunks]
    tot = sum(w)
    avail = dur - lead
    out, acc = [], lead
    for x in w:
        out.append(acc)
        acc += avail * x / tot
    return out


def render(sb, src_dir, out_path, title="", cta="", cta_sub="", grade_mode="clean",
           bgm_style="energetic", fx=True, log=print, progress=None, fps=FPS):
    cuts = sb["cuts"]
    sources = sb["sources"]
    starts = []
    acc = 0.0
    for c in cuts:
        starts.append(acc)
        acc += c["dur"]
    total = acc
    nframes = int(round(total * fps))

    # 캔버스 준비 (소스별 1회)
    canvases = {}
    for i, c in enumerate(cuts):
        key = c["src"]
        if key in canvases:
            continue
        if key == "card" or key not in sources:
            canvases[key] = (None, "card")
        else:
            p = os.path.join(src_dir, sources[key])
            if not os.path.exists(p):
                raise FileNotFoundError(f"스토리보드의 소스 '{key}' 파일이 없습니다: {p}")
            canvases[key] = build_canvas(p, grade_mode, fx)
    card_cache = {}

    # 그래픽 준비
    sub_imgs = []
    for c in cuts:
        size = 128 if c.get("hook") else 108
        sub_imgs.append([text_fx.text_image(t, size=size) for t in c["chunks"]])
    chap_imgs = {}
    cur_chap = None
    chap_of = []
    for c in cuts:
        if c.get("chapter"):
            cur_chap = c["chapter"]
            if cur_chap not in chap_imgs:
                chap_imgs[cur_chap] = text_fx.chip_image(cur_chap)
        chap_of.append(None if c.get("hook") or c.get("cta") else cur_chap)
    brand = text_fx.label_image(title) if title else None
    cta_lines = [text_fx.text_image(t, size=112) for t in (cta or "").split("/") if t.strip()]
    cta_btn = text_fx.cta_button(cta_sub) if cta_sub else None

    # 오디오 타임라인 + 효과음(6개 이하)
    body_start = sum(c["dur"] for c in cuts if c.get("hook"))
    chapter_starts = [starts[i] for i, c in enumerate(cuts) if c.get("chapter") and starts[i] > body_start + 0.01]
    cta_start = next((starts[i] for i, c in enumerate(cuts) if c.get("cta")), total)
    sfx = [{"t": 0.0, "type": "impact", "gain": 0.7}]
    for i, c in enumerate(cuts):
        if c.get("trans") in ("whip", "zoomblur"):
            sfx.append({"t": starts[i], "type": "whoosh", "gain": 0.8, "pan": 0.3})
        elif c.get("trans") == "glitch":
            sfx.append({"t": starts[i], "type": "zap", "gain": 0.7})
        elif c.get("trans") == "flash":
            sfx.append({"t": starts[i], "type": "impact", "gain": 0.6})
    sfx.append({"t": body_start, "type": "impact", "gain": 0.65})
    if cta_start < total:
        sfx.append({"t": cta_start + 0.25, "type": "ding", "gain": 0.6})
    sfx = sorted(sfx, key=lambda e: e["t"])[:6]

    work = os.path.dirname(os.path.abspath(out_path))
    wav = os.path.join(work, "_bgm.wav")
    silent = os.path.join(work, "_video.mp4")
    log(f"BGM 합성 ({bgm_style}, 효과음 {len(sfx)}개)…")
    audio, used_sfx = music.compose({"total": total, "body_start": body_start,
                                     "chapter_starts": chapter_starts, "cta_start": cta_start},
                                    style=bgm_style, sfx_events=sfx)
    music.write_wav(wav, audio)

    proc = subprocess.Popen(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", silent],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    prev_last = None
    ci = 0
    last_frame = None
    shown_first = set()
    try:
        for fi in range(nframes):
            t = fi / fps
            while ci + 1 < len(cuts) and t >= starts[ci + 1] - 1e-6:
                prev_last = last_frame
                ci += 1
            c = cuts[ci]
            u = t - starts[ci]
            p = u / c["dur"]

            # 1) 배경 (켄번즈 + 줌 펀치)
            canvas, layout = canvases.get(c["src"], (None, "card"))
            if canvas is None:
                canvas = card_cache.setdefault(ci % 4, card_canvas(ci % 4))
            if c.get("hook"):
                z = 1.0 + 0.10 * p
            elif c.get("zoom") == "out":
                z = 1.10 - 0.08 * p
            else:
                z = 1.02 + 0.08 * p
            punch = 1.0
            if fx and ci > 0 and c.get("trans") in ("cut", None) and u < 0.22:
                punch = 1 + 0.07 * (1 - ease_out(u / 0.22))
            zz = z * punch
            ww, hh = CW / zz, CH / zz
            pan = (0.03 if ci % 2 else -0.03) * (p - 0.5) * CW
            cx, cy = CW / 2 + pan, CH / 2
            if fx and c.get("hook") and ci == 0 and u < 0.18:   # 첫 컷 셰이크
                cx += math.sin(u * 160) * 10 * (1 - u / 0.18)
                cy += math.cos(u * 140) * 8 * (1 - u / 0.18)
            x0 = min(max(0, cx - ww / 2), CW - ww)
            y0 = min(max(0, cy - hh / 2), CH - hh)
            frame = canvas.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + ww, y0 + hh))

            # 2) 전환
            tr = c.get("trans")
            nf = int(u * fps + 1e-6)
            if tr in TRANS_FRAMES and nf < TRANS_FRAMES[tr] and (prev_last is not None or tr != "whip"):
                frame = apply_transition(tr, prev_last if prev_last is not None else frame, frame, nf)
            base_frame = frame

            # 3) 오버레이
            frame = frame.convert("RGBA")
            if c.get("cta"):
                a = min(1.0, u / 0.25) * 0.5
                frame = Image.alpha_composite(frame, Image.new("RGBA", (W, H), (0, 0, 0, int(255 * a))))
            if brand is not None and not c.get("cta"):
                frame.alpha_composite(brand, (int(W / 2 - brand.width / 2), 196))
            chap = chap_of[ci]
            if chap:
                chip = chap_imgs[chap]
                first = ci == 0 or chap_of[ci - 1] != chap
                k = ease_out(u / 0.25) if first else 1.0
                x = int(-chip.width + (70 + chip.width) * k)
                frame.alpha_composite(chip, (x, 290))
            # 자막(워드팝)
            imgs = sub_imgs[ci]
            if imgs:
                times = chunk_times(c["chunks"], c["dur"])
                j = max(i for i, s in enumerate(times) if u >= s - 1e-6)
                img = imgs[j]
                if img is not None:
                    du = u - times[j]
                    s = 1.0 if (ci == 0 and j == 0) else pop_scale(du)   # 0프레임부터 완성된 자막
                    im2 = text_fx.scaled(img, s)
                    yc = H * (HOOK_Y if c.get("hook") else SUB_Y)[layout]
                    yc = min(yc, H * 0.80 - im2.height / 2)       # 하단 캡션 영역 침범 방지
                    frame.alpha_composite(im2, (int(SAFE_CX - im2.width / 2), int(yc - im2.height / 2)))
                    if ci == 0 and j == 0:
                        shown_first.add(fi)
            # CTA
            if c.get("cta"):
                y = H * 0.40
                for li, im in enumerate(cta_lines):
                    if im is None:
                        continue
                    du = u - 0.12 - li * 0.22
                    if du < 0:
                        continue
                    im2 = text_fx.scaled(im, pop_scale(du))
                    frame.alpha_composite(im2, (int(SAFE_CX - im2.width / 2), int(y - im2.height / 2)))
                    y += im.height * 1.02
                if cta_btn is not None and u > 0.6:
                    puls = 1 + 0.05 * math.sin((u - 0.6) * 9)
                    b2 = text_fx.scaled(cta_btn, puls * pop_scale(u - 0.6))
                    frame.alpha_composite(b2, (int(SAFE_CX - b2.width / 2), int(y + 40)))
            # 진행바
            d = ImageDraw.Draw(frame)
            d.rectangle((0, 0, W, 11), fill=(0, 0, 0, 90))
            d.rectangle((0, 0, int(W * (t + 1 / fps) / total), 11), fill=text_fx.ACCENT)

            out = frame.convert("RGB")
            last_frame = base_frame
            proc.stdin.write(out.tobytes())
            if progress and fi % 15 == 0:
                progress(fi / nframes)
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise RuntimeError("영상 인코딩 실패: " + err[-800:])
    except BrokenPipeError:
        err = proc.stderr.read().decode("utf-8", "replace")
        raise RuntimeError("영상 인코딩 실패: " + err[-800:]) from None

    # 4) 믹스 + 라우드니스 -14 LUFS (2패스)
    log("라우드니스 -14 LUFS 맞추는 중…")
    r = run_ffmpeg(["-i", wav, "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json", "-f", "null", "-"])
    import json
    import re as _re
    m = _re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr.decode("utf-8", "replace"))
    if m:
        st = json.loads(m.group(0))
        af = ("loudnorm=I=-14:TP=-1.0:LRA=11:measured_I={input_i}:measured_TP={input_tp}:"
              "measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true"
              .format(**st))
    else:
        af = "loudnorm=I=-14:TP=-1.0:LRA=11"
    run_ffmpeg(["-i", silent, "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-af", af + ",aresample=48000", "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-movflags", "+faststart", out_path])
    for f in (wav, silent):
        try:
            os.remove(f)
        except OSError:
            pass
    return {"duration": total, "frames": nframes, "sfx": used_sfx, "starts": starts,
            "first_frame_subtitle": 0 in shown_first,
            "transitions": [c.get("trans") for c in cuts if c.get("trans") in TRANS_FRAMES]}


def make_cover(sb, src_dir, out_path, title="", grade_mode="clean", fx=True):
    """커버 = 훅 프레임: 첫 컷 사진 + 첫 훅 자막 전체(조각을 줄로 쌓음) + 브랜드."""
    c = sb["cuts"][0]
    key = c["src"]
    if key in sb["sources"] and key != "card":
        canvas, layout = build_canvas(os.path.join(src_dir, sb["sources"][key]), grade_mode, fx)
    else:
        canvas, layout = card_canvas(0), "card"
    frame = cover(canvas, (W, H)).convert("RGBA")
    frame = Image.alpha_composite(frame, Image.new("RGBA", (W, H), (0, 0, 0, 40)))
    lines = [text_fx.text_image(t, size=140) for t in c["chunks"]] or \
        [text_fx.text_image(title or " ", size=140)]
    lines = [im for im in lines if im is not None]
    total_h = sum(im.height for im in lines)
    y = H * (0.745 if layout == "wide" else 0.46) - total_h / 2
    y = min(y, H * 0.80 - total_h)
    for im in lines:
        frame.alpha_composite(im, (int(SAFE_CX - im.width / 2), int(y)))
        y += im.height * 0.98
    if title:
        lab = text_fx.label_image(title)
        frame.alpha_composite(lab, (int(W / 2 - lab.width / 2), 196))
    frame.convert("RGB").save(out_path, quality=92)
    return out_path
