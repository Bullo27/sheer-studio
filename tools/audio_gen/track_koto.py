"""koto_breeze - calm traditional-Japanese flavour, A hirajoshi (A B C E F), 72 BPM, 4/4, 24 bars (80 s).
Koto (Karplus-Strong, oshi bends, yuri vibrato), shakuhachi-like breathy flute, soft taiko, furin chimes, breeze.
Form: A (koto ostinato + fragments) | B (shakuhachi melody) | C (koto melody + shakuhachi answers)."""
import numpy as np
from synthlib import *
from instruments import *

NAME = 'koto_breeze'


def shaku_note(f, dur, vel, seed, muraiki=False):
    y = flute_note(f, dur, vel, seed=seed, vib_rate=4.7, vib_depth=0.016, breath=0.36, scoop=-1.1, scoop_t=0.09,
                   attack=0.12, rel=0.3, chiff=0.9 if muraiki else 0.45, swell=0.3, harm=(0.32, 0.12, 0.05))
    return y


def taiko_hit(vel, seed, f0=74.0):
    rng = np.random.default_rng(seed)
    N = int(1.4 * SR)
    t = np.arange(N) / SR
    bend = 1 + 0.22 * np.exp(-t / 0.035)
    y = np.zeros(N)
    for r, a, T in zip([1.0, 1.59, 2.14, 2.30, 2.65], [1.0, 0.45, 0.28, 0.18, 0.1], [1.0, 0.55, 0.35, 0.3, 0.22]):
        ph = TWOPI * np.cumsum(f0 * r * bend) / SR + rng.uniform(0, 6)
        y += a * np.sin(ph) * np.exp(-6.9 * t / T)
    th = lp1(rng.standard_normal(N), 500) * np.exp(-t / 0.02) * 4.0
    y += th
    y[:30] *= np.linspace(0, 1, 30)
    return fade_tail(y / np.max(np.abs(y)) * vel, 30)


def ka_hit(vel, seed):
    rng = np.random.default_rng(seed)
    N = int(0.12 * SR)
    t = np.arange(N) / SR
    nz = rng.standard_normal(N) * np.exp(-t / 0.006)
    y = filt(nz, 'bp', 1900, 4.0) * 2 + filt(nz, 'bp', 950, 5.0)
    return fade_tail(y / np.max(np.abs(y)) * vel, 10)


def furin(vel, seed, f=2637.0):
    return modal(f, 3.4, ratios=[1.0, 2.76, 5.40], amps=[1.0, 0.35, 0.12], t60s=[3.0, 1.2, 0.45], vel=vel,
                 attack=0.0002, seed=seed, click=0.15, click_fc=7000, beat_cents=4.0, beat_amt=0.6)


def render():
    S = Song(72, 4, 24, seed=66)
    L = S.L
    rng = S.rng
    harm = ['A', 'A', 'F', 'E'] * 6
    sect = ['A'] * 8 + ['B'] * 8 + ['C'] * 8

    ost = {'A': ['A3', 'E4', 'A4', 'B4', 'C5', 'B4', 'A4', 'E4'],
           'F': ['F3', 'C4', 'F4', 'A4', 'B4', 'A4', 'F4', 'C4'],
           'E': ['E3', 'B3', 'E4', 'F4', 'A4', 'F4', 'E4', 'B3']}
    ko = S.bus('koto')

    def kpl(nm, bar, beat, vel, ring_beats=3.0, bend=None, yuri=0.0, pan=0.0, bright=7500):
        f = float(mtof(note(nm)))
        y = koto_note(f, S.sec(ring_beats), vel, seed=int(rng.integers(1 << 30)), bend=bend, yuri=yuri,
                      bright=bright)
        ko.add(y, S.pos(bar, beat, jitter_ms=7), pan=pan)

    for bar in range(24):
        sc = sect[bar]
        pat = ost[harm[bar]]
        for k, nm in enumerate(pat):
            if sc == 'B' and k % 2 == 1:
                continue
            if sc == 'C' and k in (3, 5):
                continue
            v = (0.75 if k == 0 else 0.5) * (0.85 + 0.25 * rng.random()) * (0.8 if sc != 'A' else 1.0)
            kpl(nm, bar, k * 0.5, v, ring_beats=4.0 if k == 0 else 2.0, pan=-0.45 + 0.12 * k)
    # fragments in A, melody in C: (bar, 8th, dur8, note, bend, yuri)
    frag = [(1, 4, 2, 'E5', 1, 0.0), (1, 6, 2, 'C5', 0, 0.0), (3, 2, 4, 'B4', 0, 0.2),
            (5, 4, 1, 'A5', 0, 0.0), (5, 5, 1, 'F5', 0, 0.0), (5, 6, 2, 'E5', 1, 0.0), (7, 0, 6, 'E5', 0, 0.25)]
    mel = [(16, 0, 1, 'A4', 0, 0), (16, 1, 1, 'B4', 0, 0), (16, 2, 2, 'C5', 0, 0), (16, 4, 2, 'E5', 1, 0),
           (16, 6, 1, 'C5', 0, 0), (16, 7, 1, 'B4', 0, 0),
           (17, 0, 4, 'A4', 0, 0.25), (17, 4, 2, 'E4', 0, 0), (17, 6, 2, 'A4', 0, 0),
           (18, 0, 1, 'F4', 0, 0), (18, 1, 1, 'A4', 0, 0), (18, 2, 2, 'C5', 0, 0), (18, 4, 1, 'B4', 0, 0),
           (18, 5, 1, 'A4', 0, 0), (18, 6, 2, 'F4', 0, 0),
           (19, 0, 6, 'E4', 0, 0.3),
           (20, 0, 1, 'C5', 0, 0), (20, 1, 1, 'E5', 0, 0), (20, 2, 3, 'A5', 2, 0.2), (20, 5, 1, 'F5', 0, 0),
           (20, 6, 2, 'E5', 0, 0),
           (21, 0, 2, 'C5', 0, 0), (21, 2, 2, 'B4', 0, 0), (21, 4, 4, 'A4', 0, 0.25),
           (22, 0, 2, 'F5', 0, 0), (22, 2, 2, 'E5', 0, 0), (22, 4, 2, 'C5', 0, 0), (22, 6, 2, 'B4', 0, 0),
           (23, 0, 6, 'E4', 1, 0.3)]
    for (b, s8, d8, nm, bd, yu) in frag + mel:
        bend = (bd, 0.03, 0.11) if bd else None
        kpl(nm, b, s8 * 0.5, 0.85 if b >= 16 else 0.75, ring_beats=d8 * 0.5 + 1.5, bend=bend, yuri=yu * 0.6,
            pan=0.15, bright=8500)

    # shakuhachi
    sh = S.bus('shaku')
    smel = [(8, 0, 3, 'E5'), (8, 3, 1, 'C5'), (9, 0, 2, 'B4'), (9, 2, 2, 'A4'),
            (10, 0, 1.5, 'C5'), (10, 1.5, 0.5, 'E5'), (10, 2, 2, 'F5'), (11, 0, 3.6, 'E5'),
            (12, 0, 2, 'A5'), (12, 2, 1, 'F5'), (12, 3, 1, 'E5'), (13, 0, 1, 'C5'), (13, 1, 1, 'B4'), (13, 2, 2, 'A4'),
            (14, 0, 2, 'F4'), (14, 2, 1, 'A4'), (14, 3, 1, 'B4'), (15, 0, 3.4, 'E4'),
            (19, 1, 2.6, 'B4'), (21, 2, 1.8, 'E5'), (23, 0, 2, 'F5'), (23, 2, 2.45, 'E5')]
    for (b, bt, d, nm) in smel:
        y = shaku_note(float(mtof(note(nm))), S.sec(d) * 0.95, 0.8 * (0.9 + 0.15 * rng.random()),
                       int(rng.integers(1 << 30)), muraiki=(d >= 3 and rng.random() < 0.5))
        sh.add(y, S.pos(b, bt, jitter_ms=10), pan=0.25)

    # taiko + ka
    tk = S.bus('taiko')
    for bar in range(24):
        sc = sect[bar]
        if sc == 'A':
            hits = [(0, 0.7, 'd')] if bar % 2 == 0 else [(3.5, 0.3, 'k')]
        elif sc == 'B':
            hits = [(0, 0.75, 'd'), (3.5, 0.35, 'd')]
        else:
            hits = [(0, 0.85, 'd'), (1.5, 0.35, 'k'), (2, 0.55, 'd'), (3.5, 0.4, 'k')]
        if bar == 23:
            hits += [(3.0, 0.35, 'd'), (3.5, 0.5, 'd')]
        for (bt, v, kind) in hits:
            y = taiko_hit(v, int(rng.integers(1 << 30))) if kind == 'd' else ka_hit(v * 0.6, int(rng.integers(1 << 30)))
            tk.add(y, S.pos(bar, bt, jitter_ms=5), pan=-0.1 if kind == 'd' else 0.3)

    # furin chimes: irregular clusters
    fu = S.bus('furin')
    chime_notes = ['E7', 'C7', 'A6', 'B6', 'F7']
    for (b, bt) in [(1, 1.3), (3, 3.1), (6, 0.6), (9, 2.2), (12, 3.6), (14, 1.1), (17, 2.7), (20, 0.4), (22, 2.9)]:
        f = float(mtof(note(chime_notes[int(rng.integers(len(chime_notes)))])))
        nh = int(rng.integers(2, 4))
        tt = 0.0
        for h in range(nh):
            fu.add(furin(0.6 * 0.7 ** h, int(rng.integers(1 << 30)), f * (1 + 0.004 * h)), S.pos(b, bt) + tt * SR,
                   pan=0.55)
            tt += rng.uniform(0.12, 0.35)

    # drone + breeze
    dn = S.bus('drone')
    for b in range(0, 24, 4):
        for i, nm in enumerate(['A2', 'E3', 'A3']):
            y = pad_note(float(mtof(note(nm))), S.sec(16) - 0.2, 0.5, seed=b * 3 + i, n=2, det=4, att=2.5, rel=2.5,
                         lp=700, vib=0.001)
            dn.add(y, S.pos(b), pan=(i - 1) * 0.5)
    wind = np.zeros((2, L))
    t = np.arange(L) / SR
    for c in range(2):
        w = colored_noise_circ(L, rng, lambda fr: (np.maximum(fr, 20) / 500) ** -0.6 *
                               (1 - np.exp(-(fr / 250) ** 2)) * np.exp(-(fr / 3500) ** 2))
        g = 0.55 + 0.45 * np.sin(TWOPI * loop_freq(0.05, L) * t + c) * np.sin(TWOPI * loop_freq(0.13, L) * t + 2 * c)
        wind[c] = w * g ** 2

    # ------------------------------------------------------------------ mix
    ko_x = cfilt(koto_body(S.buses['koto'].buf), 'lp', 9000, 0.6)
    sh_x = cfilt(S.buses['shaku'].buf, 'hp', 180, 0.7)
    tk_x = cfilt(S.buses['taiko'].buf, 'lp', 4000, 0.7)
    fu_x = cfilt(S.buses['furin'].buf, 'hp', 1200, 0.7)
    dn_x = S.buses['drone'].buf
    ko_x = set_lufs(ko_x, -20.0)
    sh_x = set_lufs(sh_x, -20.5)
    tk_x = set_lufs(tk_x, -24.5)
    fu_x = set_lufs(fu_x, -28.0)
    dn_x = set_lufs(dn_x, -30.0)
    wind = set_lufs(wind, -37.0)
    ir = make_ir(t60=3.4, predelay=0.035, hf=0.7, seed=17)
    send = 0.35 * ko_x + 0.5 * sh_x + 0.3 * tk_x + 0.6 * fu_x + 0.3 * dn_x
    wet = reverb(send, ir)
    dly = delay_taps(sh_x.mean(0), S.spb * 3 // 2, fb=0.3, taps=3, lp=2500)
    mix = ko_x + sh_x + tk_x + fu_x + dn_x + wind + 0.6 * wet + 0.12 * dly
    return mix, dict(name=NAME, bpm=72, key='A hirajoshi (A B C E F), drone on A', bars=24, meter='4/4')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
