# -*- coding: utf-8 -*-
"""역세권 단지 비교 인포그래픽 생성 (PDF 6~10쪽 데이터 기준, 1536x1024)."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
CHROME = "/opt/pw-browsers/chromium"

TEAL, ORANGE, PURPLE = "#0f8f94", "#e8890c", "#6d55c9"
COLORS = {"A": TEAL, "B": ORANGE, "C": PURPLE}

ICON = {
    "home": '<path d="M3 11 12 3l9 8v10h-6v-6H9v6H3z"/>',
    "bldg": '<path d="M5 2h14v20H5zM8 5v2h2V5zm6 0v2h2V5zM8 9v2h2V9zm6 0v2h2V9zm-6 4v2h2v-2zm6 0v2h2v-2zm-4 4v5h4v-5z" fill-rule="evenodd"/>',
    "coin": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 7v3c0 1.7 3.6 3 8 3s8-1.3 8-3V7c0 1.7-3.6 3-8 3S4 8.7 4 7zm0 5v3c0 1.7 3.6 3 8 3s8-1.3 8-3v-3c0 1.7-3.6 3-8 3s-8-1.3-8-3zm0 5v2c0 1.7 3.6 3 8 3s8-1.3 8-3v-2c0 1.7-3.6 3-8 3s-8-1.3-8-3z"/>',
    "doc": '<path d="M5 2h10l4 4v16H5zm3 7v2h8V9zm0 4v2h8v-2zm0 4v2h6v-2z" fill-rule="evenodd"/>',
    "pin": '<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" fill-rule="evenodd"/>',
}


def icon(name, color="#1f2d3d", size=24):
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{color}">{ICON[name]}</svg>'


def price_html(p):
    # "7억 5,000만원" -> 숫자는 크게, 단위는 작게
    out = ""
    for part in p.split(" "):
        if part.endswith("억"):
            out += f'{part[:-1]}<small>억</small> '
        elif part.endswith("만원"):
            out += f'{part[:-2]}<small>만원</small>'
        elif part.endswith("원"):
            out += f'{part[:-1]}<small>원</small>'
    return out.strip()


def card(c, compact):
    color = COLORS[c["key"]]
    rows = [
        ("home", "전용면적", c["area"]),
        ("bldg", "준공연도", c["built"]),
        ("coin", c.get("price_label", "매매가"), f'<span class="price" style="color:{color}">{price_html(c["price"])}</span>'),
        ("doc", c.get("deal_label", "거래일 · 층"), c["deal"]),
        ("pin", "입지특징", c["loc"]),
    ]
    r = "".join(
        f'<div class="row"><span class="ic">{icon(i, color if i == "coin" else "#1f2d3d")}</span>'
        f'<span class="lb">{l}</span><span class="vl">{v}</span></div>' for i, l, v in rows)
    return f'''<div class="card{' compact' if compact else ''}" style="--c:{color}">
  <div class="hd"><div class="badge">{c["key"]}</div><div><div class="nm">{c["name"]}</div><div class="sb">{c["sub"]}</div></div></div>
  {r}
</div>'''


# ---------- 지도(위치 관계 개념도) ----------
def rail(points, color="#4f7fd1", w=7):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    return (f'<path d="{d}" stroke="{color}" stroke-width="{w}" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity=".9"/>'
            f'<path d="{d}" stroke="#fff" stroke-width="2" stroke-dasharray="10 10" fill="none" opacity=".9"/>')


def station(x, y, label, sub=None, side="right"):
    lw = 22 * len(label) + 40
    lx = x + 34 if side == "right" else x - 34 - lw
    s = (f'<g><circle cx="{x}" cy="{y}" r="27" fill="#0f2a4a" stroke="#fff" stroke-width="4"/>'
         f'<g transform="translate({x-13},{y-15})" fill="#fff"><rect x="2" y="0" width="22" height="22" rx="6"/>'
         f'<rect x="6" y="4" width="14" height="7" rx="2" fill="#0f2a4a"/><circle cx="8" cy="16" r="2" fill="#0f2a4a"/><circle cx="18" cy="16" r="2" fill="#0f2a4a"/>'
         f'<path d="M5 22 2 28M21 22l3 6" stroke="#fff" stroke-width="2.5"/></g>'
         f'<rect x="{lx}" y="{y-21}" width="{lw}" height="42" rx="21" fill="#0f2a4a"/>'
         f'<text x="{lx + lw/2}" y="{y+7}" text-anchor="middle" class="stl">{label}</text>')
    if sub:
        s += f'<text x="{lx + lw/2}" y="{y+44}" text-anchor="middle" class="sts">{sub}</text>'
    return s + "</g>"


def marker(x, y, key, label, side="right"):
    color = COLORS[key]
    lw = 24 * len(label) + 44
    lx = x + 24 if side == "right" else x - 24 - lw
    return (f'<g><rect x="{lx}" y="{y-60}" width="{lw}" height="44" rx="22" fill="#fff" stroke="{color}" stroke-width="3"/>'
            f'<text x="{lx + lw/2 + (10 if side=="right" else -10)}" y="{y-31}" text-anchor="middle" class="mkl">{label}</text>'
            f'<path d="M{x},{y} C{x-10},{y-22} {x-30},{y-36} {x-30},{y-60} A30,30 0 1 1 {x+30},{y-60} C{x+30},{y-36} {x+10},{y-22} {x},{y}z" fill="{color}" stroke="#fff" stroke-width="3"/>'
            f'<text x="{x}" y="{y-48}" text-anchor="middle" class="mkk">{key}</text></g>')


def link(x1, y1, x2, y2, text, color, tx=None, ty=None, dash="10 8"):
    tx = (x1 + x2) / 2 if tx is None else tx
    ty = (y1 + y2) / 2 if ty is None else ty
    tw = 19 * len(text) + 28
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="4" stroke-dasharray="{dash}" stroke-linecap="round"/>'
            f'<rect x="{tx - tw/2}" y="{ty-19}" width="{tw}" height="38" rx="10" fill="{color}"/>'
            f'<text x="{tx}" y="{ty+7}" text-anchor="middle" class="lkt">{text}</text>')


def area(x, y, w, h, label, kind="park"):
    fill = {"park": "#cfe8c6", "lake": "#bcdcf2", "zone": "#e4e9f0"}[kind]
    col = {"park": "#3f8a3a", "lake": "#2f6fa8", "zone": "#6b7a8c"}[kind]
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(w, h)/2.2}" fill="{fill}"/>'
            f'<text x="{x + w/2}" y="{y + h/2 + 7}" text-anchor="middle" class="arl" fill="{col}">{label}</text>')


def map_svg(body):
    # 바탕: 가상의 가로 블록 패턴 (실제 도로망 아님)
    blocks = ""
    for i in range(0, 1016, 92):
        for j in range(0, 686, 78):
            blocks += f'<rect x="{i+8}" y="{j+8}" width="76" height="62" rx="6" fill="#f6f8fa"/>'
    return f'''<svg viewBox="0 0 1016 686" width="1016" height="686">
<rect width="1016" height="686" fill="#e9edf1"/>{blocks}
{body}
<g><rect x="16" y="16" width="372" height="40" rx="10" fill="#0f2a4a" opacity=".88"/>
<text x="32" y="43" class="cap">위치 관계 개념도 · 축척·방위는 실제와 다름</text></g>
</svg>'''


CASES = [
    dict(
        file="02_아산탕정_역세권비교.png",
        t1="아산 탕정", t2a="역 도보", t2m="와 ", t2b="역 거리", t2e=" 신축 비교",
        r1="같은 탕정 신축, 다른 가격", r2="데이터로 보는 현명한 선택",
        cards=[
            dict(key="A", name="지웰시티 센트럴푸르지오 3단지", sub="탕정역 도보 생활권 신축 단지",
                 area="전용 84.72㎡ 평형", built="2022년 준공", price="7억 5,000만원",
                 deal='2026.09.13 · 11층 <i>(매매 실거래)</i>', loc='탕정역 도보 약 5분 <i>(리치고 안내)</i>'),
            dict(key="B", name="호반써밋 그랜드마크Ⅱ(2차)", sub="갈산리 · 역에서 떨어진 신축 단지",
                 area="전용 84.906㎡", built="2023년 준공", price="4억 5,900만원",
                 deal='2026.09.30 · 10층 <i>(매매 실거래)</i>', loc='탕정역 직선 약 1.86km'),
        ],
        map=lambda: (
            rail([(-10, 520), (300, 430), (520, 360), (760, 290), (1030, 210)])
            + station(470, 375, "탕정역", side="left")
            + link(470, 375, 600, 250, "도보 약 5분", TEAL, 640, 330)
            + marker(600, 250, "A", "지웰시티 3단지")
            + link(470, 375, 760, 590, "직선 약 1.86km · 보행은 더 김", ORANGE, 440, 590)
            + marker(760, 590, "B", "호반써밋Ⅱ", side="right")
        ),
        s1a="역 도보 단지가", s1b="2억 9,100만원", s1c="(7억 5,000만원 − 4억 5,900만원)",
        s2a='역 도보 단지 <b class="t">A</b>는 <b class="o">B</b> 대비', s2b="+63.4%", s2c="높음",
        s2d="(7억 5,000만원 ÷ 4억 5,900만원 − 1)",
        s3="택지 위치·학군·상권·브랜드가 다릅니다. 63.4% 전부가 역세권 효과는 아닙니다.",
        src="자료: richgo.ai · 자리톡 · 아파트손품",
    ),
    dict(
        file="03_동탄_역세권비교.png",
        t1="동탄", t2a="역 연결", t2m=" 단지와 ", t2b="버스 이동", t2e=" 생활권",
        r1="같은 동탄2신도시, 다른 가격", r2="데이터로 보는 현명한 선택",
        cards=[
            dict(key="A", name="동탄역 롯데캐슬", sub="동탄역 연결 · 백화점 복합 입지",
                 area="전용 84.70㎡", built="2021년 준공", price="22억 2,500만원",
                 deal='2026.06.04 · 33층 <i>(매매 실거래)</i>', loc='동탄역 연결 · SRT·GTX-A 이용'),
            dict(key="B", name="금강펜테리움 센트럴파크Ⅱ", sub="동탄호수공원 주변 주거 단지",
                 area="전용 84㎡대", built="2017년 준공", price="6억 7,800만원",
                 deal='2026.09.19 · 22층 <i>(매매 실거래)</i>', loc='동탄역까지 버스 이동 생활권'),
        ],
        map=lambda: (
            rail([(-10, 300), (300, 300), (520, 300), (1030, 300)], color="#6a5acd")
            + area(600, 430, 330, 170, "동탄호수공원", "lake")
            + station(330, 300, "동탄역", "SRT · GTX-A", side="left")
            + marker(400, 262, "A", "롯데캐슬 (역 연결)")
            + link(330, 300, 640, 450, "버스 이동", ORANGE, 470, 400)
            + marker(640, 450, "B", "금강펜테리움Ⅱ", side="right")
        ),
        s1a="역 연결 단지가", s1b="15억 4,700만원", s1c="(22억 2,500만원 − 6억 7,800만원)",
        s2a='역 연결 단지 <b class="t">A</b>는 <b class="o">B</b> 대비', s2b="+228.2%", s2c="약 3.28배",
        s2d="(22억 2,500만원 ÷ 6억 7,800만원 − 1)",
        s3="거래일 약 3개월 차이, A는 해당 면적 최고가 거래입니다. 순수 철도 프리미엄으로 보지 않습니다.",
        src="자료: zipgap.kr · richgo.ai · 롯데캐슬 공식",
    ),
    dict(
        file="04_광교_역세권비교.png",
        t1="광교", t2a="역 앞", t2m=" 단지와 ", t2b="2km 거리", t2e=" 단지 비교",
        r1="같은 2012년 준공, 다른 시세", r2="데이터로 보는 현명한 선택",
        cards=[
            dict(key="A", name="광교 자연앤힐스테이트", sub="광교중앙역 앞 대단지 · 1,764세대",
                 area="전용 84㎡대", built="2012년 11월 준공", price="19억 9,500만원", price_label="KB 시세",
                 deal_label="기준일", deal='2026.09.25 <i>(KB 매매 일반가)</i>', loc='광교중앙역 단지 앞 · 신분당선'),
            dict(key="B", name="광교레이크파크 한양수자인", sub="호수 인근 단지 · 453세대",
                 area="전용 84㎡대", built="2012년 7월 준공", price="10억원", price_label="KB 시세",
                 deal_label="기준일", deal='2026.10.02 <i>(KB 매매 일반가)</i>', loc='광교중앙역 직선 약 1.94km'),
        ],
        map=lambda: (
            rail([(140, 690), (300, 470), (520, 300), (760, 150), (900, -10)], color="#c8102e")
            + area(560, 470, 360, 170, "호수공원", "lake")
            + station(300, 470, "광교중앙역", "신분당선", side="left")
            + station(760, 150, "상현역", side="right")
            + marker(360, 400, "A", "자연앤힐스테이트")
            + link(300, 470, 640, 470, "직선 약 1.94km", ORANGE, 470, 530)
            + link(760, 150, 640, 470, "상현역 직선 약 1.96km", "#8a6a3a", 780, 330)
            + marker(640, 470, "B", "레이크파크 한양수자인", side="right")
        ),
        s1a="역 앞 단지가 (KB 시세)", s1b="9억 9,500만원", s1c="(19억 9,500만원 − 10억원)",
        s2a='역 앞 단지 <b class="t">A</b>는 <b class="o">B</b> 대비', s2b="+99.5%", s2c="높음",
        s2d="(19억 9,500만원 ÷ 10억원 − 1)",
        s3="세대수·학군·상권·호수 조망이 달라 99.5%가 역세권만의 효과는 아닙니다.",
        src="자료: KB부동산 · 아파트손품",
    ),
    dict(
        file="05_대구_역세권비교.png",
        t1="대구", t2a="역 인접", t2m=" 신축과 ", t2b="침산 생활권", t2e=" 비교",
        r1="같은 2024년 준공, 다른 가격", r2="데이터로 보는 현명한 선택",
        cards=[
            dict(key="A", name="힐스테이트 도원 센트럴", sub="달성공원역 인접 · 대구역 생활권",
                 area="전용 84.99㎡", built="2024년 준공", price="7억 9,000만원",
                 deal='2026.09.21 · 33층 <i>(매매 실거래)</i>', loc='달성공원역 인접 · 대구 3호선'),
            dict(key="B", name="더샵프리미엘", sub="북구 침산동 주거 생활권 신축",
                 area="전용 84.9563㎡", built="2024년 준공", price="6억 6,700만원",
                 deal='2026.07.02 · 27층 <i>(84㎡ 매매)</i>', loc='101동→대구역 약 23분 <i>(직선환산)</i>'),
        ],
        map=lambda: (
            rail([(260, -10), (260, 300), (300, 460), (420, 700)], color="#4caf50")
            + rail([(-10, 600), (400, 560), (640, 500), (1030, 420)], color="#1e4fa0")
            + station(270, 330, "달성공원역", "대구 3호선", side="left")
            + marker(360, 290, "A", "도원 센트럴")
            + station(640, 500, "대구역", side="right")
            + link(640, 500, 800, 210, "약 23분 (직선거리 환산)", ORANGE, 760, 380)
            + marker(800, 210, "B", "더샵프리미엘", side="left")
        ),
        s1a="역 인접 단지가", s1b="1억 2,300만원", s1c="(7억 9,000만원 − 6억 6,700만원)",
        s2a='역 인접 단지 <b class="t">A</b>는 <b class="o">B</b> 대비', s2b="+18.4%", s2c="높음",
        s2d="(7억 9,000만원 ÷ 6억 6,700만원 − 1)",
        s3="행정구·학교·상권이 다르고 거래일은 약 2개월 반 차이. 23분은 실제 보행시간이 아닙니다.",
        src="자료: aptndm.com · 동네픽 · 아파트손품",
    ),
    dict(
        file="06_서울동대문_역세권비교.png",
        t1="서울 동대문구", t2a="청량리역 앞", t2m="과 ", t2b="주변 생활권", t2e=" 비교",
        r1="같은 동대문구, 다른 가격", r2="면적·연식 차이까지 함께",
        cards=[
            dict(key="A", name="청량리역 한양수자인 그라시엘", sub="청량리역 인접 · 환승·상업 생활권",
                 area="전용 84.97㎡", built="2023년 준공", price="17억 5,000만원",
                 deal='2026.09.13 · 45층 <i>(매매 실거래)</i>', loc='청량리역 인접 · 여러 철도노선'),
            dict(key="B", name="래미안장안2차", sub="장안동 주거 생활권",
                 area="전용 81.05㎡", built="2007년 준공", price="13억 2,500만원",
                 deal='2026.08.08 · 20층 <i>(매매 실거래)</i>', loc='장한평역 도보 약 24분'),
            dict(key="C", name="답십리파크자이", sub="면적·연식 보조 비교",
                 area="전용 84.62㎡", built="2019년 준공", price="16억 3,500만원",
                 deal='2026.07.10 · 14층 <i>(매매 실거래)</i>', loc='답십리역 도보 약 11분'),
        ],
        map=lambda: (
            rail([(-10, 160), (240, 210), (520, 120), (1030, 20)], color="#0052a4")
            + rail([(-10, 640), (420, 470), (720, 420), (1030, 360)], color="#996cac")
            + station(250, 210, "청량리역", "여러 철도노선 환승", side="left")
            + marker(330, 180, "A", "한양수자인 그라시엘")
            + station(440, 462, "답십리역", side="left")
            + link(440, 462, 560, 330, "도보 약 11분", PURPLE, 600, 395)
            + marker(560, 330, "C", "답십리파크자이")
            + station(760, 413, "장한평역", side="right")
            + link(760, 413, 860, 630, "도보 약 24분", ORANGE, 900, 520)
            + marker(860, 630, "B", "래미안장안2차", side="left")
        ),
        s1a="청량리역 단지가 B보다", s1b="4억 2,500만원", s1c="(17억 5,000만원 − 13억 2,500만원)",
        s2a='<b class="t">A</b>는 <b class="o">B</b> 대비 · <b class="p">C</b> 대비', s2b="+32.1%", s2c="· +7.0%",
        s2d="(17.50억÷13.25억−1 · 17.50억÷16.35억−1)",
        s3="장안2차와는 준공 16년·면적 3.9㎡ 차이. 면적당 가격차는 약 26.0%입니다.",
        src="자료: richgo.ai · 아파트손품 · 살집 · 당근부동산",
    ),
]

CSS = """
@font-face{font-family:N;font-weight:400;src:url(noto400.ttf)}
@font-face{font-family:N;font-weight:500;src:url(noto500.ttf)}
@font-face{font-family:N;font-weight:700;src:url(noto700.ttf)}
@font-face{font-family:N;font-weight:900;src:url(noto900.ttf)}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1536px;height:1024px;font-family:N,sans-serif;background:#f3f5f8;color:#1f2d3d;position:relative;overflow:hidden;letter-spacing:-.02em}
.top{position:absolute;left:0;top:0;width:1536px;height:100px;background:#0f2a4a;display:flex;align-items:center;padding:0 38px;justify-content:space-between}
.title{font-weight:900;font-size:54px;color:#fff;white-space:nowrap;letter-spacing:-.04em}
.title .bar{display:inline-block;width:4px;height:44px;background:#3fd0d4;margin:0 22px;vertical-align:-4px}
.title .a{color:#3fd0d4}.title .b{color:#f7b733}
.rsub{color:#dfe7f1;font-size:23px;font-weight:500;text-align:right;line-height:1.35}
.left{position:absolute;left:20px;top:114px;width:494px;height:784px;display:flex;flex-direction:column;gap:16px}
.card{flex:1;background:#fff;border:2px solid color-mix(in srgb,var(--c) 28%,#fff);border-left:9px solid var(--c);border-radius:14px;padding:18px 20px 8px 22px;display:flex;flex-direction:column}
.hd{display:flex;align-items:center;gap:18px;margin-bottom:10px}
.badge{flex:none;width:72px;height:72px;border-radius:50%;background:var(--c);color:#fff;font-weight:900;font-size:44px;display:flex;align-items:center;justify-content:center}
.nm{font-weight:900;font-size:29px;white-space:nowrap;overflow:hidden;max-width:360px;line-height:1.15;letter-spacing:-.04em}
.sb{font-size:19px;color:#4b5a6b;margin-top:4px}
.row{display:flex;align-items:center;border-top:1.5px solid #e6eaef;flex:1;min-height:0}
.ic{flex:none;width:34px;display:flex}.lb{flex:none;width:104px;font-size:19px;color:#2c3a4a;font-weight:500}
.vl{font-size:19.5px;color:#1f2d3d;white-space:nowrap}
.vl i{font-style:normal;color:#4b5a6b;font-size:17px}
.price{font-weight:900;font-size:40px;letter-spacing:-.03em;line-height:1}
.price small{font-size:27px}
.card.compact{padding:12px 18px 4px 20px}
.card.compact .hd{margin-bottom:4px;gap:14px}.card.compact .badge{width:52px;height:52px;font-size:32px}
.card.compact .nm{font-size:24px;max-width:380px}.card.compact .sb{font-size:16px;margin-top:1px}
.card.compact .lb,.card.compact .vl{font-size:17px}.card.compact .vl i{font-size:15px}
.card.compact .price{font-size:31px}.card.compact .price small{font-size:21px}
.card.compact .ic svg{width:20px;height:20px}
.map{position:absolute;left:520px;top:104px;width:1016px;height:686px;overflow:hidden}
.stl{fill:#fff;font-weight:700;font-size:21px}.sts{fill:#0f2a4a;font-weight:700;font-size:17px}
.mkl{fill:#0f2a4a;font-weight:900;font-size:21px}.mkk{fill:#fff;font-weight:900;font-size:34px}
.lkt{fill:#fff;font-weight:700;font-size:18px}.arl{font-weight:700;font-size:20px}
.cap{fill:#fff;font-size:17px;font-weight:500}
.stats{position:absolute;left:526px;top:798px;width:1000px;height:150px;display:flex;gap:12px}
.st{flex:0 0 326px;border-radius:12px;padding:16px 18px;display:flex;gap:14px}
.s1{background:#fff6e8;border:1.5px solid #f6dfb8}.s2{background:#e6f6f6;border:1.5px solid #bfe6e6}.s3{flex:1 1 auto;background:#e9eef5;border:1.5px solid #d3dce7;align-items:center}
.sic{flex:none;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:26px}
.sh{font-size:21px;font-weight:700;color:#1f2d3d;white-space:nowrap}
.sh .t{color:#0f8f94}.sh .o{color:#e8890c}.sh .p{color:#6d55c9}
.big{font-weight:900;font-size:38px;line-height:1.25;white-space:nowrap;letter-spacing:-.03em}
.big small{font-size:24px}
.fm{font-size:15px;color:#3c4a5a;white-space:nowrap;letter-spacing:-.03em}
.s3 p{word-break:keep-all;font-size:17px;font-weight:700;line-height:1.45;color:#1f2d3d}
.foot{position:absolute;left:0;bottom:0;width:1536px;height:62px;background:#0f2a4a;color:#e3eaf3;display:flex;align-items:center;justify-content:space-between;padding:0 30px;font-size:18px}
.foot .m{font-size:16px;color:#c3cfdd}.foot .r{display:flex;align-items:center;gap:14px}.foot .r:before{content:"";width:40px;height:2px;background:#c3cfdd}
"""

BARS = '<svg width="34" height="34" viewBox="0 0 24 24" fill="#e8890c"><rect x="2" y="13" width="5" height="9" rx="1"/><rect x="9.5" y="8" width="5" height="14" rx="1"/><rect x="17" y="3" width="5" height="19" rx="1"/></svg>'


def big_amount(s):
    # "2억 9,100만원" -> 숫자 크게 + 단위 작게
    return price_html(s)


def page(c):
    compact = len(c["cards"]) > 2
    cards = "".join(card(x, compact) for x in c["cards"])
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="top"><div class="title">{c["t1"]}<span class="bar"></span><span class="a">{c["t2a"]}</span>{c["t2m"]}<span class="b">{c["t2b"]}</span>{c["t2e"]}</div>
<div class="rsub">{c["r1"]}<br>{c["r2"]}</div></div>
<div class="left">{cards}</div>
<div class="map">{map_svg(c["map"]())}</div>
<div class="stats">
 <div class="st s1">{BARS}<div><div class="sh">{c["s1a"]}</div><div class="big" style="color:#d9770a">{big_amount(c["s1b"])} <small>높음</small></div><div class="fm">{c["s1c"]}</div></div></div>
 <div class="st s2"><div class="sic" style="background:#0f8f94">%</div><div><div class="sh">{c["s2a"]}</div><div class="big" style="color:#0b5f63">{c["s2b"]} <small>{c["s2c"]}</small></div><div class="fm">{c["s2d"]}</div></div></div>
 <div class="st s3"><div class="sic" style="background:#3c4f68">!</div><p>{c["s3"]}</p></div>
</div>
<div class="foot"><span>{c["src"]} &nbsp;|&nbsp; 2026.10.03 확인</span><span class="m">PDF 자료 기반 재구성 · 지도는 개념도, 세부 위치는 원지도 확인</span><span class="r">더 나은 주거 선택을 위해, 데이터를 봅니다.</span></div>
</body></html>'''


JOBS = []
for c in CASES:
    html = os.path.join(HERE, c["file"].replace(".png", ".html"))
    with open(html, "w", encoding="utf-8") as f:
        f.write(page(c))
    JOBS.append((html, os.path.join(OUT, c["file"])))

import json
js = """const {chromium}=require('playwright');(async()=>{const b=await chromium.launch({executablePath:'%s'});
const p=await b.newPage({viewport:{width:1536,height:1024},deviceScaleFactor:1});
for(const [h,o] of %s){await p.goto('file://'+h);await p.evaluate(()=>document.fonts.ready);
await p.evaluate(()=>{document.querySelectorAll('.nm').forEach(e=>{let f=parseFloat(getComputedStyle(e).fontSize);while(e.scrollWidth>e.clientWidth&&f>16){f-=1;e.style.fontSize=f+'px';}});});
await p.screenshot({path:o});console.log('ok',o);}await b.close();})();""" % (CHROME, json.dumps(JOBS, ensure_ascii=False))
open(os.path.join(HERE, "shot.js"), "w", encoding="utf-8").write(js)
subprocess.run(["node", os.path.join(HERE, "shot.js")], check=True, env=dict(os.environ, NODE_PATH="/opt/node22/lib/node_modules"))
