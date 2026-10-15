"""테스트: python tests/test_core.py  (pytest 로도 실행 가능)

외부 인터넷 없이, 로컬에 띄운 '가짜 네이버 블로그' 페이지로 수집 → 분석 → 렌더 → 검수 전체를 검증한다.
--quick 을 주면 렌더(약 1분)를 건너뛴다.
"""
import functools
import os
import shutil
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import analyze, fetch, pipeline, storyboard  # noqa: E402
from tests import make_fixture  # noqa: E402


def serve_fixture():
    d = tempfile.mkdtemp(prefix="b2r_fx_")
    make_fixture.main(d)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=d)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, d, f"http://127.0.0.1:{srv.server_address[1]}/post.html"


def test_normalize_naver():
    n = fetch.normalize_url
    want = "https://m.blog.naver.com/PostView.naver?blogId=abc&logNo=223"
    assert n("https://blog.naver.com/abc/223") == want
    assert n("blog.naver.com/abc/223") == want
    assert n("https://m.blog.naver.com/abc/223") == want
    assert n("https://blog.naver.com/PostView.naver?blogId=abc&logNo=223&from=x") == want
    assert n("https://example.tistory.com/12") == "https://example.tistory.com/12"


def test_storyboard_roundtrip():
    text = """# 제목: 테스트
@1 = img01.jpg    # 외관
@card = 텍스트카드
1 | 1.10 | 대전에 / 2,293세대가 / 통째로 | hook
1 5.4 | 1.90 | 지하철 / 용계역 예정 | chapter=입지·교통, trans=flash, zoom=out
card | 2.0 | | loop, cta
"""
    sb = storyboard.parse(text)
    assert sb["sources"]["1"] == "img01.jpg"
    assert sb["meta"]["제목"] == "테스트"
    c0, c1, c2 = sb["cuts"]
    assert c0["hook"] and c0["chunks"] == ["대전에", "2,293세대가", "통째로"]
    assert c1["start"] == 5.4 and c1["chapter"] == "입지·교통" and c1["trans"] == "flash" and c1["zoom"] == "out"
    assert c2["loop"] and c2["cta"] and c2["chunks"] == []
    again = storyboard.parse(storyboard.write(sb, title="테스트"))
    assert [c["chunks"] for c in again["cuts"]] == [c["chunks"] for c in sb["cuts"]]


def test_chunks_are_short():
    for s in ["아메리카노는 4,500원, 시그니처 크림라떼는 6,500원이에요",
              "1층은 통창이라 채광이 좋고 원목 테이블이라 사진이 예쁘게 나와요",
              "디저트는 딸기 케이크랑 바스크 치즈케이크가 인기라서 오후 3시 전에 품절되는 날이 많대요"]:
        ch = analyze._to_chunks(s)
        assert 1 <= len(ch) <= 3, ch
        assert all(1 <= len(c.split()) <= 3 for c in ch), ch


def test_fetch_and_plan():
    srv, d, url = serve_fixture()
    try:
        post = fetch.fetch_blog(url, log=lambda *a: None)
        assert "온도" in post["title"]
        imgs = [b for b in post["blocks"] if b["type"] == "image"]
        assert len(imgs) == 7, [b["url"] for b in imgs]           # 아이콘·스티커 제외
        assert imgs[0]["url"].endswith("/img/exterior.jpg")          # data-lazy-src 우선
        assert any(b.get("caption") == "시그니처 크림라떼" for b in imgs)
        assert any(b["type"] == "heading" and b["text"] == "메뉴와 가격" for b in post["blocks"])
        out = tempfile.mkdtemp(prefix="b2r_img_")
        assert fetch.download_images(post, out, log=lambda *a: None) == 7
        for length, n_body in ((15, 5), (20, 8), (30, 13)):
            assert analyze.body_cut_count(length) == n_body
            plan = analyze.rule_plan(post, length, log=lambda *a: None)
            sb = analyze.plan_to_storyboard(plan, post, length)
            cuts = sb["cuts"]
            assert [c["dur"] for c in cuts[:3]] == [1.10, 1.05, 0.90]
            assert cuts[-1]["loop"] and cuts[-1]["cta"] and cuts[-1]["dur"] == 2.0
            flashy = [c for c in cuts if c["trans"] in ("whip", "flash", "glitch", "zoomblur")]
            assert len(flashy) <= 3
            assert all(len(ch.split()) <= 3 for c in cuts for ch in c["chunks"])
            assert not analyze.numbers_not_in_source(sb, post)
        shutil.rmtree(out, ignore_errors=True)
    finally:
        srv.shutdown()
        shutil.rmtree(d, ignore_errors=True)


def test_end_to_end():
    srv, d, url = serve_fixture()
    job = None
    try:
        job = pipeline.step_analyze(url, {"length": 15, "engine": "rule"}, log=lambda *a, **k: None)
        rep = pipeline.step_render(job, {"grade": "bright", "bgm": "energetic"}, log=lambda *a, **k: None)
        files = os.listdir(job)
        for need in ("storyboard.txt", "검수시트.jpg", "컨택트시트.jpg", "캡션_복붙용.txt", rep["video"], rep["cover"]):
            assert need in files, need
        failed = {c["label"] for c in rep["checks"] if not c["ok"]}
        assert failed <= {"자막↔사진 일치 직접 확인"}, failed
        assert abs(rep["duration"] - 14.55) < 0.05
    finally:
        srv.shutdown()
        shutil.rmtree(d, ignore_errors=True)
        if job:
            shutil.rmtree(job, ignore_errors=True)


if __name__ == "__main__":
    tests = [test_normalize_naver, test_storyboard_roundtrip, test_chunks_are_short, test_fetch_and_plan]
    if "--quick" not in sys.argv:
        tests.append(test_end_to_end)
    for t in tests:
        t()
        print("통과:", t.__name__)
    print("모든 테스트 통과")
