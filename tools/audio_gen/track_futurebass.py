"""kawaii_future_bass - half-time future bass, 150 BPM, E major, 48 bars (76.8 s).
Form: verse (8) | build (8) | drop (16) | breakdown (8) | drop 2 'wobble' (8) -> verse."""
import numpy as np
from synthlib import *
from instruments import *

NAME = 'kawaii_future_bass'


def render():
    S = Song(150, 4, 48, seed=22)
    L = S.L
    rng = S.rng
    bar_n = S.spb * 4

    # (start_beat, bass, voicing)
    P = [[(0, 'A1', 'A3 E4 G#4 B4 C#5')],                      # Amaj9
         [(0, 'B1', 'B3 F#4 A4 C#5 D#5')],                     # B9
         [(0, 'G#1', 'G#3 D#4 F#4 B4 D#5')],                   # G#m7
         [(0, 'C#2', 'C#4 E4 G#4 B4 D#5')],                    # C#m9
         [(0, 'F#1', 'F#3 E4 G#4 A4 C#5')],                    # F#m9
         [(0, 'B1', 'B3 E4 F#4 A4 C#5'), (2, 'B1', 'B3 D#4 F#4 A4 C#5')],  # Bsus4 -> B7
         [(0, 'E2', 'E4 G#4 B4 D#5 F#5')],                     # Emaj9
         [(0, 'E2', 'E4 G#4 B4 D5 F#5')]]                      # E9 (-> IV)
    Q = [[(0, 'C#2', 'C#4 E4 G#4 B4 D#5')],
         [(0, 'A1', 'A3 E4 G#4 B4 C#5')],
         [(0, 'E2', 'E4 G#4 B4 D#5 F#5')],
         [(0, 'B1', 'B3 F#4 A4 C#5 D#5')],
         [(0, 'C#2', 'C#4 E4 G#4 B4 D#5')],
         [(0, 'A1', 'A3 E4 G#4 B4 C#5')],
         [(0, 'F#1', 'F#3 E4 G#4 A4 C#5')],
         [(0, 'B1', 'B3 E4 F#4 A4 C#5'), (2, 'B1', 'B3 D#4 F#4 A4 C#5')]]
    prog = P + P + P + P + Q + P
    sect = ['verse'] * 8 + ['build'] * 8 + ['drop'] * 16 + ['brk'] * 8 + ['drop2'] * 8

    def chord_at(bar, beat):
        segs = prog[bar]
        cur = segs[0]
        for sgm in segs:
            if beat >= sgm[0]:
                cur = sgm
        return note(cur[1]), notes(cur[2])

    # ------------------------------------------------------------------ supersaw chords
    ch = S.bus('chords')
    chb = Bus(L)  # build chords (filter sweep applied later)

    def saw_chord(bus, bar, beat0, beats, gate_steps, vel=1.0, att=0.004, rel=0.12, cutoff=(9000, 3500), detune=22,
                  wobble=None):
        """Continuous supersaw for the chord segment, gated by a stab pattern (list of (step, len))."""
        bm, vo = chord_at(bar, beat0)
        dur = S.sec(beats)
        n = int((dur + rel + 0.05) * SR)
        sig = np.zeros((2, n))
        for m in vo:
            sig += supersaw(float(mtof(m)), n, detune_cents=detune, rng=np.random.default_rng(int(rng.integers(1 << 30))))
        sig /= len(vo) ** 0.5
        # gate envelope + filter envelope
        g = np.zeros(n)
        fenv = np.zeros(n)
        step = S.spb / 4.0
        for (s0, sl) in gate_steps:
            i0 = int(s0 * step)
            if i0 >= n:
                continue
            e = env_adsr(sl * step / SR - 0.01, a=att, d=0.18, s=0.75, r=rel)
            k = min(len(e), n - i0)
            g[i0:i0 + k] = np.maximum(g[i0:i0 + k], e[:k])
            te = np.arange(k) / SR
            fenv[i0:i0 + k] = np.maximum(fenv[i0:i0 + k], np.exp(-te / 0.12))
        if wobble is not None:
            t = np.arange(n) / SR
            w = 0.5 + 0.5 * np.cos(TWOPI * wobble * t)
            g *= 0.25 + 0.75 * w
            fenv *= w
        fc = cutoff[1] + (cutoff[0] - cutoff[1]) * fenv
        out = np.vstack([tv_lp4(sig[c], fc, block=64) for c in range(2)]) * g * vel
        bus.add(out, S.pos(bar, beat0))

    stabA = [(0, 2), (3, 2), (6, 2), (8, 2), (11, 2), (14, 1.6)]
    stabB = [(0, 2), (3, 2), (6, 3), (10, 2), (12, 1.5), (14, 1.6)]
    for bar in range(48):
        sc = sect[bar]
        segs = prog[bar]
        for si, sgm in enumerate(segs):
            b0 = sgm[0]
            b1 = segs[si + 1][0] if si + 1 < len(segs) else 4
            nb = b1 - b0
            if sc in ('verse', 'brk'):
                saw_chord(ch, bar, b0, nb, [(0, nb * 4)], vel=0.55, att=0.05, rel=0.35, cutoff=(3200, 2400), detune=18)
            elif sc == 'build':
                steps = [(s, 1.6) for s in range(0, int(nb * 4), 2)] if bar < 14 else [(s, 0.9) for s in range(int(nb * 4))]
                saw_chord(chb, bar, b0, nb, steps, vel=0.75, rel=0.06, cutoff=(9000, 5000))
            elif sc == 'drop':
                pat = stabA if bar % 2 == 0 else stabB
                pat = [(s - b0 * 4, l) for (s, l) in pat if b0 * 4 <= s < b1 * 4]
                saw_chord(ch, bar, b0, nb, pat, vel=1.0, rel=0.08, cutoff=(10000, 3800))
            elif sc == 'drop2':
                saw_chord(ch, bar, b0, nb, [(0, nb * 4)], vel=0.95, att=0.01, rel=0.15, cutoff=(9000, 4200),
                          wobble=150.0 / 60.0 * 1.5)
    # build filter sweep: bars 8..15 (+1 s of tail)
    i0 = S.pos(8)
    seg_n = 8 * bar_n + SR
    seg = np.zeros((2, seg_n))
    idx = (int(i0) + np.arange(seg_n)) % L
    seg[:] = chb.buf[:, idx]
    tt = np.arange(seg_n) / (8 * bar_n)
    fc = 900 * (11000 / 900) ** np.clip(tt, 0, 1) ** 1.6
    seg = np.vstack([tv_lp4(seg[c], fc, block=64) for c in range(2)])
    ch.add(seg, i0)

    # ------------------------------------------------------------------ sub bass
    sb = S.bus('sub')
    for bar in range(48):
        sc = sect[bar]
        for si, sgm in enumerate(prog[bar]):
            b0 = sgm[0]
            b1 = prog[bar][si + 1][0] if si + 1 < len(prog[bar]) else 4
            r = note(sgm[1])
            r = r + 12 if r < note('E1') + 1 else r
            if sc == 'build' and bar >= 14:
                continue
            if sc in ('drop', 'drop2'):
                hits = [(0, 2.5), (2.5, 1.5)] if (b1 - b0) == 4 else [(0, b1 - b0)]
            else:
                hits = [(0, b1 - b0)]
            for (h0, hd) in hits:
                if b0 + h0 >= b1:
                    continue
                y = sub_bass(float(mtof(r)), S.sec(min(hd, b1 - b0 - h0)) - 0.02, 0.95, rel=0.05, harm=0.22)
                sb.add(y, S.pos(bar, b0 + h0))

    # ------------------------------------------------------------------ drums
    dr = S.bus('drums')
    kick = drum_kick(f_end=47, f_start=240, tau_p=0.022, t60=0.4, click=0.4, drive=2.2, seed=1)
    clap = [drum_clap(fc=1450, Q=1.0, tail_t60=0.28, seed=s) for s in range(3)]
    snr = [drum_snare(tone_f=215, tone_amt=0.5, noise_t60=0.17, n_lo=1500, n_hi=10000, seed=10 + s) for s in range(3)]
    hats = [drum_hat(t60=0.04, metal=0.55, fc=10500, hp=7500, seed=20 + s) for s in range(4)]
    ohat = drum_hat(dur=0.35, t60=0.26, metal=0.55, fc=10000, hp=7000, seed=30)
    crash = drum_crash(dur=2.6, t60=2.3, seed=40)
    pump_times = []
    for bar in range(48):
        sc = sect[bar]
        K, C, H, O, SN = {}, {}, {}, {}, {}
        if sc == 'verse':
            K = {0: 1.0, 10: 0.75}
            C = {8: 0.85}
            H = {s: (0.55 if s % 4 == 2 else 0.35) for s in range(0, 16, 2)}
            if bar % 4 == 3:
                H.update({13: 0.25, 15: 0.3})
        elif sc == 'build':
            if bar < 12:
                K = {0: 1.0, 10: 0.75}
                C = {8: 0.85}
                H = {s: 0.45 for s in range(0, 16, 2)}
            elif bar < 14:
                K = {0: 1.0, 8: 0.8}
                SN = {s: 0.35 + 0.25 * ((bar - 12) * 16 + s) / 32 for s in range(0, 16, 2)}
                H = {s: 0.4 for s in range(0, 16, 2)}
            elif bar == 14:
                SN = {s: 0.55 + 0.2 * s / 16 for s in range(16)}
            else:
                SN = {s / 2.0: 0.75 + 0.25 * s / 24 for s in range(24)}
        elif sc in ('drop', 'drop2'):
            K = {0: 1.0, 10: 0.9} if bar % 2 == 0 else {0: 1.0, 7: 0.7, 10: 0.9}
            C = {8: 1.0}
            H = {s: (0.6 if s % 4 == 2 else (0.4 if s % 2 == 0 else 0.25)) for s in range(16)}
            O = {14: 0.5} if bar % 2 == 1 else {}
            if bar % 8 == 7:
                SN = {12: 0.5, 13: 0.6, 14: 0.7, 15: 0.8}
        elif sc == 'brk':
            K = {0: 0.6} if bar % 2 == 0 else {}
            H = {s: 0.3 for s in range(2, 16, 4)}
            if bar == 39:
                SN = {s: 0.3 + 0.5 * s / 16 for s in range(8, 16)}
        if bar == 47:
            SN = {12: 0.45, 13: 0.55, 14: 0.65, 15: 0.75}
            H.pop(14, None)
            H.pop(15, None)
        for s0, v in K.items():
            dr.add(kick * v, S.pos(bar, s0 / 4.0))
            pump_times.append(S.pos(bar, s0 / 4.0))
        for s0, v in C.items():
            dr.add(clap[rng.integers(3)] * v * 0.8, S.pos(bar, s0 / 4.0, jitter_ms=1))
            dr.add(snr[rng.integers(3)] * v * 0.35, S.pos(bar, s0 / 4.0))
            if sc != 'verse':
                pump_times.append(S.pos(bar, s0 / 4.0))
        for s0, v in SN.items():
            sn = drum_snare(tone_f=200 + 140 * (bar % 4) / 3 + 3 * s0, tone_amt=0.45, noise_t60=0.12, n_lo=1500,
                            n_hi=10000, seed=int(rng.integers(1000)))
            dr.add(sn * v * 0.55, S.pos(bar, s0 / 4.0))
        for s0, v in H.items():
            dr.add(hats[rng.integers(4)] * v * 0.35, S.pos(bar, s0 / 4.0, jitter_ms=1.5), pan=0.25)
        for s0, v in O.items():
            dr.add(ohat * v * 0.35, S.pos(bar, s0 / 4.0), pan=-0.2)
        if sc in ('verse', 'brk') and bar % 2 == 0:
            pump_times.append(S.pos(bar, 2.0))
    fx = S.bus('fx')
    for b in (16, 24, 40):
        fx.add(crash * 0.7, S.pos(b), pan=0.1)
        boom = sub_bass(55.0, 1.2, 1.0, rel=0.3, harm=0.05, glide_from=90.0, glide_t=0.08)
        boom *= np.exp(-np.arange(len(boom)) / (0.45 * SR))
        fx.add(boom * 0.8, S.pos(b))
    rs = riser(4 * bar_n - S.spb, 250, 9500, seed=5)
    rs = np.vstack([rs, np.roll(rs, 441)])
    fx.add(rs * 0.6, S.pos(12))
    rc = drum_crash(dur=S.sec(4), t60=2.0, seed=41)[::-1]
    rc = rc * np.linspace(0, 1, len(rc)) ** 2
    fx.add(rc * 0.45, S.pos(15) - 0.0, pan=-0.1)
    rc2 = drum_crash(dur=S.sec(2), t60=1.2, seed=42)[::-1]
    fx.add(rc2 * 0.3, S.pos(47, 2.0), pan=0.1)

    # ------------------------------------------------------------------ bell arps
    be = S.bus('bells')
    for bar in range(48):
        sc = sect[bar]
        if sc == 'build' and bar >= 14:
            continue
        rate = 4 if sc in ('drop', 'drop2') else 2  # notes per beat
        if sc == 'build':
            rate = 2 if bar < 12 else 4
        for k in range(4 * rate):
            beat = k / rate
            _, vo = chord_at(bar, beat)
            tones = sorted(set([m % 12 for m in vo]))
            pool = sorted([note('E5') + ((pc - 4) % 12) for pc in tones] + [note('E6') + ((pc - 4) % 12) for pc in tones])
            seq = [0, 2, 4, 3, 5, 4, 6, 5, 7, 6, 4, 5, 3, 4, 2, 1]
            m = pool[seq[k % 16] % len(pool)]
            v = (0.8 if k % rate == 0 else 0.55) * (0.9 + 0.2 * rng.random())
            y = fm_bell(float(mtof(m)), 0.9, v, ratio=4.0, index=1.6, t60=0.8, seed=int(rng.integers(1 << 30)), ting=0.3)
            be.add(y, S.pos(bar, beat), pan=0.45 if k % 2 else -0.45)

    # ------------------------------------------------------------------ vocal chops
    vx = S.bus('vox')
    # (bar, step, len_steps, note, vowels, consonant)
    hook = [(0, 0, 2, 'C#6', 'a', 'k'), (0, 3, 1, 'B5', 'i', None), (0, 4, 2, 'G#5', 'a', None),
            (0, 6, 2, 'B5', 'ua', None), (0, 10, 1, 'C#6', 'a', 'k'), (0, 11, 3, 'E6', 'ai', None),
            (1, 0, 3, 'D#6', 'a', None), (1, 3, 1, 'C#6', 'i', None), (1, 4, 2, 'B5', 'a', None),
            (1, 8, 2, 'F#5', 'o', None), (1, 10, 2, 'G#5', 'a', None), (1, 12, 4, 'B5', 'ie', None),
            (2, 0, 2, 'B5', 'a', 'k'), (2, 3, 1, 'G#5', 'i', None), (2, 4, 2, 'F#5', 'a', None),
            (2, 6, 2, 'G#5', 'ua', None), (2, 10, 1, 'B5', 'a', 'k'), (2, 11, 3, 'D#6', 'ai', None),
            (3, 0, 3, 'E6', 'a', None), (3, 4, 2, 'C#6', 'o', None), (3, 6, 2, 'B5', 'a', None),
            (3, 12, 2, 'E5', 'u', None), (3, 14, 2, 'F#5', 'i', None)]
    hook2 = [h for h in hook if h[0] < 2] + [
        (2, 0, 2, 'G#5', 'a', 'k'), (2, 3, 1, 'B5', 'i', None), (2, 4, 2, 'C#6', 'a', None), (2, 6, 2, 'E6', 'ai', None),
        (2, 10, 2, 'D#6', 'a', None), (2, 12, 2, 'C#6', 'o', None), (2, 14, 2, 'B5', 'a', None),
        (3, 0, 6, 'G#5', 'ai', None), (3, 8, 2, 'B5', 'a', 'k'), (3, 10, 2, 'C#6', 'i', None),
        (3, 12, 4, 'E6', 'ae', None)]
    soft = [(0, 4, 4, 'G#5', 'ua', None), (0, 10, 2, 'B5', 'a', None), (1, 2, 6, 'C#6', 'ai', None),
            (2, 4, 4, 'B5', 'ua', None), (2, 10, 2, 'G#5', 'a', None), (3, 0, 8, 'E5', 'ai', None)]

    def play_vox(phr, bar0, vel=0.8, oct_=0):
        for (b, s0, ln, nm, vw, cons) in phr:
            f = float(mtof(note(nm) + 12 * oct_))
            dur = ln * S.spb / 4 / SR * 0.92
            vws = tuple(vw) if len(vw) == 2 else (vw,)
            y = vox_chop(f, dur, vws, vel * (0.9 + 0.15 * rng.random()), seed=int(rng.integers(1 << 30)),
                         scoop=-1.5 if ln <= 2 else -2.5, vib=0.25 if ln >= 4 else 0.0, consonant=cons,
                         glide_to=-3.0 if ln >= 6 else None)
            vx.add(y, S.pos(bar0 + b, s0 / 4.0), pan=rng.uniform(-0.15, 0.15))

    for b0 in (16, 20, 24, 28, 40, 44):
        play_vox(hook if b0 in (16, 24, 40) else hook2, b0, 0.85)
    for b0 in (0, 4, 32, 36):
        play_vox(soft, b0, 0.6)
    play_vox([(0, 12, 2, 'B5', 'ai', 'k'), (0, 14, 2, 'E6', 'a', None)], 15, 0.9)

    # ------------------------------------------------------------------ mix
    side = sidechain_env(L, pump_times, depth=0.75, release=0.3, shape=2.0)
    ch_x = cfilt(S.buses['chords'].buf, 'hp', 170, 0.7) * side
    ch_x = cfilt(ch_x, 'peak', 3000, 0.8, 2.0)
    sb_x = cfilt(S.buses['sub'].buf, 'lp', 300, 0.7) * (0.25 + 0.75 * side)
    sb_x = saturate(sb_x / (np.max(np.abs(sb_x)) + 1e-9), 1.4)
    dr_x = S.buses['drums'].buf
    be_x = cfilt(S.buses['bells'].buf, 'hp', 400, 0.7) * (0.5 + 0.5 * side)
    vx_x = cfilt(S.buses['vox'].buf, 'hp', 300, 0.7)
    fx_x = S.buses['fx'].buf

    dr_x = set_lufs(dr_x, -19.5)
    sb_x = set_lufs(sb_x, -21.5)
    ch_x = set_lufs(ch_x, -19.5)
    be_x = set_lufs(be_x, -25.0)
    vx_x = set_lufs(vx_x, -21.0)
    fx_x = set_lufs(fx_x, -27.0)

    dly = S.spb * 3 // 4
    be_d = delay_taps(be_x.mean(0), dly, fb=0.45, taps=4, lp=6000)
    vx_d = delay_taps(vx_x.mean(0), S.spb // 2, fb=0.35, taps=3, lp=5000)
    ir = make_ir(t60=2.2, predelay=0.02, hf=0.8, seed=7)
    send = 0.18 * ch_x + 0.35 * be_x + 0.3 * vx_x + 0.1 * dr_x + 0.3 * fx_x
    wet = reverb(send, ir) * (0.4 + 0.6 * side)
    mix = dr_x + sb_x + ch_x + be_x + vx_x + fx_x + 0.25 * be_d + 0.16 * vx_d + 0.5 * wet
    return mix, dict(name=NAME, bpm=150, key='E major (Amaj9-B9-G#m7-C#m9, "royal road")', bars=48, meter='4/4 half-time')


if __name__ == '__main__':
    import time
    t = time.time()
    mix, meta = render()
    save_mix(NAME, mix, meta)
    print(NAME, 'rendered', mix.shape, 'peak', db(np.abs(mix).max()), 'lufs', lufs(mix), 'time', time.time() - t)
