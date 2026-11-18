"""
synthlib.py - small procedural synthesis toolkit (numpy/scipy only).

Everything is rendered offline.  Music tracks are built on a *circular* timeline of
exactly L samples: every voice is added with wrap-around, and every post effect is
applied circularly (FFT convolution of length L, IIR filters warmed up on the wrapped
signal, periodic LFOs with an integer number of cycles per loop).  The result is a
perfectly periodic signal, i.e. a seamless loop with all decay/reverb tails folded
back onto the start.
"""
import numpy as np
from scipy import signal
from scipy import fft as sfft
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from scipy.io import wavfile

SR = 44100
TWOPI = 2.0 * np.pi
FFT_WORKERS = 4

# ----------------------------------------------------------------------------- notes
_NI = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def note(name):
    """'C#4' -> MIDI number (C4 = 60). Ints pass through."""
    if not isinstance(name, str):
        return int(name)
    s = name.strip()
    k = _NI[s[0].upper()]
    i = 1
    while i < len(s) and s[i] in '#b':
        k += 1 if s[i] == '#' else -1
        i += 1
    return 12 * (int(s[i:]) + 1) + k


def notes(s):
    return [note(x) for x in s.split()]


def mtof(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


def db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def undb(d):
    return 10.0 ** (np.asarray(d) / 20.0)


def pan_gains(p):
    th = (np.clip(p, -1.0, 1.0) + 1.0) * np.pi / 4.0
    return np.cos(th), np.sin(th)


# ----------------------------------------------------------------------------- oscillators
def phase_cycles(freq, n, phase0=0.0):
    """Unwrapped phase in cycles; phase[0] == phase0."""
    if np.ndim(freq) == 0:
        return phase0 + np.arange(n) * (float(freq) / SR)
    f = np.asarray(freq, dtype=float)[:n]
    ph = np.empty(n)
    ph[0] = 0.0
    np.cumsum(f[:-1] * (1.0 / SR), out=ph[1:])
    return ph + phase0


def _blep(t, dt):
    out = np.zeros_like(t)
    vec = np.ndim(dt) > 0
    m = t < dt
    x = t[m] / (dt[m] if vec else dt)
    out[m] = 2.0 * x - x * x - 1.0
    m2 = t > 1.0 - dt
    x = (t[m2] - 1.0) / (dt[m2] if vec else dt)
    out[m2] = x * x + 2.0 * x + 1.0
    return out


def osc_saw(freq, n, phase0=0.0):
    ph = phase_cycles(freq, n, phase0)
    t = ph - np.floor(ph)
    dt = np.abs(np.asarray(freq, dtype=float))[:n] / SR if np.ndim(freq) else abs(freq) / SR
    return 2.0 * t - 1.0 - _blep(t, dt)


def osc_pulse(freq, n, duty=0.5, phase0=0.0):
    ph = phase_cycles(freq, n, phase0)
    t = ph - np.floor(ph)
    dt = np.abs(np.asarray(freq, dtype=float))[:n] / SR if np.ndim(freq) else abs(freq) / SR
    duty = np.asarray(duty, dtype=float)
    if duty.ndim:
        duty = duty[:n]
    y = np.where(t < duty, 1.0, -1.0)
    y += _blep(t, dt)
    t2 = t - duty
    t2 -= np.floor(t2)
    y -= _blep(t2, dt)
    return y - (2.0 * duty - 1.0)


def osc_tri(freq, n, phase0=0.0):
    ph = phase_cycles(freq, n, phase0 + 0.25)
    t = ph - np.floor(ph)
    return 4.0 * np.abs(t - 0.5) - 1.0


def osc_sine(freq, n, phase0=0.0):
    return np.sin(TWOPI * phase_cycles(freq, n, phase0))


SS_DET = np.array([-1.0, -0.64, -0.29, 0.0, 0.27, 0.61, 0.97])
SS_PAN = np.array([-0.85, 0.6, -0.35, 0.0, 0.38, -0.62, 0.82])


def supersaw(freq, n, detune_cents=20.0, center=0.55, width=1.0, rng=None):
    """7 detuned band-limited saws, stereo spread. freq may be scalar or array."""
    rng = rng or np.random.default_rng(0)
    out = np.zeros((2, n))
    f = np.asarray(freq, dtype=float)
    for k in range(7):
        fk = f * 2.0 ** (SS_DET[k] * detune_cents / 1200.0)
        s = osc_saw(fk, n, rng.random())
        amp = center if k == 3 else 1.0
        gl, gr = pan_gains(SS_PAN[k] * width)
        out[0] += s * amp * gl
        out[1] += s * amp * gr
    return out / 4.0


# ----------------------------------------------------------------------------- envelopes
def env_adsr(dur, a=0.005, d=0.2, s=0.7, r=0.2, n_total=None):
    """Gate of length dur (s) followed by release r. Exponential decay/release."""
    n_on = max(int(round(dur * SR)), 2)
    n_r = max(int(round(r * SR)), 2)
    na = max(int(round(a * SR)), 1)
    e = np.empty(n_on)
    k = min(na, n_on)
    e[:k] = np.arange(k) / na
    if n_on > k:
        td = np.arange(n_on - k) / SR
        tau = max(d, 1e-4) / 4.6
        e[k:] = s + (e[k - 1] - s) * np.exp(-td / tau) if k > 0 else s
    last = e[-1]
    tr = np.arange(n_r) / SR
    rel = last * np.exp(-tr * 6.9 / max(r, 1e-3)) * (1.0 - np.arange(n_r) / n_r)
    out = np.concatenate([e, rel])
    if n_total is not None:
        if len(out) < n_total:
            out = np.concatenate([out, np.zeros(n_total - len(out))])
        else:
            out = out[:n_total]
    return out


def env_perc(n, attack=0.001, decay=0.3, curve_t60=True):
    """attack (s) then exponential decay; decay = T60 if curve_t60 else time-constant."""
    t = np.arange(n) / SR
    tau = decay / 6.9 if curve_t60 else decay
    e = np.exp(-t / tau)
    na = max(int(attack * SR), 1)
    e[:na] *= np.linspace(0.0, 1.0, na, endpoint=False) ** 0.7 if na > 1 else 1.0
    return e


def fade_tail(x, ms=5.0):
    n = min(len(x) if x.ndim == 1 else x.shape[-1], max(int(ms * 1e-3 * SR), 2))
    w = np.linspace(1.0, 0.0, n) ** 1.5
    if x.ndim == 1:
        x[-n:] *= w
    else:
        x[..., -n:] *= w
    return x


def fade_head(x, ms=2.0):
    n = max(int(ms * 1e-3 * SR), 2)
    w = np.linspace(0.0, 1.0, n)
    if x.ndim == 1:
        x[:n] *= w
    else:
        x[..., :n] *= w
    return x


# ----------------------------------------------------------------------------- filters
def rbj(kind, f0, Q=0.7071, gain_db=0.0):
    f0 = float(np.clip(f0, 5.0, SR * 0.49))
    w0 = TWOPI * f0 / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * Q)
    A = 10.0 ** (gain_db / 40.0)
    if kind == 'lp':
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == 'hp':
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == 'bp':
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == 'notch':
        b = [1.0, -2 * cw, 1.0]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == 'peak':
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == 'ls':
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == 'hs':
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return b, a


def filt(x, kind, f0, Q=0.7071, gain_db=0.0):
    b, a = rbj(kind, f0, Q, gain_db)
    return signal.lfilter(b, a, x, axis=-1)


def circ_lfilter(b, a, x, warm=None):
    L = x.shape[-1]
    if warm is None:
        warm = min(L, 2 * SR)
    xx = np.concatenate([x[..., L - warm:], x], axis=-1)
    return signal.lfilter(b, a, xx, axis=-1)[..., warm:]


def cfilt(x, kind, f0, Q=0.7071, gain_db=0.0, warm=None):
    b, a = rbj(kind, f0, Q, gain_db)
    return circ_lfilter(b, a, x, warm)


def lp1(x, fc):
    a = np.exp(-TWOPI * fc / SR)
    return signal.lfilter([1 - a], [1, -a], x, axis=-1)


def tv_filter(x, kind, f0, Q=0.7071, block=32):
    """Time-varying RBJ biquad (DF1-consistent state carry). f0: array len(x) or scalar."""
    n = x.shape[-1]
    f0 = np.broadcast_to(np.asarray(f0, dtype=float), (n,))
    y = np.empty_like(x)
    xp = np.zeros(2)
    yp = np.zeros(2)
    for i in range(0, n, block):
        j = min(n, i + block)
        b, a = rbj(kind, f0[i], Q)
        zi = signal.lfiltic(b, a, yp, xp)
        yb, _ = signal.lfilter(b, a, x[i:j], zi=zi)
        y[i:j] = yb
        if j - i >= 2:
            xp = np.array([x[j - 1], x[j - 2]])
            yp = np.array([yb[-1], yb[-2]])
        else:
            xp = np.array([x[j - 1], xp[0]])
            yp = np.array([yb[-1], yp[0]])
    return y


def tv_lp4(x, f0, Q1=0.54, Q2=1.31, block=32):
    """24 dB/oct time-varying low-pass (two cascaded biquads, Butterworth Qs by default)."""
    return tv_filter(tv_filter(x, 'lp', f0, Q1, block), 'lp', f0, Q2, block)


def butter_sos(kind, fc, order=4):
    return signal.butter(order, fc, btype=kind, fs=SR, output='sos')


# ----------------------------------------------------------------------------- noise
def colored_noise_circ(n, rng, shape_fn):
    """Periodic (circular) noise of length n with magnitude response shape_fn(freqs)."""
    w = rng.standard_normal(n)
    W = sfft.rfft(w, workers=FFT_WORKERS)
    f = sfft.rfftfreq(n, 1.0 / SR)
    W *= shape_fn(f)
    y = sfft.irfft(W, n, workers=FFT_WORKERS)
    return y / (np.std(y) + 1e-12)


def interp_cubic(x, pos, circular=False):
    i = np.floor(pos).astype(np.int64)
    f = pos - i
    n = len(x)
    if circular:
        g = lambda k: x[(i + k) % n]
    else:
        g = lambda k: x[np.clip(i + k, 0, n - 1)]
    xm1, x0, x1, x2 = g(-1), g(0), g(1), g(2)
    c1 = 0.5 * (x1 - xm1)
    c2 = xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
    c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
    return ((c3 * f + c2) * f + c1) * f + x0


def pitch_bend(y, ratio):
    """Re-read y at a time-varying rate (ratio array, 1 = unchanged) -> pitch bend."""
    pos = np.concatenate([[0.0], np.cumsum(ratio[:-1])])
    pos = pos[pos < len(y) - 2]
    return interp_cubic(y, pos)


# ----------------------------------------------------------------------------- physical / FM voices
def ks_pluck(f, dur, t60=2.0, S=0.3, pick=0.15, bright=6000.0, seed=0, attack_click=0.0, excite_len=1.0):
    """Karplus-Strong string: allpass-tuned delay loop with 2-tap loss filter.
    S: loss filter coefficient (0 = brightest, 0.5 = classic average)."""
    rng = np.random.default_rng(seed)
    P = SR / f
    N = int(np.floor(P - S - 0.1))
    d = P - S - N
    C = (1.0 - d) / (1.0 + d)
    g = 10.0 ** (-3.0 / (f * t60))
    a = np.zeros(N + 3)
    a[0] = 1.0
    a[1] += C
    a[N] += -g * (1.0 - S) * C
    a[N + 1] += -g * ((1.0 - S) + S * C)
    a[N + 2] += -g * S
    b = np.array([1.0, C])
    n = int(dur * SR)
    Lx = max(int(P * excite_len), 4)
    ex = rng.uniform(-1.0, 1.0, Lx)
    ex = signal.lfilter(*rbj('lp', min(bright, SR * 0.45), 0.6), ex)
    ex -= ex.mean()
    ex *= np.hanning(Lx * 2)[Lx // 2: Lx // 2 + Lx] ** 0.3 if Lx > 8 else 1.0
    x = np.zeros(n)
    x[:Lx] = ex
    if attack_click > 0:
        kc = max(int(0.0006 * SR), 3)
        x[:kc] += attack_click * np.hanning(kc) * np.sign(rng.standard_normal())
    k = max(1, int(round(pick * P)))
    x[k:] = x[k:] - x[:-k]
    y = signal.lfilter(b, a, x)
    pk = np.max(np.abs(y[: min(n, int(0.08 * SR))])) + 1e-9
    return y / pk


def fm_epiano(f, dur, vel=0.8, rel=0.3, bright=1.0, seed=0, bark=0.18):
    """Rhodes-like FM electric piano (two carrier/modulator pairs + pickup nonlinearity)."""
    rng = np.random.default_rng(seed)
    n_on = max(int(dur * SR), 16)
    nr = max(int(rel * SR), 16)
    N = n_on + nr
    t = np.arange(N) / SR
    T60 = float(np.clip(11.0 * (110.0 / f) ** 0.5, 2.0, 14.0))
    amp = np.exp(-6.9 * t / T60)
    na = int(0.0012 * SR)
    amp[:na] *= np.linspace(0, 1, na)
    tr = np.arange(nr) / SR
    amp[n_on:] *= np.exp(-6.9 * tr / rel) * np.linspace(1, 0, nr)
    ph = TWOPI * f * t + rng.uniform(0, TWOPI)
    I1 = bright * (0.25 + 1.9 * vel ** 1.6) * np.exp(-t / 0.22) + 0.22 + 0.25 * vel * bright
    body = np.sin(ph + I1 * np.sin(ph))
    tine_scale = float(np.clip((6500.0 - 14 * f) / 3000.0, 0.0, 1.0))
    I2 = bright * (0.3 + 1.6 * vel) * np.exp(-t / 0.018) * tine_scale
    ph2 = TWOPI * f * 1.0007 * t + rng.uniform(0, TWOPI)
    tine = np.sin(ph2 + I2 * np.sin(14.0 * ph2)) * np.exp(-t / 0.9)
    y = body + 0.32 * tine
    y = y + bark * vel * y * y
    return y * amp * (0.35 + 0.65 * vel)


def fm_bell(f, dur, vel=0.8, ratio=4.0, index=2.2, t60=1.2, seed=0, ting=0.25):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    aliasguard = float(np.clip((15000.0 - f * ratio * 2.5) / 6000.0, 0.05, 1.0))
    I = index * vel * np.exp(-t / 0.12) * aliasguard + 0.15
    ph = TWOPI * f * t + rng.uniform(0, TWOPI)
    y = np.sin(ph + I * np.sin(ratio * ph))
    y += ting * np.sin(2.0 * ph * 1.0012) * np.exp(-t / 0.08)
    e = np.exp(-6.9 * t / t60)
    na = int(0.0008 * SR)
    e[:na] *= np.linspace(0, 1, na)
    return fade_tail(y * e * vel, 10)


def modal(f, dur, ratios, amps, t60s, vel=0.8, attack=0.0005, seed=0, detune_cents=0.0, click=0.0,
          click_fc=5000.0, beat_cents=0.0, beat_amt=0.0):
    """Sum of decaying sinusoids (bars, tines, bells, glass). Partials above 0.45*SR dropped."""
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    y = np.zeros(N)
    f = f * 2 ** (detune_cents / 1200.0)
    for r, a, T in zip(ratios, amps, t60s):
        fr = f * r
        if fr > 0.45 * SR:
            continue
        y += a * np.sin(TWOPI * fr * t + rng.uniform(0, TWOPI)) * np.exp(-6.9 * t / T)
        if beat_amt > 0:
            fb = fr * 2 ** (beat_cents / 1200.0)
            y += beat_amt * a * np.sin(TWOPI * fb * t + rng.uniform(0, TWOPI)) * np.exp(-6.9 * t / T)
    na = max(int(attack * SR), 2)
    y[:na] *= np.linspace(0, 1, na)
    if click > 0:
        nc = int(0.004 * SR)
        c = rng.standard_normal(nc) * np.exp(-np.arange(nc) / (0.0007 * SR))
        c = signal.lfilter(*rbj('bp', click_fc, 1.2), c)
        y[:nc] += click * c * 3.0
    return fade_tail(y * vel, 8)


# ----------------------------------------------------------------------------- voice (formants)
FORMANTS = {
    'a': [(800, 80, 0), (1150, 90, -5), (2900, 120, -16), (3900, 130, -20), (4950, 140, -34)],
    'e': [(350, 60, 0), (2000, 100, -10), (2800, 120, -11), (3600, 150, -24), (4950, 200, -38)],
    'i': [(270, 60, 0), (2140, 90, -9), (2950, 100, -14), (3900, 120, -20), (4950, 120, -32)],
    'o': [(450, 70, 0), (800, 80, -9), (2830, 100, -20), (3800, 130, -22), (4950, 135, -38)],
    'u': [(325, 50, 0), (700, 60, -14), (2700, 170, -26), (3800, 180, -30), (4950, 200, -42)],
}


def formant_bank(src, vowel, shift=1.0):
    y = np.zeros_like(src)
    for F, BW, gdb in FORMANTS[vowel]:
        Fs = F * shift
        if Fs > 0.45 * SR:
            continue
        b, a = rbj('bp', Fs, Fs / (BW * shift ** 0.5))
        y += undb(gdb) * signal.lfilter(b, a, src)
    return y


# ----------------------------------------------------------------------------- drums
def drum_kick(dur=0.6, f_end=48.0, f_start=170.0, tau_p=0.028, t60=0.45, click=0.25, drive=1.6, seed=0,
              click_fc=3500.0):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    f = f_end + (f_start - f_end) * np.exp(-t / tau_p)
    ph = TWOPI * np.cumsum(f) / SR
    body = np.sin(ph)
    e = np.exp(-6.9 * t / t60) * (1.0 + 0.6 * np.exp(-t / 0.012))
    na = int(0.0006 * SR)
    e[:na] *= np.linspace(0, 1, na)
    y = body * e / 1.6
    nc = int(0.012 * SR)
    c = rng.standard_normal(nc) * np.exp(-np.arange(nc) / (0.0015 * SR))
    c = signal.lfilter(*rbj('bp', click_fc, 0.8), c)
    y[:nc] += click * c
    y = np.tanh(drive * y) / np.tanh(drive)
    return fade_tail(y, 20)


def drum_snare(dur=0.4, tone_f=190.0, tone_amt=0.55, tone_t60=0.12, noise_t60=0.22, n_lo=1200.0, n_hi=9000.0,
               seed=0, drive=1.2, snap=0.4):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    f = tone_f * (1.0 + 0.35 * np.exp(-t / 0.01))
    ph = TWOPI * np.cumsum(f) / SR
    tone = (np.sin(ph) + 0.45 * np.sin(1.58 * ph + 0.7)) * np.exp(-6.9 * t / tone_t60)
    nz = rng.standard_normal(N)
    nz = signal.sosfilt(butter_sos('band', [n_lo, n_hi], 2), nz)
    ne = np.exp(-6.9 * t / noise_t60) * (1 + snap * np.exp(-t / 0.006))
    y = tone_amt * tone + nz * ne * 1.4
    na = int(0.0005 * SR)
    y[:na] *= np.linspace(0, 1, na)
    y = np.tanh(drive * y) / np.tanh(drive)
    return fade_tail(y / (np.max(np.abs(y)) + 1e-9), 20)


def drum_clap(dur=0.45, fc=1300.0, Q=1.1, tail_t60=0.3, seed=0, n_bursts=4, spacing=0.0085):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    e = np.zeros(N)
    for k in range(n_bursts):
        t0 = k * spacing * (1 + 0.15 * rng.standard_normal())
        m = t >= t0
        e[m] += (0.75 + 0.25 * rng.random()) * np.exp(-(t[m] - t0) / 0.0035)
    t0 = n_bursts * spacing
    m = t >= t0 - spacing
    e[m] += 0.55 * np.exp(-6.9 * (t[m] - (t0 - spacing)) / tail_t60)
    nz = rng.standard_normal(N)
    y = signal.lfilter(*rbj('bp', fc, Q), nz) + 0.35 * signal.lfilter(*rbj('hp', 2500, 0.7), nz)
    y *= e
    return fade_tail(y / (np.max(np.abs(y)) + 1e-9), 20)


HAT_FREQS = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def drum_hat(dur=0.08, t60=0.06, metal=0.6, fc=9000.0, seed=0, hp=6500.0, open_=False):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    m = np.zeros(N)
    for fr in HAT_FREQS * 1.45:
        m += osc_pulse(fr * (1 + 0.003 * rng.standard_normal()), N, 0.5, rng.random())
    nz = rng.standard_normal(N)
    y = metal * m / 3.0 + (1 - metal) * nz
    y = signal.lfilter(*rbj('bp', fc, 0.9), y)
    y = signal.lfilter(*rbj('hp', hp, 0.7), y)
    e = np.exp(-6.9 * t / t60)
    na = int(0.0004 * SR)
    e[:na] *= np.linspace(0, 1, na)
    y *= e
    return fade_tail(y / (np.max(np.abs(y)) + 1e-9), 6)


def drum_rim(dur=0.08, seed=0, fc=1750.0, tone=820.0):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    nz = rng.standard_normal(N) * np.exp(-t / 0.004)
    y = signal.lfilter(*rbj('bp', fc, 3.5), nz) * 2.5
    y += 0.6 * np.sin(TWOPI * tone * t) * np.exp(-t / 0.012)
    y += 0.3 * np.sin(TWOPI * tone * 2.13 * t) * np.exp(-t / 0.006)
    na = int(0.0003 * SR)
    y[:na] *= np.linspace(0, 1, na)
    return fade_tail(y / (np.max(np.abs(y)) + 1e-9), 10)


def drum_shaker(dur=0.12, seed=0, fc=6500.0):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    nz = rng.standard_normal(N)
    y = signal.lfilter(*rbj('bp', fc, 1.4), nz)
    e = (1 - np.exp(-t / 0.006)) * np.exp(-t / 0.035)
    return fade_tail(y * e / (np.max(np.abs(y * e)) + 1e-9), 10)


def drum_crash(dur=2.5, t60=2.2, seed=0):
    rng = np.random.default_rng(seed)
    N = int(dur * SR)
    t = np.arange(N) / SR
    m = np.zeros(N)
    for fr in HAT_FREQS * 2.7:
        m += osc_pulse(fr * (1 + 0.01 * rng.standard_normal()), N, 0.5, rng.random())
    nz = rng.standard_normal(N)
    y = 0.35 * m / 3 + nz
    y = signal.sosfilt(butter_sos('high', 3800, 2), y)
    y = signal.lfilter(*rbj('peak', 7000, 0.7, 4.0), y)
    e = np.exp(-6.9 * t / t60) * (1 + 1.5 * np.exp(-t / 0.03))
    na = int(0.001 * SR)
    e[:na] *= np.linspace(0, 1, na)
    return fade_tail(y * e / (np.max(np.abs(y * e)) + 1e-9), 40)


# ----------------------------------------------------------------------------- bus (circular timeline)
class Bus:
    def __init__(self, L):
        self.L = int(L)
        self.buf = np.zeros((2, self.L))

    def add(self, sig, start, pan=0.0, gain=1.0):
        L = self.L
        if sig.ndim == 1:
            gl, gr = pan_gains(pan)
            s = np.vstack([sig * (gl * gain), sig * (gr * gain)])
        else:
            if pan != 0.0:
                gl, gr = pan_gains(pan)
                s = np.vstack([sig[0] * gl * 1.4142, sig[1] * gr * 1.4142]) * gain
            else:
                s = sig * gain
        n = s.shape[1]
        start = int(round(start)) % L
        pos = 0
        while pos < n:
            i0 = (start + pos) % L
            m = min(n - pos, L - i0)
            self.buf[:, i0:i0 + m] += s[:, pos:pos + m]
            pos += m


def add_wrap(buf, sig, start):
    """Add mono/stereo sig into circular buffer buf (1-D or (2, L))."""
    L = buf.shape[-1]
    n = sig.shape[-1]
    start = int(round(start)) % L
    pos = 0
    while pos < n:
        i0 = (start + pos) % L
        m = min(n - pos, L - i0)
        buf[..., i0:i0 + m] += sig[..., pos:pos + m]
        pos += m


# ----------------------------------------------------------------------------- effects (circular)
def _smooth_mask(f, fc, sharp=3.0):
    return 0.5 * (1 + np.tanh(np.log2(np.maximum(f, 1.0) / fc) * sharp))


def make_ir(t60=1.8, predelay=0.012, hf=1.0, er=0.25, seed=0, length=None, lowcut=120.0, density_ms=4.0):
    """Synthetic stereo reverb impulse response with frequency dependent decay."""
    rng = np.random.default_rng(seed)
    n = int((length or max(t60 * 1.25, 0.25)) * SR)
    t = np.arange(n) / SR
    xo = [250.0, 700.0, 1800.0, 4000.0, 8000.0]
    facs = np.array([1.2, 1.08, 1.0, 0.82, 0.62, 0.45])
    facs[3:] = facs[3:] * hf
    freqs = sfft.rfftfreq(n, 1.0 / SR)
    steps = [np.ones_like(freqs)] + [_smooth_mask(freqs, c) for c in xo] + [np.zeros_like(freqs)]
    ir = np.zeros((2, n))
    for ch in range(2):
        W = sfft.rfft(rng.standard_normal(n), workers=FFT_WORKERS)
        out = np.zeros(n)
        for i in range(len(facs)):
            mask = steps[i] - steps[i + 1]
            band = sfft.irfft(W * mask, n, workers=FFT_WORKERS)
            out += band * np.exp(-6.9 * t / (t60 * facs[i]))
        out *= 1.0 - np.exp(-t / (density_ms * 1e-3))
        # early reflections
        for k in range(10):
            tk = rng.uniform(0.004, 0.06)
            i0 = int(tk * SR)
            if i0 < n:
                out[i0] += er * rng.choice([-1, 1]) * (1.0 - tk / 0.07) * 6.0 / np.sqrt(n / SR * 50)
        out = signal.lfilter(*rbj('hp', lowcut, 0.6), out)
        pd = int(predelay * SR)
        out = np.concatenate([np.zeros(pd), out])[:n]
        ir[ch] = out / np.sqrt(np.sum(out ** 2))
    return ir


def conv_circ(x, h):
    """Circular convolution of (2, L) or (L,) signal x with (2, M) / (M,) kernel h."""
    L = x.shape[-1]
    X = sfft.rfft(x, L, axis=-1, workers=FFT_WORKERS)
    H = sfft.rfft(h, L, axis=-1, workers=FFT_WORKERS)
    return sfft.irfft(X * H, L, axis=-1, workers=FFT_WORKERS)


def reverb(x, ir, cross=0.3):
    """Stereo (2, L) -> wet stereo (2, L), circular."""
    inL = (1 - cross) * x[0] + cross * x[1]
    inR = cross * x[0] + (1 - cross) * x[1]
    return conv_circ(np.vstack([inL, inR]), ir)


def loop_freq(f, L):
    """Closest frequency with an integer number of cycles over L samples."""
    cyc = max(1, int(round(f * L / SR)))
    return cyc * SR / L


def mod_delay(x, d_samples):
    """Circular fractional delay: y[n] = x[n - d[n]] (cubic)."""
    L = len(x)
    pos = np.arange(L) - d_samples
    return interp_cubic(x, pos, circular=True)


def chorus(x, base_ms=11.0, depth_ms=2.2, rate=0.7, mix=0.45, seed=0):
    """Stereo chorus (input (2,L) or (L,)), circular, loop-periodic LFOs."""
    rng = np.random.default_rng(seed)
    if x.ndim == 1:
        x = np.vstack([x, x])
    L = x.shape[1]
    r = loop_freq(rate, L)
    t = np.arange(L) / SR
    out = np.empty_like(x)
    for ch in range(2):
        ph = rng.uniform(0, TWOPI) + ch * np.pi * 0.5
        d = (base_ms + depth_ms * np.sin(TWOPI * r * t + ph)) * 1e-3 * SR
        out[ch] = (1 - mix) * x[ch] + mix * mod_delay(x[ch], d)
    return out


def wow_flutter(x, wow_ms=1.0, wow_hz=0.5, flut_ms=0.06, flut_hz=6.5, seed=0):
    rng = np.random.default_rng(seed)
    L = x.shape[-1]
    t = np.arange(L) / SR
    w1, w2, fl = loop_freq(wow_hz, L), loop_freq(wow_hz * 1.73, L), loop_freq(flut_hz, L)
    d = (wow_ms * (0.7 * np.sin(TWOPI * w1 * t + rng.uniform(0, 6)) + 0.3 * np.sin(TWOPI * w2 * t + rng.uniform(0, 6)))
         + flut_ms * np.sin(TWOPI * fl * t + rng.uniform(0, 6))) * 1e-3 * SR
    d = d - d.min() + 2.0
    if x.ndim == 1:
        return mod_delay(x, d)
    return np.vstack([mod_delay(x[c], d) for c in range(x.shape[0])])


def delay_taps(x, delay_samples, fb=0.4, taps=5, lp=5000.0, pingpong=True):
    """Circular multi-tap feedback-style delay. x mono (L,) -> stereo wet (2, L)."""
    L = len(x)
    out = np.zeros((2, L))
    tap = x.copy()
    b, a = rbj('lp', lp, 0.6)
    for k in range(1, taps + 1):
        tap = circ_lfilter(b, a, tap, warm=min(L, 8192))
        g = fb ** (k - 1)
        if pingpong:
            ch = (k - 1) % 2
            out[ch] += g * np.roll(tap, k * delay_samples)
        else:
            out += g * np.roll(tap, k * delay_samples)
    return out


def sidechain_env(L, times, depth=0.7, release=0.28, shape=2.2, smooth_ms=4.0):
    g = np.ones(L)
    nr = int(release * SR)
    curve = 1.0 - depth * (1.0 - np.arange(nr) / nr) ** shape
    for t0 in times:
        idx = (int(round(t0)) + np.arange(nr)) % L
        g[idx] = np.minimum(g[idx], curve)
    k = max(int(smooth_ms * 1e-3 * SR), 1)
    gg = np.concatenate([g[-k:], g, g[:k]])
    gg = uniform_filter1d(gg, k)
    return gg[k:k + L]


def saturate(x, drive=1.5, asym=0.0):
    return np.tanh(drive * (x + asym)) / np.tanh(drive) - np.tanh(drive * asym) / np.tanh(drive)


def bitcrush(x, bits=12, hold=1):
    q = 2.0 ** (bits - 1)
    y = np.round(x * q) / q
    if hold > 1:
        L = y.shape[-1]
        idx = (np.arange(L) // hold) * hold
        y = y[..., idx]
    return y


# ----------------------------------------------------------------------------- dynamics / metering
def compressor(x, thresh_db=-18.0, ratio=2.0, attack=0.012, release=0.18, knee=6.0, rms_ms=8.0, blk=32,
               makeup_db=0.0):
    """Stereo-linked feed-forward RMS compressor, circular (state wraps around the loop)."""
    L = x.shape[-1]
    p = np.mean(x ** 2, axis=0)
    a = np.exp(-1.0 / (rms_ms * 1e-3 * SR))
    ms = circ_lfilter([1 - a], [1, -a], p, warm=min(L, SR))
    lv = 10 * np.log10(ms + 1e-12)
    nb = L // blk
    lvb = lv[:nb * blk].reshape(nb, blk).max(axis=1)
    over = lvb - thresh_db
    slope = 1.0 - 1.0 / ratio
    gr = np.where(over <= -knee / 2, 0.0,
                  np.where(over >= knee / 2, over * slope, slope * (over + knee / 2) ** 2 / (2 * knee)))
    aa = np.exp(-blk / (attack * SR))
    ar = np.exp(-blk / (release * SR))
    out = np.empty(nb)
    gst = 0.0
    grl = gr.tolist()
    for rep in range(2):
        for i in range(nb):
            tg = grl[i]
            if tg > gst:
                gst = aa * gst + (1 - aa) * tg
            else:
                gst = ar * gst + (1 - ar) * tg
            out[i] = gst
    centers = np.arange(nb) * blk + blk / 2.0
    gdb = np.interp(np.arange(L), centers, out, period=L)
    return x * undb(makeup_db - gdb)


def true_peak(x, os=4):
    """Per-sample true peak estimate (max over channels) via oversampling; circular padding."""
    L = x.shape[-1]
    pad = 64
    xx = np.concatenate([x[..., L - pad:], x, x[..., :pad]], axis=-1)
    up = signal.resample_poly(xx, os, 1, axis=-1)
    a = np.abs(up)
    if a.ndim == 2:
        a = a.max(axis=0)
    a = a.reshape(-1, os).max(axis=1)
    return a[pad:pad + L]


def limiter(x, ceiling_db=-1.5, look_ms=1.5, release_db_s=25.0, os=4):
    """Offline, non-causal true-peak limiter (circular)."""
    L = x.shape[-1]
    pk = true_peak(x, os)
    ceil = undb(ceiling_db)
    a_req = np.maximum(0.0, 20 * np.log10(pk / ceil + 1e-12))
    if a_req.max() <= 0:
        return x.copy()
    W = max(int(look_ms * 1e-3 * SR), 2)
    R2 = W // 2
    pad = 4 * SR if L > 8 * SR else L // 2
    ar = np.concatenate([a_req[L - pad:], a_req, a_req[:pad]])
    # hold radius covers both smoothing stages -> attenuation at every peak >= required
    hold = maximum_filter1d(ar, 2 * (W + R2 + 1) + 1)
    rate = release_db_s / SR
    idx = np.arange(len(hold), dtype=float)
    rel = np.maximum.accumulate(hold + idx * rate) - idx * rate
    sm = uniform_filter1d(rel, 2 * W + 1)
    sm = uniform_filter1d(sm, 2 * R2 + 1)
    g = undb(-sm[pad:pad + L])
    return x * g


def _kweight_coefs():
    """BS.1770 K-weighting for arbitrary sample rate (same derivation as libebur128)."""
    f0 = 1681.974450955533
    G = 3.999843853973347
    Q = 0.7071752369554196
    K = np.tan(np.pi * f0 / SR)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b1 = np.array([(Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0])
    a1 = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])
    f0 = 38.13547087602444
    Q = 0.5003270373238773
    K = np.tan(np.pi * f0 / SR)
    b2 = np.array([1.0, -2.0, 1.0])
    a2 = np.array([1.0, 2.0 * (K * K - 1.0) / (1.0 + K / Q + K * K), (1.0 - K / Q + K * K) / (1.0 + K / Q + K * K)])
    return (b1, a1), (b2, a2)


_KW = _kweight_coefs()


def lufs(x):
    """ITU-R BS.1770-4 integrated loudness of (2, L) or (L,) signal (mono counted as one channel)."""
    if x.ndim == 1:
        x = x[None, :]
    (b1, a1), (b2, a2) = _KW
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, x, axis=-1), axis=-1)
    pw = np.sum(y ** 2, axis=0)
    blk = int(0.4 * SR)
    hop = int(0.1 * SR)
    if len(pw) < blk:
        z = np.array([pw.mean()])
    else:
        cs = np.concatenate([[0.0], np.cumsum(pw)])
        st = np.arange(0, len(pw) - blk + 1, hop)
        z = (cs[st + blk] - cs[st]) / blk
    lk = -0.691 + 10 * np.log10(z + 1e-20)
    z1 = z[lk > -70]
    if len(z1) == 0:
        return -99.0
    rel = -0.691 + 10 * np.log10(z1.mean()) - 10
    z2 = z[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(z2.mean()))


def set_lufs(x, target):
    l = lufs(x)
    if l < -90:
        return x
    return x * undb(target - l)


def master(x, target=-16.0, ceiling=-1.6, comp=None, iters=5):
    x = x - x.mean(axis=-1, keepdims=True)
    x = cfilt(x, 'hp', 22.0, 0.6)
    if comp:
        x = compressor(x, **comp)
    g = 1.0
    y = x
    for _ in range(iters):
        y = limiter(x * g, ceiling)
        l = lufs(y)
        g *= undb(target - l)
    y = limiter(x * g, ceiling)
    return y


def write_wav(path, x, bits=16):
    x = np.asarray(x)
    if x.ndim == 2:
        x = x.T
    if bits == 16:
        y = np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int16)
    else:
        y = x.astype(np.float32)
    wavfile.write(path, SR, y)


def loop_report(x):
    """Seam continuity + head/tail RMS. x: (2, L)."""
    d = np.abs(np.diff(x, axis=-1))
    seam = np.abs(x[:, 0] - x[:, -1])
    typ = np.percentile(d, 99.0)
    n = int(0.2 * SR)
    rh = np.sqrt(np.mean(x[:, :n] ** 2))
    rt = np.sqrt(np.mean(x[:, -n:] ** 2))
    return dict(seam=float(seam.max()), d99=float(typ), d_max=float(d.max()), rms_head_db=float(db(rh)),
                rms_tail_db=float(db(rt)))
