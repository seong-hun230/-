"""STEP 3 컷 편집: 말 없는 구간을 자르고, 같은 문장을 두 번 읽은 곳은 뒤에 읽은 쪽만 남긴다.

사용법:
  # 1) 계획만 보기 (영상은 안 만듦)
  python workflow/scripts/cut.py 원본.mp4 작업폴더/transcript.json -o 작업폴더/cut.mp4 --dry-run
  # 2) 실제 편집
  python workflow/scripts/cut.py 원본.mp4 작업폴더/transcript.json -o 작업폴더/cut.mp4
  # 특정 문장을 강제로 빼거나 살리기 (번호는 cut_report.txt 참고)
  python workflow/scripts/cut.py ... --drop 3,7 --keep 5

결과물:
  cut.mp4               잘라낸 영상
  cut.transcript.json   잘라낸 영상 기준으로 시각을 다시 맞춘 받아쓰기 (꾸미기·숏폼에 사용)
  cut.transcript.txt    같은 내용을 사람이 읽기 쉽게 (글쓰기 재료)
  cut_report.txt        무엇을 왜 잘랐는지 (사람 확인용)
"""
import argparse
import difflib
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_time, load_json, normalize, probe, run, save_json, write_srt  # noqa: E402

FILLERS = {"어", "음", "그", "저", "아", "에", "으", "흠", "어어", "음음", "그러니까", "뭐지"}
SENT_END = re.compile(r"[.?!。]$|(요|다|죠|까|네|군요|세요|니다)[.?!]?$")


def split_sentences(segments, pause=0.7):
    """whisper 문장을 실제 문장 단위로 다시 나눈다 (마침표·어미 또는 긴 쉼 기준)."""
    words = [w for s in segments for w in s["words"]]
    sents, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 99
        if gap >= pause or (SENT_END.search(w["w"]) and gap >= 0.15) or re.search(r"[.?!]$", w["w"]):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)
    out = []
    for ws in sents:
        text = " ".join(w["w"] for w in ws)
        out.append({"id": len(out), "start": ws[0]["start"], "end": ws[-1]["end"], "text": text, "words": ws})
    return out


def is_filler(sent):
    toks = [normalize(w["w"]) for w in sent["words"]]
    toks = [t for t in toks if t]
    return bool(toks) and all(t in FILLERS for t in toks)


def is_retake(a, b, sim):
    """b 가 a 를 다시 읽은 것인가? (a 를 버리고 b 를 남긴다)"""
    na, nb = normalize(a["text"]), normalize(b["text"])
    if len(na) < 4 or len(nb) < 4:
        return False
    if difflib.SequenceMatcher(None, na, nb).ratio() >= sim:
        return True
    # 읽다가 멈춘 경우: a 가 b 의 앞부분과 거의 같음
    head = nb[: len(na)]
    if len(na) <= len(nb) and difflib.SequenceMatcher(None, na, head).ratio() >= 0.8:
        return True
    return False


def plan(sents, sim, lookahead, drop, keep):
    reason = {}
    for i, s in enumerate(sents):
        if is_filler(s):
            reason[i] = "군말"
            continue
        for j in range(i + 1, min(len(sents), i + 1 + lookahead)):
            if is_retake(s, sents[j], sim):
                reason[i] = f"다시 읽음 → #{j:03d} 를 남김"
                break
    for i in drop:
        reason[i] = "직접 지정해서 뺌"
    for i in keep:
        reason.pop(i, None)
    return reason


def keep_ranges(sents, removed, gap, max_inner, duration):
    """남길 구간 목록. 문장 사이·문장 안의 긴 쉼은 gap 초만 남기고 자른다."""
    lead, tail = gap * 0.4, gap * 0.6
    ranges = []  # (start, end, [words])
    for i, s in enumerate(sents):
        if i in removed:
            continue
        piece = [s["words"][0]]
        for w in s["words"][1:]:
            if w["start"] - piece[-1]["end"] > max_inner:
                ranges.append(piece)
                piece = []
            piece.append(w)
        ranges.append(piece)
    out = []
    for ws in ranges:
        a = max(0.0, ws[0]["start"] - lead)
        b = min(duration, ws[-1]["end"] + tail)
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2] + ws)
        else:
            out.append((a, b, ws))
    return out


def render(src, ranges, dst, info):
    parts, labels = [], []
    has_a = info["has_audio"]
    for k, (a, b, _) in enumerate(ranges):
        d = b - a
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{k}]")
        if has_a:
            fade = min(0.01, d / 4)
            parts.append(
                f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={fade:.3f},afade=t=out:st={d - fade:.3f}:d={fade:.3f}[a{k}]"
            )
            labels.append(f"[v{k}][a{k}]")
        else:
            labels.append(f"[v{k}]")
    parts.append(f"{''.join(labels)}concat=n={len(ranges)}:v=1:a={1 if has_a else 0}[vo]" + ("[ao]" if has_a else ""))
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(";\n".join(parts))
        script = f.name
    cmd = ["ffmpeg", "-y", "-i", str(src), "-filter_complex_script", script, "-map", "[vo]"]
    if has_a:
        cmd += ["-map", "[ao]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
    run(cmd)
    os.unlink(script)


def remap(ranges):
    """잘라낸 영상 기준 시각으로 단어·문장을 다시 맞춘다."""
    words, offset = [], 0.0
    for a, b, ws in ranges:
        for w in ws:
            words.append({**w, "start": round(w["start"] - a + offset, 3), "end": round(w["end"] - a + offset, 3)})
        offset += b - a
    return words, offset


def main():
    ap = argparse.ArgumentParser(description="말 없는 구간·다시 읽은 문장 자르기")
    ap.add_argument("video")
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--gap", type=float, default=0.05, help="문장 사이에 남길 정적(초). 기본 0.05")
    ap.add_argument("--max-inner", type=float, default=0.30, help="문장 안에서 이보다 긴 쉼은 자름(초)")
    ap.add_argument("--sim", type=float, default=0.6, help="다시 읽은 문장으로 볼 유사도(0~1)")
    ap.add_argument("--lookahead", type=int, default=3, help="몇 문장 뒤까지 다시 읽은 문장을 찾을지")
    ap.add_argument("--drop", default="", help="강제로 뺄 문장 번호 (예: 3,7)")
    ap.add_argument("--keep", default="", help="강제로 살릴 문장 번호")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = lambda s: [int(x) for x in s.split(",") if x.strip()]  # noqa: E731
    info = probe(args.video)
    tr = load_json(args.transcript)
    sents = split_sentences(tr["segments"])
    removed = plan(sents, args.sim, args.lookahead, ids(args.drop), ids(args.keep))
    ranges = keep_ranges(sents, removed, args.gap, args.max_inner, info["duration"])
    new_words, new_dur = remap(ranges)

    out = Path(args.out)
    report = [f"원본 {info['duration']:.1f}초 → 편집본 {new_dur:.1f}초 (구간 {len(ranges)}개)", ""]
    for i, s in enumerate(sents):
        mark = f"  ✂ 뺌 ({removed[i]})" if i in removed else ""
        report.append(f"#{i:03d} [{fmt_time(s['start'])}] {s['text']}{mark}")
    report_text = "\n".join(report)
    print(report_text)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_name(out.stem + "_report.txt").write_text(report_text, encoding="utf-8")
    if args.dry_run:
        print("\n(--dry-run: 영상은 만들지 않았습니다)")
        return

    render(args.video, ranges, out, info)
    kept = [s for i, s in enumerate(sents) if i not in removed]
    # 문장 단위로 다시 묶기
    segs, k = [], 0
    for s in kept:
        n = len(s["words"])
        ws = new_words[k : k + n]
        k += n
        segs.append({"id": len(segs), "start": ws[0]["start"], "end": ws[-1]["end"], "text": s["text"], "words": ws})
    tr_path = out.with_suffix(".transcript.json")
    save_json({"source": str(out), "duration": round(new_dur, 3), "segments": segs}, tr_path)
    write_srt(segs, tr_path.with_suffix(".srt"))
    tr_path.with_suffix(".txt").write_text(
        "\n".join(f"#{s['id']:03d} [{fmt_time(s['start'])}] {s['text']}" for s in segs), encoding="utf-8")
    print(f"\n완료: {out}  ({new_dur:.1f}초)")
    print("다음: 완성본을 다시 받아쓰기 → verify.py 로 잘림·중복 확인")


if __name__ == "__main__":
    main()
