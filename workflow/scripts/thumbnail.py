"""STEP 7 썸네일 시안 3개: 후킹 방식이 다른 3개(질문형·숫자형·손해형)를 만들고 사람이 고른다.
+ 유튜브 쇼츠용: 고른 썸네일을 영상 맨 앞 0.1초에 붙이기.
+ 블로그용: 영상에서 사진 몇 장 뽑기.

사용법:
  python workflow/scripts/thumbnail.py make 작업폴더/final.mp4 작업폴더/thumbs.json -o 작업폴더/thumbs
  python workflow/scripts/thumbnail.py prepend 작업폴더/final.mp4 작업폴더/thumbs/2_숫자형.jpg -o 작업폴더/final_yt.mp4
  python workflow/scripts/thumbnail.py frames 작업폴더/cut.mp4 3.5 12 27.8 41 -o 작업폴더/blog_photos

thumbs.json 형식: workflow/templates/thumbs.example.json
  frame   : 배경으로 쓸 영상 시각(초). 얼굴이 잘 나온 장면 추천
  style   : 질문형 / 숫자형 / 손해형
  lines   : 큰 글씨 1~2줄 (짧게!)
  highlight: 색을 넣을 단어
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import korean_font, load_json, probe, run  # noqa: E402

COLORS = {"질문형": "#FFD400", "숫자형": "#00E5FF", "손해형": "#FF3B30"}


def grab(video, t, path):
    run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(path)])


def draw(bg_path, spec, size, font_file, out):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont

    W, H = size
    img = Image.open(bg_path).convert("RGB")
    # 가운데 기준으로 원하는 비율로 자르기
    r = W / H
    iw, ih = img.size
    if iw / ih > r:
        nw = int(ih * r)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / r)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    img = img.resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.55)
    d = ImageDraw.Draw(img)
    accent = spec.get("color") or COLORS.get(spec.get("style", ""), "#FFD400")
    hl = spec.get("highlight", [])
    lines = spec["lines"]
    vertical = H > W
    max_w = W * 0.88
    fs = int(H * (0.085 if vertical else 0.15))
    font = ImageFont.truetype(font_file, fs)
    while fs > 20 and max(d.textlength(l, font=font) for l in lines) > max_w:
        fs -= 4
        font = ImageFont.truetype(font_file, fs)
    gap = int(fs * 0.25)
    total = len(lines) * fs + (len(lines) - 1) * gap
    y = int(H * (0.38 if vertical else 0.5)) - total // 2
    stroke = max(4, fs // 12)
    for line in lines:
        x = (W - d.textlength(line, font=font)) / 2
        # 강조 단어만 색 넣기
        pos = 0
        segs = []
        while pos < len(line):
            hit = next((h for h in hl if h and line.startswith(h, pos)), None)
            if hit:
                segs.append((hit, accent))
                pos += len(hit)
            else:
                if segs and segs[-1][1] == "#FFFFFF":
                    segs[-1] = (segs[-1][0] + line[pos], "#FFFFFF")
                else:
                    segs.append((line[pos], "#FFFFFF"))
                pos += 1
        for text, color in segs:
            d.text((x, y), text, font=font, fill=color, stroke_width=stroke, stroke_fill="#000000")
            x += d.textlength(text, font=font)
        y += fs + gap
    tag = spec.get("tag")
    if tag:
        tf = ImageFont.truetype(font_file, int(fs * 0.4))
        tw = d.textlength(tag, font=tf)
        pad = int(fs * 0.15)
        ty = int(H * (0.18 if vertical else 0.12))
        d.rectangle(((W - tw) / 2 - pad, ty - pad, (W + tw) / 2 + pad, ty + int(fs * 0.4) + pad), fill=accent)
        d.text(((W - tw) / 2, ty), tag, font=tf, fill="#000000")
    img.save(out, quality=92)


def cmd_make(args):
    cfg = load_json(args.config)
    info = probe(args.video)
    _, font_file = korean_font()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    size = (1080, 1920) if info["height"] >= info["width"] else (1280, 720)
    if args.size:
        size = tuple(int(x) for x in args.size.lower().split("x"))
    with tempfile.TemporaryDirectory() as td:
        for k, spec in enumerate(cfg["thumbs"], 1):
            bg = Path(td) / f"bg{k}.jpg"
            grab(args.video, float(spec.get("frame", cfg.get("frame", 1.0))), bg)
            out = outdir / f"{k}_{spec.get('style', 'thumb')}.jpg"
            draw(bg, spec, size, font_file, out)
            print(f"  {out}  — {' / '.join(spec['lines'])}")
    print(f"완료: {outdir}  (3개 중 하나를 사람이 고르세요)")


def cmd_prepend(args):
    """유튜브 쇼츠는 커버를 자동으로 못 넣으므로, 맨 앞 0.1초에 썸네일 장면을 붙인다."""
    info = probe(args.video)
    W, H, fps = info["width"], info["height"], info["fps"]
    dur = args.seconds
    a_in = (["-f", "lavfi", "-t", f"{dur}", "-i", "anullsrc=r=48000:cl=stereo"] if info["has_audio"] else [])
    graph = (
        f"[1:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps:.3f},format=yuv420p[c];"
        f"[0:v]setsar=1,fps={fps:.3f},format=yuv420p[m];"
    )
    if info["has_audio"]:
        graph += "[2:a]aformat=sample_rates=48000:channel_layouts=stereo[ca];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[ma];"
        graph += "[c][ca][m][ma]concat=n=2:v=1:a=1[v][a]"
        maps = ["-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        graph += "[c][m]concat=n=2:v=1:a=0[v]"
        maps = ["-map", "[v]"]
    run(["ffmpeg", "-y", "-i", str(args.video), "-loop", "1", "-t", f"{dur}", "-i", str(args.image), *a_in,
         "-filter_complex", graph, *maps, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(args.out)])
    print(f"완료: {args.out}  (올린 뒤 유튜브 앱에서 맨 앞 장면을 커버로 고르세요)")


def cmd_frames(args):
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    for k, t in enumerate(args.times, 1):
        out = outdir / f"photo{k}.jpg"
        grab(args.video, float(t), out)
        print(f"  {out}  ({t}초)")


def main():
    ap = argparse.ArgumentParser(description="썸네일 시안 3개 / 쇼츠 앞에 커버 붙이기")
    sub = ap.add_subparsers(dest="mode", required=True)
    m = sub.add_parser("make")
    m.add_argument("video")
    m.add_argument("config")
    m.add_argument("-o", "--out", required=True)
    m.add_argument("--size", help="예: 1080x1920 또는 1280x720 (기본: 영상 방향에 맞춤)")
    p = sub.add_parser("prepend")
    p.add_argument("video")
    p.add_argument("image")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--seconds", type=float, default=0.1)
    f = sub.add_parser("frames")
    f.add_argument("video")
    f.add_argument("times", nargs="+", help="뽑을 시각(초) 여러 개")
    f.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    {"make": cmd_make, "prepend": cmd_prepend, "frames": cmd_frames}[args.mode](args)


if __name__ == "__main__":
    main()
