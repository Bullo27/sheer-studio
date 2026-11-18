#!/usr/bin/env python3
# SHEER — fits the light intensities to the original video. Inputs: per-light renders in linear output (tonemapping
# None, exposure +2 EV: scene-linear = 4 x sRGB-decoded pixel), one with all lights off (sky ambient), for one or more
# views; the original frames. Model: display = AgX(ambient + sum_l k_l (render_l - ambient)); k_l >= 0 fitted by
# least squares on block-averaged leg + floor pixels (backdrop, UI and holes excluded), in display-linear space.
# Usage: fit_lights.py NAMES  ORIG1 DIR1 HOLES1  [ORIG2 DIR2 HOLES2 ...]   (NAMES = key,fill,... in variant order)
import sys
import numpy as np
from PIL import Image
from scipy.optimize import least_squares
import agx

B = 6                                                      # block size (px at 540 x 945)


def load(f):
    return np.asarray(Image.open(f).convert('RGB').resize((540, 945))).astype(np.float64)


def blocks(a):
    H, W = a.shape[0] // B * B, a.shape[1] // B * B
    return a[:H, :W].reshape(H // B, B, W // B, B, -1).mean((1, 3))


def view_data(orig, d, holes_png, n):
    O = load(orig); Hs = load(holes_png)
    lin = [4.0 * agx.srgb_to_lin(load('%s/var_%02d.png' % (d, i))) for i in range(n + 1)]   # n lights + ambient
    amb = lin[n]
    bg = lambda im: im[..., 2] > im[..., 0] + 12
    hole = lambda im: (im[..., 0] > 150) & (im[..., 0] - im[..., 2] > 35)
    H, W = 945, 540
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    ui = (xx < 0.2) & (yy > 0.88)
    skirt = yy < 0.2 if 'v1' in d else np.zeros_like(ui)
    mask = ~bg(O) & ~bg(Hs) & ~hole(O) & ~hole(Hs) & ~ui & ~skirt & (yy > 0.02) & (xx < 0.96)
    mb = blocks(mask[..., None].astype(float))[..., 0] > 0.99
    tgt = blocks(agx.srgb_to_lin(O))[mb]
    C = np.stack([blocks(l - amb)[mb] for l in lin[:n]], 0)        # n x P x 3
    A = blocks(amb)[mb]
    return tgt, C, A, mb


def main():
    names = sys.argv[1].split(',')
    n = len(names)
    sets = [view_data(sys.argv[i], sys.argv[i + 1], sys.argv[i + 2], n) for i in range(2, len(sys.argv), 3)]

    def resid(lk):
        k = np.exp(lk)
        r = []
        for tgt, C, A, _ in sets:
            sc = A + np.tensordot(k, C, 1)
            r.append(((agx.forward(sc) - tgt) / np.sqrt(tgt + 0.01)).ravel())   # ~ relative error, stable in the darks
        return np.concatenate(r)

    for tgt, C, A, mb in sets:
        print('pixels (blocks) used:', mb.sum())
    r0 = resid(np.log(np.full(n, 0.5)))
    res = least_squares(resid, np.log(np.full(n, 0.5)), bounds=(np.log(1e-3), np.log(20)))
    k = np.exp(res.x)
    print('rms start (all 0.5) %.4f -> fit %.4f' % (np.sqrt((r0 ** 2).mean()), np.sqrt((res.fun ** 2).mean())))
    print('light scales: ' + ', '.join('%s=%.3f' % (nm, kk) for nm, kk in zip(names, k)))
    # per-view summary: mean display sRGB of the fitted vs original
    for (tgt, C, A, mb), i in zip(sets, range(2, len(sys.argv), 3)):
        sc = A + np.tensordot(k, C, 1)
        print(sys.argv[i], 'mean sRGB orig', agx.lin_to_srgb(tgt.mean(0)).round(0), 'fit', agx.lin_to_srgb(agx.forward(sc).mean(0)).round(0))


if __name__ == '__main__':
    main()
