#!/usr/bin/env python3
"""드라마 쇼츠 자동 제작기

유튜브 링크나 영상 파일을 받아 3분 이하(기본 약 2분 55초)의 9:16 세로 쇼츠를 만든다.

  python drama_shorts.py auto    <링크|파일> [--title 제목]   전부 자동
  python drama_shorts.py analyze <링크|파일>                  받아쓰기 + 장면 분석만
  python drama_shorts.py render  <작업폴더> --plan plan.json   편집 계획대로 렌더

필요: ffmpeg, ffprobe (PATH), pip 패키지 faster-whisper, scenedetect, yt-dlp, numpy
"""
import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

W, H = 1080, 1920
MAX_LEN = 178.0          # 유튜브 쇼츠 / 인스타 릴스 3분 제한보다 2초 짧게
DEFAULT_TARGET = 175.0

KEYWORDS = [
    '왜', '진짜', '정말', '어떻게', '미안', '사랑', '거짓말', '비밀', '헤어', '결혼', '이혼',
    '죽', '살려', '제발', '안 돼', '안돼', '그만', '엄마', '아빠', '배신', '복수', '임신',
    '회장', '기억', '약속', '누구', '설마', '뭐야', '미쳤', '용서', '경찰', '돈', '아이',
    '가지 마', '떠나', '울', '때리', '찾았', '알고 있', '모르', '처음', '마지막',
]


def log(msg):
    print(msg, flush=True)


def run(cmd, cwd=None):
    log('$ ' + ' '.join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def need_bin(name):
    if not shutil.which(name):
        sys.exit(f'[오류] {name} 을(를) 찾을 수 없습니다. FFmpeg를 설치한 뒤 다시 실행하세요.')


def default_font():
    s = platform.system()
    if s == 'Windows':
        return 'Malgun Gothic'
    if s == 'Darwin':
        return 'Apple SD Gothic Neo'
    return 'Noto Sans CJK KR'


def is_url(s):
    return re.match(r'^https?://', s.strip()) is not None


# ---------------------------------------------------------------- 입력 / 분석

def work_dir_for(src, out_dir):
    if is_url(src):
        base = Path(out_dir) if out_dir else default_url_out()
        name = 'shorts_' + hashlib.md5(src.strip().encode()).hexdigest()[:8]
    else:
        p = Path(src).expanduser().resolve()
        base = Path(out_dir) if out_dir else p.parent
        name = p.stem + '_shorts_work'
    w = base / name
    w.mkdir(parents=True, exist_ok=True)
    return w


def default_url_out():
    videos = Path.home() / 'Videos'
    return (videos if videos.is_dir() else Path.home()) / 'DramaShorts'


def fetch(src, work):
    meta_path = work / 'meta.json'
    if not is_url(src):
        p = Path(src).expanduser().resolve()
        if not p.is_file():
            sys.exit(f'[오류] 영상 파일을 찾을 수 없습니다: {p}')
        meta = {'source': str(p), 'title': p.stem}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
        return p, meta
    existing = sorted(work.glob('source.*'))
    existing = [e for e in existing if e.suffix.lower() in ('.mp4', '.mkv', '.webm')]
    if existing and meta_path.exists():
        return existing[0], json.loads(meta_path.read_text(encoding='utf-8'))
    import yt_dlp
    opts = {
        'format': 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b',
        'merge_output_format': 'mp4',
        'outtmpl': str(work / 'source.%(ext)s'),
        'noplaylist': True,
        'js_runtimes': {'deno': {}, 'node': {}},
    }
    log('[1/5] 유튜브 영상 내려받는 중...')
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(src.strip(), download=True)
    except Exception as e:
        sys.exit('[오류] 유튜브에서 영상을 내려받지 못했습니다.\n'
                 f'  원인: {e}\n'
                 '  해결: 영상을 직접 내려받아 그 파일을 넣어 주세요. '
                 '(클라우드 서버에서는 유튜브가 접속을 막는 경우가 많고, 집 PC에서는 대부분 됩니다)')
    files = [e for e in sorted(work.glob('source.*')) if e.suffix.lower() in ('.mp4', '.mkv', '.webm')]
    if not files:
        sys.exit('[오류] 영상을 내려받지 못했습니다.')
    meta = {'source': src.strip(), 'title': info.get('title') or '', 'channel': info.get('channel') or ''}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    return files[0], meta


def probe(video):
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height',
         '-of', 'json', str(video)], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    vs = [s for s in d.get('streams', []) if s.get('codec_type') == 'video']
    has_audio = any(s.get('codec_type') == 'audio' for s in d.get('streams', []))
    if not vs:
        sys.exit('[오류] 영상 트랙이 없는 파일입니다.')
    return {
        'duration': float(d['format']['duration']),
        'width': int(vs[0]['width']),
        'height': int(vs[0]['height']),
        'has_audio': has_audio,
    }


def transcribe(video, work, model_name, language):
    out = work / 'transcript.json'
    if out.exists():
        return json.loads(out.read_text(encoding='utf-8'))
    log(f'[2/5] 받아쓰기 중 (모델: {model_name}) - 영상 길이에 따라 수 분~수십 분 걸립니다...')
    import numpy as np
    from faster_whisper import WhisperModel
    # 소리는 ffmpeg로 직접 풀어서 넘긴다 (faster-whisper 내장 해독기는 PyAV 버전에 따라 오류가 난다)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-vn', '-ac', '1', '-ar', '16000',
                          '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)

    def run_model(device, compute):
        model = WhisperModel(model_name, device=device, compute_type=compute)
        segments, _ = model.transcribe(audio, language=language or None, vad_filter=True, beam_size=5)
        segs = []
        for s in segments:
            t = s.text.strip()
            if t:
                segs.append({'start': round(s.start, 2), 'end': round(s.end, 2), 'text': t})
                if len(segs) % 50 == 0:
                    log(f'  ... {fmt_time(s.end)} 까지 받아씀')
        return segs

    use_gpu = False
    try:
        import ctranslate2
        use_gpu = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass
    segs = None
    if use_gpu:
        try:
            segs = run_model('cuda', 'float16')
        except Exception as e:
            log(f'  그래픽카드로 받아쓰기를 못 해 CPU로 다시 합니다 ({e})')
    if segs is None:
        segs = run_model('cpu', 'int8')
    out.write_text(json.dumps(segs, ensure_ascii=False, indent=0), encoding='utf-8')
    return segs


def detect_scenes(video, work):
    out = work / 'scenes.json'
    if out.exists():
        return json.loads(out.read_text(encoding='utf-8'))
    log('[3/5] 장면 전환 찾는 중...')
    try:
        from scenedetect import detect, AdaptiveDetector
        scenes = detect(str(video), AdaptiveDetector(), show_progress=False)
        cuts = [round(s[0].get_seconds(), 2) for s in scenes[1:]]
    except Exception as e:
        log(f'  장면 감지를 건너뜁니다 ({e})')
        cuts = []
    out.write_text(json.dumps(cuts), encoding='utf-8')
    return cuts


def loudness(video, work, has_audio):
    """1초 단위 음량(dB) 목록."""
    out = work / 'loudness.json'
    if out.exists():
        return json.loads(out.read_text(encoding='utf-8'))
    if not has_audio:
        return []
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-vn', '-ac', '1', '-ar', '8000',
                          '-f', 's16le', '-'], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32)
    n = len(a) // 8000
    if n == 0:
        return []
    rms = np.sqrt((a[:n * 8000].reshape(n, 8000) ** 2).mean(axis=1)) + 1e-6
    db = [round(float(x), 1) for x in 20 * np.log10(rms / 32768.0)]
    out.write_text(json.dumps(db), encoding='utf-8')
    return db


def write_analysis(work, meta, info, segs, cuts, db):
    lines = [
        f"# 분석 결과: {meta.get('title', '')}",
        '',
        f"- 원본 길이: {fmt_time(info['duration'])} ({info['width']}x{info['height']})",
        f'- 대사 {len(segs)}줄, 장면 전환 {len(cuts)}곳',
        '',
        '## 대사 (시작~끝 초 | 그 구간 평균 음량 dB | 대사)',
        '',
    ]
    for s in segs:
        lines.append(f"{s['start']:.1f}~{s['end']:.1f} | {avg_db(db, s['start'], s['end']):.0f} | {s['text']}")
    lines += ['', '## 장면 전환 시각(초)', '', ', '.join(f'{c:.1f}' for c in cuts) or '(없음)', '']
    path = work / 'analysis.md'
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path


def analyze(src, args):
    need_bin('ffmpeg')
    need_bin('ffprobe')
    work = work_dir_for(src, args.out)
    video, meta = fetch(src, work)
    info = probe(video)
    segs = transcribe(video, work, args.model, args.lang) if info['has_audio'] else []
    cuts = detect_scenes(video, work)
    log('[4/5] 음량 분석 중...')
    db = loudness(video, work, info['has_audio'])
    (work / 'info.json').write_text(json.dumps(dict(info, video=str(video)), ensure_ascii=False), encoding='utf-8')
    path = write_analysis(work, meta, info, segs, cuts, db)
    return work, video, meta, info, segs, cuts, db, path


# ---------------------------------------------------------------- 자동 선택

def avg_db(db, start, end):
    if not db:
        return -30.0
    a, b = max(0, int(start)), min(len(db), int(math.ceil(end)))
    vals = db[a:b] or [db[min(a, len(db) - 1)]]
    return sum(vals) / len(vals)


def build_blocks(segs, duration, max_len=28.0, gap=1.2):
    blocks, cur = [], None
    for s in segs:
        if cur and s['start'] - cur['end'] <= gap and s['end'] - cur['start'] <= max_len:
            cur['end'] = s['end']
            cur['segs'].append(s)
        else:
            if cur:
                blocks.append(cur)
            cur = {'start': s['start'], 'end': s['end'], 'segs': [s]}
    if cur:
        blocks.append(cur)
    if not blocks:  # 대사가 없으면 10초 단위로 나눈다
        t = 0.0
        while t + 4 < duration:
            blocks.append({'start': t, 'end': min(duration, t + 10), 'segs': []})
            t += 10
    return blocks


def score_blocks(blocks, db, duration):
    if db:
        mean = sum(db) / len(db)
        sd = (sum((x - mean) ** 2 for x in db) / len(db)) ** 0.5 or 1.0
    else:
        mean, sd = -30.0, 1.0
    for b in blocks:
        text = ' '.join(s['text'] for s in b['segs'])
        length = max(1.0, b['end'] - b['start'])
        kw = sum(text.count(k) for k in KEYWORDS)
        punct = text.count('?') + 1.5 * text.count('!')
        cps = len(text.replace(' ', '')) / length
        loud = (avg_db(db, b['start'], b['end']) - mean) / sd
        score = 1.0 * loud + 0.6 * kw + 0.5 * punct + 0.15 * cps
        # 긴 원본은 앞부분(오프닝)과 끝부분(예고·크레딧)을 피한다
        if duration > 1200 and (b['start'] < duration * 0.03 or b['end'] > duration * 0.95):
            score -= 3
        b['score'] = score
        b['density'] = score / math.sqrt(length)
        b['text'] = text
    return blocks


def snap(t, cuts, before, after):
    best = None
    for c in cuts:
        if t - before <= c <= t + after and (best is None or abs(c - t) < abs(best - t)):
            best = c
    return best if best is not None else t


def auto_plan(segs, cuts, db, info, meta, target, title=None):
    duration = info['duration']
    target = min(target, MAX_LEN)
    blocks = score_blocks(build_blocks(segs, duration), db, duration)
    if not blocks:
        sys.exit('[오류] 쇼츠로 만들 구간을 찾지 못했습니다.')

    top = max(blocks, key=lambda b: b['score'])
    if not title:
        first = (top['segs'][0]['text'] if top['segs'] else meta.get('title', '')).strip()
        title = first[:24] if first else '이 장면 놓치지 마세요'

    # 원본이 목표 길이보다 짧으면 자르지 않고 통째로 쓴다
    if duration <= target:
        return {'title': title, 'clips': [{'start': 0.0, 'end': round(duration, 2), 'why': '원본 전체'}]}

    # 후킹 클립: 점수가 가장 높은 블록의 앞 3~8초
    hook ={'start': top['start'], 'end': min(top['end'], top['start'] + 8.0)}
    if hook['end'] - hook['start'] < 3:
        hook['end'] = min(duration, hook['start'] + 3.0)

    chosen, total = [], hook['end'] - hook['start']
    for b in sorted(blocks, key=lambda b: b['density'], reverse=True):
        length = b['end'] - b['start']
        if length < 2.5 or total + length > target:
            continue
        chosen.append(b)
        total += length
        if total >= target - 3:
            break

    # 시간이 많이 남으면, 다음으로 좋은 블록을 대사가 끝나는 곳에서 잘라 채운다
    room = target - total
    if room > 8:
        picked = {id(b) for b in chosen}
        for b in sorted(blocks, key=lambda b: b['density'], reverse=True):
            if id(b) in picked or b['end'] - b['start'] <= room:
                continue
            end = b['start'] + (room if not b['segs'] else 0.0)
            for s in b['segs']:
                if s['end'] - b['start'] > room:
                    break
                end = s['end']
            if end - b['start'] >= 4:
                chosen.append(dict(b, end=end))
                break

    # 시간 순으로 정렬하고, 가까운 블록은 하나로 이어 붙인다
    chosen.sort(key=lambda b: b['start'])
    clips = []
    for b in chosen:
        if clips and b['start'] - clips[-1]['end'] <= 2.0:
            clips[-1]['end'] = b['end']
        else:
            clips.append({'start': b['start'], 'end': b['end']})

    # 앞뒤 여유를 주고 장면 전환에 맞춘다
    for i, c in enumerate(clips):
        lo = clips[i - 1]['end'] if i > 0 else 0.0
        hi = clips[i + 1]['start'] if i + 1 < len(clips) else duration
        c['start'] = max(lo, snap(c['start'] - 0.25, cuts, 0.8, 0.4))
        c['end'] = min(hi, snap(c['end'] + 0.35, cuts, 0.4, 0.8))

    plan = {
        'title': title,
        'clips': [{'start': round(hook['start'], 2), 'end': round(hook['end'], 2), 'why': '후킹(가장 강한 장면 미리보기)'}]
        + [{'start': round(c['start'], 2), 'end': round(c['end'], 2), 'why': '자동 선택'} for c in clips],
    }
    return plan


# ---------------------------------------------------------------- 렌더

def fmt_time(t):
    t = max(0.0, t)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def wrap(text, width):
    words, lines, cur = text.split(), [], ''
    for w in words:
        while len(w) > width:  # 띄어쓰기 없는 긴 말은 강제로 자른다
            if cur:
                lines.append(cur)
                cur = ''
            lines.append(w[:width])
            w = w[width:]
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += ' ' + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def ass_escape(s):
    return s.replace('\\', '').replace('{', '(').replace('}', ')')


def remap_subs(segs, clips):
    """원본 대사 시각을 쇼츠 시간축으로 옮기고 2줄(한 줄 15자) 단위로 나눈다."""
    out, offset = [], 0.0
    for c in clips:
        for s in segs:
            a, b = max(s['start'], c['start']), min(s['end'], c['end'])
            if b - a < 0.3:
                continue
            lines = wrap(s['text'], 15)
            chunks = ['\n'.join(lines[i:i + 2]) for i in range(0, len(lines), 2)] or ['']
            total_chars = sum(len(x) for x in chunks) or 1
            t = offset + (a - c['start'])
            span = b - a
            for ch in chunks:
                d = span * len(ch) / total_chars
                out.append((t, t + d, ch))
                t += d
        offset += c['end'] - c['start']
    return out


def layout_margins(info, layout):
    """제목·자막 위치(ASS MarginV / Alignment)."""
    if layout == 'crop':
        return {'title_mv': 200, 'sub_align': 2, 'sub_mv': 420}
    fg_h = round(W * info['height'] / info['width'])
    if fg_h >= 1500:  # 원본이 이미 세로 영상
        return {'title_mv': 150, 'sub_align': 2, 'sub_mv': 330}
    top = (H - fg_h) / 2
    return {'title_mv': int(max(100, top - 250)), 'sub_align': 8, 'sub_mv': int(top + fg_h + 50)}


def write_ass(path, title, subs, total, font, m, with_subs):
    title_text = '\\N'.join(ass_escape(x) for x in wrap(title, 12)[:2])
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{font},86,&H0000FFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,2,8,50,50,{m['title_mv']},1
Style: Sub,{font},64,&H00FFFFFF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,5,1,{m['sub_align']},60,60,{m['sub_mv']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if title.strip():
        ev.append(f'Dialogue: 1,{ass_time(0)},{ass_time(total)},Title,,0,0,0,,{title_text}')
    if with_subs:
        for a, b, t in subs:
            ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{ass_escape(t).replace(chr(10), chr(92) + 'N')}")
    path.write_text(head + '\n'.join(ev) + '\n', encoding='utf-8')


def write_srt(path, subs):
    lines = []
    for i, (a, b, t) in enumerate(subs, 1):
        lines += [str(i), f'{srt_time(a)} --> {srt_time(b)}', t, '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def clean_plan(plan, duration):
    clips = []
    for c in plan.get('clips', []):
        s, e = max(0.0, float(c['start'])), min(duration, float(c['end']))
        if e - s >= 0.5:
            clips.append({'start': s, 'end': e})
    if not clips:
        sys.exit('[오류] 편집 계획에 쓸 수 있는 구간이 없습니다.')
    total, kept = 0.0, []
    for c in clips:
        room = MAX_LEN - total
        if room < 0.5:
            break
        if c['end'] - c['start'] > room:
            c['end'] = c['start'] + room
        kept.append(c)
        total += c['end'] - c['start']
    return kept


def render(work, plan, args):
    need_bin('ffmpeg')
    info = json.loads((work / 'info.json').read_text(encoding='utf-8'))
    video = Path(info['video'])
    segs_path = work / 'transcript.json'
    segs = json.loads(segs_path.read_text(encoding='utf-8')) if segs_path.exists() else []
    clips = clean_plan(plan, info['duration'])
    title = args.title if args.title is not None else plan.get('title', '')
    layout = args.layout
    log(f'[5/5] 쇼츠 편집 중... (구간 {len(clips)}개)')

    if layout == 'crop':
        vchain = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
    else:
        vchain = ('split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
                  'boxblur=20:2,eq=brightness=-0.12[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2')
    fc = f'[0:v]{vchain},fps=30,setsar=1,format=yuv420p[v]'

    parts = work / 'parts'
    if parts.exists():
        shutil.rmtree(parts)
    parts.mkdir()
    listing = []
    for i, c in enumerate(clips):
        d = c['end'] - c['start']
        part = parts / f'part_{i:03d}.mp4'
        cmd = ['ffmpeg', '-y', '-v', 'error', '-ss', f"{c['start']:.3f}", '-t', f'{d:.3f}', '-i', video]
        if info['has_audio']:
            amap = ['-map', '0:a:0']
        else:
            cmd += ['-f', 'lavfi', '-t', f'{d:.3f}', '-i', 'anullsrc=r=48000:cl=stereo']
            amap = ['-map', '1:a:0']
        fade = f'afade=t=in:d=0.06,afade=t=out:st={max(0.0, d - 0.08):.3f}:d=0.08'
        cmd += ['-filter_complex', fc, '-map', '[v]'] + amap + [
            '-af', fade, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', part]
        log(f'  구간 {i + 1}/{len(clips)}: {fmt_time(c["start"])} ~ {fmt_time(c["end"])}')
        subprocess.run([str(x) for x in cmd], check=True)
        listing.append(f"file '{part.name}'")
    (parts / 'list.txt').write_text('\n'.join(listing) + '\n', encoding='utf-8')
    run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', 'joined.mp4'],
        cwd=parts)

    total = sum(c['end'] - c['start'] for c in clips)
    subs = remap_subs(segs, clips)
    write_ass(work / 'subs.ass', title, subs, total, args.font or default_font(),
              layout_margins(info, layout), not args.no_subs)

    out_dir = work.parent
    stem = re.sub(r'[\\/:*?"<>|]+', '', (title or 'drama').strip())[:30].strip() or 'drama'
    out = out_dir / f'{stem}_쇼츠.mp4'
    n = 2
    while out.exists():
        out = out_dir / f'{stem}_쇼츠_{n}.mp4'
        n += 1
    run(['ffmpeg', '-y', '-v', 'error', '-i', 'parts/joined.mp4', '-vf', 'ass=subs.ass',
         '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', out], cwd=work)
    shutil.rmtree(parts, ignore_errors=True)

    write_srt(out.with_suffix('.srt'), subs)
    meta_path = work / 'meta.json'
    meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
    caption = [title, '', '#드라마 #드라마쇼츠 #명장면 #shorts #드라마추천']
    if meta.get('title'):
        caption += ['', f"원본: {meta['title']}" + (f" ({meta['channel']})" if meta.get('channel') else '')]
    out.with_name(out.stem + '_캡션.txt').write_text('\n'.join(caption) + '\n', encoding='utf-8')
    (work / 'plan_used.json').write_text(json.dumps({'title': title, 'clips': clips}, ensure_ascii=False, indent=1),
                                         encoding='utf-8')

    final = probe(out)
    log('')
    log(f'완성: {out}')
    log(f"길이 {fmt_time(final['duration'])} / {final['width']}x{final['height']}")
    if final['duration'] > 180:
        log('[주의] 3분을 넘었습니다. 쇼츠로 올라가지 않을 수 있습니다.')
    if args.open and platform.system() == 'Windows':
        os.startfile(str(out_dir))
    return out


# ---------------------------------------------------------------- CLI

def main():
    p = argparse.ArgumentParser(description='드라마 쇼츠 자동 제작기')
    sub = p.add_subparsers(dest='cmd', required=True)

    def common(sp):
        sp.add_argument('--out', help='결과를 저장할 폴더')
        sp.add_argument('--model', default='small', help='받아쓰기 모델 (tiny/base/small/medium/large-v3)')
        sp.add_argument('--lang', default='ko', help='대사 언어 (기본 ko)')

    def look(sp):
        sp.add_argument('--title', default=None, help='상단 제목 문구 (빈 문자열이면 제목 없음)')
        sp.add_argument('--layout', choices=['blur', 'crop'], default='blur',
                        help='blur: 원본 전체 + 흐린 배경(기본), crop: 가운데를 세로로 꽉 채움')
        sp.add_argument('--font', default=None, help='자막 글꼴 이름')
        sp.add_argument('--no-subs', action='store_true', help='자막을 넣지 않음 (원본에 자막이 있을 때)')
        sp.add_argument('--open', action='store_true', help='완성 후 결과 폴더 열기 (Windows)')

    a = sub.add_parser('auto', help='링크/파일 -> 쇼츠까지 전부 자동')
    a.add_argument('source')
    a.add_argument('--target', type=float, default=DEFAULT_TARGET, help='목표 길이(초), 최대 178')
    common(a)
    look(a)

    z = sub.add_parser('analyze', help='받아쓰기 + 장면 분석만')
    z.add_argument('source')
    common(z)

    r = sub.add_parser('render', help='편집 계획(plan.json)대로 렌더')
    r.add_argument('work')
    r.add_argument('--plan', required=True)
    look(r)

    args = p.parse_args()
    if args.cmd == 'analyze':
        work, *_rest, path = analyze(args.source, args)
        log('')
        log(f'작업 폴더: {work}')
        log(f'분석 파일: {path}')
    elif args.cmd == 'auto':
        work, video, meta, info, segs, cuts, db, _ = analyze(args.source, args)
        plan = auto_plan(segs, cuts, db, info, meta, args.target, args.title)
        (work / 'plan_auto.json').write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
        args.title = plan['title']
        render(work, plan, args)
    else:
        work = Path(args.work).expanduser().resolve()
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
        render(work, plan, args)


if __name__ == '__main__':
    main()
