"""블로그 원고 업로드 전 저품질 위험 점검.

사용법:
  python precheck.py blog/            # blog 아래 모든 원고(.docx) 점검
  python precheck.py a.docx b.docx    # 지정한 원고만
  python precheck.py blog/ --out reports/precheck.md

원고 형식: 이 저장소에서 만든 워드 원고(본문은 '본문 (네이버에 붙여넣기)' 다음 줄부터 '태그' 전까지).
머리말에 '메인 키워드: ○○'가 있으면 그 키워드로, 없으면 제목 앞부분(단지명)으로 반복 횟수를 센다.
blog/발행기록.md 에 적힌 파일명은 '발행 완료'로 표시하고 유사도 비교 대상으로만 쓴다.
"""

from __future__ import annotations

import argparse
import itertools
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 규칙 (CLAUDE.md 기준)
PRICE_PATTERNS = [
    (r"\d[\d,]*\s*만\s*원", "금액(만원)"),
    (r"\d+(?:\.\d+)?\s*억", "금액(억)"),
    (r"평당|3\.3\s*㎡\s*당", "평당가"),
    (r"할인율|\d+(?:\.\d+)?\s*%\s*(?:할인|↓|인하|저렴)", "할인율"),
    (r"취득가", "취득가 기준 금액"),
    (r"원분양가|할인가|혜택가|분양가\s*\d", "분양가 표기"),
]
MODELHOUSE = r"모델하우스|견본주택|홍보관|오시는\s*길"
ADDRESS = r"(?:[가-힣]+(?:시|구|군|동|읍|면|로|길)\s*\d+(?:-\d+)?)|번지"
HYPE = ["무조건", "100%", "백프로", "확정 수익", "수익 보장", "프리미엄 보장", "마지막 기회", "대박", "로또",
        "완판 임박", "마감 임박", "선착순 마감", "폭등", "무조건 오른", "최고의 투자", "절대 손해"]
AI_PHRASES = ["결론적으로", "요약하자면", "살펴보았습니다", "알아보겠습니다", "알아보았습니다", "도움이 되셨길",
              "이상으로", "마무리하겠습니다", "다양한", "중요합니다"]
PHONE = "1666-0992"


@dataclass
class Post:
    path: Path
    title: str = ""
    keyword: str = ""
    paras: list[str] = field(default_factory=list)
    photos: int = 0
    banners: int = 0
    phone_lines: int = 0
    published: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.paras)


def extract(path: Path) -> Post:
    raw = subprocess.run(["pandoc", "-t", "plain", "--wrap=none", str(path)], capture_output=True, text=True, check=True).stdout
    lines = [l.strip() for l in raw.splitlines()]
    post = Post(path)
    m = next((re.search(r"메인 키워드:\s*(.+)", l) for l in lines[:6] if "메인 키워드:" in l), None)
    if m:
        post.keyword = m.group(1).strip()
    try:
        start = lines.index("본문 (네이버에 붙여넣기)") + 1
    except ValueError:
        start = 0
    end = next((i for i in range(start, len(lines)) if lines[i] == "태그"), len(lines))
    body = [l for l in lines[start:end] if l]
    if body:
        post.title = body[0]
        body = body[1:]
    for l in body:
        if l.startswith("[사진"):
            post.photos += 1
        elif l.startswith("[배너"):
            post.banners += 1
        elif l.startswith("☎"):
            post.phone_lines += PHONE in l
        else:
            post.paras.append(l)
    if not post.keyword:
        # 제목 앞부분에서 본문에 실제로 반복되는 가장 긴 구절
        head = re.split(r"[,·|]", post.title)[0].split()
        for n in range(len(head), 0, -1):
            cand = " ".join(head[:n])
            if post.text.count(cand) >= 2:
                post.keyword = cand
                break
    return post


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def ngrams(s: str, n: int = 6) -> set[str]:
    s = norm(s)
    return {s[i:i + n] for i in range(max(len(s) - n + 1, 0))}


def sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", s) if len(x.strip()) >= 20]


def check(post: Post) -> tuple[int, list[tuple[str, str, str]]]:
    items: list[tuple[str, str, str]] = []
    score = 100

    def add(status: str, name: str, msg: str, penalty: int = 0):
        nonlocal score
        items.append((status, name, msg))
        score -= penalty

    text, title = post.text, post.title
    every = title + "\n" + text
    # 1) 금액·주소 규칙
    hits = []
    for pat, label in PRICE_PATTERNS:
        for m in re.finditer(pat, every):
            hits.append(f"{label}: '{every[max(0, m.start() - 8):m.end() + 8].strip()}'")
    for m in re.finditer(MODELHOUSE, every):
        window = every[max(0, m.start() - 40):m.end() + 60]
        if re.search(ADDRESS, window):
            hits.append(f"모델하우스 주소 의심: '{window.strip()[:60]}'")
    if hits:
        add("수정", "분양가·모델하우스 주소", "; ".join(hits[:5]), 40)
    else:
        add("통과", "분양가·모델하우스 주소", "금액·주소 표기 없음")
    # 2) 광고 표시
    if "분양 홍보 목적" in text:
        add("통과", "광고 표시", "첫 부분에 '분양 홍보 목적' 문구 있음")
    else:
        add("수정", "광고 표시", "'분양 홍보 목적으로 작성한 글' 문구가 없습니다", 15)
    # 3) 분량
    n = len(norm(text))
    if 2500 <= n <= 3200:
        add("통과", "분량", f"공백 제외 {n:,}자")
    elif n >= 2000:
        add("주의", "분량", f"공백 제외 {n:,}자 — 2,500~3,200자 권장", 5)
    else:
        add("수정", "분량", f"공백 제외 {n:,}자 — 너무 짧습니다", 15)
    # 4) 메인 키워드 반복
    if post.keyword:
        k = text.count(post.keyword)
        in_title = post.keyword.replace(" ", "") in norm(title)
        if not in_title:
            add("주의", "제목 키워드", f"제목에 '{post.keyword}'가 없습니다", 5)
        if 4 <= k <= 8:
            add("통과", "키워드 반복", f"'{post.keyword}' 본문 {k}회")
        elif k > 10:
            add("수정", "키워드 반복", f"'{post.keyword}' 본문 {k}회 — 남용으로 저품질 위험", 15)
        elif k > 8:
            add("주의", "키워드 반복", f"'{post.keyword}' 본문 {k}회 — 조금 많습니다(4~8회 권장)", 5)
        else:
            add("주의", "키워드 반복", f"'{post.keyword}' 본문 {k}회 — 4회 이상 권장", 5)
    else:
        add("주의", "키워드 반복", "메인 키워드를 찾지 못했습니다", 3)
    # 5) 과장 표현
    found = sorted({w for w in HYPE if w in every})
    if found:
        add("수정", "과장·보장 표현", ", ".join(found), min(10 * len(found), 30))
    else:
        add("통과", "과장·보장 표현", "없음")
    # 6) AI 상투구
    ai = {p: text.count(p) for p in AI_PHRASES if p in text}
    if sum(ai.values()) >= 4:
        add("주의", "AI 상투구", ", ".join(f"{k}({v})" for k, v in ai.items()), 5)
    else:
        add("통과", "AI 상투구", "적음" + (f" ({', '.join(ai)})" if ai else ""))
    # 7) 긴 문단
    long_p = [p for p in post.paras if len(p) > 300]
    if long_p:
        add("주의", "문단 길이", f"300자 넘는 문단 {len(long_p)}개 — 모바일 가독성", 3)
    else:
        add("통과", "문단 길이", "모두 300자 이하")
    # 8) 글 안 중복 문장
    ss = sentences(text)
    dup = {s for s in ss if ss.count(s) > 1}
    if dup:
        add("주의", "중복 문장", f"같은 문장 반복: '{next(iter(dup))[:30]}…'", 5)
    else:
        add("통과", "중복 문장", "없음")
    # 9) 이미지·전화 유도
    if post.photos + post.banners >= 8:
        add("통과", "이미지", f"사진 {post.photos}장 · 배너 {post.banners}장")
    else:
        add("주의", "이미지", f"사진 {post.photos}장 · 배너 {post.banners}장 — 8장 이상 권장", 3)
    if post.banners >= 3 and post.phone_lines >= post.banners:
        add("통과", "전화 유도", f"배너 {post.banners}장, 배너 아래 번호 줄 {post.phone_lines}개 ({PHONE})")
    elif post.banners >= 3:
        add("주의", "전화 유도", f"배너 {post.banners}장인데 번호 줄은 {post.phone_lines}개 — 배너마다 번호 줄 권장", 3)
    else:
        add("주의", "전화 유도", f"배너 {post.banners}장 — 핵심 지점 3곳 이상 권장(CLAUDE.md)", 5)
    return max(score, 0), items


def similarity(a: Post, b: Post) -> tuple[float, int]:
    ga, gb = ngrams(a.text), ngrams(b.text)
    if not ga or not gb:
        return 0.0, 0
    contain = len(ga & gb) / min(len(ga), len(gb))
    same = len(set(sentences(a.text)) & set(sentences(b.text)))
    return contain, same


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()

    files: list[Path] = []
    for p in map(Path, a.paths):
        files += sorted(p.rglob("*.docx")) if p.is_dir() else [p]
    files = [f for f in files if not f.name.startswith("~$")]
    if not files:
        sys.exit("점검할 원고(.docx)가 없습니다.")
    log = Path("blog/발행기록.md")
    published = log.read_text(encoding="utf-8") if log.exists() else ""
    posts = [extract(f) for f in files]
    for p in posts:
        p.published = p.path.name in published

    out = ["# 업로드 전 저품질 위험 점검", ""]
    for p in posts:
        score, items = check(p)
        grade = "업로드 가능" if score >= 85 else ("수정 후 업로드" if score >= 65 else "업로드 보류")
        state = " (발행 완료)" if p.published else ""
        out += [f"## {p.title or p.path.name}{state}", "",
                f"- 파일: `{p.path}`", f"- 메인 키워드: {p.keyword or '-'}", f"- **점수 {score}점 · {grade}**", "",
                "| 결과 | 항목 | 내용 |", "|---|---|---|"]
        out += [f"| {s} | {n} | {m} |" for s, n, m in items]
        out.append("")
    if len(posts) > 1:
        out += ["## 원고끼리 유사도 (유사문서 위험)", "",
                "| 원고 A | 원고 B | 문장 조각 겹침 | 똑같은 문장 | 판단 |", "|---|---|---|---|---|"]
        for x, y in itertools.combinations(posts, 2):
            c, same = similarity(x, y)
            verdict = "위험 — 다시 쓰기" if c >= 0.45 or same >= 5 else ("주의 — 겹치는 문단 고치기" if c >= 0.30 or same >= 2 else "괜찮음")
            out.append(f"| {x.path.parent.name} | {y.path.parent.name} | {c:.0%} | {same}개 | {verdict} |")
        out += ["", "같은 단지 글은 문장을 새로 쓰고, 발행 간격을 3일 이상 두는 것을 권장합니다.", ""]
    report = "\n".join(out)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
