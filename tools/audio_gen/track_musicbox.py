"""music_box_dream - music-box / celesta lullaby, 3/4 at 84 BPM, G major, 40 bars (85.7 s).
Form: A | A' (cadence) | B (minor colour) | B' (borrowed iv: Cm) | A'' (glockenspiel doubling)."""
import numpy as np
from synthlib import *
from instruments import *

NAME = 'music_box_dream'


def musicbox_note(f, vel, seed):
    T = float(np.clip(4.8 * (523.0 / f) ** 0.7, 1.3, 7.0))
    return modal(f, T + 0.3, ratios=[1.0, 2.003, 6.27, 17.55], amps=[1.0, 0.05, 0.3, 0.09],
                 t60s=[T, T * 0.45, T * 0.17, T * 0.06], vel=vel, attack=0.0003, seed=seed, click=0.12,
                 click_fc=6500.0, beat_cents=1.3, beat_amt=0.3, detune_cents=np.random.default_rng(seed).normal(0, 1.5))


def celesta_note(f, vel, seed):
    T = float(np.clip(3.2 * (523.0 / f) ** 0.6, 1.0, 5.5))
    return modal(f, T + 0.3, ratios=[1.0, 2.0, 2.76, 5.40], amps=[1.0, 0.08, 0.07, 0.025],
                 t60s=[T, T * 0.4, T * 0.2, T * 0.08], vel=vel, attack=0.0025, seed=seed, click=0.04, click_fc=3000.0)


def glock_note(f, vel, seed):
    return modal(f, 3.2, ratios=[1.0, 2.76, 5.40, 8.93], amps=[1.0, 0.28, 0.1, 0.04], t60s=[3.0, 0.9, 0.35, 0.15],
                 vel=vel, attack=0.0002, seed=seed, click=0.2, click_fc=8000.0)


def render():
    S = Song(84, 3, 40, seed=44)
    L = S.L
    rng = S.rng
    E = 0.5  # eighth in beats

    # chord: (bass, [triad pcs as names], arp root)
    C = {'G': ('G2', 'G B D'), 'Em': ('E2', 'E G B'), 'C': ('C3', 'C E G'), 'D': ('D2', 'D F# A'),
         'G/B': ('B2', 'G B D'), 'Am7': ('A2', 'A C E G'), 'D7': ('D2', 'D F# A C'), 'Am': ('A2', 'A C E'),
         'Dsus': ('D2', 'D G A'), 'D/F#': ('F#2', 'D F# A'), 'Cm': ('C3', 'C Eb G'), 'G/D': ('D2', 'G B D')}
    A = [['G'], ['Em'], ['C'], ['D'], ['G/B'], ['C'], ['Am7'], ['D7']]
    A2 = [['G'], ['Em'], ['C'], ['D'], ['Em'], ['C'], ['Am7', 'D7'], ['G']]
    B = [['Em'], ['C'], ['G'], ['D'], ['Em'], ['C'], ['Am'], ['Dsus', 'D']]
    B2 = [['Em'], ['C'], ['G'], ['D/F#'], ['Em'], ['Cm'], ['G/D'], ['D7']]
    prog = A + A2 + B + B2 + A2
    sect = ['A'] * 8 + ['A2'] * 8 + ['B'] * 8 + ['B2'] * 8 + ['A3'] * 8

    # melody: (bar, start_8th, dur_8ths, note)
    MA = [(0, 0, 3, 'B5'), (0, 3, 1, 'A5'), (0, 4, 2, 'G5'),
          (1, 0, 2, 'E5'), (1, 2, 2, 'G5'), (1, 4, 2, 'B5'),
          (2, 0, 3, 'C6'), (2, 3, 1, 'B5'), (2, 4, 1, 'A5'), (2, 5, 1, 'G5'),
          (3, 0, 4, 'A5'), (3, 4, 2, 'F#5'),
          (4, 0, 3, 'D6'), (4, 3, 1, 'B5'), (4, 4, 2, 'G5'),
          (5, 0, 2, 'E5'), (5, 2, 2, 'C6'), (5, 4, 1, 'B5'), (5, 5, 1, 'A5'),
          (6, 0, 2, 'G5'), (6, 2, 2, 'E5'), (6, 4, 2, 'A5'),
          (7, 0, 3, 'F#5'), (7, 3, 1, 'E5'), (7, 4, 2, 'D5')]
    MA2 = [m for m in MA if m[0] < 3] + [
        (3, 0, 4, 'A5'), (3, 4, 2, 'D6'),
        (4, 0, 3, 'B5'), (4, 3, 1, 'G5'), (4, 4, 2, 'E5'),
        (5, 0, 2, 'C6'), (5, 2, 2, 'E6'), (5, 4, 1, 'D6'), (5, 5, 1, 'C6'),
        (6, 0, 2, 'B5'), (6, 2, 2, 'A5'), (6, 4, 2, 'F#5'),
        (7, 0, 4, 'G5'), (7, 4, 1, 'F#5'), (7, 5, 1, 'A5')]
    MB = [(0, 0, 1, 'G5'), (0, 1, 1, 'A5'), (0, 2, 2, 'B5'), (0, 4, 2, 'E6'),
          (1, 0, 2, 'D6'), (1, 2, 2, 'C6'), (1, 4, 2, 'G5'),
          (2, 0, 1, 'B5'), (2, 1, 1, 'C6'), (2, 2, 2, 'D6'), (2, 4, 2, 'B5'),
          (3, 0, 3, 'A5'), (3, 3, 1, 'F#5'), (3, 4, 2, 'A5'),
          (4, 0, 1, 'G5'), (4, 1, 1, 'A5'), (4, 2, 2, 'B5'), (4, 4, 2, 'E6'),
          (5, 0, 2, 'D6'), (5, 2, 2, 'C6'), (5, 4, 2, 'G5'),
          (6, 0, 2, 'C6'), (6, 2, 1, 'B5'), (6, 3, 1, 'A5'), (6, 4, 2, 'E5'),
          (7, 0, 3, 'G5'), (7, 3, 3, 'F#5')]
    MB2 = [m for m in MB if m[0] < 4] + [
        (4, 0, 2, 'B5'), (4, 2, 2, 'G5'), (4, 4, 2, 'E5'),
        (5, 0, 3, 'C6'), (5, 3, 1, 'G5'), (5, 4, 2, 'Eb5'),
        (6, 0, 2, 'D5'), (6, 2, 2, 'G5'), (6, 4, 2, 'B5'),
        (7, 0, 2, 'A5'), (7, 2, 1, 'C6'), (7, 3, 1, 'B5'), (7, 4, 2, 'A5')]
    mel = [(b, s, d, n) for (b, s, d, n) in MA] + [(b + 8, s, d, n) for (b, s, d, n) in MA2] + \
          [(b + 16, s, d, n) for (b, s, d, n) in MB] + [(b + 24, s, d, n) for (b, s, d, n) in MB2] + \
          [(b + 32, s, d, n) for (b, s, d, n) in MA2]

    mb = S.bus('musicbox')
    gl = S.bus('glock')
    for (b, s8, d8, nm) in mel:
        m = note(nm)
        v = 0.8 if s8 == 0 else 0.68
        v *= 0.9 + 0.15 * rng.random()
        pos = S.pos(b, s8 * E, jitter_ms=2)
        mb.add(musicbox_note(float(mtof(m)), v, int(rng.integers(1 << 30))), pos, pan=0.12 * np.sin(m))
        if sect[b] == 'A3' and s8 % 2 == 0 and rng.random() < 0.6:
            gl.add(glock_note(float(mtof(m + 12)), 0.3, int(rng.integers(1 << 30))), pos, pan=0.35)

    # celesta waltz arpeggio + strings + bass
    ce = S.bus('celesta')
    st = S.bus('strings')
    ba = S.bus('bass')
    for bar in range(40):
        chs = prog[bar]
        n8 = 6 // len(chs)
        for ci, cname in enumerate(chs):
            bass, tones = C[cname]
            pcs = [note(x + '4') % 12 for x in tones.split()]
            root3 = 48 + pcs[0] if pcs[0] >= 5 else 48 + pcs[0] + 12 - 12
            third = root3 + ((pcs[1] - pcs[0]) % 12)
            fifth = root3 + ((pcs[2] - pcs[0]) % 12)
            arp = [root3, fifth, root3 + 12, third + 12, root3 + 12, fifth]
            if len(pcs) > 3:
                arp[4] = root3 + ((pcs[3] - pcs[0]) % 12)
            for k in range(n8):
                s8 = ci * n8 + k
                m = arp[s8 % 6]
                v = (0.62 if s8 == 0 else 0.45) * (0.9 + 0.15 * rng.random())
                ce.add(celesta_note(float(mtof(m)), v, int(rng.integers(1 << 30))), S.pos(bar, s8 * E, jitter_ms=3),
                       pan=-0.3 + 0.1 * (k % 3))
            # strings: 4-note voicing around G3..D5
            vs = []
            for pc in pcs[:4]:
                mm = 55 + ((pc - 7) % 12)
                vs.append(mm)
            vs = sorted(vs)
            dur_b = 3.0 * n8 / 6
            swell = 0.6 if sect[bar] in ('B', 'B2') else 0.45
            for i, mm in enumerate(vs):
                st.add(pad_note(float(mtof(mm)), S.sec(dur_b) + 0.15, swell, seed=bar * 13 + i + ci * 5, n=4, det=7.0,
                                att=0.6, rel=1.4, lp=2300, vib=0.0035),
                       S.pos(bar, ci * dur_b), pan=(i - 1.5) * 0.4)
            bm = note(bass)
            y = sub_bass(float(mtof(bm)), S.sec(dur_b) * 0.95, 0.8, rel=0.5, harm=0.25, a=0.03)
            ba.add(y, S.pos(bar, ci * dur_b))
        # glock sparkle at phrase ends
        if bar % 8 == 7:
            cname = chs[-1]
            pcs = [note(x + '4') % 12 for x in C[cname][1].split()]
            run = sorted([note('C6') + pc for pc in pcs] + [note('C7') + pcs[0]])
            for k, m in enumerate(run):
                gl.add(glock_note(float(mtof(m)), 0.35 + 0.08 * k, int(rng.integers(1 << 30))),
                       S.pos(bar, 2.0 + k * 0.25), pan=-0.4 + 0.25 * k)

    # ------------------------------------------------------------------ mix
    mb_x = cfilt(S.buses['musicbox'].buf, 'hp', 180, 0.7)
    mb_x = cfilt(mb_x, 'peak', 2500, 1.0, -1.5)
    ce_x = cfilt(S.buses['celesta'].buf, 'hp', 110, 0.7)
    st_x = cfilt(S.buses['strings'].buf, 'hp', 130, 0.7)
    st_x = chorus(st_x, base_ms=13, depth_ms=3.0, rate=0.4, mix=0.5, seed=2)
    ba_x = cfilt(S.buses['bass'].buf, 'lp', 350, 0.7)
    gl_x = cfilt(S.buses['glock'].buf, 'hp', 600, 0.7)

    mb_x = set_lufs(mb_x, -19.5)
    ce_x = set_lufs(ce_x, -23.5)
    st_x = set_lufs(st_x, -24.0)
    ba_x = set_lufs(ba_x, -26.0)
    gl_x = set_lufs(gl_x, -29.0)
    ir = make_ir(t60=3.2, predelay=0.03, hf=0.75, seed=12)
    send = 0.4 * mb_x + 0.4 * ce_x + 0.6 * st_x + 0.6 * gl_x
    wet = reverb(send, ir)
    dly = delay_taps(mb_x.mean(0), S.spb, fb=0.35, taps=3, lp=4000)
    mix = mb_x + ce_x + st_x + ba_x + gl_x + 0.7 * wet + 0.12 * dly
    return mix, dict(name=NAME, bpm=84, key='G major (borrowed Cm in B\')', bars=40, meter='3/4')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
