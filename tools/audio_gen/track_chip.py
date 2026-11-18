"""pixel_heart_8bit - chiptune, 140 BPM, C major, 48 bars (82.3 s).
2 pulse channels (duty 12.5/25/50 %, 60 Hz frame-stepped volume/pitch, delayed vibrato), 4-bit 32-step
triangle bass, 15-bit LFSR noise drums. Form: A | A' | B | B' | C (bVI-bVII-I bridge) | A''."""
import numpy as np
from scipy import signal
from synthlib import *
from instruments import *

NAME = 'pixel_heart_8bit'
FRAME = SR // 60  # 735 samples


def fq(x):
    n = len(x)
    return x[(np.arange(n) // FRAME) * FRAME]


def chip_pulse(f, dur, duty=0.25, vol=0.8, decay=0.0, sustain=1.0, vib=0.0, vib_delay=0.22, vib_rate=6.0,
               slide=0.0, duty_seq=None, rel=0.035):
    n_on = int(dur * SR)
    N = n_on + int(rel * SR)
    t = np.arange(N) / SR
    env = np.full(N, float(vol))
    if decay > 0:
        env *= sustain + (1 - sustain) * np.exp(-t / decay)
    env[n_on:] *= np.linspace(1, 0, N - n_on)
    env = np.round(fq(env) * 15) / 15
    semis = slide * np.exp(-t / 0.035) + vib * np.clip((t - vib_delay) / 0.12, 0, 1) * np.sin(TWOPI * vib_rate * t)
    fc = fq(f * 2 ** (semis / 12.0))
    if duty_seq is not None:
        k = np.minimum(np.arange(N) // FRAME, len(duty_seq) - 1)
        d = np.asarray(duty_seq)[k]
    else:
        d = duty
    y = osc_pulse(fc, N, d)
    y[:40] *= np.linspace(0, 1, 40)
    return y * env * 0.5


def chip_arp(freqs, dur, duty=0.25, vol=0.5, frames=1, decay=0.0, sustain=1.0, rel=0.03):
    n_on = int(dur * SR)
    N = n_on + int(rel * SR)
    t = np.arange(N) / SR
    step = (np.arange(N) // (FRAME * frames)) % len(freqs)
    fc = np.asarray(freqs, dtype=float)[step]
    env = np.full(N, float(vol))
    if decay > 0:
        env *= sustain + (1 - sustain) * np.exp(-t / decay)
    env[n_on:] *= np.linspace(1, 0, N - n_on)
    env = np.round(fq(env) * 15) / 15
    y = osc_pulse(fc, N, duty)
    y[:40] *= np.linspace(0, 1, 40)
    return y * env * 0.5


TRI_SEQ = np.array(list(range(15, -1, -1)) + list(range(0, 16)), dtype=float) / 7.5 - 1.0


def chip_tri(f, dur, f_end=None, sweep_t=0.05):
    n = int(dur * SR)
    os_ = 4
    t = np.arange(n * os_) / (SR * os_)
    if f_end is None:
        ph = t * f
    else:
        fc = f_end + (f - f_end) * np.exp(-t / sweep_t)
        ph = np.cumsum(fc) / (SR * os_)
    y = TRI_SEQ[(np.floor(ph * 32).astype(np.int64)) % 32]
    y = signal.resample_poly(y, 1, os_)[:n]
    k = min(80, n // 4)
    y[:k] *= np.linspace(0, 1, k)
    y[-k:] *= np.linspace(1, 0, k)
    return y


def lfsr(mode, n):
    reg = 1
    out = np.empty(n)
    tap = 6 if mode else 1
    for i in range(n):
        fb = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (fb << 14)
        out[i] = reg & 1
    return out * 2.0 - 1.0


NOISE_LONG = lfsr(0, 32767)
NOISE_SHORT = lfsr(1, 32767)


def chip_noise(rate, frames_env, mode=0):
    env = np.repeat(np.asarray(frames_env, dtype=float) / 15.0, FRAME)
    n = len(env)
    t = np.arange(n) / SR
    seq = NOISE_SHORT if mode else NOISE_LONG
    idx = np.floor(t * rate).astype(np.int64) % len(seq)
    y = seq[idx] * env
    y[:20] *= np.linspace(0, 1, 20)
    return fade_tail(y, 3)


def padd(a, b):
    n = max(len(a), len(b))
    return np.pad(a, (0, n - len(a))) + np.pad(b, (0, n - len(b)))


def render():
    S = Song(140, 4, 48, seed=33)
    L = S.L
    rng = S.rng
    E = S.spb / 2.0  # eighth note in samples

    CH = {'F': 'F A C', 'G': 'G B D', 'Em': 'E G B', 'Am': 'A C E', 'Dm': 'D F A', 'C': 'C E G', 'Ab': 'Ab C Eb',
          'Bb': 'Bb D F'}
    progA = ['F', 'G', 'Em', 'Am', 'Dm', 'G', 'C', 'C']
    progB = ['Am', 'F', 'G', 'C', 'Am', 'F', 'Dm', 'G']
    progC = ['Ab', 'Bb', 'C', 'C', 'Ab', 'Bb', 'G', 'G']
    prog = progA + progA + progB + progB + progC + progA
    sect = ['A'] * 8 + ['A2'] * 8 + ['B'] * 8 + ['B2'] * 8 + ['C'] * 8 + ['A3'] * 8

    def pcs(ch):
        return [note(x + '4') % 12 for x in CH[ch].split()]

    MA = [[(0, 1, 'C5'), (1, 1, 'F5'), (2, 2, 'A5'), (4, 1, 'G5'), (5, 1, 'A5'), (6, 2, 'C6')],
          [(0, 2, 'B5'), (2, 1, 'G5'), (3, 1, 'D5'), (4, 3, 'G5')],
          [(0, 1, 'E5'), (1, 1, 'G5'), (2, 2, 'B5'), (4, 1, 'A5'), (5, 1, 'B5'), (6, 2, 'D6')],
          [(0, 3, 'C6'), (3, 1, 'B5'), (4, 2, 'A5'), (6, 2, 'E5')],
          [(0, 1, 'F5'), (1, 1, 'A5'), (2, 2, 'D6'), (4, 1, 'C6'), (5, 1, 'A5'), (6, 2, 'F5')],
          [(0, 2, 'D6'), (2, 1, 'B5'), (3, 1, 'G5'), (4, 1, 'A5'), (5, 1, 'B5'), (6, 2, 'D6')],
          [(0, 3, 'E6'), (3, 1, 'D6'), (4, 2, 'C6'), (6, 2, 'G5')],
          [(0, 4, 'C6'), (6, 1, 'G4'), (7, 1, 'B4')]]
    MA2 = MA[:6] + [[(0, 2, 'E6'), (2, 2, 'G6'), (4, 1, 'E6'), (5, 1, 'D6'), (6, 2, 'C6')],
                    [(0, 4, 'C6'), (4, 1, 'G5'), (5, 1, 'E5'), (6, 1, 'C5'), (7, 1, 'E5')]]
    MB = [[(0, 1, 'A4'), (1, 1, 'C5'), (2, 1, 'E5'), (3, 2, 'A5'), (5, 1, 'G5'), (6, 2, 'E5')],
          [(0, 2, 'F5'), (2, 1, 'A5'), (3, 3, 'C6'), (6, 2, 'A5')],
          [(0, 1, 'B5'), (1, 1, 'A5'), (2, 2, 'G5'), (4, 2, 'D5'), (6, 2, 'G5')],
          [(0, 2, 'E5'), (2, 2, 'G5'), (4, 4, 'C6')],
          [(0, 1, 'A5'), (1, 1, 'C6'), (2, 2, 'E6'), (4, 1, 'D6'), (5, 1, 'C6'), (6, 2, 'A5')],
          [(0, 2, 'C6'), (2, 1, 'A5'), (3, 3, 'F5'), (6, 1, 'A5'), (7, 1, 'C6')],
          [(0, 2, 'D6'), (2, 1, 'C6'), (3, 1, 'A5'), (4, 2, 'F5'), (6, 2, 'A5')],
          [(0, 3, 'B5'), (3, 1, 'A5'), (4, 4, 'G5')]]
    MB2 = MB[:6] + [[(0, 1, 'F5'), (1, 1, 'A5'), (2, 2, 'D6'), (4, 2, 'E6'), (6, 2, 'F6')],
                    [(0, 4, 'G6'), (4, 1, 'F6'), (5, 1, 'E6'), (6, 2, 'D6')]]
    MC = [[(0, 4, 'C6'), (4, 2, 'Eb6'), (6, 2, 'C6')],
          [(0, 4, 'D6'), (4, 2, 'F6'), (6, 2, 'D6')],
          [(0, 4, 'E6'), (4, 1, 'D6'), (5, 1, 'E6'), (6, 2, 'G6')],
          [(0, 6, 'E6'), (6, 1, 'D6'), (7, 1, 'C6')],
          [(0, 4, 'Eb6'), (4, 2, 'C6'), (6, 2, 'Ab5')],
          [(0, 4, 'F6'), (4, 2, 'D6'), (6, 2, 'Bb5')],
          [(0, 2, 'B5'), (2, 2, 'D6'), (4, 4, 'G6')],
          [(0, 3, 'G6'), (3, 1, 'D6'), (4, 1, 'B5'), (5, 1, 'G5'), (6, 1, 'G4'), (7, 1, 'B4')]]
    melody = MA + MA2 + MB + MB2 + MC + MA

    p1 = S.bus('p1')
    p2 = S.bus('p2')
    tr = S.bus('tri')
    nz = S.bus('noise')

    duty_of = {'A': 0.125, 'A2': 0.25, 'B': 0.5, 'B2': 0.25, 'C': 0.5, 'A3': 0.25}
    C_SCALE = [0, 2, 4, 5, 7, 9, 11]

    def third_below(m):
        pc = m % 12
        if pc not in C_SCALE:
            return m - 3
        i = C_SCALE.index(pc)
        j = (i - 2) % 7
        d = (C_SCALE[i] - C_SCALE[j]) % 12
        return m - d

    for bar in range(48):
        sc = sect[bar]
        for (s8, d8, nm) in melody[bar]:
            m = note(nm)
            f = float(mtof(m))
            dur = d8 * E / SR - 0.012
            long_ = d8 >= 3
            dseq = None
            if sc in ('A2', 'A3') and d8 >= 2:
                dseq = [0.125, 0.125, 0.25, 0.25, 0.25, 0.5]
            y = chip_pulse(f, dur, duty=duty_of[sc], vol=0.85, decay=0.25 if not long_ else 0.6, sustain=0.65,
                           vib=0.22 if long_ else 0.0, slide=-0.6 if (d8 >= 2 and rng.random() < 0.35) else 0.0,
                           duty_seq=dseq)
            pos = S.pos(bar, s8 / 2.0)
            p1.add(y, pos, pan=-0.12)
            if sc == 'A2':  # echo channel
                p2.add(chip_pulse(f, dur, duty=0.5, vol=0.4, decay=0.25, sustain=0.6), pos + 3 * FRAME * 4, pan=0.45)
            if sc == 'A3':  # harmony a third below
                h = third_below(m)
                p2.add(chip_pulse(float(mtof(h)), dur, duty=0.25, vol=0.5, decay=0.3, sustain=0.65,
                                  vib=0.15 if long_ else 0.0), pos, pan=0.4)
            if sc == 'C':
                p2.add(chip_pulse(f / 2, dur, duty=0.125, vol=0.35, decay=0.4, sustain=0.6), pos + 2 * E / 2, pan=0.5)

        chd = prog[bar]
        tones = pcs(chd)
        root = note(CH[chd].split()[0] + '2')
        if root < note('E2'):
            root += 12
        # pulse 2 accompaniment
        if sc == 'A':
            fr = [float(mtof(note('C4') + ((pc - 0) % 12))) for pc in tones]
            for s8 in (1, 3, 5, 7):
                p2.add(chip_arp(fr, E / SR * 0.7, duty=0.25, vol=0.45, frames=1, decay=0.08, sustain=0.3),
                       S.pos(bar, s8 / 2.0), pan=0.4)
        elif sc in ('B', 'B2'):
            arp = sorted([note('C5') + ((pc - 0) % 12) for pc in tones])
            seq = [0, 1, 2, 1, 0, 1, 2, 1] if sc == 'B' else [0, 1, 2, 0, 1, 2, 0, 1]
            octs = [0, 0, 0, 12, 0, 0, 0, 12]
            for k in range(16):
                m = arp[seq[k % 8]] + (12 if (k % 4 == 3) else 0)
                p2.add(chip_pulse(float(mtof(m)), S.spb / 4 / SR * 0.8, duty=0.125, vol=0.42, decay=0.06, sustain=0.2),
                       S.pos(bar, k / 4.0), pan=0.4)
        elif sc == 'C':
            fr = [float(mtof(note('C4') + ((pc - 0) % 12))) for pc in tones]
            p2.add(chip_arp(fr, 4 * S.spb / SR * 0.98, duty=0.5, vol=0.3, frames=2, decay=1.2, sustain=0.5),
                   S.pos(bar, 0), pan=0.45)
        # triangle bass
        if sc in ('A', 'A2', 'A3'):
            for s8 in range(8):
                m = root + (12 if s8 % 2 else 0)
                tr.add(chip_tri(float(mtof(m)), E / SR * 0.85), S.pos(bar, s8 / 2.0))
        elif sc in ('B', 'B2'):
            fifth = root + 7
            for (s8, d8, m) in [(0, 1, root), (2, 1, root), (3, 1, fifth), (5, 1, root), (6, 1, root + 12), (7, 1, fifth)]:
                tr.add(chip_tri(float(mtof(m)), d8 * E / SR * 0.85), S.pos(bar, s8 / 2.0))
        else:
            for (s8, d8, m) in [(0, 3, root), (3, 1, root), (4, 2, root + 12), (6, 2, root + 7)]:
                tr.add(chip_tri(float(mtof(m)), d8 * E / SR * 0.9), S.pos(bar, s8 / 2.0))

        # noise drums (16 steps)
        K = {0: 1.0, 6: 0.7, 8: 0.9}
        SN = {4: 1.0, 12: 1.0}
        H = {s: (0.7 if s % 4 == 2 else 0.45) for s in range(0, 16, 2)}
        if sc in ('B', 'B2'):
            H = {s: (0.7 if s % 4 == 2 else 0.4) for s in range(16)}
        if sc == 'C':
            K = {0: 1.0, 4: 0.9, 8: 1.0, 12: 0.9}
            H = {s: 0.75 for s in (2, 6, 10, 14)}
        if sc == 'A' and bar < 2:
            K = {0: 1.0, 8: 0.8}
        if bar % 8 == 7:
            SN = {4: 1.0, 8: 0.6, 10: 0.7, 12: 0.85, 13: 0.7, 14: 0.9, 15: 1.0}
            H = {s: v for s, v in H.items() if s < 8}
        for s0, v in K.items():
            kk = padd(chip_tri(150.0, 0.09, f_end=45.0, sweep_t=0.025) * 0.9, chip_noise(200000, [11, 6, 2, 0]) * 0.25)
            nz.add(kk * v, S.pos(bar, s0 / 4.0))
        for s0, v in SN.items():
            rate = 9000 + 1200 * (s0 - 8) if (bar % 8 == 7 and s0 >= 8) else 11000
            sn = chip_noise(rate, [15, 13, 11, 9, 8, 7, 6, 5, 4, 3, 2, 1, 1, 0])
            sn = padd(sn, 0.4 * chip_tri(200.0, 0.05, f_end=120, sweep_t=0.03))
            nz.add(sn * v * 0.6, S.pos(bar, s0 / 4.0))
        for s0, v in H.items():
            hh = chip_noise(150000 if sc != 'C' else 90000, [9, 5, 2, 1, 0] if sc != 'C' else [10, 8, 6, 4, 3, 2, 1, 0],
                            mode=1 if (sc == 'C' and s0 % 4 == 2) else 0)
            nz.add(hh * v * 0.3, S.pos(bar, s0 / 4.0), pan=0.15)

    # ------------------------------------------------------------------ mix
    def nes_out(x):
        x = cfilt(x, 'hp', 38, 0.7)
        return cfilt(x, 'lp', 13500, 0.7)

    p1_x = set_lufs(nes_out(S.buses['p1'].buf), -20.0)
    p2_x = set_lufs(nes_out(S.buses['p2'].buf), -24.0)
    tr_x = set_lufs(nes_out(S.buses['tri'].buf), -21.5)
    nz_x = set_lufs(nes_out(S.buses['noise'].buf), -21.5)
    ir = make_ir(t60=0.9, predelay=0.008, hf=0.8, seed=9)
    wet = reverb(0.18 * p1_x + 0.25 * p2_x + 0.08 * nz_x, ir)
    echo = delay_taps(p1_x.mean(0), int(S.spb * 0.75), fb=0.3, taps=2, lp=6000)
    mix = p1_x + p2_x + tr_x + nz_x + 0.45 * wet + 0.12 * echo
    return mix, dict(name=NAME, bpm=140, key='C major (IV-V-iii-vi; bVI-bVII-I bridge)', bars=48, meter='4/4')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
