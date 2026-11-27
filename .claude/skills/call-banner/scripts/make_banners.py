"""상담/방문예약 전화 유도 배너 만들기.

사용법:
  python make_banners.py --spec spec.json --out 출력폴더 [--bg 배경사진.jpg]

spec.json 예시는 ../examples/daejeon_cielio.json 참고.
제목(title)에서 *별표* 로 감싼 부분은 금색으로 강조된다. 줄바꿈은 \n. 그 밖의 HTML은 모두 글자로 처리된다.

필요한 것: playwright(파이썬), Chromium, Pretendard 글꼴(없으면 npm으로 자동 설치), ImageMagick(convert, montage).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W, H = 1000, 380  # CSS px. 2배로 찍은 뒤 가로 1200px JPG로 저장

PHONE_SVG = (
    '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" style="vertical-align:-0.12em">'
    '<path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20'
    'a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"/></svg>'
)

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1000px;height:380px;font-family:'Pretendard',sans-serif;-webkit-font-smoothing:antialiased;color:#fff;overflow:hidden}
.b{position:relative;width:1000px;height:380px;padding:46px 56px;display:flex;flex-direction:column;justify-content:center;overflow:hidden}
.photo{background:#0b1f47 url(__BG__) center 42%/cover}
.photo::before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(6,14,32,.95) 0%,rgba(6,14,32,.84) 55%,rgba(6,14,32,.35) 100%)}
.photo .h,.photo .sub,.photo .eyebrow,.photo .num{text-shadow:0 2px 10px rgba(0,0,0,.45)}
.navy{background:linear-gradient(120deg,#0b1f47 0%,#13306b 70%,#1d3f86 100%)}
.navy::after{content:"";position:absolute;right:-90px;top:-90px;width:380px;height:380px;border-radius:50%;border:46px solid rgba(201,160,110,.18)}
.b>*{position:relative;z-index:1}
.eyebrow{font-size:27px;font-weight:800;color:#f0c98f;letter-spacing:-.01em;margin-bottom:10px}
.h{font-size:64px;font-weight:900;line-height:1.13;letter-spacing:-.035em}
.h.small{font-size:50px}
.h em{font-style:normal;color:#ffd38f}
.sub{font-size:27px;font-weight:700;color:#fff;margin-top:12px;letter-spacing:-.02em}
.cta{margin-top:24px;display:inline-flex;align-items:center;gap:14px;align-self:flex-start;background:#e8372b;border-radius:999px;padding:15px 32px 15px 26px;font-size:38px;font-weight:900;letter-spacing:-.02em;box-shadow:0 8px 22px rgba(0,0,0,.3)}
.cta small{font-size:22px;font-weight:800;opacity:.95;margin-left:4px}
.num{font-size:104px;font-weight:900;letter-spacing:-.01em;line-height:1;margin-top:8px;display:flex;align-items:center;gap:18px}
.num .ic{width:92px;height:92px;border-radius:50%;background:#e13b2f;display:grid;place-items:center;font-size:52px}
.note{position:absolute;right:28px;bottom:18px;font-size:15px;font-weight:600;color:rgba(255,255,255,.6)}
"""


def ensure_pretendard() -> None:
    """Pretendard 글꼴이 없으면 npm 패키지에서 받아 글꼴 폴더에 설치한다."""
    listed = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    if "Pretendard" in listed and "Black" in listed:
        return
    if not shutil.which("npm"):
        sys.exit("Pretendard 글꼴이 없고 npm도 없습니다. https://github.com/orioncactus/pretendard 에서 설치하세요.")
    dest = Path("/usr/share/fonts/opentype/pretendard") if os.geteuid() == 0 else Path.home() / ".local/share/fonts/pretendard"
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npm", "pack", "pretendard", "--silent"], cwd=tmp, check=True, capture_output=True)
        tgz = next(Path(tmp).glob("pretendard-*.tgz"))
        names = [f"package/dist/public/static/Pretendard-{w}.otf" for w in ("Medium", "SemiBold", "Bold", "ExtraBold", "Black")]
        subprocess.run(["tar", "-xzf", str(tgz), *names], cwd=tmp, check=True)
        for n in names:
            shutil.copy(Path(tmp) / n, dest)
    subprocess.run(["fc-cache", "-f"], check=True, capture_output=True)


def chromium_path() -> str | None:
    for p in (os.environ.get("BANNER_CHROMIUM"), "/opt/pw-browsers/chromium"):
        if p and Path(p).exists():
            return p
    return None  # playwright 기본 브라우저 사용


def title_html(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    return s.replace("\n", "<br>")


def banner_html(b: dict, phone: str, label: str) -> str:
    e = html.escape
    style = "photo" if b.get("style") == "photo" else "navy"
    parts = [f'<div class="b {style}">']
    if b.get("eyebrow"):
        parts.append(f'<div class="eyebrow">{e(b["eyebrow"])}</div>')
    if b.get("big_number"):
        parts.append(f'<div class="h small">{e(label)}</div>')
        parts.append(f'<div class="num"><span class="ic">{PHONE_SVG}</span>{e(phone)}</div>')
    elif b.get("title"):
        parts.append(f'<div class="h">{title_html(b["title"])}</div>')
    if b.get("sub"):
        parts.append(f'<div class="sub">{e(b["sub"])}</div>')
    if b.get("cta", not b.get("big_number")):
        hint = f' <small>{e(b["cta_hint"])}</small>' if b.get("cta_hint") else ""
        parts.append(f'<div class="cta">{PHONE_SVG} {e(label)} {e(phone)}{hint}</div>')
    if style == "photo":
        parts.append(f'<div class="note">{e(b.get("note", "이미지는 CG로 실제와 다를 수 있습니다"))}</div>')
    parts.append("</div>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bg", help="사진 배경(style: photo)에 쓸 조감도 등. 없으면 남색 배경으로 대체")
    a = ap.parse_args()

    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    phone, label = spec.get("phone", "1666-0992"), spec.get("label", "상담/방문예약")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bg = ""
    if a.bg:
        mime = "png" if a.bg.lower().endswith(".png") else "jpeg"
        bg = f"data:image/{mime};base64," + base64.b64encode(Path(a.bg).read_bytes()).decode()
    css = CSS.replace("__BG__", bg or "none")

    ensure_pretendard()
    from playwright.sync_api import sync_playwright

    made = []
    with sync_playwright() as p:
        exe = chromium_path()
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        for b in spec["banners"]:
            if b.get("style") == "photo" and not bg:
                b = {**b, "style": "navy"}
            page.set_content(
                f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>"
                f"<body>{banner_html(b, phone, label)}</body></html>"
            )
            page.wait_for_timeout(250)
            png = out / f"{b['name']}.png"
            page.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": W, "height": H})
            jpg = out / f"{b['name']}.jpg"
            subprocess.run(["convert", str(png), "-resize", "1200x", "-strip", "-quality", "90", str(jpg)], check=True)
            png.unlink()
            made.append(jpg)
        browser.close()
    if len(made) > 1:
        subprocess.run(["montage", *map(str, made), "-tile", "2x", "-geometry", "600x228+6+6",
                        "-background", "#cccccc", str(out / "_preview.jpg")], check=False)
    for m in made:
        print(m)


if __name__ == "__main__":
    main()
