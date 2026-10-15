"""블로그 본문 수집: 네이버 · 티스토리 · 워드프레스 · 일반 웹페이지.

결과는 '읽는 순서 그대로'의 블록 목록이다.
    [{"type": "heading", "text": ...},
     {"type": "text", "text": ...},
     {"type": "image", "url": ..., "caption": ...}, ...]
사진 바로 앞뒤 문장이 그 사진을 설명하는 경우가 많으므로 순서를 지키는 것이 핵심이다.
"""
import gzip
import hashlib
import io
import os
import re
import urllib.parse
import urllib.request
import zlib
from html import unescape
from html.parser import HTMLParser

UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

VOID = {"img", "br", "hr", "meta", "link", "input", "source", "area", "base", "col",
        "embed", "param", "track", "wbr"}
SKIP = {"script", "style", "noscript", "button", "svg", "iframe", "form", "select",
        "nav", "footer", "header", "aside", "template"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section",
         "article", "figure", "figcaption", "tr", "td", "ul", "ol", "table", "pre", "br", "hr",
         "dd", "dt", "main"}
HEADINGS = {"h1", "h2", "h3", "h4"}


# ───────────────────────── 간단한 DOM ─────────────────────────
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent

    def cls(self):
        return self.attrs.get("class", "") or ""

    def iter(self):
        stack = [self]
        while stack:
            n = stack.pop()
            if isinstance(n, Node):
                yield n
                stack.extend(reversed(n.children))

    def text(self):
        out = []
        for n in self._walk_text():
            out.append(n)
        return re.sub(r"\s+", " ", "".join(out)).strip()

    def _walk_text(self):
        for c in self.children:
            if isinstance(c, str):
                yield c
            elif c.tag not in SKIP:
                yield from c._walk_text()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(html):
    b = _Builder()
    b.feed(html)
    return b.root


# ───────────────────────── HTTP ─────────────────────────
def http_get(url, referer=None, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_MOBILE,
        "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip, deflate",
        **({"Referer": referer} if referer else {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
        if enc == "gzip":
            data = gzip.decompress(data)
        elif enc == "deflate":
            data = zlib.decompress(data)
        return data, r.geturl(), r.headers.get_content_charset()


def decode_html(data, charset=None):
    if not charset:
        m = re.search(rb"charset=[\"']?([\w-]+)", data[:4000], re.I)
        charset = m.group(1).decode() if m else "utf-8"
    try:
        return data.decode(charset, "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


# ───────────────────────── 주소 정규화 ─────────────────────────
def normalize_url(url):
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    p = urllib.parse.urlparse(url)
    host = p.netloc.lower()
    q = urllib.parse.parse_qs(p.query)
    if host.endswith("blog.naver.com"):
        blog_id = (q.get("blogId") or [None])[0]
        log_no = (q.get("logNo") or [None])[0]
        parts = [x for x in p.path.split("/") if x]
        if not blog_id and parts and not parts[0].lower().endswith(".naver"):
            blog_id = parts[0]
            if len(parts) > 1 and parts[1].isdigit():
                log_no = parts[1]
        if blog_id and log_no:
            return f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
    return url


def detect_platform(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    if "naver.com" in host or "naver.me" in host:
        return "naver"
    if "tistory.com" in host:
        return "tistory"
    if "brunch.co.kr" in host:
        return "brunch"
    return "web"


# ───────────────────────── 본문 영역 찾기 ─────────────────────────
ROOT_HINTS = [
    "se-main-container",          # 네이버 스마트에디터 ONE
    "post_ct", "postViewArea", "post-view",  # 네이버 구버전
    "tt_article_useless_p_margin", "contents_style", "article-view",  # 티스토리
    "wrap_body",                  # 브런치
    "entry-content", "post-content", "article-content", "post_content", "article-body",
]


def find_content_root(dom):
    nodes = list(dom.iter())
    for hint in ROOT_HINTS:
        for n in nodes:
            if hint in n.cls().split() or n.attrs.get("id") == hint:
                return n
    arts = [n for n in nodes if n.tag in ("article", "main")]
    if arts:
        return max(arts, key=lambda n: len(n.text()))
    # 문단 텍스트가 가장 많이 모인 조상 노드
    score = {}
    for n in nodes:
        if n.tag == "p":
            ln = len(n.text())
            a, depth = n.parent, 0
            while a is not None and depth < 3:
                score[id(a)] = score.get(id(a), 0) + ln * (1.0 if depth == 0 else 0.6)
                a, depth = a.parent, depth + 1
    if score:
        best = max(score, key=score.get)
        for n in nodes:
            if id(n) == best:
                return n
    return dom


def _img_url(node, base):
    a = node.attrs
    for k in ("data-lazy-src", "data-src", "data-original", "data-url", "src"):
        v = a.get(k, "")
        if v and not v.startswith("data:"):
            return urllib.parse.urljoin(base, unescape(v))
    ss = a.get("srcset") or a.get("data-srcset")
    if ss:
        last = ss.split(",")[-1].strip().split(" ")[0]
        return urllib.parse.urljoin(base, last)
    return None


def _is_junk_image(node, url):
    cls = node.cls() + " " + (node.parent.cls() if node.parent else "")
    if re.search(r"sticker|emoticon|emoji|icon|profile|avatar|logo|btn|banner_ad|spinner",
                 cls, re.I):
        return True
    if re.search(r"storep-phinf|/sticker/|emoticon|\.svg(\?|$)|spacer|blank\.gif|pixel",
                 url, re.I):
        return True
    for k in ("width", "height"):
        v = node.attrs.get(k, "")
        if v.isdigit() and int(v) < 120:
            return True
    return False


def _upgrade_naver_img(url):
    if "pstatic.net" in url:
        url = re.sub(r"([?&])type=[^&]*", r"\1type=w966", url)
        if "type=" not in url:
            url += ("&" if "?" in url else "?") + "type=w966"
    return url


def extract_blocks(root, base_url):
    blocks = []
    buf = []
    seen = set()

    def flush(kind="text"):
        t = re.sub(r"\s+", " ", "".join(buf)).strip()
        buf.clear()
        if t and len(t) > 1:
            blocks.append({"type": kind, "text": t})

    def walk(node):
        for c in node.children:
            if isinstance(c, str):
                buf.append(c)
                continue
            if c.tag in SKIP:
                continue
            cls = c.cls()
            if "se-sticker" in cls or "se-oglink" in cls:
                continue
            if c.tag == "img":
                url = _img_url(c, base_url)
                if url and not _is_junk_image(c, url):
                    url = _upgrade_naver_img(url)
                    if url not in seen:
                        seen.add(url)
                        flush()
                        blocks.append({"type": "image", "url": url,
                                       "alt": c.attrs.get("alt", "").strip()})
                continue
            if c.tag in HEADINGS or "se-section-sectionTitle" in cls or "se-quotation" in cls:
                flush()
                t = c.text()
                if t:
                    blocks.append({"type": "heading", "text": t})
                if c.tag in HEADINGS:
                    continue
                # 인용구 안에 이미지가 있을 수 있어 계속 진행하지 않는다
                continue
            if c.tag == "figcaption" or "se-caption" in cls:
                flush()
                t = c.text()
                if t:
                    # 바로 앞 이미지의 캡션으로 붙인다
                    for b in reversed(blocks):
                        if b["type"] == "image":
                            b["caption"] = t
                            break
                    else:
                        blocks.append({"type": "text", "text": t})
                continue
            is_block = c.tag in BLOCK
            if is_block:
                flush()
            walk(c)
            if is_block:
                flush()

    walk(root)
    flush()
    # 너무 짧은 반복 문구 정리 + 연속 중복 제거
    out = []
    for b in blocks:
        if b["type"] == "text" and out and out[-1].get("text") == b["text"]:
            continue
        out.append(b)
    return out


def _meta(dom, *names):
    for n in dom.iter():
        if n.tag == "meta":
            key = n.attrs.get("property") or n.attrs.get("name") or ""
            if key in names and n.attrs.get("content"):
                return unescape(n.attrs["content"]).strip()
    return ""


def _title(dom):
    t = _meta(dom, "og:title", "twitter:title")
    if not t:
        for n in dom.iter():
            if n.tag == "title":
                t = n.text()
                break
    t = re.sub(r"\s*[:|\-]\s*네이버\s*블로그\s*$", "", t)
    return t.strip()


# ───────────────────────── 공개 함수 ─────────────────────────
def fetch_blog(url, log=print):
    """URL → {'title','url','platform','blocks','og_image'}"""
    url = normalize_url(url)
    data, final_url, cs = http_get(url)
    final_url = normalize_url(final_url)
    html = decode_html(data, cs)
    dom = parse_html(html)

    # 네이버 PC 주소: 본문이 iframe(mainFrame) 안에 있다
    if detect_platform(final_url) == "naver" and "se-main-container" not in html:
        for n in dom.iter():
            if n.tag == "iframe" and n.attrs.get("id") == "mainFrame":
                inner = normalize_url(urllib.parse.urljoin(final_url, n.attrs.get("src", "")))
                log(f"네이버 본문 프레임으로 이동: {inner}")
                data, final_url, cs = http_get(inner, referer=final_url)
                html = decode_html(data, cs)
                dom = parse_html(html)
                break

    root = find_content_root(dom)
    blocks = extract_blocks(root, final_url)
    title = _title(dom)
    og_image = _meta(dom, "og:image")
    if not any(b["type"] == "image" for b in blocks) and og_image:
        blocks.insert(0, {"type": "image", "url": urllib.parse.urljoin(final_url, og_image),
                          "alt": "대표 이미지"})
    return {"title": title, "url": final_url, "platform": detect_platform(final_url),
            "blocks": blocks, "og_image": og_image}


def download_images(post, out_dir, log=print, max_images=40, min_side=320):
    """본문 이미지를 img01.jpg … 로 저장. 작은 이미지·중복은 제외."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    hashes = set()
    n = 0
    for b in post["blocks"]:
        if b["type"] != "image":
            continue
        if n >= max_images:
            b["skip"] = "개수 제한"
            continue
        try:
            data, _, _ = http_get(b["url"], referer=post["url"])
            im = Image.open(io.BytesIO(data))
            im.seek(0)
            im = im.convert("RGB")
        except Exception as e:  # noqa: BLE001
            b["skip"] = f"다운로드 실패: {e}"
            continue
        if min(im.size) < min_side:
            b["skip"] = f"너무 작음 {im.size}"
            continue
        h = hashlib.md5(im.resize((16, 16)).tobytes()).hexdigest()
        if h in hashes:
            b["skip"] = "중복"
            continue
        hashes.add(h)
        n += 1
        if max(im.size) > 2400:
            im.thumbnail((2400, 2400), Image.LANCZOS)
        name = f"img{n:02d}.jpg"
        im.save(os.path.join(out_dir, name), quality=92)
        b["file"] = name
        b["idx"] = n
        b["size"] = im.size
    log(f"이미지 {n}장 저장")
    return n
