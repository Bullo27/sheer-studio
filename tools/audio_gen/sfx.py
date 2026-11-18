"""Procedural sound effects (44.1 kHz, 16-bit PCM WAV)."""
import os
import json
import numpy as np
from synthlib import *
from instruments import koto_note

DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'unity', 'Assets', 'Sheer', 'Resources', 'Audio', 'Sfx')
R = np.random.default_rng(2026)


def T(sec):
    return np.arange(int(sec * SR)) / SR


def finish(x, peak_db=-3.0, head_ms=0.3, tail_ms=8.0, loop=False):
    x = np.array(x, dtype=float)
    if loop:
        x = x - x.mean(axis=-1, keepdims=True)
        x = cfilt(x, 'hp', 25, 0.7)
    else:
        x = x - np.mean(x[..., -64:], axis=-1, keepdims=True) * 0
        x = filt(x, 'hp', 18, 0.6)
        x = fade_head(x, head_ms) if head_ms > 0 else x
        x = fade_tail(x, tail_ms)
    tp = true_peak(x if x.ndim == 2 else x[None, :]).max() if loop else np.abs(signal_up(x)).max()
    return x * undb(peak_db) / tp


def signal_up(x):
    from scipy import signal as sg
    return sg.resample_poly(np.pad(x, [(0, 0)] * (x.ndim - 1) + [(64, 64)]), 4, 1, axis=-1)


def periodic2(fn, n):
    """Render fn(2n) and keep the second period (filters/LFO states settled -> loop-clean)."""
    y = fn(2 * n)
    return y[..., n:]


# ----------------------------------------------------------------------------- stretch loop
def stretch_loop():
    n = int(2.0 * SR)
    base = R.standard_normal(n)
    t1 = np.arange(n) / SR

    def make(m):
        t = np.arange(m) / SR
        nz = np.tile(base, 2)
        # stick-slip creak: pulse train with periodically varying rate (integer number of pulses per loop)
        rate = 62 + 22 * np.sin(TWOPI * 1.0 * t / 2.0) + 9 * np.sin(TWOPI * 3.0 * t / 2.0 + 1.0)
        per = rate[:n].sum() / SR
        rate *= round(per) / per
        ph = np.cumsum(rate) / SR
        k = np.floor(ph)
        imp = np.zeros(m)
        idx = np.where(np.diff(k) > 0)[0] + 1
        amps = np.tile(np.random.default_rng(5).lognormal(0, 0.45, len(idx) // 2 + 1), 2)[:len(idx)]
        imp[idx] = amps
        creak = filt(imp, 'bp', 820, 9.0) * 1.0 + filt(imp, 'bp', 1650, 12.0) * 0.8 + filt(imp, 'bp', 2900, 14.0) * 0.5
        # nylon squeak: narrow resonance gliding slowly
        fc = 1150 + 260 * np.sin(TWOPI * 2.0 * t / 2.0 + 0.5) + 90 * np.sin(TWOPI * 5.0 * t / 2.0)
        sq = tv_filter(nz, 'bp', fc, 28.0, block=64) * 3.0
        sq *= 0.6 + 0.4 * np.sin(TWOPI * 3.0 * t / 2.0) ** 2
        # fabric rub hiss
        rub = filt(filt(nz, 'hp', 2500, 0.7), 'lp', 7500, 0.7) * (0.75 + 0.25 * np.sin(TWOPI * 4.0 * t / 2.0 + 2))
        return 0.9 * creak + 0.5 * sq + 0.1 * rub

    y = periodic2(make, n)
    y = cfilt(cfilt(y, 'lp', 8500, 0.7), 'lp', 11000, 0.7)
    return finish(y, -4.0, loop=True)


# ----------------------------------------------------------------------------- rip
def rip():
    t = T(0.42)
    n = len(t)
    nz = R.standard_normal(n)
    snap = filt(nz * np.exp(-t / 0.0025), 'hp', 1200, 0.7) * 1.4
    snap += filt(nz * np.exp(-t / 0.001), 'bp', 3300, 6.0) * 2.5 * 4
    rate = 2600 * np.exp(-t / 0.14) + 150
    p = rate / SR
    hit = R.random(n) < p
    hit[:int(0.006 * SR)] = False
    amp = R.lognormal(0, 0.7, n) * hit * R.choice([-1, 1], n)
    cr = filt(amp, 'bp', 2600, 0.8) + 0.5 * filt(amp, 'hp', 5000, 0.7)
    env = np.clip((t - 0.004) / 0.008, 0, 1) * np.exp(-t / 0.13)
    hiss = filt(filt(nz, 'hp', 1500, 0.7), 'lp', 7000, 0.7) * env * 0.35
    rp = cr * env * 1.1 + hiss
    y = snap / np.max(np.abs(snap)) + 0.85 * rp / np.max(np.abs(rp))
    return finish(y, -1.5, head_ms=0.15, tail_ms=40)


# ----------------------------------------------------------------------------- zip loop (ladder run)
def zip_loop():
    n = int(1.0 * SR)
    y = np.zeros(n)
    nt = 190
    times = (np.arange(nt) / nt + R.normal(0, 0.0015, nt)) % 1.0
    for i, tt in enumerate(times):
        ln = int(0.0012 * SR)
        b = R.standard_normal(ln) * np.exp(-np.arange(ln) / (0.00025 * SR))
        b = filt(b, 'bp', R.uniform(2800, 6500), 2.2)
        g = R.uniform(0.35, 1.0) * (0.75 + 0.25 * np.sin(TWOPI * 7 * tt) ** 2)
        add_wrap(y, b * g, int(tt * n))
    bed = colored_noise_circ(n, R, lambda f: np.exp(-((f - 5000) / 2500) ** 2))
    y = y / np.max(np.abs(y)) + 0.025 * bed
    return finish(y, -5.0, loop=True)


# ----------------------------------------------------------------------------- snap (elastic thwip)
def snap():
    t = T(0.16)
    f = 170 + 1300 * np.exp(-t / 0.028)
    ph = TWOPI * np.cumsum(f) / SR
    tone = (np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)) * np.exp(-t / 0.045)
    nz = R.standard_normal(len(t))
    fc = 900 + 5200 * np.exp(-t / 0.03)
    wh = tv_filter(nz, 'bp', fc, 1.5, block=32) * np.exp(-t / 0.03) * 1.5
    cl = filt(nz * np.exp(-t / 0.0007), 'hp', 2000, 0.7) * 2
    y = tone + 0.6 * wh + 0.5 * cl
    y[:20] *= np.linspace(0, 1, 20)
    return finish(y, -3.0, head_ms=0.2, tail_ms=20)


# ----------------------------------------------------------------------------- pop (bubble)
def pop():
    t = T(0.06)
    f = 330 * (3.1) ** np.clip(t / 0.035, 0, 1)
    ph = TWOPI * np.cumsum(f) / SR
    e = (1 - np.exp(-t / 0.0015)) * np.exp(-t / 0.018)
    y = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * e
    return finish(y, -6.0, head_ms=0.5, tail_ms=8)


def tick():
    t = T(0.02)
    e = (1 - np.exp(-t / 0.0003)) * np.exp(-t / 0.0025)
    y = (np.sin(TWOPI * 3100 * t) + 0.5 * np.sin(TWOPI * 1550 * t + 0.4)) * e
    y += 0.08 * filt(R.standard_normal(len(t)) * np.exp(-t / 0.0008), 'bp', 5000, 1.5)
    return finish(y, -10.0, head_ms=0.2, tail_ms=4)


def blip(f, dur):
    t = T(dur)
    e = (1 - np.exp(-t / 0.0015)) * np.exp(-t / 0.032)
    ph = TWOPI * f * t
    return (np.sin(ph + 0.6 * np.exp(-t / 0.02) * np.sin(2 * ph)) + 0.2 * np.sin(2 * ph)) * e


def toggle(up=True):
    a, b = (note('E6'), note('B6')) if up else (note('B6'), note('E6'))
    y = np.zeros(int(0.12 * SR))
    n1 = fade_tail(blip(float(mtof(a)), 0.09), 25) * 0.9
    n2 = fade_tail(blip(float(mtof(b)), 0.068), 12)
    y[:len(n1)] += n1[:len(y)]
    i0 = int(0.052 * SR)
    y[i0:i0 + len(n2)] += n2[:len(y) - i0]
    return finish(y, -8.0, head_ms=0.5, tail_ms=8)


# ----------------------------------------------------------------------------- shutter
def click_event(n, at, level, rings, thunk=None):
    t = np.arange(n) / SR
    y = np.zeros(n)
    i0 = int(at * SR)
    tt = t[: n - i0]
    nz = R.standard_normal(len(tt))
    y[i0:] += filt(nz * np.exp(-tt / 0.0009), 'hp', 1800, 0.7) * 1.2 * level
    for f, d, a in rings:
        y[i0:] += a * level * np.sin(TWOPI * f * tt + R.uniform(0, 6)) * np.exp(-tt / d)
    if thunk:
        f0, d = thunk
        ph = TWOPI * np.cumsum(f0 * (1 + 0.5 * np.exp(-tt / 0.006))) / SR
        y[i0:] += 0.9 * level * np.sin(ph) * np.exp(-tt / d)
    return y


def shutter():
    n = int(0.25 * SR)
    y = click_event(n, 0.0, 1.0, [(2350, 0.012, 0.25), (3900, 0.009, 0.18), (6100, 0.006, 0.12)], thunk=(150, 0.022))
    y += click_event(n, 0.072, 0.8, [(4600, 0.008, 0.25), (7200, 0.005, 0.15), (2900, 0.01, 0.12)])
    y += click_event(n, 0.135, 0.55, [(3300, 0.01, 0.2), (5200, 0.006, 0.12)], thunk=(120, 0.018))
    t = np.arange(n) / SR
    whir = filt(R.standard_normal(n), 'bp', 1800, 2.0) * np.exp(-((t - 0.1) / 0.04) ** 2) * 0.08
    return finish(y + whir, -2.0, head_ms=0.1, tail_ms=15)


# ----------------------------------------------------------------------------- sparkle / achievement (stereo)
def glassy(f, dur, vel, seed):
    return modal(f, dur, ratios=[1.0, 2.0, 2.76, 5.4], amps=[1.0, 0.25, 0.12, 0.05], t60s=[0.7, 0.35, 0.2, 0.08],
                 vel=vel, attack=0.0005, seed=seed, beat_cents=6, beat_amt=0.4)


def sparkle():
    n = int(0.9 * SR)
    out = np.zeros((2, n))
    run = notes('E6 G6 A6 C7 D7 E7 G7 A7')
    for i, m in enumerate(run):
        y = glassy(float(mtof(m)), 0.7, 0.8 - 0.04 * i, seed=i)
        gl, gr = pan_gains(np.sin(i * 1.7) * 0.7)
        i0 = int(i * 0.045 * SR)
        k = min(len(y), n - i0)
        out[0, i0:i0 + k] += y[:k] * gl
        out[1, i0:i0 + k] += y[:k] * gr
    for j in range(45):
        tt = R.uniform(0.0, 0.6) ** 1.3
        f = R.uniform(5500, 11000)
        ln = int(0.05 * SR)
        tp = np.arange(ln) / SR
        p = np.sin(TWOPI * f * tp) * np.exp(-tp / 0.012) * R.uniform(0.05, 0.18)
        gl, gr = pan_gains(R.uniform(-0.9, 0.9))
        i0 = int(tt * SR)
        k = min(ln, n - i0)
        out[0, i0:i0 + k] += p[:k] * gl
        out[1, i0:i0 + k] += p[:k] * gr
    ir = make_ir(t60=0.9, predelay=0.01, hf=1.0, seed=3, length=0.9)
    wet = np.vstack([np.convolve(0.7 * out[c] + 0.3 * out[1 - c], ir[c])[:n] for c in range(2)])
    y = out + 0.35 * wet
    t = np.arange(n) / SR
    y *= np.clip((0.9 - t) / 0.25, 0, 1) ** 1.5
    return finish(y, -5.0, head_ms=0.3, tail_ms=20)


def marimba(f, vel, seed):
    return modal(f, 1.1, ratios=[1.0, 3.93, 9.2], amps=[1.0, 0.22, 0.06], t60s=[0.9, 0.18, 0.06], vel=vel,
                 attack=0.0012, seed=seed, click=0.08, click_fc=2500)


def achievement():
    n = int(1.2 * SR)
    out = np.zeros((2, n))

    def put(y, at, pan):
        gl, gr = pan_gains(pan)
        i0 = int(at * SR)
        k = min(len(y), n - i0)
        out[0, i0:i0 + k] += y[:k] * gl
        out[1, i0:i0 + k] += y[:k] * gr

    seq = [('G5', 0.0), ('C6', 0.085), ('E6', 0.17), ('G6', 0.255)]
    for i, (nm, at) in enumerate(seq):
        f = float(mtof(note(nm)))
        put(marimba(f, 0.8, i), at, -0.3 + 0.2 * i)
        put(fm_bell(2 * f, 0.6, 0.35, ratio=4.0, index=1.2, t60=0.5, seed=i), at, 0.3 - 0.2 * i)
    for j, nm in enumerate(['C6', 'E6', 'G6', 'C7']):
        f = float(mtof(note(nm)))
        put(marimba(f, 0.7, 10 + j), 0.40 + 0.012 * j, -0.4 + 0.27 * j)
        put(glassy(2 * f, 0.8, 0.3, 20 + j), 0.40 + 0.012 * j, 0.4 - 0.27 * j)
    ir = make_ir(t60=1.0, predelay=0.012, hf=0.9, seed=4, length=1.0)
    wet = np.vstack([np.convolve(0.7 * out[c] + 0.3 * out[1 - c], ir[c])[:n] for c in range(2)])
    y = out + 0.3 * wet
    t = np.arange(n) / SR
    y *= np.clip((1.2 - t) / 0.3, 0, 1) ** 1.5
    return finish(y, -3.0, head_ms=0.3, tail_ms=20)


# ----------------------------------------------------------------------------- boing / squeak / whoosh
def boing():
    t = T(0.42)
    f0 = 185 * 2 ** (0.55 * (1 - np.exp(-t / 0.12)))
    wob = 0.32 * np.exp(-t / 0.13) * np.sin(TWOPI * 15.5 * t)
    f = f0 * 2 ** wob
    ph = TWOPI * np.cumsum(f) / SR
    y = np.sin(ph) + 0.45 * np.sin(2 * ph) + 0.22 * np.sin(3 * ph) + 0.1 * np.sin(4 * ph)
    fc = 900 * 2 ** (wob * 2.0)
    y = tv_filter(y, 'bp', fc, 1.2, block=32) * 1.5 + 0.5 * y
    e = (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.16)
    return finish(y * e, -3.0, head_ms=0.5, tail_ms=25)


def squeak():
    t = T(0.3)
    f = 1550 + 900 * np.clip(t / 0.12, 0, 1) ** 0.7 - 320 * np.clip((t - 0.17) / 0.12, 0, 1)
    f = f * (1 + 0.012 * np.sin(TWOPI * 38 * t))
    src = osc_pulse(f, len(t), 0.33)
    y = tv_filter(src, 'bp', f * 1.02, 3.0, block=32) * 2.0 + 0.25 * src
    am = 0.78 + 0.22 * np.sin(TWOPI * 46 * t) ** 2
    air = filt(R.standard_normal(len(t)), 'bp', 3200, 1.2) * 0.12
    e = np.clip(t / 0.02, 0, 1) * np.clip((0.3 - t) / 0.07, 0, 1)
    y = (y * am + air) * e
    y = filt(filt(y, 'lp', 5000, 0.7), 'lp', 6500, 0.7)
    return finish(y, -9.0, head_ms=0.5, tail_ms=15)


def whoosh():
    t = T(1.5)
    n = len(t)
    nz = R.standard_normal(n)
    x = np.clip(t / 1.5, 0, 1)
    fc = 260 * (1800 / 260) ** np.sin(np.pi * np.clip(t / 1.3, 0, 1)) ** 1.5
    y = tv_filter(nz, 'bp', fc, 0.9, block=64) + 0.3 * tv_filter(nz, 'bp', fc * 2.3, 1.2, block=64)
    flutter = 1 + 0.15 * lp1(R.standard_normal(n), 6.0) * 30
    env = (np.sin(np.pi * np.clip(t / 1.45, 0, 1)) ** 2) * np.exp(-((t - 0.6) / 0.9) ** 2)
    y = filt(y * env * flutter, 'lp', 4500, 0.7)
    return finish(y, -3.0, head_ms=2, tail_ms=60)


SFX = {'stretch_loop': stretch_loop, 'rip': rip, 'zip_loop': zip_loop, 'snap': snap, 'pop': pop, 'tick': tick,
       'toggle_on': lambda: toggle(True), 'toggle_off': lambda: toggle(False), 'shutter': shutter,
       'sparkle': sparkle, 'achievement': achievement, 'boing': boing, 'squeak': squeak, 'whoosh': whoosh}

if __name__ == '__main__':
    os.makedirs(DEST, exist_ok=True)
    rep = {}
    for name, fn in SFX.items():
        y = fn()
        write_wav(os.path.join(DEST, name + '.wav'), y, bits=16)
        x = y if y.ndim == 2 else y[None, :]
        tp = float(db(np.abs(signal_up(x)).max()))
        info = dict(dur=round(x.shape[1] / SR, 3), ch=x.shape[0], peak=round(float(db(np.abs(x).max())), 2),
                    tp=round(tp, 2), dc=float(np.abs(x.mean(axis=1)).max()), lufs=round(lufs(x), 1))
        if name.endswith('_loop'):
            info['loop'] = {k: round(v, 4) for k, v in loop_report(x).items()}
        rep[name] = info
        print(name, info)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out', 'sfx_report.json'), 'w') as fh:
        json.dump(rep, fh, indent=1)
