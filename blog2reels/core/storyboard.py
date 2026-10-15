"""스토리보드 파서 / 작성기.

형식 (릴스 자동화 앱과 동일한 문법, 소스는 블로그 사진 번호):

    @1 = img01.jpg
    @card = 텍스트카드

    # 소스 | 길이 | 자막(/ 로 조각 구분) | 옵션
    1     | 1.10 | 대전에 / 2,293세대가 / 통째로 | hook
    4     | 1.90 | 지하철 2호선 / 용계역 예정    | chapter=입지·교통
    1     | 2.00 |                               | loop, cta

옵션: hook  loop  cta  chapter=이름  trans=cut|whip|flash|glitch|zoomblur|none  zoom=in|out
소스 칸에 '1 0.5' 처럼 두 번째 숫자를 쓰면 시작 위치(초)로 해석한다(영상 소스 호환용).
"""
import re

TRANS = {"cut", "whip", "flash", "glitch", "zoomblur", "none"}


def parse(text):
    sources, cuts, meta = {}, [], {}
    for ln, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"#\s*(제목|CTA|CTA_SUB)\s*:\s*(.*)$", line)
            if m:
                meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if line.startswith("@"):
            k, _, v = line[1:].partition("=")
            sources[k.strip()] = v.split("#", 1)[0].strip()
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            raise ValueError(f"{ln}번째 줄 형식 오류: '|' 로 칸을 나눠야 합니다 → {raw}")
        src_tokens = parts[0].split()
        if not src_tokens:
            raise ValueError(f"{ln}번째 줄: 소스가 비어 있습니다")
        try:
            dur = float(parts[1])
        except ValueError:
            raise ValueError(f"{ln}번째 줄: 길이는 숫자여야 합니다 → '{parts[1]}'") from None
        sub = parts[2] if len(parts) > 2 else ""
        opts = parts[3] if len(parts) > 3 else ""
        cut = {"src": src_tokens[0],
               "start": float(src_tokens[1]) if len(src_tokens) > 1 else 0.0,
               "dur": max(0.4, dur),
               "chunks": [c.strip() for c in sub.split("/") if c.strip()],
               "hook": False, "loop": False, "cta": False,
               "chapter": None, "trans": "cut", "zoom": None, "line": ln}
        for o in [o.strip() for o in opts.split(",") if o.strip()]:
            k, _, v = o.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in ("hook", "loop", "cta"):
                cut[k] = True
            elif k == "chapter":
                cut["chapter"] = v
            elif k == "trans":
                if v not in TRANS:
                    raise ValueError(f"{ln}번째 줄: trans 값은 {sorted(TRANS)} 중 하나")
                cut["trans"] = v
            elif k == "zoom":
                cut["zoom"] = v if v in ("in", "out") else None
        cuts.append(cut)
    if not cuts:
        raise ValueError("스토리보드에 컷이 없습니다")
    return {"sources": sources, "cuts": cuts, "meta": meta}


def write(sb, title="", cta="", cta_sub="", notes=None):
    out = ["# 블로그 → 릴스 스토리보드 (이 파일을 고쳐서 다시 렌더할 수 있습니다)",
           f"# 제목: {title}", f"# CTA: {cta}", f"# CTA_SUB: {cta_sub}", ""]
    for k, v in sb["sources"].items():
        note = (notes or {}).get(k)
        out.append(f"@{k} = {v}" + (f"    # {note}" if note else ""))
    out += ["", "# 소스 | 길이 | 자막(/ 로 조각 구분) | 옵션"]
    for c in sb["cuts"]:
        opts = []
        for k in ("hook", "loop", "cta"):
            if c.get(k):
                opts.append(k)
        if c.get("chapter"):
            opts.append(f"chapter={c['chapter']}")
        if c.get("trans") and c["trans"] != "cut":
            opts.append(f"trans={c['trans']}")
        if c.get("zoom"):
            opts.append(f"zoom={c['zoom']}")
        src = str(c["src"]) + (f" {c['start']:g}" if c.get("start") else "")
        out.append(f"{src:<6}| {c['dur']:.2f} | {' / '.join(c['chunks'])} | {', '.join(opts)}")
    return "\n".join(out) + "\n"


def total_duration(sb):
    return sum(c["dur"] for c in sb["cuts"])
