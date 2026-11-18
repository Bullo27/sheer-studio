#!/usr/bin/env python3
# (SUPERSEDED 2026-11-16: the feet are part of each leg's one lattice now - tools/sim/export_sock_lattice.py. Kept for
#  reference; Unity no longer reads foot_lattice.bin.)
# SHEER - cloth lattices for the FEET (unity/Assets/StreamingAssets/foot_lattice.bin), so that the stocking can be
# pulled and torn on the foot too (user, 2026-11-16: "That area is fair game too"). The legs' lattices are tubes about a
# vertical axis that end at the ankle; a foot is a tube along the foot. Each foot's lattice is built in the foot's LOCAL
# frame (x, -z, y) - its long axis (heel -> toes) is the frame's 'up' - so the same solver (SheerCloth.compute) runs it:
# rows by position along the foot, cross-sections in the (x, height) plane, a radial height field R(theta, row) about
# each row's centre (theta = atan2(x - ax, height - az): 0 = the instep, +-pi = the sole).
# Above CUT (world height) the stocking belongs to the leg's lattice: there the cross-sections end at the cut, and those
# nodes are pinned (the junction with the leg's held ankle band), as are the sole (standing on the floor) and the ends.
# Format 'SLAT' version 2: version 1 (u32 NU, NV, f32 y0, y1; per foot: ax[NV], az[NV], R[NV*NU], X[NV*NU*3]) + per foot
# PIN[NV*NU] (1 = held) and PINS[NV*NU] (held, softened over a few nodes: leash / tether falloff).
#   python3 tools/sim/export_foot_lattice.py [NU NV]
import os, sys, struct
import numpy as np
from scipy.ndimage import gaussian_filter1d, gaussian_filter, binary_dilation
from scipy.interpolate import CloughTocher2DInterpolator, LinearNDInterpolator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom
from smesh import load

CUT = 0.072          # world height (m): below it the stocking is the foot's; above it, the leg's
SOLE = 0.0045        # nodes this close to the floor are held by it


def build_foot(P, side, NU, NV):
    """P: the stocking's vertices of this foot (world). Returns dict like geom.build_leg, in the foot's local frame."""
    L = np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)               # local: x, along the foot (heel -> toes), height
    ys = L[:, 1]
    y0, y1 = ys.min() + 0.004, ys.max() - 0.003
    y = np.linspace(y0, y1, NV)
    # each row's centre: middle of the cross-section (x span, height span), smoothed along the foot
    cx = np.zeros(NV); cz = np.zeros(NV)
    order = np.argsort(ys); Ls = L[order]
    for j, yy in enumerate(y):
        a, b = np.searchsorted(Ls[:, 1], [yy - 0.004, yy + 0.004])
        q = Ls[a:b] if b - a > 8 else Ls[max(0, a - 20):b + 20]
        cx[j] = 0.5 * (q[:, 0].min() + q[:, 0].max()); cz[j] = 0.5 * (q[:, 2].min() + q[:, 2].max())
    cx = gaussian_filter1d(cx, 3, mode='nearest'); cz = gaussian_filter1d(cz, 3, mode='nearest')
    # cylindrical coordinates of every vertex about its row's centre
    pax = np.interp(ys, y, cx); paz = np.interp(ys, y, cz)
    th = np.arctan2(L[:, 0] - pax, L[:, 2] - paz); r = np.hypot(L[:, 0] - pax, L[:, 2] - paz)
    S = 0.035                                                    # theta scale (m) for an isotropic triangulation
    pts = np.concatenate([np.stack([(th + k * 2 * np.pi) * S, ys], 1) for k in (-1, 0, 1)])
    val = np.concatenate([r, r, r])
    keep = (pts[:, 0] > -1.25 * np.pi * S) & (pts[:, 0] < 1.25 * np.pi * S)
    pts, val = pts[keep], val[keep]
    _, ui = np.unique(np.round(pts / 1e-6).astype(np.int64), axis=0, return_index=True)
    pts, val = pts[ui], val[ui]
    itp = CloughTocher2DInterpolator(pts, val)
    thg = (np.arange(NU) / NU) * 2 * np.pi
    thq = np.where(thg > np.pi, thg - 2 * np.pi, thg)
    TH, Y = np.meshgrid(thq, y)
    R = itp(np.stack([TH.ravel() * S, Y.ravel()], 1)).reshape(NV, NU)
    if np.isnan(R).any():
        lin = LinearNDInterpolator(pts, val); bad = np.isnan(R)
        R[bad] = lin(np.stack([TH[bad] * S, Y[bad]], 1))
    if np.isnan(R).any():
        R = np.where(np.isnan(R), np.nanmedian(R), R)
    R = np.clip(R, 0.002, 0.075)                                  # (the pinned end caps can overshoot)
    X = np.stack([cx[:, None] + R * np.sin(thg)[None, :], np.repeat(y[:, None], NU, 1), cz[:, None] + R * np.cos(thg)[None, :]], -1)
    # held: the junction with the leg (at the cut), the sole on the floor, both ends
    height = X[..., 2]
    pin = (height >= CUT - 0.0025) | (height <= SOLE)
    pin[:2, :] = True; pin[-2:, :] = True
    pin = binary_dilation(pin, iterations=1)
    pins = gaussian_filter(pin.astype(float), (1.5, 1.5), mode=('nearest', 'wrap'))
    pins = np.maximum(pins, pin.astype(float))
    return dict(y=y, ax=cx, az=cz, R=R, X=X, pin=pin.astype(np.float32), pins=pins.astype(np.float32))


def main():
    NU = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    NV = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    nv, subs, ch = load(os.path.join(geom.SA, 'tights.smesh'))
    P = ch['position'].astype(np.float64); sd = ch['uv2'][:, 0]
    feet = []
    for side in (1, -1):
        m = (sd * side > 0) & (P[:, 1] < CUT + 0.004)
        feet.append(build_foot(P[m], side, NU, NV))
    y0 = max(f['y'][0] for f in feet); y1 = min(f['y'][-1] for f in feet)
    # (one row grid for both feet - mirror images - so the file keeps one y0 / y1)
    if any(abs(f['y'][0] - y0) > 1e-4 or abs(f['y'][-1] - y1) > 1e-4 for f in feet):
        feet = []
        for side in (1, -1):
            m = (sd * side > 0) & (P[:, 1] < CUT + 0.004)
            Q = P[m]; Lq = -Q[:, 2]
            Q = Q[(Lq >= y0 - 0.004) & (Lq <= y1 + 0.003)]
            feet.append(build_foot(Q, side, NU, NV))
        y0 = feet[0]['y'][0]; y1 = feet[0]['y'][-1]
    out = os.path.join(geom.SA, 'foot_lattice.bin')
    with open(out, 'wb') as fh:
        fh.write(b'SLAT'); fh.write(struct.pack('<IIIff', 2, NU, NV, y0, y1))
        for f in feet:
            for k in ('ax', 'az', 'R', 'X'):
                fh.write(np.ascontiguousarray(f[k], dtype='<f4').tobytes())
            fh.write(np.ascontiguousarray(f['pin'], dtype='<f4').tobytes())
            fh.write(np.ascontiguousarray(f['pins'], dtype='<f4').tobytes())
    for s, f in zip((1, -1), feet):
        R = f['R']; X = f['X']
        per = np.linalg.norm(np.roll(X, -1, 1) - X, axis=-1).sum(1)
        print('foot %+d: rows %.3f..%.3f (%d x %d, dy %.2f mm), R %.1f..%.1f mm, perimeter %.0f..%.0f mm, held %.0f %%' % (
            s, f['y'][0], f['y'][-1], NU, NV, (f['y'][1] - f['y'][0]) * 1e3, R.min() * 1e3, R.max() * 1e3, per.min() * 1e3, per.max() * 1e3, 100 * f['pin'].mean()))
    print('wrote %s (%.1f MB)' % (out, os.path.getsize(out) / 1e6))


if __name__ == '__main__':
    main()
