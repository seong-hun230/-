"""컨택트시트 · 검수 시트 · 자동 점검."""
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from . import text_fx
from .util import ffmpeg_exe


def _wrap(text, f, max_w):
    lines, cur = [], ""
    for ch in text:
        if f.getlength(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def blog_contact_sheet(post, img_dir, out_path, cols=4, tw=300):
    """블로그 사진 번호표: 사진 + 번호 + 바로 앞뒤 문장(자막 짝짓기용)."""
    items = []
    blocks = post["blocks"]
    for i, b in enumerate(blocks):
        if b["type"] == "image" and b.get("file"):
            ctx = b.get("caption") or ""
            for j in (i + 1, i - 1):
                if not ctx and 0 <= j < len(blocks) and blocks[j]["type"] in ("text", "heading"):
                    ctx = blocks[j]["text"]
            items.append((b["idx"], os.path.join(img_dir, b["file"]), ctx))
    if not items:
        return None
    th = int(tw * 1.0)
    cap_h = 96
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 16) + 16, rows * (th + cap_h + 16) + 16), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    f_num = text_fx.font(34, "Black")
    f_cap = text_fx.font(19, "SemiBold")
    for k, (idx, path, ctx) in enumerate(items):
        x = 16 + (k % cols) * (tw + 16)
        y = 16 + (k // cols) * (th + cap_h + 16)
        im = Image.open(path).convert("RGB")
        im.thumbnail((tw, th))
        sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
        d.rounded_rectangle((x + 6, y + 6, x + 74, y + 52), 10, fill=(255, 212, 59))
        d.text((x + 14, y + 8), f"{idx}", font=f_num, fill=(17, 17, 17))
        for li, line in enumerate(_wrap(ctx, f_cap, tw)[:3]):
            d.text((x, y + th + 8 + li * 27), line, font=f_cap, fill=(220, 220, 220))
    sheet.save(out_path, quality=88)
    return out_path


def extract_frame(video, t, out_path=None):
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
                        "-i", video, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("프레임 추출 실패")
    import io
    im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    if out_path:
        im.save(out_path, quality=92)
    return im


def letterbox_suspect(im):
    a = np.asarray(im.convert("L")).astype(np.float32)
    top, bot = a[:60], a[-60:]
    return (top.mean() < 10 and top.std() < 3) or (bot.mean() < 10 and bot.std() < 3)


def verify_sheet(video, sb, starts, notes, out_path, cols=4):
    """컷별 [실제 렌더 프레임 + 그 컷의 자막 + 사진 메모] 시트."""
    tw, th = 270, 480
    cap_h = 150
    cuts = sb["cuts"]
    rows = (len(cuts) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 20) + 20, rows * (th + cap_h + 20) + 20), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    f1 = text_fx.font(22, "ExtraBold")
    f2 = text_fx.font(19, "SemiBold")
    issues = []
    for k, (c, s) in enumerate(zip(cuts, starts)):
        tmid = s + min(c["dur"] * 0.75, c["dur"] - 0.05)
        im = extract_frame(video, tmid)
        if letterbox_suspect(im):
            issues.append(f"컷 {k + 1}: 위/아래 검은 띠 의심")
        x = 20 + (k % cols) * (tw + 20)
        y = 20 + (k // cols) * (th + cap_h + 20)
        sheet.paste(im.resize((tw, th)), (x, y))
        tag = "훅" if c.get("hook") else ("CTA·루프" if c.get("cta") else (c.get("chapter") or ""))
        head = f"컷{k + 1}  {s:.2f}s +{c['dur']:.2f}  #{c['src']} {tag}"
        while f1.getlength(head) > tw and len(head) > 4:
            head = head[:-2] + "…"
        d.text((x, y + th + 6), head, font=f1, fill=(255, 212, 59))
        sub = " / ".join(c["chunks"]) or "(자막 없음)"
        yy = y + th + 38
        for line in _wrap("자막: " + sub, f2, tw)[:3]:
            d.text((x, yy), line, font=f2, fill=(255, 255, 255))
            yy += 25
        note = notes.get(str(c["src"])) or notes.get(c["src"]) or ""
        for line in _wrap("사진: " + note, f2, tw)[:2] if note else []:
            d.text((x, yy), line, font=f2, fill=(160, 200, 255))
            yy += 25
    sheet.save(out_path, quality=88)
    return issues


def loudness(video):
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", video, "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True)
    txt = r.stderr.decode("utf-8", "replace")
    m = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", txt)
    return float(m[-1]) if m else None


def subtitle_visible_at_zero(video):
    """0프레임 자막 확인: 자막 영역에 흰 글자 + 검은 외곽선 픽셀이 함께 있는가."""
    im = extract_frame(video, 0.0)
    a = np.asarray(im).astype(np.int16)
    h = a.shape[0]
    band = a[int(h * 0.38): int(h * 0.62)]
    white = ((band > 235).all(axis=2)).mean()
    dark = ((band < 25).all(axis=2)).mean()
    return white > 0.004 and dark > 0.004


