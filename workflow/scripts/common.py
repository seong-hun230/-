"""워크플로우 스크립트 공통 도구: ffmpeg 실행, 받아쓰기 파일 읽고 쓰기, 한글 글꼴 찾기."""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def need(tool):
    if shutil.which(tool) is None:
        sys.exit(f"[오류] '{tool}' 프로그램이 없습니다. workflow/설치안내.md 를 보고 먼저 설치하세요.")


def run(cmd, quiet=True):
    """ffmpeg 같은 외부 명령 실행. 실패하면 마지막 오류 줄을 보여주고 멈춘다."""
    need(cmd[0])
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        sys.exit(f"[오류] {' '.join(cmd[:3])} ... 실패\n{tail}")
    return p.stdout if quiet else p


def probe(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    fps = 30.0
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else 30.0
    w, h = (int(v["width"]), int(v["height"])) if v else (0, 0)
    # 휴대폰 세로 영상은 회전 정보로 저장되는 경우가 있어 보정
    rot = 0
    if v:
        rot = int(v.get("tags", {}).get("rotate", 0) or 0)
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return {
        "duration": float(info["format"]["duration"]),
        "width": w,
        "height": h,
        "fps": fps,
        "has_audio": a is not None,
    }


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def fmt_time(t):
    """초 → 00:01:02.345"""
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def srt_time(t):
    return fmt_time(t).replace(".", ",")


def write_srt(segments, path):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines += [str(i), f"{srt_time(seg['start'])} --> {srt_time(seg['end'])}", seg["text"].strip(), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def normalize(text):
    """비교용: 공백·문장부호 제거"""
    return re.sub(r"[\s\.,!?~…·\"'“”‘’()\[\]-]", "", text)


FONT_CANDIDATES = {
    "Windows": [("Malgun Gothic", "C:/Windows/Fonts/malgunbd.ttf"), ("Malgun Gothic", "C:/Windows/Fonts/malgun.ttf")],
    "Darwin": [
        ("Apple SD Gothic Neo", "/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        ("AppleGothic", "/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    ],
    "Linux": [
        ("Noto Sans CJK KR", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        ("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        ("WenQuanYi Zen Hei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ],
}


def korean_font():
    """(글꼴 이름, 파일 경로). workflow/assets/font.ttf 를 두면 그것을 우선 사용."""
    custom = Path(__file__).resolve().parent.parent / "assets" / "font.ttf"
    if custom.exists():
        return ("custom", str(custom))
    for name, path in FONT_CANDIDATES.get(platform.system(), []):
        if os.path.exists(path):
            return (name, path)
    for cands in FONT_CANDIDATES.values():
        for name, path in cands:
            if os.path.exists(path):
                return (name, path)
    sys.exit("[오류] 한글 글꼴을 찾지 못했습니다. 원하는 글꼴 파일을 workflow/assets/font.ttf 로 복사해 두세요.")
