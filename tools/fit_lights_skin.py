#!/usr/bin/env python3
# SHEER — light intensities from material-independent pixels: bare skin seen through the ORIGINAL's holes (our renders
# with the stocking hidden and no under-nylon shadow, per light, linear output at +2 EV) and the white floor (VIEW 02).
# display = AgX(ambient + sum_l k_l (render_l - ambient)), k_l >= 0, relative least squares in display-linear.
# Usage: fit_lights_skin.py NAMES ORIG1 DIR1 [ORIG2 DIR2 ...]   (DIR with var_00.. = lights in NAMES order, last = ambient)
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from scipy.optimize import least_squares
import agx


def load(f):
    return np.asarray(Image.open(f).convert('RGB').resize((540, 945))).astype(np.float64)


def view_data(orig, d, n):
    O = load(orig)
    H, W = 945, 540
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    ui = (xx < 0.2) & (yy > 0.88)
    hole = (O[..., 0] > 150) & (O[..., 0] - O[..., 2] > 30) & ~ui
    hole = binary_erosion(hole, iterations=3)
    floor = np.zeros_like(hole)
    if 'v2' in d:                                            # the white drop cloth, away from the feet
        floor = (yy > 0.80) & (O.min(2) > 180) & ~ui & ((xx > 0.55) & (xx < 0.85))
    lin = [4.0 * agx.srgb_to_lin(load('%s/var_%02d.png' % (d, i))) for i in range(n + 1)]
    sel = {}
    for name, m in (('skin', hole), ('floor', floor)):
        idx = np.flatnonzero(m.ravel())[::3]
        if len(idx) == 0:
            continue
        tgt = agx.srgb_to_lin(O).reshape(-1, 3)[idx]
        C = np.stack([(lin[i] - lin[n]).reshape(-1, 3)[idx] for i in range(n)], 0)
        A = lin[n].reshape(-1, 3)[idx]
        sel[name] = (tgt, C, A)
    return sel


LUM = np.array([0.2126, 0.7152, 0.0722])


def main():
    import os
    names = sys.argv[1].split(',')
    n = len(names)
    fixed = {kv.split('=')[0]: float(kv.split('=')[1]) for kv in os.environ.get('FIX', '').split(',') if '=' in kv}
    lum_only = os.environ.get('LUMONLY', '1') == '1'
    sets = [(sys.argv[i], view_data(sys.argv[i], sys.argv[i + 1], n)) for i in range(2, len(sys.argv), 2)]
    free = [i for i, nm in enumerate(names) if nm not in fixed]
    groups = [(o, nm, g) for o, sel in sets for nm, g in sel.items()]
    for o, nm, (tgt, C, A) in groups:
        print('%-60s %-5s %5d px  orig mean sRGB %s' % (o[-30:], nm, len(tgt), agx.lin_to_srgb(tgt.mean(0)).round(0)))

    def kvec(lk):
        k = np.array([fixed.get(nm, 0.5) for nm in names])
        k[free] = np.exp(lk)
        return k

    def resid(lk):
        k = kvec(lk); r = []
        for o, nm, (tgt, C, A) in groups:
            sc = A + np.tensordot(k, C, 1)
            w = 1.0 / np.sqrt(len(tgt))                        # each group counts equally
            d = agx.forward(sc)
            if lum_only:
                r.append(w * (d @ LUM - tgt @ LUM) / (tgt @ LUM + 0.02))
            else:
                r.append((w * (d - tgt) / (tgt + 0.02)).ravel())
        return np.concatenate(r)

    x0 = np.log(np.full(len(free), 0.5))
    res = least_squares(resid, x0, bounds=(np.log(1e-3), np.log(20)))
    k = kvec(res.x)
    print('light scales: ' + ', '.join('%s=%.3f' % (nm, kk) for nm, kk in zip(names, k)))
    for o, nm, (tgt, C, A) in groups:
        sc = A + np.tensordot(k, C, 1)
        sc5 = A + np.tensordot(np.full(n, 0.5), C, 1)
        print('%-30s %-5s orig %s  fit %s  (all x0.5: %s)' % (o[-30:], nm, agx.lin_to_srgb(tgt.mean(0)).round(0),
              agx.lin_to_srgb(agx.forward(sc).mean(0)).round(0), agx.lin_to_srgb(agx.forward(sc5).mean(0)).round(0)))


if __name__ == '__main__':
    main()
