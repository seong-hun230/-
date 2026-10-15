"""명령줄 실행: 블로그 주소 → 릴스 세트.

    python make_reels.py https://blog.naver.com/아이디/글번호 --length 20
    python make_reels.py --rerender output/20261015_…   (storyboard.txt 고친 뒤 다시 렌더)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="블로그 주소만 넣으면 릴스 영상을 만들어 줍니다.")
    ap.add_argument("url", nargs="?", help="블로그 글 주소")
    ap.add_argument("--length", type=int, default=20, choices=[15, 20, 30], help="영상 길이(초)")
    ap.add_argument("--grade", default="bright", choices=["clean", "warm", "cine", "punch", "bright"])
    ap.add_argument("--bgm", default="energetic", choices=["energetic", "trendy", "emotional", "cinematic"])
    ap.add_argument("--engine", default="auto", choices=["auto", "claude", "rule"],
                    help="auto: ANTHROPIC_API_KEY 가 있으면 Claude, 없으면 규칙 기반")
    ap.add_argument("--no-fx", action="store_true", help="줌 펀치·셰이크·비네트 끄기")
    ap.add_argument("--analyze-only", action="store_true", help="스토리보드까지만 만들고 멈춤")
    ap.add_argument("--rerender", metavar="작업폴더", help="기존 작업 폴더의 storyboard.txt 로 다시 렌더")
    a = ap.parse_args()

    opts = {"length": a.length, "grade": a.grade, "bgm": a.bgm, "engine": a.engine, "fx": not a.no_fx}
    if a.rerender:
        job = a.rerender
        rep = pipeline.step_render(job, {"grade": a.grade, "bgm": a.bgm, "fx": not a.no_fx})
    else:
        if not a.url:
            ap.error("블로그 주소를 입력하세요")
        job = pipeline.step_analyze(a.url, opts)
        print(f"\n스토리보드: {os.path.join(job, 'storyboard.txt')}")
        if a.analyze_only:
            return
        rep = pipeline.step_render(job, opts)
    print("\n=== 결과 ===")
    print("폴더:", job)
    print("영상:", rep["video"], f"({rep['duration']}초, {rep['lufs']} LUFS)")
    for c in rep["checks"]:
        print(("  [OK] " if c["ok"] else "  [확인] ") + c["label"] + (f" — {c['detail']}" if c["detail"] else ""))


if __name__ == "__main__":
    main()
