"""BGM · 효과음 엔진 (numpy 합성, 저작권 걱정 없는 자체 음원).

- BPM = 컷 길이 정렬: 본문 컷 1.9초 = 4박 → 126.3 BPM. 코드는 컷마다 바뀐다.
- BGM 드롭 = 챕터 전환: 챕터 직전 1박은 킥·베이스를 비우고, 챕터 첫 박에 꽉 채운다.
- 사이드체인: 킥이 칠 때 패드·베이스가 숨을 쉰다.
- 폰 스피커 마스터: 300Hz 아래를 걷어내고 배음(포화)으로 저음을 '들리게' 만든다.
"""
import numpy as np

SR = 44100
RNG = np.random.default_rng(7)

STYLES = {
    # 코드 진행(근음 MIDI, 화음 구성음 간격), 킥 패턴, 음색
    "energetic": {"chords": [(57, "m"), (53, "M"), (48, "M"), (55, "M")], "kick": "four",
                  "lead": "saw", "hat": 0.9, "swing": 0.0},
    "trendy": {"chords": [(53, "M7"), (52, "m7"), (50, "m7"), (48, "M7")], "kick": "half",
               "lead": "ep", "hat": 0.7, "swing": 0.12},
    "emotional": {"chords": [(48, "M"), (55, "M"), (57, "m"), (53, "M")], "kick": "soft",
                  "lead": "piano", "hat": 0.35, "swing": 0.0},
    "cinematic": {"chords": [(50, "m"), (46, "M"), (53, "M"), (48, "M")], "kick": "taiko",
                  "lead": "strings", "hat": 0.0, "swing": 0.0},
}
INTERVALS = {"M": [0, 4, 7], "m": [0, 3, 7], "M7": [0, 4, 7, 11], "m7": [0, 3, 7, 10]}


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _t(n):
    return np.arange(n) / SR


def _add(buf, sig, t0, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    if i0 >= buf.shape[0] or i0 + len(sig) <= 0:
        return
    if i0 < 0:
        sig = sig[-i0:]
        i0 = 0
    n = min(len(sig), buf.shape[0] - i0)
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[i0:i0 + n, 0] += sig[:n] * gain * l * 1.414
    buf[i0:i0 + n, 1] += sig[:n] * gain * r * 1.414


def fft_filter(x, sr=SR, lo=None, hi=None, gain_curve=None):
    """주파수 영역 필터(scipy 없이). x: (n,) 또는 (n,2)."""
    n = x.shape[0]
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(n, 1 / sr)
    g = np.ones_like(f)
    if lo:
        g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi:
        g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if gain_curve is not None:
        g *= gain_curve(f)
    if X.ndim == 2:
        g = g[:, None]
    return np.fft.irfft(X * g, n=n, axis=0)


# ───────────────────────── 악기 ─────────────────────────
def kick(style):
    n = int(0.45 * SR)
    t = _t(n)
    f = 48 + 110 * np.exp(-t * 28) if style != "taiko" else 70 + 60 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * (7 if style != "soft" else 11))
    click = RNG.standard_normal(n) * np.exp(-t * 300) * 0.25
    s = body + click
    if style == "taiko":
        s += fft_filter(RNG.standard_normal(n) * np.exp(-t * 14), hi=900) * 0.6
    return np.tanh(s * 1.6) * 0.9


def clap():
    n = int(0.3 * SR)
    t = _t(n)
    env = np.zeros(n)
    for d in (0.0, 0.011, 0.022):
        env += np.where(t >= d, np.exp(-(t - d) * 60), 0)
    env += np.exp(-t * 18) * 0.5
    return fft_filter(RNG.standard_normal(n), lo=900, hi=6000) * env * 0.5


def hat(open_=False):
    n = int((0.22 if open_ else 0.06) * SR)
    t = _t(n)
    return fft_filter(RNG.standard_normal(n), lo=7000) * np.exp(-t * (14 if open_ else 70)) * 0.25


def saw_voice(freq, dur, detune=(-0.12, 0.0, 0.12), cutoff=3500):
    n = int(dur * SR)
    t = _t(n)
    s = np.zeros(n)
    for d in detune:
        f = freq * 2 ** (d / 12)
        ph = (t * f + RNG.random()) % 1.0
        s += 2 * ph - 1
    s /= len(detune)
    return fft_filter(s, hi=cutoff)


def ep_voice(freq, dur):
    n = int(dur * SR)
    t = _t(n)
    s = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 6)
    return s * (1 + 0.15 * np.sin(2 * np.pi * 5 * t)) * np.exp(-t * 1.2)


def piano_voice(freq, dur):
    n = int(dur * SR)
    t = _t(n)
    s = sum(a * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (2.2 + k * 1.3))
            for k, a in ((1, 1.0), (2, 0.45), (3, 0.2), (4, 0.1)))
    return s * (1 - np.exp(-t * 400))


def adsr(n, a=0.01, r=0.15):
    env = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    if na:
        env[:na] = np.linspace(0, 1, na)
    if nr and nr < n:
        env[-nr:] *= np.linspace(1, 0, nr)
    return env


def bass_note(freq, dur):
    n = int(dur * SR)
    t = _t(n)
    s = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    s = np.tanh(s * 2.2)                      # 배음 → 폰 스피커에서도 들린다
    return s * adsr(n, 0.005, 0.05) * 0.6


# ───────────────────────── 효과음 ─────────────────────────
def sfx_whoosh(dur=0.45):
    n = int(dur * SR)
    t = _t(n)
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    lowband = fft_filter(RNG.standard_normal(n), lo=300, hi=2500)
    highband = fft_filter(RNG.standard_normal(n), lo=1500, hi=9000)
    mix = t / dur
    return (lowband * (1 - mix) + highband * mix) * env * 0.8


def sfx_impact():
    n = int(1.2 * SR)
    t = _t(n)
    f = 40 + 90 * np.exp(-t * 9)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    crack = fft_filter(RNG.standard_normal(n), lo=200, hi=5000) * np.exp(-t * 25) * 0.6
    return np.tanh((boom + crack) * 1.4) * 0.9


def sfx_riser(dur=0.9):
    n = int(dur * SR)
    t = _t(n)
    f = 300 * 2 ** (3 * t / dur)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    noise = fft_filter(RNG.standard_normal(n), lo=2000) * 0.4
    return (tone + noise) * (t / dur) ** 2


def sfx_ding():
    n = int(1.0 * SR)
    t = _t(n)
    return (np.sin(2 * np.pi * 1318.5 * t) * np.exp(-t * 4)
            + 0.4 * np.sin(2 * np.pi * 2637 * t) * np.exp(-t * 7)) * 0.45


def sfx_zap():
    n = int(0.25 * SR)
    t = _t(n)
    f = 2400 * np.exp(-t * 14) + 200
    return np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 16) * 0.25


SFX = {"whoosh": sfx_whoosh, "impact": sfx_impact, "riser": sfx_riser, "ding": sfx_ding,
       "zap": sfx_zap}


# ───────────────────────── 편곡 ─────────────────────────
def compose(timeline, style="energetic", body_dur=1.9, sfx_events=None):
    """timeline: {'total', 'body_start', 'chapter_starts':[t], 'cta_start'}"""
    st = STYLES.get(style, STYLES["energetic"])
    T = timeline["total"]
    n = int((T + 0.05) * SR)
    drums = np.zeros((n, 2))
    music = np.zeros((n, 2))
    bassb = np.zeros((n, 2))
    beat = body_dur / 4.0
    t0 = timeline["body_start"]
    k0 = -int(np.ceil(t0 / beat))
    breaks = [c - beat for c in timeline["chapter_starts"]]
    cta = timeline["cta_start"]
    kk = kick(st["kick"])
    kick_times = []

    def in_break(t):
        return any(b <= t < b + beat - 1e-3 for b in breaks)

    k = k0
    while True:
        tb = t0 + k * beat
        if tb >= T:
            break
        bar_pos = k % 4
        chord_i = (k // 4) % 4
        root, q = st["chords"][chord_i]
        hook_part = tb < t0
        brk = in_break(tb)
        # 킥
        if not brk and tb < cta + beat * 2:
            hit = {"four": True, "half": bar_pos in (0, 2), "soft": bar_pos == 0,
                   "taiko": bar_pos in (0, 2)}[st["kick"]]
            if st["kick"] == "half" and bar_pos == 2:
                _add(drums, kk, tb + beat * 0.5, 0.7)
                kick_times.append(tb + beat * 0.5)
            if hit:
                _add(drums, kk, tb, 0.95 if not hook_part else 0.75)
                kick_times.append(tb)
        # 클랩 / 하이햇
        if st["kick"] in ("four", "half") and bar_pos in (1, 3) and not brk:
            _add(drums, clap(), tb, 0.55 if st["kick"] == "four" else 0.6, 0.1)
        if st["hat"] > 0 and not hook_part:
            sw = st["swing"] * beat
            _add(drums, hat(True), tb + beat / 2 + sw, 0.5 * st["hat"], 0.3)
            for s16 in (0.25, 0.75):
                _add(drums, hat(False), tb + beat * s16, 0.35 * st["hat"], -0.3)
        # 화음 (마디 첫 박)
        if bar_pos == 0:
            notes = [root + 12 + iv for iv in INTERVALS[q]]
            dur = beat * 4
            for i, m in enumerate(notes):
                f = mtof(m)
                if st["lead"] == "saw":
                    v = saw_voice(f, dur, cutoff=2600 if hook_part else 4200) * adsr(int(dur * SR), 0.02, 0.2)
                elif st["lead"] == "ep":
                    v = ep_voice(f, dur)
                elif st["lead"] == "piano":
                    v = np.zeros(int(dur * SR))
                    for j in range(8):  # 8분 아르페지오
                        mm = notes[(j + i) % len(notes)] + (12 if j >= 4 else 0)
                        p = piano_voice(mtof(mm), beat * 1.5)
                        a = int(j * beat / 2 * SR)
                        e = min(len(v), a + len(p))
                        v[a:e] += p[: e - a] * 0.5
                    if i:
                        continue
                else:
                    v = saw_voice(f / 2, dur, detune=(-0.08, 0.08), cutoff=1400) * adsr(int(dur * SR), 0.35, 0.4)
                _add(music, v, tb, 0.22, pan=(i - 1) * 0.45)
            # 베이스
            if st["lead"] != "piano" or not hook_part:
                bf = mtof(root - 12)
                if st["kick"] == "four":
                    for j in range(4):
                        tt = tb + j * beat + beat / 2
                        if not in_break(tt):
                            _add(bassb, bass_note(bf, beat * 0.45), tt, 0.8)
                else:
                    _add(bassb, bass_note(bf, beat * 3.5), tb, 0.7)
        k += 1

    # 훅 구간은 얇게(하이패스), 본문 시작에서 드롭
    hook_n = int(t0 * SR)
    if hook_n > 0:
        thin = fft_filter(music[:hook_n] + bassb[:hook_n], lo=500)
        music[:hook_n] = thin * 0.8
        bassb[:hook_n] = 0
    # 사이드체인
    env = np.ones(n)
    tt = _t(n)
    for kt in kick_times:
        i0 = int(kt * SR)
        if 0 <= i0 < n:
            seg = tt[i0:] - kt
            seg = seg[: int(0.3 * SR)]
            env[i0:i0 + len(seg)] = np.minimum(env[i0:i0 + len(seg)], 1 - 0.6 * np.exp(-seg / 0.08))
    music *= env[:, None]
    bassb *= env[:, None]
    mix = drums * 0.9 + music * 0.75 + bassb * 0.85

    # 효과음
    used = []
    for ev in (sfx_events or [])[:6]:
        fn = SFX.get(ev["type"])
        if fn:
            s = fn()
            start = ev["t"] - (len(s) / SR if ev["type"] == "riser" else 0.05 if ev["type"] == "whoosh" else 0)
            _add(mix, s, start, ev.get("gain", 0.8), ev.get("pan", 0.0))
            used.append(ev)

    # 끝 부분 살짝 페이드(루프 이음새)
    fade = int(0.08 * SR)
    mix[-fade:] *= np.linspace(1, 0.3, fade)[:, None]
    return master(mix), used


def master(x):
    """폰 스피커 기준 마스터링: 저역 정리 + 존재감 + 소프트 리미트."""
    def curve(f):
        g = np.ones_like(f)
        g *= 1 / np.sqrt(1 + (70 / np.maximum(f, 1e-3)) ** 6)       # 70Hz 아래 차단
        g *= np.where((f > 80) & (f < 250), 0.8, 1.0)                 # 탁한 저역 감소
        g *= 1 + 0.35 * np.exp(-((np.log2(np.maximum(f, 1) / 3000)) ** 2) / 0.6)  # 3kHz 존재감
        g *= 1 + 0.2 * np.exp(-((np.log2(np.maximum(f, 1) / 10000)) ** 2) / 0.5)  # 공기감
        return g
    y = fft_filter(x, gain_curve=curve)
    peak = np.max(np.abs(y)) + 1e-9
    y = y / peak * 1.4
    y = np.tanh(y) / np.tanh(1.4) * 0.89
    return y.astype(np.float32)


def write_wav(path, x):
    import wave
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
