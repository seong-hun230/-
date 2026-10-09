"""STEP 2 받아쓰기: 영상에서 말한 단어와 시각(시작·끝)을 뽑는다.

사용법:
  python workflow/scripts/transcribe.py 원본.mp4 -o 작업폴더/transcript.json
  python workflow/scripts/transcribe.py 원본.mp4 -o 작업폴더/transcript.json --model large-v3

결과물:
  transcript.json  문장(segments)마다 start/end/text 와 단어(words)별 start/end
  transcript.srt   자막 파일(확인용)
  transcript.txt   시각이 붙은 문장 목록(사람이 읽기용)
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fmt_time, save_json, write_srt  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="영상 받아쓰기 (단어별 시각 포함)")
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True, help="transcript.json 저장 경로")
    ap.add_argument("--model", default="large-v3", help="whisper 모델 (small / medium / large-v3). 느리면 medium")
    ap.add_argument("--lang", default="ko")
    ap.add_argument("--prompt", default="", help="고유명사 힌트 (예: '클로드코드, 제르니오, 오송역')")
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("[오류] faster-whisper 가 없습니다. 'pip install -r workflow/requirements.txt' 를 먼저 실행하세요.")

    device, compute = "cpu", "int8"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:
        pass

    print(f"모델 불러오는 중: {args.model} ({device}) — 처음 한 번은 다운로드로 몇 분 걸립니다.")
    try:
        model = WhisperModel(args.model, device=device, compute_type=compute)
    except Exception as e:  # 첫 실행 때 모델 다운로드 실패가 대부분
        sys.exit(f"[오류] 받아쓰기 모델 '{args.model}' 을 불러오지 못했습니다 ({type(e).__name__}: {str(e)[:200]}).\n"
                 "인터넷 연결을 확인하고 다시 실행하세요. 계속 실패하면 --model medium 으로 시도해 보세요.")
    seg_iter, info = model.transcribe(
        args.video,
        language=args.lang,
        word_timestamps=True,
        vad_filter=False,  # 말 없는 구간도 시각표에 그대로 남겨야 컷 편집이 정확함
        condition_on_previous_text=False,  # 같은 문장을 다시 읽은 것을 합쳐버리지 않도록
        initial_prompt=args.prompt or None,
    )

    segments = []
    for s in seg_iter:
        words = [
            {"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)}
            for w in (s.words or [])
            if w.word.strip()
        ]
        if not words:
            continue
        segments.append(
            {
                "id": len(segments),
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "text": s.text.strip(),
                "words": words,
            }
        )
        print(f"  [{fmt_time(words[0]['start'])}] {s.text.strip()}")

    out = Path(args.out)
    save_json({"source": str(args.video), "duration": round(info.duration, 3), "segments": segments}, out)
    write_srt(segments, out.with_suffix(".srt"))
    out.with_suffix(".txt").write_text(
        "\n".join(f"#{s['id']:03d} [{fmt_time(s['start'])} ~ {fmt_time(s['end'])}] {s['text']}" for s in segments),
        encoding="utf-8",
    )
    print(f"\n완료: 문장 {len(segments)}개 → {out}")


if __name__ == "__main__":
    main()
