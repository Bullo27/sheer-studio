"""city_pop_night - 80s Japanese city-pop style, 108 BPM, Eb major, 40 bars (88.9 s).
Form: verse (8) | pre-chorus (8) | chorus (16) | interlude/lead riff (8) -> verse."""
import numpy as np
from synthlib import *
from instruments import *

NAME = 'city_pop_night'


def lead_note(f, dur, vel, seed, f_prev=None, vib=0.18, cutoff=5200.0, rel=0.12, n_samples=None):
    rng = np.random.default_rng(seed)
    n_on = int(dur * SR)
    nr = int(rel * SR)
    N = n_on + nr
    t = np.arange(N) / SR
    semis = np.zeros(N)
    if f_prev is not None:
        semis += 12 * np.log2(f_prev / f) * np.exp(-t / 0.028)
    ve = np.clip((t - 0.18) / 0.15, 0, 1)
    semis += vib * ve * np.sin(TWOPI * 5.6 * t + rng.uniform(0, 6))
    fc = f * 2 ** (semis / 12.0)
    y = osc_saw(fc * 2 ** (-5 / 1200), N, rng.random()) + 0.7 * osc_pulse(fc * 2 ** (6 / 1200), N, 0.5, rng.random())
    y += 0.35 * osc_saw(fc * 0.5, N, rng.random())
    cut = cutoff * (1 + 0.8 * np.exp(-t / 0.08))
    y = tv_filter(y, 'lp', cut, 0.9, block=64)
    env = env_adsr(dur, a=0.008, d=0.35, s=0.78, r=rel, n_total=N)
    return y * env * vel


def brass_stab(freqs, dur, vel, seed):
    rng = np.random.default_rng(seed)
    n_on = int(dur * SR)
    nr = int(0.14 * SR)
    N = n_on + nr
    t = np.arange(N) / SR
    out = np.zeros((2, N))
    for i, f in enumerate(freqs):
        for k, c in enumerate((-7, 0, 7)):
            s = osc_saw(f * 2 ** (c / 1200) * (1 + 0.002 * np.sin(TWOPI * 5 * t + rng.uniform(0, 6))), N, rng.random())
            gl, gr = pan_gains((k - 1) * 0.6)
            out[0] += s * gl
            out[1] += s * gr
    out /= len(freqs) * 2
    rise = 1 - np.exp(-t / 0.022)
    cut = 450 + 4200 * rise * (0.55 + 0.45 * np.exp(-t / 0.18))
    out = np.vstack([tv_lp4(out[c], cut, block=64) for c in range(2)])
    env = env_adsr(dur, a=0.012, d=0.2, s=0.72, r=0.12, n_total=N)
    return out * env * vel


def bass_note(f, dur, vel, seed, kind='f'):
    """Fingered/slap synth bass: Karplus-Strong string + sub sine, pop = brighter + click."""
    rng = np.random.default_rng(seed)
    S = 0.38 if kind != 'p' else 0.2
    bright = 2500 if kind == 'f' else (5000 if kind == 'p' else 1500)
    y = ks_pluck(f, dur + 0.1, t60=1.3, S=S, pick=0.18, bright=bright, seed=seed, attack_click=0.6 if kind == 'p' else 0.2)
    N = int(dur * SR) + int(0.045 * SR)
    y = y[:N]
    if len(y) < N:
        y = np.pad(y, (0, N - len(y)))
    t = np.arange(N) / SR
    sub = np.sin(TWOPI * f * t + 0.3) * np.exp(-t / 0.6) * (0.0 if kind == 'p' else 0.55)
    y = y + sub
    e = np.ones(N)
    n_on = int(dur * SR)
    e[n_on:] = np.linspace(1, 0, N - n_on) ** 2
    e[:30] *= np.linspace(0, 1, 30)
    if kind == 'g':
        e *= np.exp(-t / 0.03)
    return y * e * vel


def render():
    S = Song(108, 4, 40, seed=55)
    L = S.L
    rng = S.rng

    V = [[(0, 'Ab1', 'Ab2 G3 C4 Eb4 Bb4')],
         [(0, 'G1', 'G2 F3 Bb3 D4 F4')],
         [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')],
         [(0, 'Bb1', 'Bb2 Ab3 C4 Eb4 G4'), (2, 'Bb1', 'Bb2 Ab3 D4 G4 C5')],
         [(0, 'Ab1', 'Ab2 G3 C4 Eb4 Bb4')],
         [(0, 'G1', 'G2 F3 Bb3 D4 F4'), (2, 'C2', 'C3 Bb3 E4 Db5')],
         [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')],
         [(0, 'Bb1', 'Bb2 Ab3 C4 Eb4 F4'), (2, 'Bb1', 'Bb2 Ab3 D4 F4')]]
    PRE = [[(0, 'C2', 'C3 Bb3 D4 Eb4 G4')],
           [(0, 'Bb1', 'Bb2 Ab3 C4 Db4 F4'), (2, 'Eb2', 'Eb3 Db4 F4 G4 Bb4')],
           [(0, 'Ab1', 'Ab2 G3 C4 Eb4 Bb4')],
           [(0, 'G1', 'G2 F3 Bb3 D4 F4'), (2, 'C2', 'C3 Bb3 E4 Eb5')],
           [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')],
           [(0, 'G1', 'G2 F3 Bb3 D4 F4')],
           [(0, 'Ab1', 'Ab2 G3 C4 Eb4')],
           [(0, 'Bb1', 'Bb2 Ab3 C4 Eb4 G4')]]
    AB = 'Ab2 G3 C4 Eb4 Bb4'
    B13 = 'Bb2 Ab3 D4 G4 C5'
    CHO = [[(0, 'Ab1', AB)], [(0, 'Bb1', B13)], [(0, 'G1', 'G2 F3 A3 Bb3 D4')], [(0, 'C2', 'C3 Bb3 D4 Eb4 G4')],
           [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')], [(0, 'Bb1', B13)], [(0, 'Eb2', 'Eb3 D4 F4 G4 Bb4')],
           [(0, 'Eb2', 'Eb3 Db4 G4 Bb4')],
           [(0, 'Ab1', AB)], [(0, 'Bb1', B13)], [(0, 'G1', 'G2 F3 Bb3 D4 F4'), (2, 'C2', 'C3 Bb3 E4 Db5')],
           [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')], [(0, 'Db2', 'Db3 C4 Eb4 F4 Ab4')], [(0, 'C2', 'C3 Bb3 D4 Eb4 G4')],
           [(0, 'F1', 'F2 Eb3 Ab3 C4 G4')], [(0, 'Bb1', 'Bb2 Ab3 C4 Eb4 G4'), (2, 'Bb1', B13)]]
    prog = V + PRE + CHO + V
    sect = ['V'] * 8 + ['P'] * 8 + ['C'] * 16 + ['I'] * 8

    def segs(bar):
        sg = prog[bar]
        out = []
        for i, (b0, bs, vo) in enumerate(sg):
            b1 = sg[i + 1][0] if i + 1 < len(sg) else 4
            out.append((b0, b1, note(bs), notes(vo)))
        return out

    # ------------------------------------------------------------------ EP comping
    ep = S.bus('ep')
    pd = S.bus('pad')
    comp = {'V': [(0, 5, 0.62), (6, 3, 0.45), (10, 5, 0.55)],
            'I': [(0, 5, 0.62), (6, 3, 0.45), (10, 5, 0.55)],
            'P': [(0, 3, 0.6), (3, 3, 0.5), (8, 3, 0.55), (11, 4, 0.5)],
            'C': [(0, 6, 0.66), (6, 2, 0.46), (10, 3, 0.56), (14, 2, 0.46)]}
    for bar in range(40):
        for (b0, b1, r, vo) in segs(bar):
            for (s0, d, v) in comp[sect[bar]]:
                if not (b0 * 4 <= s0 < b1 * 4):
                    continue
                d = min(d, b1 * 4 - s0)
                ep_chord(ep, S, vo, S.pos(bar, s0 / 4.0, jitter_ms=3), S.sec(d / 4.0) - 0.04, vel=v, roll_ms=6,
                         bright=1.0, rel=0.3, pan_spread=0.6, seed=bar * 101 + s0, bark=0.25)
            if sect[bar] in ('C', 'P'):
                for i, m in enumerate(vo[1:]):
                    pd.add(pad_note(float(mtof(m + 12)), S.sec(b1 - b0) - 0.05, 0.45, seed=bar * 7 + i, n=3, det=10,
                                    att=0.25, rel=0.6, lp=3200), S.pos(bar, b0), pan=(i - 1.5) * 0.4)

    # ------------------------------------------------------------------ bass
    bs_bus = S.bus('bass')
    full = [(0, 3, 0, 0.95, 'f'), (3, 1, 0, 0.4, 'g'), (4, 1, 12, 0.75, 'p'), (6, 2, 0, 0.75, 'f'),
            (8, 2, 7, 0.75, 'f'), (10, 1, 12, 0.78, 'p'), (11, 1, 10, 0.55, 'f'), (12, 2, 0, 0.8, 'f'),
            (14, 2, 'app', 0.7, 'f')]
    half = [(0, 3, 0, 0.95, 'f'), (3, 1, 12, 0.7, 'p'), (4, 2, 7, 0.7, 'f'), (6, 2, 'app', 0.68, 'f')]
    all_segs = [(bar, sg) for bar in range(40) for sg in segs(bar)]
    for i, (bar, (b0, b1, r, vo)) in enumerate(all_segs):
        nxt = all_segs[(i + 1) % len(all_segs)][1][2]
        pat = full if (b1 - b0) == 4 else half
        for (s0, d, iv, v, kind) in pat:
            if iv == 'app':
                m = nxt - 1 if (nxt - 1) % 12 != r % 12 else nxt + 1
                m = m if abs(m - r) < 9 else m - 12 * int(np.sign(m - r))
            else:
                m = r + iv
            y = bass_note(float(mtof(m)), S.sec(d / 4.0) * 0.9, v, int(rng.integers(1 << 30)), kind)
            bs_bus.add(y, S.pos(bar, b0 + s0 / 4.0, jitter_ms=3))

    # ------------------------------------------------------------------ drums
    dr = S.bus('drums')
    kick = drum_kick(f_end=52, f_start=185, tau_p=0.024, t60=0.36, click=0.3, drive=1.7, seed=3)
    sn_dry = drum_snare(dur=0.5, tone_f=196, tone_amt=0.55, noise_t60=0.2, n_lo=1100, n_hi=9000, seed=4)
    gir = make_ir(t60=1.4, predelay=0.004, hf=0.9, seed=21, length=0.6, density_ms=1.0)
    n_g = len(sn_dry) + gir.shape[1]
    rv = np.vstack([np.convolve(sn_dry, gir[c])[:n_g] for c in range(2)])
    tg = np.arange(rv.shape[1]) / SR
    gate = np.clip((0.27 - tg) / 0.035, 0, 1)
    rv *= gate
    gsn = rv * 0.75
    gsn[:, :len(sn_dry)] += sn_dry
    gsn = fade_tail(gsn / np.max(np.abs(gsn)), 10)
    ghost = drum_snare(dur=0.2, tone_f=200, tone_amt=0.4, noise_t60=0.08, seed=5)
    clap = drum_clap(fc=1600, seed=6)
    hats = [drum_hat(t60=0.045, metal=0.4, fc=9500, hp=7000, seed=10 + s) for s in range(4)]
    ohat = drum_hat(dur=0.4, t60=0.3, metal=0.45, fc=9000, hp=6500, seed=15)
    crash = drum_crash(dur=2.5, t60=2.2, seed=16)
    tom = [drum_kick(dur=0.4, f_end=f, f_start=f * 1.6, tau_p=0.04, t60=0.3, click=0.1, drive=1.2, seed=20 + i)
           for i, f in enumerate((180.0, 140.0, 105.0))]
    for bar in range(40):
        sc = sect[bar]
        K = {0: 1.0, 6: 0.6, 8: 0.9}
        if sc == 'C':
            K[14] = 0.5
        SN = {4: 1.0, 12: 1.0}
        GH = {7: 0.18, 15: 0.22} if sc != 'V' else {15: 0.18}
        acc = [0.8, 0.3, 0.55, 0.32]
        H = {s: acc[s % 4] for s in range(16)}
        O = {}
        if sc in ('C', 'I') and bar % 2 == 1:
            O = {14: 0.6}
            H.pop(14)
        T = {}
        if bar in (15, 31):
            T = {12: 0, 13: 0, 14: 1, 15: 2}
            SN = {4: 1.0}
            for s in (12, 13, 14, 15):
                H.pop(s, None)
        for s0, v in K.items():
            dr.add(kick * v, S.pos(bar, s0 / 4.0, jitter_ms=1.5))
        for s0, v in SN.items():
            dr.add(gsn * v * 0.85, S.pos(bar, s0 / 4.0, jitter_ms=1.5))
            if sc == 'C':
                dr.add(clap * v * 0.4, S.pos(bar, s0 / 4.0, jitter_ms=1), pan=0.1)
        for s0, v in GH.items():
            dr.add(ghost * v, S.pos(bar, s0 / 4.0, jitter_ms=3), pan=0.05)
        for s0, v in H.items():
            dr.add(hats[rng.integers(4)] * v * 0.3 * (0.9 + 0.2 * rng.random()), S.pos(bar, s0 / 4.0, jitter_ms=3),
                   pan=0.3)
        for s0, v in O.items():
            dr.add(ohat * v * 0.32, S.pos(bar, s0 / 4.0, jitter_ms=2), pan=0.3)
        for s0, ti in T.items():
            dr.add(tom[ti] * 0.7, S.pos(bar, s0 / 4.0, jitter_ms=2), pan=(-0.4, 0.0, 0.4)[ti])
    for b in (8, 16, 32):
        dr.add(crash * 0.5, S.pos(b), pan=-0.25)

    # ------------------------------------------------------------------ brass stabs
    br = S.bus('brass')
    hits = [(3, 14, 1.5), (7, 10, 2), (7, 14, 2)]
    hits += [(b, s, l) for b in range(8, 15) for (s, l) in ((0, 3), (6, 1.5), (10, 2))]
    hits += [(15, 0, 2), (15, 4, 2), (15, 8, 2), (15, 12, 4)]
    hits += [(16, 0, 3), (19, 14, 2), (20, 0, 3), (23, 10, 2), (23, 14, 2), (24, 0, 3), (27, 14, 2), (28, 0, 3),
             (31, 8, 2), (31, 12, 3)]
    hits += [(32, 0, 3), (35, 14, 2), (36, 0, 3), (39, 10, 2), (39, 14, 2)]
    for (b, s0, ln) in hits:
        tb = b + (1 if s0 >= 14 else 0)  # anticipations take the next bar's chord
        beat = 0.0 if s0 >= 14 else s0 / 4.0
        sg = [x for x in segs(tb % 40) if x[0] <= beat][-1]
        vo = sg[3]
        top = sorted(set([note('G4') + ((m - note('G4')) % 12) for m in vo[1:]]))[-4:]
        fr = [float(mtof(m)) for m in top]
        br.add(brass_stab(fr, S.sec(ln / 4.0) * 0.85, 0.9, int(rng.integers(1 << 30))), S.pos(b, s0 / 4.0, jitter_ms=2))

    # ------------------------------------------------------------------ lead
    ld = S.bus('lead')
    CH = [(0, 2, 2, 'G5'), (0, 4, 2, 'Ab5'), (0, 6, 4, 'Bb5'), (0, 10, 2, 'C6'), (0, 12, 4, 'Bb5'),
          (1, 0, 2, 'Ab5'), (1, 2, 2, 'G5'), (1, 4, 4, 'F5'), (1, 8, 2, 'D5'), (1, 10, 2, 'F5'), (1, 14, 6, 'G5'),
          (2, 4, 2, 'Bb5'), (2, 6, 4, 'D6'), (2, 10, 2, 'C6'), (2, 12, 4, 'Bb5'),
          (3, 0, 4, 'G5'), (3, 4, 2, 'Eb5'), (3, 6, 2, 'F5'), (3, 8, 4, 'G5'), (3, 12, 2, 'Bb5'), (3, 14, 2, 'C6'),
          (4, 0, 4, 'C6'), (4, 4, 2, 'Bb5'), (4, 6, 4, 'Ab5'), (4, 10, 2, 'G5'), (4, 12, 4, 'F5'),
          (5, 0, 2, 'F5'), (5, 2, 2, 'G5'), (5, 4, 4, 'Ab5'), (5, 8, 2, 'G5'), (5, 10, 2, 'F5'), (5, 12, 2, 'D5'),
          (5, 14, 2, 'Eb5'),
          (6, 0, 8, 'G5'), (6, 8, 2, 'Bb5'), (6, 10, 2, 'G5'), (6, 12, 2, 'F5'), (6, 14, 2, 'Eb5'),
          (7, 0, 4, 'F5'), (7, 4, 2, 'Eb5'), (7, 6, 4, 'Db5'), (7, 14, 2, 'Eb5'),
          (8, 2, 2, 'G5'), (8, 4, 2, 'Ab5'), (8, 6, 4, 'Bb5'), (8, 10, 2, 'C6'), (8, 12, 4, 'Eb6'),
          (9, 0, 4, 'D6'), (9, 4, 2, 'C6'), (9, 6, 4, 'Bb5'), (9, 10, 2, 'Ab5'), (9, 12, 4, 'G5'),
          (10, 0, 4, 'Bb5'), (10, 4, 2, 'G5'), (10, 6, 2, 'Bb5'), (10, 8, 4, 'Db6'), (10, 12, 2, 'C6'),
          (10, 14, 2, 'Bb5'),
          (11, 0, 6, 'Ab5'), (11, 6, 2, 'G5'), (11, 8, 4, 'F5'), (11, 12, 2, 'Eb5'), (11, 14, 2, 'F5'),
          (12, 0, 4, 'Ab5'), (12, 4, 4, 'C6'), (12, 8, 4, 'Eb6'), (12, 12, 2, 'C6'), (12, 14, 2, 'Ab5'),
          (13, 0, 4, 'G5'), (13, 4, 2, 'Bb5'), (13, 6, 4, 'D6'), (13, 10, 2, 'C6'), (13, 12, 4, 'Bb5'),
          (14, 0, 2, 'Ab5'), (14, 2, 2, 'G5'), (14, 4, 4, 'F5'), (14, 8, 2, 'Eb5'), (14, 10, 2, 'F5'),
          (14, 12, 4, 'G5'),
          (15, 0, 4, 'Ab5'), (15, 4, 2, 'G5'), (15, 6, 2, 'F5'), (15, 8, 6, 'D5')]
    VS = [(0, 2, 2, 'C5'), (0, 4, 2, 'Eb5'), (0, 6, 6, 'G5'), (0, 12, 2, 'F5'), (0, 14, 2, 'Eb5'),
          (1, 0, 8, 'D5'), (1, 10, 2, 'Bb4'), (1, 12, 2, 'D5'), (1, 14, 2, 'F5'),
          (2, 0, 6, 'G5'), (2, 6, 2, 'F5'), (2, 8, 4, 'Eb5'), (2, 12, 4, 'C5'),
          (3, 0, 6, 'Eb5'), (3, 6, 2, 'C5'), (3, 8, 6, 'D5'),
          (4, 2, 2, 'C5'), (4, 4, 2, 'Eb5'), (4, 6, 6, 'Bb5'), (4, 12, 2, 'Ab5'), (4, 14, 2, 'G5'),
          (5, 0, 6, 'F5'), (5, 6, 2, 'D5'), (5, 8, 4, 'E5'), (5, 12, 4, 'G5'),
          (6, 0, 8, 'Ab5'), (6, 8, 2, 'G5'), (6, 10, 2, 'F5'), (6, 12, 4, 'Eb5'),
          (7, 0, 8, 'F5'), (7, 8, 6, 'D5')]
    RIFF = [(0, 0, 1, 'Eb6'), (0, 1, 1, 'C6'), (0, 2, 2, 'Bb5'), (0, 4, 1, 'G5'), (0, 5, 2, 'Bb5'), (0, 7, 3, 'C6'),
            (0, 10, 2, 'Bb5'), (0, 12, 2, 'G5'), (0, 14, 2, 'F5'),
            (1, 0, 6, 'G5'), (1, 8, 2, 'Bb5'), (1, 10, 2, 'D6'), (1, 12, 4, 'D6'),
            (2, 0, 1, 'C6'), (2, 1, 1, 'Ab5'), (2, 2, 2, 'G5'), (2, 4, 1, 'F5'), (2, 5, 2, 'G5'), (2, 7, 3, 'Ab5'),
            (2, 10, 2, 'G5'), (2, 12, 2, 'Eb5'), (2, 14, 2, 'F5'),
            (3, 0, 6, 'G5'), (3, 8, 2, 'F5'), (3, 10, 2, 'D5'), (3, 12, 4, 'F5')]
    RIFF2 = [r for r in RIFF if r[0] < 3] + [(3, 0, 6, 'F5'), (3, 8, 2, 'Ab5'), (3, 10, 2, 'G5'), (3, 12, 4, 'F5')]

    def play_lead(mel, bar0, vel, cutoff, vib=0.18):
        prev_end = -10
        prev_f = None
        for (b, s0, d, nm) in mel:
            f = float(mtof(note(nm)))
            start = (bar0 + b) * 16 + s0
            legato = (start - prev_end) <= 0.5
            y = lead_note(f, S.sec(d / 4.0) * (0.98 if legato else 0.9), vel * (0.92 + 0.12 * rng.random()),
                          int(rng.integers(1 << 30)), f_prev=prev_f if legato else None, vib=vib if d >= 4 else 0.0,
                          cutoff=cutoff)
            ld.add(y, S.pos(bar0 + b, s0 / 4.0, jitter_ms=3))
            prev_end = start + d
            prev_f = f

    play_lead(VS, 0, 0.55, 2600)
    play_lead(CH, 16, 0.9, 5200)
    play_lead(RIFF, 32, 0.85, 4200)
    play_lead(RIFF2, 36, 0.85, 4200)

    # ------------------------------------------------------------------ mix
    ep_x = cfilt(S.buses['ep'].buf, 'hp', 110, 0.7)
    ep_x = cfilt(ep_x, 'hs', 3000, 0.7, 2.0)
    ep_x = chorus(ep_x, base_ms=9, depth_ms=2.0, rate=0.9, mix=0.45, seed=7)
    pd_x = cfilt(S.buses['pad'].buf, 'hp', 200, 0.7)
    bs_x = cfilt(S.buses['bass'].buf, 'hp', 32, 0.7)
    bs_x = cfilt(bs_x, 'lp', 3200, 0.7)
    bs_x = saturate(bs_x / (np.max(np.abs(bs_x)) + 1e-9), 1.3)
    dr_x = S.buses['drums'].buf
    br_x = cfilt(S.buses['brass'].buf, 'hp', 180, 0.7)
    ld_x = cfilt(S.buses['lead'].buf, 'hp', 160, 0.7)
    ld_x = chorus(ld_x, base_ms=8, depth_ms=1.6, rate=1.1, mix=0.4, seed=8)

    dr_x = set_lufs(dr_x, -19.5)
    bs_x = set_lufs(bs_x, -21.0)
    ep_x = set_lufs(ep_x, -21.5)
    pd_x = set_lufs(pd_x, -28.0)
    br_x = set_lufs(br_x, -23.0)
    ld_x = set_lufs(ld_x, -20.0)
    dly = int(S.spb * 0.75)
    ld_d = delay_taps(ld_x.mean(0), dly, fb=0.38, taps=4, lp=4000)
    ir = make_ir(t60=1.8, predelay=0.02, hf=0.85, seed=13)
    send = 0.2 * ep_x + 0.3 * pd_x + 0.25 * br_x + 0.3 * ld_x + 0.08 * dr_x
    wet = reverb(send, ir)
    mix = dr_x + bs_x + ep_x + pd_x + br_x + ld_x + 0.16 * ld_d + 0.45 * wet
    return mix, dict(name=NAME, bpm=108, key='Eb major (Abmaj9-Gm7-Fm9-Bb13; chorus with Dbmaj9 borrowed)', bars=40,
                     meter='4/4')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
