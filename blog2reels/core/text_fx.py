"""자막 · 챕터칩 · 브랜드 라벨 · CTA 그래픽 (Pillow)."""
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .util import font_path

WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
ACCENT = (255, 212, 59, 255)      # 숫자·강조 노랑
INK = (17, 17, 17, 255)


@lru_cache(maxsize=64)
def font(size, weight="Black"):
    return ImageFont.truetype(font_path(weight), int(size))


def _tokens(text):
    """[대괄호] 와 숫자가 든 어절은 강조색."""
    out = []
    for m in re.finditer(r"\[([^\]]+)\]|(\S+)", text):
        if m.group(1):
            out.append((m.group(1), True))
        else:
            w = m.group(2)
            out.append((w, bool(re.search(r"\d", w))))
    return out


def text_image(text, size=110, max_w=860, weight="Black", stroke_ratio=0.10,
               color=WHITE, accent=ACCENT, shadow=True):
    """굵은 흰 글자 + 검은 외곽선 + 그림자. 너비를 넘으면 자동 축소, 그래도 넘으면 2줄."""
    toks = _tokens(text)
    if not toks:
        return None

    def measure(sz):
        f_ = font(sz, weight)
        return f_, max(2, int(sz * stroke_ratio)), f_.getlength(" "), [f_.getlength(t) for t, _ in toks]

    def layout(widths, space, two):
        if not two:
            return [list(range(len(toks)))]
        total_ = sum(widths) + space * (len(toks) - 1)
        acc, cut = 0, 1
        for i, w in enumerate(widths):
            if acc + w / 2 >= total_ / 2:
                cut = max(1, i)
                break
            acc += w + space
        cut = min(cut, len(toks) - 1)
        return [list(range(0, cut)), list(range(cut, len(toks)))]

    # 0.8배까지만 줄이고, 그래도 넘치면 2줄로 나눈 뒤 맞을 때까지 줄인다
    base, two = size, False
    while True:
        f, sw, space, widths = measure(size)
        lines = layout(widths, space, two)
        need = max(sum(widths[i] for i in ln) + space * (len(ln) - 1) for ln in lines) + sw * 2
        if need <= max_w or size <= 54:
            break
        if not two and len(toks) > 1 and size <= base * 0.8:
            two, size = True, base
            continue
        size = int(size * 0.94)
    asc, desc = f.getmetrics()
    lh = asc + desc
    line_w = [sum(widths[i] for i in ln) + space * (len(ln) - 1) for ln in lines]
    pad = sw * 2 + 24
    Wd = int(max(line_w) + pad * 2)
    Hd = int(lh * len(lines) * 1.05 + pad * 2)
    img = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pos = []
    y = pad
    for ln, lw in zip(lines, line_w):
        x = (Wd - lw) / 2
        for i in ln:
            pos.append((x, y, toks[i]))
            x += widths[i] + space
        y += lh * 1.05
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        for x, y, (t, _) in pos:
            sd.text((x + 6, y + 10), t, font=f, fill=(0, 0, 0, 150), stroke_width=sw,
                    stroke_fill=(0, 0, 0, 150))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        img = Image.alpha_composite(img, sh)
        d = ImageDraw.Draw(img)
    for x, y, (t, hi) in pos:
        d.text((x, y), t, font=f, fill=accent if hi else color, stroke_width=sw, stroke_fill=BLACK)
    return img.crop(img.getbbox())


def chip_image(text, size=40):
    """챕터 칩: 노란 알약 + 검은 글자 + 앞에 점."""
    f = font(size, "ExtraBold")
    tw = f.getlength(text)
    h = int(size * 1.75)
    dot = int(size * 0.42)
    w = int(tw + size * 1.6 + dot)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=ACCENT)
    cx = int(size * 0.7)
    d.ellipse((cx, h / 2 - dot / 2, cx + dot, h / 2 + dot / 2), fill=INK)
    asc, desc = f.getmetrics()
    d.text((cx + dot + size * 0.35, (h - (asc + desc)) / 2 + 1), text, font=f, fill=INK)
    return img


def label_image(text, size=34):
    """상단 브랜드 라벨(반투명 검정 바탕)."""
    f = font(size, "Bold")
    tw = f.getlength(text)
    h = int(size * 1.6)
    w = int(tw + size * 1.2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=12, fill=(0, 0, 0, 120))
    asc, desc = f.getmetrics()
    d.text((size * 0.6, (h - (asc + desc)) / 2), text, font=f, fill=(255, 255, 255, 235))
    return img


def cta_button(text, size=44):
    """CTA 보조 문구 버튼(저장 아이콘 + 글자)."""
    f = font(size, "ExtraBold")
    tw = f.getlength(text)
    h = int(size * 2.0)
    icon = int(size * 0.9)
    w = int(tw + icon + size * 2.0)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=WHITE)
    x0, y0 = size * 0.8, (h - icon) / 2
    bw = icon * 0.72
    d.polygon([(x0, y0), (x0 + bw, y0), (x0 + bw, y0 + icon), (x0 + bw / 2, y0 + icon * 0.72),
               (x0, y0 + icon)], fill=INK)
    asc, desc = f.getmetrics()
    d.text((x0 + bw + size * 0.45, (h - (asc + desc)) / 2), text, font=f, fill=INK)
    return img


def scaled(img, s):
    if abs(s - 1.0) < 1e-3:
        return img
    w, h = img.size
    return img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)


def with_alpha(img, a):
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    al = al.point(lambda v: int(v * a))
    return Image.merge("RGBA", (r, g, b, al))
