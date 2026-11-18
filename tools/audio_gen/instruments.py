"""Shared instrument voices and song helpers built on synthlib."""
import os
import numpy as np
from synthlib import *
from synthlib import _smooth_mask

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')


class Song:
    def __init__(self, bpm, beats_per_bar, bars, seed=0):
        self.bpm = bpm
        self.bpb = beats_per_bar
        self.bars = bars
        self.spb = SR * 60.0 / bpm
        assert abs(self.spb - round(self.spb)) < 1e-9, 'samples per beat must be an integer'
        self.spb = int(round(self.spb))
        self.L = self.spb * beats_per_bar * bars
        self.rng = np.random.default_rng(seed)
        self.buses = {}

    def pos(self, bar, beat=0.0, jitter_ms=0.0, late_ms=0.0):
        p0 = (bar * self.bpb + beat) * self.spb
        p = p0
        if jitter_ms:
            p += self.rng.normal(0, jitter_ms) * 1e-3 * SR
        p += late_ms * 1e-3 * SR
        if p0 >= 0 and p < 0:
            p = 0.0  # never let humanisation wrap an on-time event to the end of the loop
        return p

    def sec(self, beats):
        return beats * 60.0 / self.bpm

    def bus(self, name):
        if name not in self.buses:
            self.buses[name] = Bus(self.L)
        return self.buses[name]


def sub_bass(f, dur, vel=0.9, rel=0.07, harm=0.1, a=0.006, glide_from=None, glide_t=0.04):
    env = env_adsr(dur, a=a, d=0.6, s=0.8, r=rel)
    N = len(env)
    t = np.arange(N) / SR
    if glide_from is not None:
        fc = f * (glide_from / f) ** np.exp(-t / glide_t)
    else:
        fc = np.full(N, f)
    ph = TWOPI * np.cumsum(fc) / SR
    y = np.sin(ph) + harm * np.sin(2 * ph) + 0.35 * harm * np.sin(3 * ph)
    return y * env * vel


def flute_note(f, dur, vel=0.8, seed=0, vib_rate=5.2, vib_depth=0.011, breath=0.22, scoop=-0.7,
               scoop_t=0.045, attack=0.07, rel=0.18, chiff=0.35, swell=0.15, harm=(0.2, 0.07, 0.025)):
    """Breathy flute (sine + few harmonics, pitched breath noise, scoop, delayed vibrato)."""
    rng = np.random.default_rng(seed)
    n_on = int(dur * SR)
    nr = int(rel * SR)
    N = n_on + nr
    t = np.arange(N) / SR
    semis = scoop * np.exp(-t / scoop_t)
    vib_env = np.clip((t - 0.22) / 0.45, 0, 1) * (0.8 + 0.2 * np.sin(TWOPI * 0.7 * t))
    drift = 0.0015 * lp1(rng.standard_normal(N), 3.0) * 20
    fcur = f * 2 ** (semis / 12.0) * (1 + vib_depth * vib_env * np.sin(TWOPI * vib_rate * t + rng.uniform(0, 6)) + drift)
    ph = TWOPI * np.cumsum(fcur) / SR
    tone = np.sin(ph) + harm[0] * np.sin(2 * ph + 0.3) + harm[1] * np.sin(3 * ph + 1.1) + harm[2] * np.sin(4 * ph + 2.0)
    nz = rng.standard_normal(N)
    pn = lp1(nz, 180.0) * 9.0 * np.sin(ph)
    bb = filt(nz, 'bp', min(2.8 * f + 1500, 9000), 0.8) * 0.6
    env = np.ones(N)
    na = int(attack * SR)
    env[:na] = (np.arange(na) / na) ** 1.5
    env[:n_on] *= 1.0 + swell * np.sin(np.pi * np.clip(t[:n_on] / max(dur, 0.05), 0, 1))
    env[n_on:] = env[n_on - 1] * np.exp(-np.arange(nr) / (0.25 * nr)) * np.linspace(1, 0, nr)
    breath_env = env * (1 + 1.2 * np.exp(-t / 0.06))
    y = tone * env * (1 - breath) + breath * (0.6 * pn + 0.4 * bb) * breath_env
    nc = int(0.05 * SR)
    ch = filt(rng.standard_normal(nc), 'bp', min(4 * f, 6000), 1.5) * np.exp(-np.arange(nc) / (0.012 * SR))
    y[:nc] += chiff * ch
    return y * vel


def koto_note(f, ring, vel=0.8, seed=0, bend=None, yuri=0.0, t60=None, bright=7500.0, S=0.17, pick=0.11,
              click=0.5, damp=0.25):
    """Koto-like pluck (Karplus-Strong), optional oshi bend (semitones, time) and yuri vibrato."""
    t60 = t60 or float(np.clip(2.8 * (220.0 / f) ** 0.4, 0.9, 4.0))
    total = ring + damp + 0.05
    y = ks_pluck(f, total + 0.2, t60=t60, S=S, pick=pick, bright=bright, seed=seed, attack_click=click)
    N = int(total * SR)
    if bend is not None or yuri > 0:
        t = np.arange(len(y)) / SR
        semis = np.zeros(len(y))
        if bend is not None:
            amt, t0, tb = bend  # start offset (semis), delay before press, press time
            # start at -amt below, press up to the target
            prog = np.clip((t - t0) / tb, 0, 1)
            prog = prog * prog * (3 - 2 * prog)
            semis += -amt * (1 - prog)
        if yuri > 0:
            ve = np.clip((t - 0.25) / 0.3, 0, 1)
            semis += yuri * ve * np.sin(TWOPI * 5.0 * t)
        y = pitch_bend(y, 2 ** (semis / 12.0))
    y = y[:N]
    if len(y) < N:
        y = np.concatenate([y, np.zeros(N - len(y))])
    e = np.ones(N)
    n_ring = int(ring * SR)
    nd = N - n_ring
    if nd > 0:
        e[n_ring:] = np.exp(-np.arange(nd) / (0.2 * nd)) * np.linspace(1, 0, nd)
    return y * e * vel


def koto_body(x):
    x = filt(x, 'peak', 320, 1.2, 3.0)
    x = filt(x, 'peak', 1100, 1.5, -2.0)
    x = filt(x, 'peak', 2600, 1.4, 2.5)
    return filt(x, 'hp', 90, 0.7)


def ep_chord(bus, song, midi_notes, start, dur_s, vel=0.7, roll_ms=15.0, bright=0.8, rel=0.35, pan_spread=0.5,
             seed=0, bark=0.18):
    rng = np.random.default_rng(seed)
    nn = sorted(midi_notes)
    for i, m in enumerate(nn):
        v = vel * (0.85 + 0.15 * rng.random()) * (1.0 - 0.05 * i)
        off = (i * roll_ms + rng.normal(0, 2.0)) * 1e-3 * SR
        y = fm_epiano(float(mtof(m)), dur_s, v, rel=rel, bright=bright, seed=int(rng.integers(1 << 30)), bark=bark)
        p = (i / max(len(nn) - 1, 1) - 0.5) * pan_spread
        bus.add(y, start + off, pan=p)


def pad_note(f, dur, vel=0.5, seed=0, n=3, det=9.0, att=0.5, rel=1.0, lp=1500.0, vib=0.0025):
    rng = np.random.default_rng(seed)
    env = env_adsr(dur, a=att, d=1.5, s=0.85, r=rel)
    N = len(env)
    t = np.arange(N) / SR
    y = np.zeros(N)
    for k in range(n):
        cents = (k - (n - 1) / 2.0) * (2.0 * det / max(n - 1, 1))
        v = 1 + vib * np.sin(TWOPI * (4.3 + 0.6 * k) * t + rng.uniform(0, 6))
        y += osc_saw(f * 2 ** (cents / 1200.0) * v, N, rng.random())
    y = filt(filt(y / n, 'lp', lp, 0.6), 'lp', lp * 1.4, 0.6)
    return y * env * vel


def autopan(x, rate, depth, L):
    r = loop_freq(rate, L)
    t = np.arange(L) / SR
    m = np.sin(TWOPI * r * t)
    gl = 1.0 + depth * m
    gr = 1.0 - depth * m
    return np.vstack([x[0] * gl, x[1] * gr])


def vinyl(L, rng, hiss_db=-54.0, crackle_rate=14.0, pop_rate=1.2):
    """Circular vinyl noise bed (hiss + crackle), stereo."""
    out = np.zeros((2, L))
    for ch in range(2):
        hiss = colored_noise_circ(L, rng, lambda f: (np.maximum(f, 20) / 1000.0) ** -0.5 *
                                  _smooth_mask(f, 250.0, 2.0) * (1 - _smooth_mask(f, 9000.0, 1.5)))
        imp = np.zeros(L)
        for rate, amp, spread in [(crackle_rate, 0.5, 0.6), (pop_rate, 1.0, 0.9)]:
            k = rng.poisson(rate * L / SR)
            pos = rng.integers(0, L, k)
            a = amp * rng.lognormal(0, spread, k) * rng.choice([-1, 1], k)
            np.add.at(imp, pos, a)
            np.add.at(imp, (pos + 1) % L, -0.5 * a)
        cr = cfilt(imp, 'hp', 1400, 0.7, warm=8192)
        cr = cfilt(cr, 'lp', 7000, 0.7, warm=8192)
        out[ch] = undb(hiss_db) * hiss + 0.06 * cr
    return out


def save_mix(name, x, meta):
    os.makedirs(OUT, exist_ok=True)
    np.save(os.path.join(OUT, name + '_mix.npy'), x.astype(np.float32))
    import json
    with open(os.path.join(OUT, name + '_meta.json'), 'w') as fh:
        json.dump(meta, fh, indent=1)


def vox_chop(f, dur, vowels=('a',), vel=0.8, seed=0, scoop=-1.2, scoop_t=0.022, vib=0.0, shift=1.2, breath=0.06,
             consonant=None, rel=0.03, tilt=2600.0, glide_to=None):
    """Cute synthetic 'vocal chop': band-limited glottal-ish source through morphing formant banks."""
    rng = np.random.default_rng(seed)
    N = int((dur + rel) * SR)
    t = np.arange(N) / SR
    semis = scoop * np.exp(-t / scoop_t)
    if glide_to is not None:
        semis = semis + glide_to * np.clip((t - dur * 0.55) / (dur * 0.45), 0, 1) ** 2
    vibe = vib * np.clip((t - 0.1) / 0.12, 0, 1) * np.sin(TWOPI * 5.8 * t)
    fcur = f * 2 ** ((semis + vibe) / 12.0)
    src = osc_saw(fcur, N, rng.random())
    src = lp1(src, tilt) * 1.5 + 0.25 * src
    exc = src + breath * rng.standard_normal(N)
    if len(vowels) == 1:
        y = formant_bank(exc, vowels[0], shift)
    else:
        ya = formant_bank(exc, vowels[0], shift)
        yb = formant_bank(exc, vowels[1], shift)
        m = np.clip((t - 0.25 * dur) / (0.5 * dur + 1e-3), 0, 1)
        m = m * m * (3 - 2 * m)
        y = ya * (1 - m) + yb * m
    env = env_adsr(dur, a=0.007, d=0.3, s=0.85, r=rel, n_total=N)
    y = y * env
    if consonant == 's':
        nc = int(0.035 * SR)
        c = filt(rng.standard_normal(nc), 'hp', 5500, 0.7) * np.exp(-np.arange(nc) / (0.01 * SR))
        y[:nc] += 0.25 * c
    elif consonant == 'k':
        nc = int(0.012 * SR)
        c = filt(rng.standard_normal(nc), 'bp', 2800, 1.5) * np.exp(-np.arange(nc) / (0.003 * SR))
        y[:nc] += 0.5 * c
    pk = np.max(np.abs(y)) + 1e-9
    return y / pk * vel


def riser(n, f0=300.0, f1=9000.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / n
    fc = f0 * (f1 / f0) ** (t ** 1.3)
    nz = rng.standard_normal(n)
    y = tv_filter(nz, 'bp', fc, 1.6, block=64)
    return y * (t ** 2.2) / (np.max(np.abs(y)) + 1e-9)
