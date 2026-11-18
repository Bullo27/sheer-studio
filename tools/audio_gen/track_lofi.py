"""sakura_lofi - lo-fi hip hop, 80 BPM, F major, 4/4, 32 bars (96 s).
Form: A (chords + fills) | A' (koto melody) | B (flute melody, relative-minor turn) | A'' (koto + flute line)."""
import numpy as np
from synthlib import *
from instruments import *

NAME = 'sakura_lofi'


def render():
    S = Song(80, 4, 32, seed=11)
    L = S.L
    rng = S.rng
    SW = 0.60

    def st(step):
        b = step / 4.0
        if int(round(step)) % 2 == 1:
            b += (SW - 0.5) * 0.5
        return b

    progA = [('Bb1', 'Bb2 A3 C4 D4 F4'),   # Bbmaj9
             ('C2', 'C3 Bb3 D4 F4 G4'),    # C9sus4
             ('A1', 'A2 G3 C4 D4 E4'),     # Am11
             ('D2', 'D3 F3 C4 E4 A4'),     # Dm9
             ('G1', 'G2 F3 A3 Bb3 D4'),    # Gm9
             ('C2', 'C3 Bb3 D4 E4 A4'),    # C13
             ('F1', 'F2 E3 G3 A3 C4'),     # Fmaj9
             ('F1', 'F2 Eb3 G3 A3 D4')]    # F13
    progB = [('D2', 'D3 C4 E4 F4 A4'),     # Dm9
             ('Bb1', 'Bb2 A3 C4 D4 F4'),   # Bbmaj9
             ('G1', 'G2 F3 A3 Bb3 D4'),    # Gm9
             ('A1', 'A2 G3 C#4 F4'),       # A7b13
             ('D2', 'D3 F3 A3 C4 E4'),     # Dm9
             ('Eb2', 'Eb3 D4 F4 G4 Bb4'),  # Ebmaj9
             ('G1', 'G2 F3 Bb3 C4 D4'),    # Gm11
             ('C2', 'C3 Bb3 D4 F4 A4')]    # C13sus4
    chords = progA + progA + progB + progA
    sect = ['A'] * 16 + ['B'] * 8 + ['A'] * 8
    roots = [note(c[0]) for c in chords]
    voic = [notes(c[1]) for c in chords]

    # ------------------------------------------------------------------ electric piano
    ep = S.bus('ep')
    pats = {1: [(0, 10, 0.70), (10, 6, 0.50)],
            2: [(0, 16, 0.66)],
            3: [(0, 7, 0.70), (7, 3, 0.42), (10, 6, 0.56)],
            4: [(0, 14, 0.68), (14, 2, 0.40)],
            5: [(0, 6, 0.66), (6, 10, 0.52)]}
    seqA = [2, 1, 2, 3, 2, 5, 2, 4]
    seqB = [1, 2, 3, 5, 1, 2, 3, 4]
    antic = {7, 15, 23, 31}
    pd = S.bus('pad')
    for bar in range(32):
        p = (seqB if sect[bar] == 'B' else seqA)[bar % 8]
        hits = list(pats[p])
        if (bar - 1) % 32 in antic:
            hits = [h for h in hits if h[0] != 0]
        if bar in antic:
            hits = [(s0, min(d, 14 - s0), v) for (s0, d, v) in hits if s0 < 14]
            nb = (bar + 1) % 32
            ep_chord(ep, S, voic[nb], S.pos(bar, st(14), jitter_ms=3), S.sec(4.0) - 0.05, vel=0.7, roll_ms=12,
                     bright=0.62, rel=0.45, pan_spread=0.55, seed=bar * 977, bark=0.22)
        for (s0, d, v) in hits:
            start = S.pos(bar, st(s0), jitter_ms=4)
            ep_chord(ep, S, voic[bar], start, S.sec(d / 4.0) - 0.03, vel=v, roll_ms=13, bright=0.62, rel=0.45,
                     pan_spread=0.55, seed=bar * 31 + s0, bark=0.22)
        for i, m in enumerate(voic[bar][1:]):
            y = pad_note(float(mtof(m)), S.sec(4.0) - 0.1, 0.5, seed=bar * 7 + i, att=0.7, rel=1.2, lp=1300)
            pd.add(y, S.pos(bar, 0.0), pan=(i - 1.5) * 0.35)

    # ------------------------------------------------------------------ sub bass
    ba = S.bus('bass')
    for bar in range(32):
        r = roots[bar]
        nxt = roots[(bar + 1) % 32]
        pcs = {5, 7, 9, 10, 0, 2, 4} | ({1} if sect[bar] == 'B' else set())
        app = next(c for c in [nxt - 2, nxt - 1, nxt + 2, nxt + 1] if c % 12 in pcs)
        r = r + 12 if r < note('A1') else r
        app = app + 12 if app < note('A1') else app
        pat = [(0, 8.6, r, 0.95), (10, 3.6, r, 0.8), (14, 1.8, app, 0.64)]
        if bar % 4 == 1:
            pat.insert(1, (7, 1.6, r + 12, 0.45))
        for (s0, d, m, v) in pat:
            y = sub_bass(float(mtof(m)), S.sec(d / 4.0), v, rel=0.07, harm=0.14)
            ba.add(y, S.pos(bar, st(s0), jitter_ms=3))

    # ------------------------------------------------------------------ drums
    dr = S.bus('drums')
    kicks = [filt(drum_kick(f_end=50, f_start=128, tau_p=0.03, t60=0.42, click=0.12, drive=1.4, seed=s), 'lp', 3200)
             for s in range(3)]
    snares = [filt(drum_snare(tone_f=182, tone_amt=0.65, noise_t60=0.19, n_lo=900, n_hi=6500, seed=10 + s), 'lp', 6200)
              for s in range(3)]
    rims = [drum_rim(seed=20 + s) for s in range(2)]
    hats = [filt(drum_hat(t60=0.05, metal=0.3, fc=8500, hp=5200, seed=30 + s), 'lp', 12500) for s in range(4)]
    ohat = filt(drum_hat(dur=0.4, t60=0.32, metal=0.35, fc=8000, hp=5200, seed=40), 'lp', 10000)
    shk = [drum_shaker(seed=50 + s, fc=6000) for s in range(3)]
    for bar in range(32):
        K = {0: 1.0, 7: 0.42, 10: 0.86}
        Sn = {4: 0.9, 12: 0.95}
        H = {0: .7, 2: .48, 4: .64, 6: .48, 8: .7, 10: .48, 12: .64, 14: .48, 3: .16, 11: .2, 15: .26}
        R = {}
        O = {}
        sh = {}
        if bar % 4 == 3:
            K = {0: 1.0, 10: 0.8, 13: 0.5}
            Sn[15] = 0.28
            H.pop(14)
            O[14] = 0.32
        if sect[bar] == 'B':
            K = {0: 1.0, 6: 0.5, 10: 0.82} if bar % 4 != 3 else K
            sh = {s: (0.5 if s % 2 == 0 else 0.3) for s in range(16)}
            R = {7: 0.35}
        if bar < 4:
            K.pop(7, None)
        if bar == 15:
            Sn.update({13: 0.22, 14: 0.32, 15: 0.42})
        if bar == 31:
            K = {0: 1.0, 10: 0.8}
            Sn.update({13: 0.22, 14: 0.3, 15: 0.4})
            H.pop(14, None)
            O[14] = 0.36
        for s0, v in K.items():
            dr.add(kicks[rng.integers(3)] * v, S.pos(bar, st(s0), jitter_ms=2))
        for s0, v in Sn.items():
            dr.add(snares[rng.integers(3)] * v * 0.8, S.pos(bar, st(s0), jitter_ms=3, late_ms=11), pan=0.03)
        for s0, v in R.items():
            dr.add(rims[rng.integers(2)] * v * 0.5, S.pos(bar, st(s0), jitter_ms=3), pan=-0.3)
        for s0, v in H.items():
            dr.add(hats[rng.integers(4)] * v * 0.4 * (0.85 + 0.3 * rng.random()), S.pos(bar, st(s0), jitter_ms=6),
                   pan=0.28)
        for s0, v in O.items():
            dr.add(ohat * v * 0.3, S.pos(bar, st(s0), jitter_ms=4), pan=0.3)
        for s0, v in sh.items():
            dr.add(shk[rng.integers(3)] * v * 0.16, S.pos(bar, st(s0), jitter_ms=5), pan=-0.35)

    # ------------------------------------------------------------------ koto melody (pentatonic)
    # (bar, beat, dur, note, bend_semitones)
    M1 = [(0, 0.5, 0.5, 'F5', 0), (0, 1.0, 0.5, 'G5', 0), (0, 1.5, 1.5, 'A5', 2), (0, 3.0, 0.5, 'C6', 0),
          (0, 3.5, 0.5, 'A5', 0),
          (1, 0.0, 1.5, 'G5', 2), (1, 2.0, 0.5, 'D5', 0), (1, 2.5, 0.5, 'F5', 0), (1, 3.0, 1.0, 'G5', 0),
          (2, 0.5, 0.5, 'A5', 0), (2, 1.0, 0.5, 'C6', 0), (2, 1.5, 1.5, 'D6', 2), (2, 3.0, 0.5, 'C6', 0),
          (2, 3.5, 0.5, 'A5', 0),
          (3, 0.0, 1.0, 'C6', 0), (3, 1.0, 1.0, 'A5', 0), (3, 2.0, 2.0, 'G5', 1),
          (4, 0.5, 0.5, 'F5', 0), (4, 1.0, 0.5, 'G5', 0), (4, 1.5, 1.5, 'A5', 2), (4, 3.0, 0.5, 'C6', 0),
          (4, 3.5, 0.5, 'D6', 0),
          (5, 0.0, 1.5, 'C6', 0), (5, 1.5, 0.5, 'A5', 0), (5, 2.0, 1.0, 'G5', 0), (5, 3.0, 1.0, 'A5', 0),
          (6, 0.0, 1.0, 'G5', 0), (6, 1.0, 1.0, 'A5', 0), (6, 2.0, 1.5, 'C6', 2), (6, 3.5, 0.5, 'A5', 0),
          (7, 0.0, 3.0, 'F5', 2)]
    M1v = [m for m in M1 if m[0] < 6] + [
        (6, 0.0, 1.0, 'A5', 0), (6, 1.0, 0.5, 'G5', 0), (6, 1.5, 0.5, 'A5', 0), (6, 2.0, 2.0, 'C6', 2),
        (7, 0.0, 0.5, 'A5', 0), (7, 0.5, 0.5, 'G5', 0), (7, 1.0, 2.5, 'F5', 1)]
    fills = [(3, 2.5, 0.5, 'C6', 0), (3, 3.0, 0.5, 'D6', 0), (3, 3.5, 0.5, 'F6', 0),
             (7, 2.0, 0.5, 'C6', 0), (7, 2.5, 0.5, 'A5', 0), (7, 3.0, 1.0, 'G5', 1)]
    ko = S.bus('koto')

    def play_koto(mel, bar0, vel=0.75, octave=0):
        for (b, bt, d, nm, bend) in mel:
            m = note(nm) + 12 * octave
            f = float(mtof(m))
            ring = S.sec(d) + 0.5
            v = vel * (0.85 + 0.2 * rng.random())
            bd = (bend, 0.025, 0.09) if bend else None
            y = koto_note(f, ring, v, seed=int(rng.integers(1 << 30)), bend=bd, yuri=0.12 if d >= 2 else 0.0,
                          bright=6500)
            ko.add(y, S.pos(bar0 + b, st(bt * 4), jitter_ms=5), pan=-0.22)

    play_koto(fills, 0, 0.6)
    play_koto(M1, 8, 0.78)
    play_koto(M1v, 24, 0.8)

    # ------------------------------------------------------------------ flute
    fl = S.bus('flute')
    M2 = [(0, 0, 2.0, 'A4'), (0, 2, 1.0, 'C5'), (0, 3, 1.0, 'D5'),
          (1, 0, 2.5, 'F5'), (1, 2.5, 0.5, 'D5'), (1, 3, 1.0, 'C5'),
          (2, 0, 2.0, 'D5'), (2, 2, 1.0, 'A4'), (2, 3, 1.0, 'C5'),
          (3, 0, 1.5, 'E5'), (3, 1.5, 0.5, 'F5'), (3, 2, 1.0, 'E5'), (3, 3, 1.0, 'C#5'),
          (4, 0, 3.0, 'D5'), (4, 3, 0.5, 'E5'), (4, 3.5, 0.5, 'F5'),
          (5, 0, 2.0, 'G5'), (5, 2, 1.0, 'F5'), (5, 3, 1.0, 'D5'),
          (6, 0, 1.5, 'C5'), (6, 1.5, 0.5, 'D5'), (6, 2, 1.0, 'F5'), (6, 3, 1.0, 'G5'),
          (7, 0, 2.0, 'G5'), (7, 2, 1.0, 'F5'), (7, 3, 1.0, 'D5')]
    pad = [(0, 0, 3.8, 'D5'), (1, 0, 3.8, 'C5'), (2, 0, 3.8, 'C5'), (3, 0, 3.8, 'A4'), (4, 0, 3.8, 'Bb4'),
           (5, 0, 3.8, 'Bb4'), (6, 0, 3.8, 'A4'), (7, 0, 3.0, 'A4')]

    def play_flute(mel, bar0, vel, breath=0.24):
        for (b, bt, d, nm) in mel:
            f = float(mtof(note(nm)))
            dur = S.sec(d) * 0.97
            y = flute_note(f, dur, vel * (0.9 + 0.15 * rng.random()), seed=int(rng.integers(1 << 30)), breath=breath,
                           scoop=-0.6 if d >= 1 else -0.25, attack=0.06 if d >= 1 else 0.03)
            fl.add(y, S.pos(bar0 + b, bt, jitter_ms=6), pan=0.22)

    play_flute(M2, 16, 0.8)
    play_flute(pad, 24, 0.33, breath=0.3)

    # ------------------------------------------------------------------ stem processing & mix
    ep_x = S.buses['ep'].buf
    ep_x = cfilt(ep_x, 'hp', 85, 0.7)
    ep_x = cfilt(ep_x, 'ls', 260, 0.7, -3.0)
    ep_x = cfilt(ep_x, 'lp', 5200, 0.6)
    ep_x = autopan(ep_x, 3.4, 0.25, L)
    ba_x = cfilt(S.buses['bass'].buf, 'lp', 420, 0.7)
    ba_x = saturate(ba_x / (np.max(np.abs(ba_x)) + 1e-9), 1.3) * 0.5
    dr_x = S.buses['drums'].buf
    dr_x = dr_x / (np.max(np.abs(dr_x)) + 1e-9)
    dr_x = 0.75 * saturate(dr_x, 1.6) + 0.25 * bitcrush(dr_x, 10, 2)
    dr_x = cfilt(dr_x, 'lp', 12000, 0.6)
    ko_x = cfilt(koto_body(S.buses['koto'].buf), 'lp', 7500, 0.6)
    fl_x = cfilt(S.buses['flute'].buf, 'hp', 200, 0.7)
    pd_x = cfilt(S.buses['pad'].buf, 'hp', 150, 0.7)
    pd_x = chorus(pd_x, base_ms=14, depth_ms=3, rate=0.35, mix=0.5, seed=4)

    dr_x = set_lufs(dr_x, -20.5)
    ba_x = set_lufs(ba_x, -23.0)
    ep_x = set_lufs(ep_x, -20.0)
    ko_x = set_lufs(ko_x, -21.0)
    pd_x = set_lufs(pd_x, -28.0)
    fl_x = set_lufs(fl_x, -23.0)

    dly = S.spb * 3 // 4
    ko_d = delay_taps(ko_x.mean(0), dly, fb=0.42, taps=4, lp=3500)
    fl_d = delay_taps(fl_x.mean(0), dly, fb=0.35, taps=3, lp=3000)
    ir = make_ir(t60=1.9, predelay=0.018, hf=0.55, seed=5)
    send = 0.22 * ep_x + 0.3 * pd_x + 0.4 * ko_x + 0.45 * fl_x + 0.12 * dr_x + 0.18 * (ko_d + fl_d)
    wet = reverb(send, ir)
    music = dr_x + ba_x + ep_x + pd_x + ko_x + fl_x + 0.22 * ko_d + 0.18 * fl_d + 0.55 * wet
    music = wow_flutter(music, wow_ms=0.75, wow_hz=0.42, flut_ms=0.05, flut_hz=6.3, seed=3)
    music = cfilt(music, 'lp', 13000, 0.6)
    music = set_lufs(music, -16.0)
    vin = set_lufs(vinyl(L, rng), -41.0)
    mix = music + vin
    return mix, dict(name=NAME, bpm=80, key='F major (Bbmaj9-C9sus4-Am11-Dm9 / D minor turn)', bars=32, meter='4/4')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
