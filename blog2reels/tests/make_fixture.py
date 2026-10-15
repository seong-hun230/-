"""테스트용 '네이버 블로그 모바일 글' 페이지 + 사진을 만든다(외부 접속 없이 전체 흐름 검증용)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.text_fx import font  # noqa: E402

SCENES = [
    ("exterior", (1600, 1067), (90, 120, 150), "카페 외관 · 붉은 벽돌 2층 건물"),
    ("interior", (1080, 1440), (150, 120, 90), "실내 · 통창 + 원목 테이블"),
    ("menu", (1200, 1200), (40, 40, 40), "메뉴판 · 아메리카노 4,500원"),
    ("latte", (1080, 1350), (190, 160, 120), "시그니처 크림라떼 한 잔"),
    ("dessert", (1500, 1000), (220, 180, 190), "딸기 케이크 · 바스크 치즈케이크"),
    ("rooftop", (1600, 900), (110, 170, 220), "2층 루프탑 좌석"),
    ("map", (1200, 900), (230, 230, 220), "지도 · 성수역 3번 출구"),
    ("tiny_icon", (60, 60), (255, 0, 0), ""),
]


def make_images(d):
    os.makedirs(d, exist_ok=True)
    for name, (w, h), col, label in SCENES:
        im = Image.new("RGB", (w, h), col)
        dr = ImageDraw.Draw(im)
        if name == "map":
            for k in range(0, w, 80):
                dr.line((k, 0, k + 200, h), fill=(200, 200, 190), width=10)
            dr.ellipse((w / 2 - 40, h / 2 - 40, w / 2 + 40, h / 2 + 40), fill=(230, 60, 60))
        else:
            for k in range(14):
                x, y = (k * 137) % w, (k * 251) % h
                dr.ellipse((x, y, x + w // 5, y + w // 5), fill=tuple(min(255, c + 30) for c in col))
            im = im.filter(ImageFilter.GaussianBlur(25))
            dr = ImageDraw.Draw(im)
        if label:
            f = font(max(36, w // 18), "Bold")
            tw = f.getlength(label)
            dr.rounded_rectangle((w / 2 - tw / 2 - 30, h / 2 - 60, w / 2 + tw / 2 + 30, h / 2 + 60), 20,
                                 fill=(255, 255, 255))
            dr.text((w / 2 - tw / 2, h / 2 - 45), label, font=f, fill=(20, 20, 20))
        im.save(os.path.join(d, f"{name}.jpg"), quality=90)


HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="성수동 신상 카페 '온도' 솔직 후기 (주차·메뉴·가격) : 네이버 블로그">
<meta property="og:image" content="/img/exterior.jpg"><title>테스트</title></head>
<body><header>블로그 헤더 <img src="/img/tiny_icon.jpg" width="40"></header>
<div class="se-main-container">
 <div class="se-component se-text"><p class="se-text-paragraph">안녕하세요 여러분 ㅎㅎ 오늘은 요즘 성수동에서 제일 핫한 신상 카페 온도에 다녀왔어요!</p></div>
 <div class="se-component se-image"><img class="se-image-resource" src="/img/exterior.jpg?type=w80_blur" data-lazy-src="/img/exterior.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">붉은 벽돌로 된 2층 건물이라 멀리서도 눈에 확 띄더라고요.</p></div>
 <div class="se-component se-sectionTitle"><div class="se-section-sectionTitle">위치와 영업시간</div></div>
 <div class="se-component se-image"><img src="/img/map.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">성수역 3번 출구에서 도보 5분 거리예요. 영업시간은 오전 10시부터 오후 9시까지, 월요일은 휴무입니다.</p></div>
 <div class="se-component se-sticker"><img src="/img/tiny_icon.jpg" class="se-sticker-image"></div>
 <div class="se-component se-sectionTitle"><div class="se-section-sectionTitle">메뉴와 가격</div></div>
 <div class="se-component se-image"><img src="/img/menu.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">아메리카노는 4,500원, 시그니처 크림라떼는 6,500원이에요.</p></div>
 <div class="se-component se-image"><img src="/img/latte.jpg"><div class="se-caption">시그니처 크림라떼</div></div>
 <div class="se-component se-text"><p class="se-text-paragraph">크림라떼는 크림이 정말 진하고 달지 않아서 제일 추천해요.</p></div>
 <div class="se-component se-image"><img src="/img/dessert.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">디저트는 딸기 케이크랑 바스크 치즈케이크가 인기라서 오후 3시 전에 품절되는 날이 많대요.</p></div>
 <div class="se-component se-sectionTitle"><div class="se-section-sectionTitle">좌석과 분위기</div></div>
 <div class="se-component se-image"><img src="/img/interior.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">1층은 통창이라 채광이 좋고 원목 테이블이라 사진이 예쁘게 나와요.</p></div>
 <div class="se-component se-image"><img src="/img/rooftop.jpg"></div>
 <div class="se-component se-text"><p class="se-text-paragraph">2층 루프탑은 40석 정도인데 해 질 무렵에 가면 노을이 정말 예뻐요. 주차는 불가하니 대중교통 추천드려요!</p></div>
</div>
<footer>공감 댓글 이웃추가</footer></body></html>"""


def main(out):
    make_images(os.path.join(out, "img"))
    with open(os.path.join(out, "post.html"), "w", encoding="utf-8") as f:
        f.write(HTML)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
