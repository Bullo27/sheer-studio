#!/usr/bin/env python3
# SHEER — the scene's display transform in Python (the baked AgX 'Punchy' LUT that HDRP applies in External
# tonemapping mode) and its numerical inverse: display sRGB 0..255 <-> scene-linear Rec.709 (exposure applied).
import os
import numpy as np
from scipy.optimize import least_squares

LUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'unity', 'Assets', 'Sheer', 'Data', 'agx_punchy_lut32.raw')
A, B, C, D = 5.555556, 0.047996, 0.244161, 0.386036
_lut = None


def _load():
    global _lut
    if _lut is None:
        f = np.fromfile(LUT_PATH, np.float32)
        n = round((f.size / 3) ** (1 / 3))
        _lut = f.reshape(n, n, n, 3).astype(np.float64)        # [b][g][r]
    return _lut


def logc(x):
    return C * np.log10(A * np.maximum(x, 0.0) + B) + D


def forward(rgb):
    """scene-linear (exposed) -> display-linear (before the sRGB encoding)"""
    lut = _load(); n = lut.shape[0]
    p = np.clip(logc(np.asarray(rgb, np.float64)), 0, 1) * (n - 1)
    i0 = np.minimum(np.floor(p).astype(int), n - 2); t = p - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    tr, tg, tb = t[..., 0:1], t[..., 1:2], t[..., 2:3]
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (tr if dr else 1 - tr) * (tg if dg else 1 - tg) * (tb if db else 1 - tb)
                out = out + w * lut[b0 + db, g0 + dg, r0 + dr]
    return out


def srgb_to_lin(c):
    c = np.asarray(c, np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(l):
    l = np.clip(l, 0, 1)
    return 255.0 * np.where(l <= 0.0031308, l * 12.92, 1.055 * l ** (1 / 2.4) - 0.055)


def display(rgb):
    """scene-linear -> display sRGB 0..255"""
    return lin_to_srgb(forward(rgb))


def inverse(srgb8):
    """display sRGB 0..255 -> scene-linear (least squares through the LUT)"""
    target = srgb_to_lin(srgb8)
    x0 = np.maximum(target, 1e-3)
    r = least_squares(lambda x: (forward(np.exp(x)) - target) * 10, np.log(x0), method='lm')
    return np.exp(r.x)


if __name__ == '__main__':
    for v in (0.02, 0.05, 0.18, 0.5, 1.0, 2.0):
        d = display([v, v, v])
        print('scene %.2f -> sRGB %s -> back %s' % (v, d.round(1), inverse(d).round(3)))
