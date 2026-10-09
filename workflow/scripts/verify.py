"""STEP 3 검증: 완성본을 다시 받아쓰기한 결과와 '남기기로 한 문장'을 비교해서
말이 잘린 곳·두 번 나오는 곳을 찾는다.

사용법:
  python workflow/scripts/transcribe.py 작업폴더/cut.mp4 -o 작업폴더/cut.recheck.json
  python workflow/scripts/verify.py 작업폴더/cut.transcript.json 작업폴더/cut.recheck.json

문제가 없으면 '이상 없음', 있으면 위치(시각)와 내용을 보여주고 종료코드 1로 끝난다.
"""
import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_time, load_json, normalize  # noqa: E402


def char_stream(tr):
    """정규화된 글자열과, 글자마다 해당 단어의 시각."""
    chars, times = [], []
    for s in tr["segments"]:
        for w in s["words"]:
            for c in normalize(w["w"]):
                chars.append(c)
                times.append(w["start"])
    return "".join(chars), times


def find_repeats(text, times, min_len):
    """바로 이어서 똑같이 반복된 구간(예: '이거 이거', '설치하고 설치하고')."""
    hits, i, n = [], 0, len(text)
    while i < n:
        found = False
        for L in range(min(40, (n - i) // 2), min_len - 1, -1):
            if text[i : i + L] == text[i + L : i + 2 * L]:
                hits.append((times[i], text[i : i + L]))
                i += 2 * L
                found = True
                break
        if not found:
            i += 1
    return hits


def main():
    ap = argparse.ArgumentParser(description="잘림·중복 검사")
    ap.add_argument("expected", help="cut.py 가 만든 cut.transcript.json")
    ap.add_argument("actual", help="완성본을 다시 받아쓰기한 json")
    ap.add_argument("--min-miss", type=int, default=2, help="이 글자 수 이상 빠지면 '잘림'으로 표시")
    ap.add_argument("--min-repeat", type=int, default=3, help="이 글자 수 이상 반복되면 '중복'으로 표시")
    args = ap.parse_args()

    exp_text, exp_times = char_stream(load_json(args.expected))
    act_text, act_times = char_stream(load_json(args.actual))
    problems = []

    exp_repeats = {t for _, t in find_repeats(exp_text, exp_times, args.min_repeat)}
    repeats = [(at, t) for at, t in find_repeats(act_text, act_times, args.min_repeat) if t not in exp_repeats]
    for at, t in repeats:  # 원래 대본에 있던 반복(강조)은 제외
        problems.append((at, "중복?", f"'{t}' 가 연달아 두 번 나옴"))
    repeated = {t for _, t in repeats}

    sm = difflib.SequenceMatcher(None, exp_text, act_text, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and (i2 - i1) >= args.min_miss:
            at = act_times[min(j1, len(act_times) - 1)] if act_times else 0
            problems.append((at, "잘림?", f"'{exp_text[i1:i2]}' 가 완성본에서 안 들림" + (f" (대신 '{act_text[j1:j2]}')" if j2 > j1 else "")))
        if tag == "insert" and (j2 - j1) >= args.min_repeat and act_text[j1:j2] not in repeated:
            problems.append((act_times[j1], "추가?", f"'{act_text[j1:j2]}' 가 완성본에 더 있음"))

    ratio = sm.ratio()
    print(f"일치율 {ratio * 100:.1f}%  (받아쓰기 자체 오차가 있어 100%가 아니어도 정상)")
    if not problems:
        print("이상 없음: 잘리거나 겹친 곳을 찾지 못했습니다. 그래도 STEP 8 에서 사람이 한 번은 직접 보세요.")
        return
    print(f"\n확인할 곳 {len(problems)}개 (완성본 기준 시각):")
    for at, kind, msg in sorted(problems):
        print(f"  [{fmt_time(at)}] {kind} {msg}")
    print("\n받아쓰기 오차일 수도 있으니, 해당 시각을 직접 들어보고 판단하세요.")
    sys.exit(1)


if __name__ == "__main__":
    main()
