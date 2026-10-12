"""STEP 5 숏폼 자동 분할: 롱폼에서 30~45초짜리 숏폼을 '한 편 = 정보 하나'로 잘라낸다.

사용법:
  # 1) 문장 목록 보기 (Claude 가 이걸 보고 어떤 구간을 자를지 고른다)
  python workflow/scripts/shorts.py list 작업폴더/cut.transcript.json
  # 2) 계획(json)대로 자르기 → 숏폼마다 영상 + 받아쓰기가 생김 (그 다음 decorate.py 로 꾸미기)
  python workflow/scripts/shorts.py cut 작업폴더/cut.mp4 작업폴더/cut.transcript.json 작업폴더/shorts_plan.json -o 작업폴더/shorts
  # 가로 영상이면 --vertical 로 가운데를 세로(9:16)로 잘라냄

계획 파일 형식: workflow/templates/shorts_plan.example.json
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_time, load_json, probe, run, save_json  # noqa: E402
from cut import split_sentences  # noqa: E402

# 이런 말로 시작하면 앞 문장을 모르면 이해가 안 됨 → 자동으로 앞 문장까지 포함
CONNECTIVES = ("그래서", "아까", "그러니까", "그런데", "근데", "그리고", "그러면", "그럼", "그래도", "앞에서", "방금",
               "그다음", "그 다음", "다음으로")
# 이런 말로 시작하면 앞 맥락이 필요할 수 있음 → 경고만 (판단은 Claude/사람)
MAYBE = ("이게", "그게", "이렇게", "그렇게", "여기서", "또", "이건", "그건")


def sentences(tr):
    segs = tr["segments"]
    # cut.py 결과는 이미 문장 단위. 원본 받아쓰기면 문장으로 다시 나눈다.
    if any(len(s["words"]) > 25 for s in segs):
        return split_sentences(segs)
    return [{**s, "id": i} for i, s in enumerate(segs)]


def _head(text):
    return re.sub(r"^[\s\"'“‘(]+", "", text)


def starts_with_connective(text):
    return _head(text).startswith(CONNECTIVES)


def maybe_needs_context(text):
    return _head(text).startswith(MAYBE)


def cmd_list(args):
    sents = sentences(load_json(args.transcript))
    for s in sents:
        flag = "  ← 앞 문장 필요" if starts_with_connective(s["text"]) else ("  ← 앞 맥락 확인" if maybe_needs_context(s["text"]) else "")
        print(f"#{s['id']:03d} [{fmt_time(s['start'])}] ({s['end'] - s['start']:4.1f}초) {s['text']}{flag}")
    print(f"\n총 {len(sents)}문장, {sents[-1]['end']:.1f}초")


def cmd_cut(args):
    tr = load_json(args.transcript)
    sents = sentences(tr)
    plan = load_json(args.plan)
    info = probe(args.video)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    lead, tail = 0.05, 0.25
    for k, item in enumerate(plan["shorts"], 1):
        a_id, b_id = int(item["from"]), int(item["to"])
        notes = []
        while a_id > 0 and starts_with_connective(sents[a_id]["text"]):
            a_id -= 1
            notes.append(f"'{sents[a_id + 1]['text'][:12]}…' 가 이어지는 말로 시작해서 #{a_id:03d} 부터 포함")
        if maybe_needs_context(sents[a_id]["text"]):
            notes.append(f"첫 문장 '{sents[a_id]['text'][:15]}…' 이 앞 맥락 없이 이해되는지 확인")
        a = max(0.0, sents[a_id]["start"] - lead)
        b = min(info["duration"], sents[b_id]["end"] + tail)
        dur = b - a
        if not (args.min <= dur <= args.max):
            notes.append(f"길이 {dur:.1f}초 — 권장 {args.min:.0f}~{args.max:.0f}초 밖")
        name = item.get("name") or f"short{k}"
        dst = outdir / f"{name}.mp4"
        vf = []
        if args.vertical and info["width"] > info["height"]:
            vf.append("crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920")
        cmd = ["ffmpeg", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(args.video)]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)]
        run(cmd)
        segs = []
        for s in sents[a_id : b_id + 1]:
            ws = [{**w, "start": round(w["start"] - a, 3), "end": round(w["end"] - a, 3)} for w in s["words"]]
            segs.append({"id": len(segs), "start": ws[0]["start"], "end": ws[-1]["end"], "text": s["text"], "words": ws})
        save_json({"source": str(dst), "duration": round(dur, 3), "segments": segs, "title": item.get("title", "")},
                  dst.with_suffix(".transcript.json"))
        print(f"[{name}] #{a_id:03d}~#{b_id:03d}  {dur:.1f}초  {item.get('title', '')}")
        for n in notes:
            print(f"   - {n}")
    print(f"\n완료: {outdir}  (다음: 숏폼마다 decor.json 을 만들어 decorate.py 로 꾸미기)")


def main():
    ap = argparse.ArgumentParser(description="롱폼 → 숏폼 분할")
    sub = ap.add_subparsers(dest="mode", required=True)
    p1 = sub.add_parser("list")
    p1.add_argument("transcript")
    p2 = sub.add_parser("cut")
    p2.add_argument("video")
    p2.add_argument("transcript")
    p2.add_argument("plan")
    p2.add_argument("-o", "--out", required=True)
    p2.add_argument("--vertical", action="store_true", help="가로 영상을 세로 9:16 으로 가운데 자르기")
    p2.add_argument("--min", type=float, default=30)
    p2.add_argument("--max", type=float, default=45)
    args = ap.parse_args()
    cmd_list(args) if args.mode == "list" else cmd_cut(args)


if __name__ == "__main__":
    main()
