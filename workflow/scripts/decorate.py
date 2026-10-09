"""STEP 4 꾸미기: 상단 고정 제목 2줄, 짧은 자막, 말하는 순간 하나씩 뜨는 배지·키워드·도장·터미널 박스,
로고 그림, 효과음, 주제 바뀔 때 줌.

사용법:
  python workflow/scripts/decorate.py 작업폴더/cut.mp4 작업폴더/cut.transcript.json 작업폴더/decor.json -o 작업폴더/final.mp4
  (--preview 를 붙이면 앞 15초만 빠르게 만들어 확인)

decor.json 형식은 workflow/templates/decor.example.json 참고.
'at' 에는 영상에서 말하는 단어(예: "받아쓰기")나 초(예: 12.5)를 쓴다.
단어로 쓰면 '앞의 효과 다음에 처음 나오는' 그 단어 시각에 맞춰 뜬다.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_time, korean_font, load_json, normalize, probe, run  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_DUR = {"badge": 3.0, "chip": 2.5, "stamp": 1.6, "logo": 2.0}


# ---------- 시각 찾기 ----------
class Timeline:
    def __init__(self, tr):
        self.chars, self.times, self.ends = [], [], []
        for s in tr["segments"]:
            for w in s["words"]:
                for c in normalize(w["w"]):
                    self.chars.append(c)
                    self.times.append(w["start"])
                    self.ends.append(w["end"])
        self.text = "".join(self.chars)
        self.cursor = 0

    def find(self, at, label):
        if isinstance(at, (int, float)):
            return float(at)
        key = normalize(str(at))
        i = self.text.find(key, self.cursor)
        if i < 0:
            i = self.text.find(key)  # 순서가 어긋났으면 처음부터
        if i < 0:
            sys.exit(f"[오류] {label}: '{at}' 라는 말을 받아쓰기에서 찾지 못했습니다. 받아쓰기 표기대로 쓰거나 초로 지정하세요.")
        self.cursor = i + len(key)
        return self.times[i]


# ---------- ASS 도우미 ----------
def ass_color(hex_rgb, alpha=0):
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t - h * 3600 - m * 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def esc(text):
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def colorize(text, words, color):
    out = esc(text)
    for w in sorted(set(words), key=len, reverse=True):
        if w and w in text:
            out = out.replace(esc(w), "{\\c" + color + "}" + esc(w) + "{\\c&HFFFFFF&}")
    return out


POP_IN = "\\fscx40\\fscy40\\t(0,110,\\fscx112\\fscy112)\\t(110,190,\\fscx100\\fscy100)"


def build_ass(cfg, tl, tr, W, H, font, duration):
    vertical = H >= W
    s = (H / 1920) if vertical else (H / 1080) * 0.8
    accent = ass_color(cfg.get("title", {}).get("color", "#FFD400"))
    styles = {
        # 이름: 크기, 글자색, 테두리(또는 상자)색, 상자여부, 테두리 두께
        "Title": (int(74 * s), "&H00FFFFFF", "&H50000000", 3, int(16 * s)),
        "Caption": (int(80 * s), "&H00FFFFFF", "&H00000000", 1, int(7 * s)),
        "Badge": (int(96 * s), "&H00FFFFFF", ass_color("#FF3B30"), 3, int(22 * s)),
        "Chip": (int(64 * s), "&H00111111", ass_color(cfg.get("title", {}).get("color", "#FFD400")), 3, int(18 * s)),
        "Stamp": (int(120 * s), ass_color("#FF2D2D"), ass_color("#FF2D2D"), 1, int(6 * s)),
        "Term": (int(60 * s), ass_color("#7CFC7C"), "&H10101010", 3, int(26 * s)),
    }
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    for name, (size, prim, outl, bs, ow) in styles.items():
        lines.append(
            f"Style: {name},{font},{size},{prim},&H000000FF,{outl},&H64000000,-1,0,0,0,100,100,0,0,{bs},{ow},0,8,20,20,20,1"
        )
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def ev(layer, a, b, style, text):
        lines.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    cx = W // 2
    sfx_pops, sfx_whoosh, logos = [], [], []

    # 1) 상단 고정 제목 2줄
    title = cfg.get("title")
    if title:
        hl = title.get("highlight", [])
        y1 = int(H * (0.085 if vertical else 0.06))
        ev(5, 0, duration, "Title", f"{{\\an8\\pos({cx},{y1})}}" + colorize(title.get("line1", ""), hl, accent))
        ev(5, 0, duration, "Title", f"{{\\an8\\pos({cx},{y1 + int(100 * s)})}}" + colorize(title.get("line2", ""), hl, accent))

    # 2) 효과(배지·키워드·도장·터미널·로고): 말하는 순간 하나씩
    pops = []
    for i, p in enumerate(cfg.get("pops", [])):
        t = tl.find(p["at"], f"pops[{i}]")
        pops.append({**p, "t": t + float(p.get("offset", 0))})
    pops.sort(key=lambda p: p["t"])
    highlight_words = list(cfg.get("title", {}).get("highlight", []))
    for idx, p in enumerate(pops):
        kind, t = p["type"], p["t"]
        if kind == "terminal":
            dur = p.get("duration", len(p["text"]) * 0.07 + 2.2)
        else:
            dur = p.get("duration", DEFAULT_DUR.get(kind, 2.5))
        # 같은 종류가 다시 뜨면 앞의 것은 그때 사라진다
        nxt = next((q["t"] for q in pops[idx + 1 :] if q["type"] == kind), None)
        end = min(t + dur, nxt) if nxt else t + dur
        end = min(end, duration)
        text = esc(str(p.get("text", "")))
        if kind == "badge":
            ev(10, t, end, "Badge", f"{{\\an7\\pos({int(W * 0.06)},{int(H * 0.25)}){POP_IN}}} {text} ")
        elif kind == "chip":
            highlight_words.append(p.get("text", ""))
            x = int(W * 0.06 + 150 * s) if any(q["type"] == "badge" for q in pops) else cx
            an = 7 if x != cx else 8
            ev(10, t, end, "Chip", f"{{\\an{an}\\pos({x},{int(H * 0.25 + 12 * s)}){POP_IN}}} {text} ")
        elif kind == "stamp":
            ev(12, t, end, "Stamp", f"{{\\an5\\pos({cx},{int(H * 0.56)})\\frz-8\\fscx260\\fscy260\\alpha&HFF&"
               f"\\t(0,140,\\fscx100\\fscy100\\alpha&H00&)\\bord{int(8 * s)}\\3c&HFFFFFF&}}{text}")
        elif kind == "terminal":
            full = str(p["text"])
            prompt = "> "
            type_dur = min(len(full) * 0.06, max(0.6, (end - t) * 0.6))
            step = type_dur / max(1, len(full))
            y = int(H * 0.36)
            for k in range(1, len(full) + 1):
                a = t + (k - 1) * step
                b = t + k * step if k < len(full) else end
                cursor = "▌" if k < len(full) else ""
                ev(11, a, b, "Term", f"{{\\an8\\pos({cx},{y})}}" + esc(prompt + full[:k]) + cursor)
        elif kind == "logo":
            logos.append({"image": p["image"], "t": t, "end": end})
        if kind != "zoom":
            sfx_pops.append(t)

    # 3) 짧은 자막 (2~4단어)
    cap = cfg.get("captions", {"enabled": True})
    if cap.get("enabled", True):
        mn, mx, mc = cap.get("min_words", 2), cap.get("max_words", 4), cap.get("max_chars", 14)
        y = int(H * (0.70 if vertical else 0.82))
        for seg in tr["segments"]:
            ws = seg["words"]
            chunks, cur = [], []
            for w in ws:
                if cur and (len(cur) >= mx or len("".join(x["w"] for x in cur + [w])) > mc) and len(cur) >= mn:
                    chunks.append(cur)
                    cur = []
                cur.append(w)
            if cur:
                if chunks and len(cur) < mn and len(chunks[-1]) + len(cur) <= mx + 1:
                    chunks[-1] += cur
                else:
                    chunks.append(cur)
            for i, c in enumerate(chunks):
                a = c[0]["start"]
                b = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else c[-1]["end"] + 0.15
                text = " ".join(x["w"] for x in c).rstrip(".,")
                ev(4, a, b, "Caption", f"{{\\an8\\pos({cx},{y})}}" + colorize(text, highlight_words, accent))

    # 4) 줌 시각
    zooms = []
    for i, z in enumerate(cfg.get("zoom", [])):
        t = tl.find(z["at"], f"zoom[{i}]")
        zooms.append((t, float(z.get("scale", 1.10))))
        sfx_whoosh.append(max(0.0, t - 0.05))
    return "\n".join(lines) + "\n", sfx_pops, sfx_whoosh, logos, zooms


def ensure_sfx():
    """효과음 파일이 없으면 직접 만든다 (원하는 소리로 바꾸려면 같은 이름으로 덮어쓰기)."""
    d = ASSETS / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    pop, whoosh = d / "pop.wav", d / "whoosh.wav"
    if not pop.exists():
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=0.09", "-af",
             "afade=t=out:st=0.01:d=0.08,volume=0.9", str(pop)])
    if not whoosh.exists():
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.35:c=pink:a=0.5", "-af",
             "highpass=f=600,lowpass=f=5000,afade=t=in:d=0.15,afade=t=out:st=0.15:d=0.2,volume=0.6", str(whoosh)])
    return pop, whoosh


def zoom_expr(zooms, fps):
    """주제 바뀔 때: 0.15초에 살짝 확대 → 0.6초 동안 제자리로."""
    if not zooms:
        return None
    terms = []
    for t0, sc in zooms:
        a = sc - 1
        tt = f"(on/{fps:.3f}-{t0:.3f})"
        terms.append(
            f"if(between({tt},0,0.15),{a:.3f}*{tt}/0.15,if(between({tt},0.15,0.75),{a:.3f}*(1-({tt}-0.15)/0.6),0))"
        )
    return "1+" + "+".join(terms)


def main():
    ap = argparse.ArgumentParser(description="제목·자막·효과·효과음·줌 입히기")
    ap.add_argument("video")
    ap.add_argument("transcript")
    ap.add_argument("config")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--preview", action="store_true", help="앞 15초만 빠르게")
    ap.add_argument("--no-sfx", action="store_true")
    args = ap.parse_args()

    info = probe(args.video)
    W, H, fps, dur = info["width"], info["height"], info["fps"], info["duration"]
    cfg = load_json(args.config)
    tr = load_json(args.transcript)
    tl = Timeline(tr)
    font_name, font_file = korean_font()
    if font_name == "custom":
        from PIL import ImageFont

        font_name = ImageFont.truetype(font_file, 20).getname()[0]
    ass_text, pops, whooshes, logos, zooms = build_ass(cfg, tl, tr, W, H, font_name, dur)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ass_path = out.with_suffix(".ass")
    ass_path.write_text(ass_text, encoding="utf-8")

    # 필터 경로는 ffmpeg 문법상 ':' '\' 를 피해야 해서 상대경로로 넘긴다
    def fpath(p):
        rel = os.path.relpath(p, os.getcwd()).replace("\\", "/")
        return rel.replace(":", "\\:").replace("'", "\\'")

    inputs = ["-i", str(args.video)]
    vf = []
    ze = zoom_expr(zooms, fps)
    last = "[0:v]"
    if ze:
        vf.append(f"{last}zoompan=z='{ze}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps:.3f},setsar=1[vz]")
        last = "[vz]"
    vf.append(f"{last}ass='{fpath(ass_path)}':fontsdir='{fpath(os.path.dirname(font_file))}'[vs]")
    last = "[vs]"
    n_in = 1
    for k, lg in enumerate(logos):
        img = Path(lg["image"])
        if not img.exists():
            print(f"[주의] 로고 파일 없음, 건너뜀: {img}")
            continue
        inputs += ["-loop", "1", "-i", str(img)]
        size = int(min(W, H) * 0.22)
        ly = 0.48 if H >= W else 0.26
        vf.append(f"[{n_in}:v]scale={size}:-1,format=rgba[lg{k}]")
        vf.append(f"{last}[lg{k}]overlay=x=(W-w)/2:y=H*{ly}:shortest=1:enable='between(t,{lg['t']:.2f},{lg['end']:.2f})'[vl{k}]")
        last = f"[vl{k}]"
        n_in += 1

    af = []
    a_last = "[0:a]" if info["has_audio"] else None
    if not args.no_sfx and (pops or whooshes) and info["has_audio"]:
        pop, whoosh = ensure_sfx()
        labels = ["[0:a]"]
        for kind, times, path, vol in (("p", pops, pop, 0.35), ("w", whooshes, whoosh, 0.45)):
            for k, t in enumerate(times):
                inputs += ["-i", str(path)]
                ms = int(t * 1000)
                af.append(f"[{n_in}:a]volume={vol},adelay={ms}|{ms}[{kind}{k}]")
                labels.append(f"[{kind}{k}]")
                n_in += 1
        af.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0[ao]")
        a_last = "[ao]"

    graph = ";".join(vf + af)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", last]
    if a_last:
        cmd += ["-map", a_last if a_last != "[0:a]" else "0:a", "-c:a", "aac", "-b:a", "192k"]
    if args.preview:
        cmd += ["-t", "15", "-preset", "veryfast"]
    else:
        cmd += ["-preset", "medium"]
    cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", f"{fps:.3f}", "-movflags", "+faststart", str(out)]
    print(f"렌더링 중... ({W}x{H}, {dur:.1f}초, 효과 {len(pops)}개, 줌 {len(zooms)}개)")
    run(cmd)
    print(f"완료: {out}")
    for t in sorted(pops):
        print(f"  효과 {fmt_time(t)}")


if __name__ == "__main__":
    main()
