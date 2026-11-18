"""Master, encode and verify music loops.
usage: python3 master.py name [name ...]   (reads out/<name>_mix.npy)"""
import os
import sys
import json
import subprocess
import numpy as np
from synthlib import *

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'unity', 'Assets', 'Sheer', 'Resources', 'Audio', 'Music')

COMP = dict(thresh_db=-20.0, ratio=2.0, attack=0.015, release=0.2, knee=6.0)


def decode(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-acodec', 'pcm_f32le', '-ac', '2',
                        '-ar', str(SR), '-'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).T.astype(np.float64)


def ffmpeg_ebur128(path):
    r = subprocess.run(['ffmpeg', '-nostats', '-hide_banner', '-i', path, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True)
    txt = r.stderr
    i = txt.rfind('Summary:')
    s = txt[i:]
    I = [l for l in s.splitlines() if l.strip().startswith('I:')]
    P = [l for l in s.splitlines() if l.strip().startswith('Peak:')]
    return (I[0].split()[1] if I else '?'), (P[0].split()[1] if P else '?')


def spectrogram_png(x, path, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from scipy import signal as sg
    m = x.mean(0)
    f, t, Z = sg.spectrogram(m, SR, nperseg=4096, noverlap=2048)
    fig, ax = plt.subplots(2, 1, figsize=(16, 9), gridspec_kw=dict(height_ratios=[3, 1]))
    ax[0].pcolormesh(t, f, 10 * np.log10(Z + 1e-12), vmin=-120, vmax=-30, shading='auto', cmap='magma')
    ax[0].set_yscale('symlog', linthresh=200)
    ax[0].set_ylim(30, 22050)
    ax[0].set_title(title)
    blk = int(0.05 * SR)
    nb = x.shape[1] // blk
    r = np.sqrt(np.mean(x[:, :nb * blk].reshape(2, nb, blk) ** 2, axis=(0, 2)))
    pk = np.abs(x[:, :nb * blk]).reshape(2, nb, blk).max(axis=(0, 2))
    tt = np.arange(nb) * blk / SR
    ax[1].plot(tt, db(r), lw=0.7, label='rms')
    ax[1].plot(tt, db(pk), lw=0.5, label='peak')
    ax[1].set_ylim(-60, 0)
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=60)
    plt.close(fig)


def band_report(x):
    m = x.mean(0)
    F = np.abs(np.fft.rfft(m)) ** 2
    f = np.fft.rfftfreq(len(m), 1 / SR)
    edges = [20, 60, 120, 250, 500, 1000, 2000, 4000, 8000, 16000, 22050]
    tot = F.sum()
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        out.append('%d-%d:%.1f' % (lo, hi, 10 * np.log10(F[(f >= lo) & (f < hi)].sum() / tot + 1e-12)))
    return ' '.join(out)


def process(name, target=-16.0, ceiling=-2.0):
    x = np.load(os.path.join(OUT, name + '_mix.npy')).astype(np.float64)
    meta = json.load(open(os.path.join(OUT, name + '_meta.json')))
    x = set_lufs(x, -18.0)
    y = master(x, target=target, ceiling=ceiling, comp=COMP)
    wav = os.path.join(OUT, name + '_master.wav')
    write_wav(wav, y, bits=32)
    os.makedirs(DEST, exist_ok=True)
    ogg = os.path.join(DEST, name + '.ogg')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-c:a', 'libvorbis', '-q:a', '5', '-ar', str(SR),
                    '-ac', '2', ogg], check=True)
    d = decode(ogg)
    rep = dict(name=name, dur_s=round(y.shape[1] / SR, 3), samples=y.shape[1], ogg_samples=d.shape[1],
               lufs_master=round(lufs(y), 2), tp_master=round(float(db(true_peak(y).max())), 2),
               lufs_ogg=round(lufs(d), 2), tp_ogg=round(float(db(true_peak(d).max())), 2),
               sp_ogg=round(float(db(np.abs(d).max())), 2), size_kb=round(os.path.getsize(ogg) / 1024, 1))
    rep['loop_master'] = {k: round(v, 4) for k, v in loop_report(y).items()}
    rep['loop_ogg'] = {k: round(v, 4) for k, v in loop_report(d).items()}
    I, P = ffmpeg_ebur128(ogg)
    rep['ffmpeg_I'] = I
    rep['ffmpeg_TP'] = P
    rep['bands'] = band_report(y)
    rep.update(meta)
    spectrogram_png(y, os.path.join(OUT, name + '_spec.png'), name)
    with open(os.path.join(OUT, name + '_report.json'), 'w') as fh:
        json.dump(rep, fh, indent=1)
    return rep


if __name__ == '__main__':
    for nm in sys.argv[1:]:
        r = process(nm)
        print(json.dumps(r, indent=1))
