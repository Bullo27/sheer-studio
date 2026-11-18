#!/usr/bin/env python3
# SHEER — colour calibration against the original: patch means at matched normalized points of an original frame
# and our frame (same camera), in display sRGB and linear, with per-channel linear ratios (ours / original).
# Usage: python3 tools/colorcal.py v1|v2 ORIGINAL.png OURS.png
import sys
import numpy as np
from PIL import Image

PTS = {
    # VIEW 01 (t ~ 0.1 s: clean thigh, knee pinch only)
    'v1': [('thigh_ul', .32, .33), ('thigh_m', .40, .45), ('thigh_r', .55, .40), ('thigh_edge', .63, .42),
           ('knee_l', .30, .68), ('shin', .40, .92), ('other_leg', .06, .55), ('bg_mid', .85, .55), ('bg_top', .85, .12)],
    # VIEW 02 (t ~ 26.5 s: the left leg is clean)
    'v2': [('calf', .33, .30), ('shin', .34, .50), ('ankle', .33, .66), ('calf_edge', .235, .36), ('foot', .32, .90),
           ('bg_mid', .62, .40), ('bg_top', .62, .08), ('floor', .62, .92)],
}


def lin(c):
    c = np.asarray(c) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def patch(im, x, y, r):
    H, W, _ = im.shape
    cx, cy = int(x * W), int(y * H)
    return im[max(cy - r, 0):cy + r + 1, max(cx - r, 0):cx + r + 1].reshape(-1, 3).mean(0)


def main():
    view, a, b = sys.argv[1:4]
    A = np.asarray(Image.open(a).convert('RGB').resize((540, 945))).astype(np.float64)
    B = np.asarray(Image.open(b).convert('RGB').resize((540, 945))).astype(np.float64)
    print('%-11s %-16s %-16s %-22s' % ('point', 'original', 'ours', 'linear ratio ours/orig'))
    errs = []
    for n, x, y in PTS[view]:
        pa, pb = patch(A, x, y, 5), patch(B, x, y, 5)
        la, lb = lin(pa), lin(pb)
        ratio = lb / np.maximum(la, 1e-4)
        errs.append(np.abs(np.log(np.maximum(ratio, 1e-3))))
        print('%-11s (%3d,%3d,%3d)    (%3d,%3d,%3d)    (%.2f, %.2f, %.2f)' % ((n,) + tuple(pa) + tuple(pb) + tuple(ratio)))
    e = np.array(errs)
    print('mean |log ratio| per channel: %.3f %.3f %.3f  (0.10 ~ 10%%)' % tuple(e.mean(0)))


if __name__ == '__main__':
    main()
