#!/usr/bin/env python3
# SHEER - ONE cloth lattice per leg for the whole stocking, toes to under the skirt (user, 2026-11-16: "Can't limitation 1
# be overcome?" - the leg's and the foot's fabric were two lattices joined only at the ankle: a ladder could not run on
# from the shin onto the foot, a pull on one did not draw the other). A real tube-knit stocking is one tube: its wales run
# down the leg, bend round the ankle and run on along the foot to the toe seam. So is this lattice (NU around x NV along):
#   rows are cross-sections of the tube by a family of planes that never meet inside the stocking -
#     LEG  (rest height y >= YC):           horizontal planes (as the old leg lattice: row j at height y0 + j * ds)
#     BEND (y < YC, in front of the leg):   half-planes through a line parallel to x at (YC, ZC) - the bend's axis, in
#                                           front of the ankle - turning from horizontal (pointing back) to vertical
#                                           (pointing down) round the ankle and heel
#     FOOT (z <= ZC):                       vertical planes, z = const, to the toe tip
#   row parameter S (m): 0 at the toe tip, + along the foot, rho x the bend's angle round it, + height up the leg;
#   in each row's plane: a = x and B (= z on the leg; ZC + distance from the bend's axis in the bend; ZC + YC - y on the
#   foot), the row's centre (ax, az) in those coordinates, theta = atan2(a - ax, B - az) (0 = back of the leg / heel /
#   sole, pi = front of the shin / instep), and the worn stocking's radius R(theta, row) about that centre.
# Column i is then one wale from the toe seam to the top: on the shin's front it runs on down the ankle onto the instep,
# at the back down the heel and along the sole. Z (per node) = where it is in the damage maps along its wale: the rest
# height on the leg, below YC the height of the bend's top minus the arc length down the wale (so tears and ladders are
# drawn at their true size round the ankle).
# Format 'SLAT' version 3: u32 NU, NV, f32 y0, y1 (the leg rows: height = y0 + j * ds), f32 YC, ZC, rho, sc (S at the
# bend's top), s0 (S of row 0), ds; per leg (side +1, then -1): ax[NV], az[NV], R[NV*NU], X[NV*NU*3], PIN[NV*NU],
# PINS[NV*NU], Z[NV*NU], DU[NU] (the damage maps' u offset of each wale below the bend's top).
#   python3 tools/sim/export_sock_lattice.py [NU]
import os, sys, struct
import numpy as np
from scipy.ndimage import gaussian_filter1d, gaussian_filter, binary_dilation
from scipy.interpolate import CloughTocher2DInterpolator, LinearNDInterpolator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom
from smesh import load

YC, ZC = 0.110, -0.030      # the bend's axis (m): height, depth (in front of the ankle, above the instep)
RHO = 0.066                 # reference radius of the bend (S per radian): the leg's axis lies ~6.8 cm behind it, the foot's ~6.5 below
TOP = 0.776                 # top row (rest height): under the skirt, as the old leg lattice
DS = 0.69 / 319             # row spacing along S (= the old leg lattice's 2.16 mm)
S0 = 0.012                  # row 0: 12 mm in from the toe tip (nearer, the planes graze the cap: patches of vertices, no outline)
SOLE = 0.0045               # nodes this close to the floor are held by it


def coords(P, sc):
    """mesh points -> S (row parameter), a (= x), B (in-plane), region (0 foot, 1 bend, 2 leg)"""
    y, z = P[:, 1], P[:, 2]
    S = np.empty(len(P)); B = np.empty(len(P)); reg = np.empty(len(P), int)
    leg = y >= YC; foot = ~leg & (z <= ZC); bend = ~leg & ~foot
    S[leg] = sc + (y[leg] - YC); B[leg] = z[leg]; reg[leg] = 2
    g = np.arctan2(YC - y[bend], z[bend] - ZC)
    S[bend] = sc - RHO * g; B[bend] = ZC + np.hypot(YC - y[bend], z[bend] - ZC); reg[bend] = 1
    S[foot] = sc - RHO * np.pi / 2 - (ZC - z[foot]); B[foot] = ZC + (YC - y[foot]); reg[foot] = 0
    return S, P[:, 0].copy(), B, reg


def to_mesh(S, a, B, sc):
    """(S, a, B) -> mesh points (inverse of coords)"""
    S = np.asarray(S, float); a = np.asarray(a, float); B = np.asarray(B, float)
    out = np.empty(S.shape + (3,)); out[..., 0] = a
    leg = S >= sc; foot = S <= sc - RHO * np.pi / 2; bend = ~leg & ~foot
    out[..., 1] = np.where(leg, YC + (S - sc), 0.0); out[..., 2] = np.where(leg, B, 0.0)
    g = (sc - S) / RHO; b = B - ZC
    out[..., 1] = np.where(bend, YC - b * np.sin(g), out[..., 1]); out[..., 2] = np.where(bend, ZC + b * np.cos(g), out[..., 2])
    zf = ZC - ((sc - RHO * np.pi / 2) - S)
    out[..., 1] = np.where(foot, YC - b, out[..., 1]); out[..., 2] = np.where(foot, zf, out[..., 2])
    return out


def centres(S, a, B, s, sc):
    """row centres (ax, az) in the rows' own (a, B): centroid of the cross-section's outline by sectors, smoothed along S
    (12 mm on the leg as the old lattice, 5 mm round the ankle and on the foot)"""
    NV = len(s); cx = np.full(NV, np.nan); cz = np.full(NV, np.nan)
    order = np.argsort(S); Ss, As, Bs = S[order], a[order], B[order]
    SEC = 48
    for j, sj in enumerate(s):
        lo, hi = np.searchsorted(Ss, [sj - 0.004, sj + 0.004])
        if hi - lo < 24: continue
        qa, qb = As[lo:hi], Bs[lo:hi]
        a0, b0 = 0.5 * (qa.min() + qa.max()), 0.5 * (qb.min() + qb.max())
        th = np.arctan2(qa - a0, qb - b0); r = np.hypot(qa - a0, qb - b0)
        sec = ((th + np.pi) / (2 * np.pi) * SEC).astype(int) % SEC
        cnt = np.bincount(sec, minlength=SEC); sm = np.bincount(sec, weights=r, minlength=SEC)
        ok = cnt > 0
        if ok.sum() < 0.6 * SEC: cx[j], cz[j] = a0, b0; continue
        ang = (np.arange(SEC) + 0.5) / SEC * 2 * np.pi - np.pi; rr = sm[ok] / cnt[ok]
        cx[j] = (a0 + np.sin(ang[ok]) * rr).mean(); cz[j] = (b0 + np.cos(ang[ok]) * rr).mean()
    ok = ~np.isnan(cx)
    cx = np.interp(s, s[ok], cx[ok]); cz = np.interp(s, s[ok], cz[ok])
    w = np.clip((s - (sc - 0.01)) / 0.03, 0, 1); w = w * w * (3 - 2 * w)        # 0 below the ankle, 1 from 2 cm up the leg
    out = []
    for c in (cx, cz):
        out.append((1 - w) * gaussian_filter1d(c, 0.005 / DS, mode='nearest') + w * gaussian_filter1d(c, 0.012 / DS, mode='nearest'))
    return out[0], out[1]


def build_sock(P, NU, sc, NV, U0):
    S, a, B, reg = coords(P, sc)
    s = S0 + DS * np.arange(NV)
    m = (S > s[0] - 0.02) & (S < s[-1] + 0.04)
    S, a, B, reg, U0 = S[m], a[m], B[m], reg[m], U0[m]
    ax, az = centres(S, a, B, s, sc)
    pax = np.interp(S, s, ax); paz = np.interp(S, s, az)
    th = np.arctan2(a - pax, B - paz); r = np.hypot(a - pax, B - paz)
    # single-valued? the radius spread of the points of one row inside one sector (the stocking's two shells share positions)
    spread = []
    for j in range(0, NV, 4):
        q = np.abs(S - s[j]) < 0.0008
        if q.sum() < 40: spread.append((j, 0.0)); continue
        sec = ((th[q] + np.pi) / (2 * np.pi) * 64).astype(int) % 64
        mx = np.full(64, -1.0); mn = np.full(64, 1e9)
        np.maximum.at(mx, sec, r[q]); np.minimum.at(mn, sec, r[q])
        okk = mx >= 0
        spread.append((j, float((mx[okk] - mn[okk]).max())))
    SC = 0.05                                                     # theta scale (m) for an isotropic triangulation
    pts = np.concatenate([np.stack([(th + k * 2 * np.pi) * SC, S], 1) for k in (-1, 0, 1)])
    val = np.concatenate([r, r, r])
    keep = (pts[:, 0] > -1.25 * np.pi * SC) & (pts[:, 0] < 1.25 * np.pi * SC)
    pts, val = pts[keep], val[keep]
    _, ui = np.unique(np.round(pts / 1e-6).astype(np.int64), axis=0, return_index=True)
    pts, val = pts[ui], val[ui]
    itp = CloughTocher2DInterpolator(pts, val)
    thg = (np.arange(NU) / NU) * 2 * np.pi
    thq = np.where(thg > np.pi, thg - 2 * np.pi, thg)
    TH, SS = np.meshgrid(thq, s)
    R = itp(np.stack([TH.ravel() * SC, SS.ravel()], 1)).reshape(NV, NU)
    bad = np.isnan(R)
    if bad.any():
        lin = LinearNDInterpolator(pts, val); R[bad] = lin(np.stack([TH[bad] * SC, SS[bad]], 1))
    if np.isnan(R).any():
        # (off the mesh at the toe tip: from the nearest row of the same column that has a value)
        print('  (filling %d nodes off the mesh from their columns)' % np.isnan(R).sum())
        for i in range(NU):
            ok = ~np.isnan(R[:, i])
            R[~ok, i] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), R[ok, i])
    # the toe tip: the last vertices of the cap are sparse and its outline spikes between them - smoothed round the tip
    # (those rows are held by the solver anyway)
    from scipy.ndimage import gaussian_filter1d as g1
    for j in range(NV):
        w = np.clip((0.018 - s[j]) / 0.010, 0, 1)
        if w > 0: R[j] = (1 - w) * R[j] + w * g1(R[j], 4.0, mode='wrap')
    R = np.clip(R, 0.002, 0.09)
    aa = ax[:, None] + R * np.sin(thg)[None, :]; bb = az[:, None] + R * np.cos(thg)[None, :]
    X = to_mesh(np.repeat(s[:, None], NU, 1), aa, bb, sc)
    # held: the sole on the floor (the toe tip / top rows are held by the solver's pinned rows)
    pin = X[..., 1] <= SOLE
    pin = binary_dilation(pin, iterations=1)
    pins = gaussian_filter(pin.astype(float), (1.5, 1.5), mode=('nearest', 'wrap'))
    pins = np.maximum(pins, pin.astype(float))
    # Z: the rest height on the leg; below the bend's top, YC minus the arc length down each wale
    Z = X[..., 1].copy()
    jc = int(np.searchsorted(s, sc))                              # first leg row
    for j in range(jc - 1, -1, -1):
        Z[j] = Z[j + 1] - np.linalg.norm(X[j + 1] - X[j], axis=-1)
    # du: the damage maps' u on the leg is the mesh's own (uv0.x: the angle about the stocking export's axis), a few
    # degrees off this lattice's angle at the ankle - per column, what to add to theta / 2 pi below the bend's top so
    # that a ladder runs on from the shin down its wale without a step (measured on the vertices at the bend's top)
    ring = np.abs(S - sc - 0.0015) < 0.0025
    th01 = (th[ring] / (2 * np.pi)) % 1.0
    dl = ((U0[ring] - th01 + 0.5) % 1.0) - 0.5
    col = (th01 * NU).astype(int) % NU
    cnt = np.bincount(col, minlength=NU); sm = np.bincount(col, weights=dl, minlength=NU)
    okc = cnt > 0; idx = np.arange(NU)
    du = np.interp(idx, np.concatenate([idx[okc] - NU, idx[okc], idx[okc] + NU]), np.tile(sm[okc] / cnt[okc], 3))
    du = gaussian_filter1d(du, 4.0, mode='wrap')
    return dict(s=s, ax=ax, az=az, R=R, X=X, pin=pin.astype(np.float32), pins=pins.astype(np.float32), Z=Z, du=du, jc=jc, spread=spread)


def main():
    NU = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    nv, subs, ch = load(os.path.join(geom.SA, 'tights.smesh'))
    P = ch['position'].astype(np.float64); sd = ch['uv2'][:, 0]; U0 = ch['uv0'][:, 0].astype(np.float64)
    tips = [P[sd * side > 0, 2].min() for side in (1, -1)]
    z_tip = max(tips)                                             # (both legs: rows from 4 mm inside the shorter toe)
    sc = RHO * np.pi / 2 + (ZC - z_tip)
    s_top = sc + (TOP - YC)
    NV = int(np.floor((s_top - S0) / DS + 1e-6)) + 1
    socks = [build_sock(P[sd * side > 0], NU, sc, NV, U0[sd * side > 0]) for side in (1, -1)]
    y0 = YC - sc + S0; y1 = y0 + (NV - 1) * DS
    out = os.path.join(geom.SA, 'sock_lattice.bin')
    with open(out, 'wb') as fh:
        fh.write(b'SLAT'); fh.write(struct.pack('<IIIff', 3, NU, NV, y0, y1))
        fh.write(struct.pack('<6f', YC, ZC, RHO, sc, S0, DS))
        for f in socks:
            for k in ('ax', 'az', 'R', 'X', 'pin', 'pins', 'Z', 'du'):
                fh.write(np.ascontiguousarray(f[k], dtype='<f4').tobytes())
    print('toe tips %.4f / %.4f, sc %.4f, NV %d (foot rows %d, bend rows %d, leg rows %d), y0 %.4f y1 %.4f' % (
        tips[0], tips[1], sc, NV, int((sc - RHO * np.pi / 2 - S0) / DS) + 1,
        int(RHO * np.pi / 2 / DS), NV - socks[0]['jc'], y0, y1))
    for side, f in zip((1, -1), socks):
        X, R, Z = f['X'], f['R'], f['Z']
        du = np.linalg.norm(np.roll(X, -1, 1) - X, axis=-1); dv = np.linalg.norm(X[1:] - X[:-1], axis=-1)
        per = du.sum(1)
        print('side %+d: R %.1f..%.1f mm, perimeter %.0f..%.0f mm, du %.2f..%.2f mm, dv %.2f..%.2f mm, held %.1f %%, Z %.3f..%.3f' % (
            side, R.min() * 1e3, R.max() * 1e3, per.min() * 1e3, per.max() * 1e3, du.min() * 1e3, du.max() * 1e3,
            dv.min() * 1e3, dv.max() * 1e3, 100 * f['pin'].mean(), Z.min(), Z.max()))
        sp = np.array([v for _, v in f['spread']]); js = [j for j, _ in f['spread']]
        worst = np.argsort(sp)[-6:]
        print('   du (u offset per wale): %.4f..%.4f' % (f['du'].min(), f['du'].max()))
        print('   radius spread per row/sector: median %.2f mm, worst %s' % (np.median(sp) * 1e3, ', '.join('row %d (S %.3f) %.1f mm' % (js[k], f['s'][js[k]], sp[k] * 1e3) for k in worst)))
        for j in (0, 10, 25, 49, 60, 75, 90, 100, 110, f['jc'], f['jc'] + 20, NV - 1):
            print('   j %3d S %.3f  centre (%.4f, %.4f)  R %.1f..%.1f mm  perim %.0f mm  Z instep %.3f sole %.3f  X[front] (%.3f %.3f %.3f)' % (
                j, f['s'][j], f['ax'][j], f['az'][j], R[j].min() * 1e3, R[j].max() * 1e3, per[j] * 1e3, Z[j, NU // 2], Z[j, 0],
                *X[j, NU // 2]))
    print('wrote %s (%.1f MB)' % (out, os.path.getsize(out) / 1e6))
    np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_sock_debug.npz'),
             **{('%s_%d' % (k, i)): v for i, f in enumerate(socks) for k, v in f.items() if isinstance(v, np.ndarray)})


if __name__ == '__main__':
    main()
