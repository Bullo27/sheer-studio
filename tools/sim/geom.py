# Leg geometry for the stocking simulation prototype: per leg, the worn stocking surface as a radial height field
# R(theta, y) around a smooth vertical-ish axis curve, sampled on the cloth lattice itself (NU around x NV along).
# theta = atan2(x - ax, z - az) (0 = back, +z), node (j, i) at height y_j = y0 + j * dy and angle theta_i = 2 pi i / NU.
import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from smesh import load
from scipy.ndimage import gaussian_filter1d
from scipy.interpolate import CloughTocher2DInterpolator, LinearNDInterpolator

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SA = os.path.join(ROOT, 'unity', 'Assets', 'StreamingAssets')

def leg_axis(P, y_lo, y_hi, step=0.002, sigma_mm=12.0):
    """Axis centre per height bin: centroid of the cross-section outline (sector means), Gaussian smoothed."""
    ys = np.arange(y_lo - 0.03, y_hi + 0.03 + 1e-9, step)
    cx = np.full(len(ys), np.nan); cz = np.full(len(ys), np.nan)
    SEC = 48
    order = np.argsort(P[:, 1]); Ps = P[order]
    for b, y in enumerate(ys):
        a, e = np.searchsorted(Ps[:, 1], [y - 0.004, y + 0.004])
        if e - a < 24: continue
        q = Ps[a:e]
        x0, z0 = 0.5 * (q[:, 0].min() + q[:, 0].max()), 0.5 * (q[:, 2].min() + q[:, 2].max())
        th = np.arctan2(q[:, 0] - x0, q[:, 2] - z0); r = np.hypot(q[:, 0] - x0, q[:, 2] - z0)
        s = ((th + np.pi) / (2 * np.pi) * SEC).astype(int) % SEC
        cnt = np.bincount(s, minlength=SEC); sm = np.bincount(s, weights=r, minlength=SEC)
        ok = cnt > 0
        if ok.sum() < 0.6 * SEC: continue
        ang = (np.arange(SEC) + 0.5) / SEC * 2 * np.pi - np.pi
        rr = sm[ok] / cnt[ok]
        cx[b] = (x0 + np.sin(ang[ok]) * rr).mean(); cz[b] = (z0 + np.cos(ang[ok]) * rr).mean()
    ok = ~np.isnan(cx)
    cx = np.interp(ys, ys[ok], cx[ok]); cz = np.interp(ys, ys[ok], cz[ok])
    sg = sigma_mm * 1e-3 / step
    return ys, gaussian_filter1d(cx, sg, mode='nearest'), gaussian_filter1d(cz, sg, mode='nearest')

def build_leg(side, NU=256, NV=320, y0=0.086, y1=0.776, cache=True):
    """Returns dict: y (NV), ax, az (NV), R (NV, NU), X (NV, NU, 3) worn rest positions."""
    key = os.path.join(ROOT, 'tools', 'sim', '_cache_leg_%s_%d_%d_%.3f_%.3f.npz' % ('p' if side > 0 else 'm', NU, NV, y0, y1))
    if cache and os.path.exists(key):
        d = np.load(key); return {k: d[k] for k in d.files}
    nv, subs, ch = load(os.path.join(SA, 'tights.smesh'))
    P = ch['position'].astype(np.float64); sd = ch['uv2'][:, 0]
    m = (sd * side > 0) & (P[:, 1] > y0 - 0.04) & (P[:, 1] < y1 + 0.04)
    P = P[m]
    ys, cx, cz = leg_axis(P, y0, y1)
    y = np.linspace(y0, y1, NV)
    ax = np.interp(y, ys, cx); az = np.interp(y, ys, cz)
    # cylindrical coordinates of every mesh vertex about the axis at its own height
    pax = np.interp(P[:, 1], ys, cx); paz = np.interp(P[:, 1], ys, cz)
    th = np.arctan2(P[:, 0] - pax, P[:, 2] - paz); r = np.hypot(P[:, 0] - pax, P[:, 2] - paz)
    # periodic copies; scale theta so the triangulation is roughly isotropic (mean radius ~ 5.5 cm)
    S = 0.055
    pts = np.concatenate([np.stack([(th + k * 2 * np.pi) * S, P[:, 1]], 1) for k in (-1, 0, 1)])
    val = np.concatenate([r, r, r])
    keep = (pts[:, 0] > -1.25 * np.pi * S) & (pts[:, 0] < 1.25 * np.pi * S)   # theta in [-pi, pi] plus a margin
    pts, val = pts[keep], val[keep]
    # drop duplicates (double-sided submeshes share positions)
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
    assert not np.isnan(R).any(), 'height field has gaps'
    X = np.stack([ax[:, None] + R * np.sin(thg)[None, :], np.repeat(y[:, None], NU, 1), az[:, None] + R * np.cos(thg)[None, :]], -1)
    out = dict(y=y, ax=ax, az=az, R=R, X=X)
    if cache: np.savez(key, **out)
    return out

if __name__ == '__main__':
    for s in (1, -1):
        g = build_leg(s, cache=False)
        R = g['R']; X = g['X']
        du = np.linalg.norm(np.roll(X, -1, 1) - X, axis=-1); dv = np.linalg.norm(X[1:] - X[:-1], axis=-1)
        print('side %+d R [%.4f %.4f] circ ankle %.3f mid %.3f top %.3f  du [%.5f %.5f] dv [%.5f %.5f]' % (
            s, R.min(), R.max(), du[0].sum(), du[160].sum(), du[-1].sum(), du.min(), du.max(), dv.min(), dv.max()))
        for j in (0, 10, 40, 100, 160, 220, 280, 319):
            print('   j %3d y %.3f ax %.4f az %.4f R mean %.4f min %.4f max %.4f circ %.3f' % (j, g['y'][j], g['ax'][j], g['az'][j], R[j].mean(), R[j].min(), R[j].max(), du[j].sum()))
