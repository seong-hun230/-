"""블로그 → 릴스 자동 제작 앱 (브라우저 화면).

실행:  python app.py   → 브라우저가 자동으로 열립니다 (http://127.0.0.1:8800)
추가 설치 없이 파이썬 표준 라이브러리 웹서버로 동작합니다.
"""
import json
import mimetypes
import os
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import pipeline  # noqa: E402
from core.util import Logger  # noqa: E402

PORT = int(os.environ.get("BLOG2REELS_PORT", "8800"))
JOBS = {}
LOCK = threading.Lock()
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def job_state(job_id):
    with LOCK:
        return JOBS.setdefault(job_id, {"state": "idle", "progress": 0, "log": []})


def make_logger(job_id):
    st = job_state(job_id)

    def cb(msg, progress=None):
        with LOCK:
            st["log"].append(msg)
            st["log"] = st["log"][-200:]
            if progress is not None:
                st["progress"] = round(progress, 1)
    return Logger(cb)


def run_job(job_id, kind, payload):
    st = job_state(job_id)
    job_dir = os.path.join(pipeline.OUT_ROOT, job_id)
    log = make_logger(job_id)
    with LOCK:
        st.update(state="running", progress=0, error=None, report=None)
        if kind == "start":
            st["log"] = []
    try:
        opts = {k: payload[k] for k in ("length", "grade", "bgm", "engine", "fx", "api_key")
                if k in payload}
        if "length" in opts:
            opts["length"] = int(opts["length"])
        if kind == "start":
            pipeline.step_analyze(payload["url"], opts, job_dir=job_dir, log=log)
            if payload.get("analyze_only"):
                with LOCK:
                    st.update(state="analyzed", progress=100)
                return
            rep = pipeline.step_render(job_dir, opts, log=log)
        else:
            opts.pop("api_key", None)
            rep = pipeline.step_render(job_dir, opts, storyboard_text=payload.get("storyboard"), log=log)
        with LOCK:
            st.update(state="done", progress=100, report=rep)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        with LOCK:
            st.update(state="error", error=str(e))
            st["log"].append("오류: " + str(e))


def job_files(job_id):
    d = os.path.join(pipeline.OUT_ROOT, job_id)
    out = {}
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        p = os.path.join(d, f)
        if not os.path.isfile(p) or f.startswith("_"):
            continue
        if f.endswith(".mp4"):
            out["video"] = f
        elif f.endswith("_커버.jpg"):
            out["cover"] = f
        elif f in ("검수시트.jpg", "컨택트시트.jpg", "캡션_복붙용.txt", "storyboard.txt", "report.json"):
            out[f] = f
    return out


def read_text(job_id, name):
    p = os.path.join(pipeline.OUT_ROOT, job_id, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 조용히
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def _file(self, path):
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if q.get("dl"):
            fn = urllib.parse.quote(os.path.basename(path))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{fn}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._file(os.path.join(STATIC, "index.html"))
        if u.path == "/api/status":
            jid = (q.get("job") or [""])[0]
            st = dict(job_state(jid))
            st["log"] = st.get("log", [])[-60:]
            st["files"] = job_files(jid)
            if st["state"] in ("done", "analyzed", "idle") and st["files"]:
                st["storyboard"] = read_text(jid, "storyboard.txt")
                st["caption"] = read_text(jid, "캡션_복붙용.txt")
                if not st.get("report") and "report.json" in st["files"]:
                    st["report"] = json.loads(read_text(jid, "report.json"))
            return self._json(st)
        if u.path == "/api/jobs":
            os.makedirs(pipeline.OUT_ROOT, exist_ok=True)
            items = sorted(os.listdir(pipeline.OUT_ROOT), reverse=True)[:30]
            return self._json([{"job": j, "files": job_files(j)} for j in items
                               if os.path.isdir(os.path.join(pipeline.OUT_ROOT, j))])
        if u.path.startswith("/files/"):
            parts = [urllib.parse.unquote(x) for x in u.path.split("/")[2:]]
            if len(parts) != 2 or any(p in ("", ".", "..") or "/" in p or "\\" in p for p in parts):
                return self._json({"error": "잘못된 경로"}, 400)
            p = os.path.join(pipeline.OUT_ROOT, parts[0], parts[1])
            if not os.path.isfile(p):
                return self._json({"error": "파일 없음"}, 404)
            return self._file(p)
        self._json({"error": "없는 주소"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        try:
            data = self._body()
        except Exception:  # noqa: BLE001
            return self._json({"error": "요청 형식 오류"}, 400)
        if u.path == "/api/start":
            url = (data.get("url") or "").strip()
            if not url:
                return self._json({"error": "블로그 주소를 입력하세요"}, 400)
            jid = os.path.basename(pipeline.new_job_dir("blog"))
            threading.Thread(target=run_job, args=(jid, "start", data), daemon=True).start()
            return self._json({"job": jid})
        if u.path == "/api/rerender":
            jid = data.get("job", "")
            if not jid or "/" in jid or "\\" in jid or not os.path.isdir(os.path.join(pipeline.OUT_ROOT, jid)):
                return self._json({"error": "작업을 찾을 수 없습니다"}, 404)
            if job_state(jid).get("state") == "running":
                return self._json({"error": "이미 진행 중입니다"}, 409)
            threading.Thread(target=run_job, args=(jid, "rerender", data), daemon=True).start()
            return self._json({"job": jid})
        self._json({"error": "없는 주소"}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"\n  블로그 → 릴스 앱이 실행되었습니다:  {url}\n  (이 창을 닫으면 앱이 종료됩니다)\n")
    if not os.environ.get("BLOG2REELS_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
