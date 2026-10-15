"""공통 유틸: ffmpeg 경로, 폰트, 로그."""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")

W, H = 1080, 1920
FPS = 30


def font_path(weight="Black"):
    p = os.path.join(FONT_DIR, f"Pretendard-{weight}.otf")
    if not os.path.exists(p):
        raise FileNotFoundError(f"폰트 파일이 없습니다: {p}")
    return p


_FFMPEG = None


def ffmpeg_exe():
    """시스템 ffmpeg → 없으면 imageio-ffmpeg 내장 바이너리."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    exe = os.environ.get("BLOG2REELS_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = None
    if not exe:
        raise RuntimeError(
            "ffmpeg 를 찾을 수 없습니다. 'pip install imageio-ffmpeg' 를 실행하거나 ffmpeg 를 설치하세요.")
    _FFMPEG = exe
    return exe


def run_ffmpeg(args, input_bytes=None, capture=True):
    cmd = [ffmpeg_exe(), "-hide_banner", "-y"] + list(args)
    r = subprocess.run(cmd, input=input_bytes, capture_output=capture)
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace")[-1500:]
        raise RuntimeError(f"ffmpeg 실패: {' '.join(args[:6])} ...\n{err}")
    return r


def media_duration(path):
    """ffprobe 없이 ffmpeg 출력에서 길이를 읽는다."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr.decode("utf-8", "replace"))
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def slugify(text, limit=40):
    text = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", text or "").strip("_.")
    return (text[:limit] or "reels")


class Logger:
    """진행률 + 로그를 콜백으로 전달 (웹 UI · CLI 공용)."""

    def __init__(self, cb=None):
        self.cb = cb
        self.lines = []

    def __call__(self, msg, progress=None):
        self.lines.append(msg)
        if self.cb:
            self.cb(msg, progress)
        else:
            pct = f"[{progress:3.0f}%] " if progress is not None else ""
            print(pct + msg, file=sys.stderr, flush=True)
