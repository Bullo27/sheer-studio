# SHEER - lays the stocking on the skin (used by tools/reshape_legs.py).
#
# A worn stocking is a taut knit tube: round the tube its tension pulls it onto the skin wherever the skin's
# cross-section is convex, and it bridges only what is concave ROUND the tube - the hollows either side of the Achilles
# tendon, the clefts between the toes, the arch seen from the front. Along the leg it follows the skin (the hoop tension
# holds it in the bend at the front of the ankle and above the heel). So in each cross-section of the tube the worn
# fabric is the convex hull of the skin's section, plus the fabric's own thickness.
#
# The stocking meshes from the Blender build stood off the skin by 0.6 mm on shin and thigh but 1 - 3 mm round the knee and
# 5 - 17 mm round the ankle and over the instep (a loose bag: straight from the instep to the shin, bulging behind the
# heel). Seen edge-on at a hole, the fabric floated in the air (user, 2026-11-17: 'the stocking is effectively just
# floating around', 'floating ultra distant from the foot').
#
# Cross-sections = the cloth lattice's row planes (export_sock_lattice.py): horizontal on the leg, half-planes through
# the bend's axis round ankle and heel, vertical (z = const) along the foot. Each stocking vertex moves only in its own
# row plane, along its ray from the row's centre: its lattice coordinates (row, angle) - and with them the damage maps',
# the wales' - do not change.
import numpy as np
from scipy.spatial import ConvexHull, QhullError
from scipy.ndimage import gaussian_filter1d

import export_sock_lattice as L

NTH = 720


def smooth01(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0); return t * t * (3 - 2 * t)


def _row_cut(P, tri, S, sc):
    """Points (a, B) where the triangles' edges cross the row plane of parameter S."""
    if S >= sc:
        f = P[:, 1] - (L.YC + S - sc); a = P[:, 0]; Bc = P[:, 2]; ok = np.ones(len(P), bool)
    elif S <= sc - L.RHO * np.pi / 2:
        zf = L.ZC - ((sc - L.RHO * np.pi / 2) - S)
        f = P[:, 2] - zf; a = P[:, 0]; Bc = L.ZC + (L.YC - P[:, 1]); ok = P[:, 1] < L.YC + 0.02
    else:
        g = (sc - S) / L.RHO; cg, sg = np.cos(g), np.sin(g)
        dy = P[:, 1] - L.YC; dz = P[:, 2] - L.ZC
        f = dy * cg + dz * sg; b = dz * cg - dy * sg
        a = P[:, 0]; Bc = L.ZC + b; ok = b > -1e-4
    sgn = f > 0
    pts = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        vi, vj = tri[:, i], tri[:, j]
        m = (sgn[vi] != sgn[vj]) & ok[vi] & ok[vj]
        vi, vj = vi[m], vj[m]
        t = f[vi] / (f[vi] - f[vj])
        pts.append(np.stack([a[vi] + t * (a[vj] - a[vi]), Bc[vi] + t * (Bc[vj] - Bc[vi])], 1))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def _hull_radius(pts, c, th):
    """Radius of the convex hull of pts about the centre c along the directions th (angle from +B toward +a)."""
    try:
        hull = ConvexHull(pts)
    except (QhullError, ValueError):
        return None
    V = pts[hull.vertices]                                   # counter-clockwise
    E = np.roll(V, -1, 0) - V
    d = np.stack([np.sin(th), np.cos(th)], 1)                # (a, B) components
    w = V - c
    den = d[:, None, 0] * E[None, :, 1] - d[:, None, 1] * E[None, :, 0]          # cross(d, E)
    num_r = w[None, :, 0] * E[None, :, 1] - w[None, :, 1] * E[None, :, 0]        # cross(V - c, E)
    num_t = w[None, :, 0] * d[:, None, 1] - w[None, :, 1] * d[:, None, 0]        # cross(V - c, d)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = num_r / den; t = num_t / den
    good = (np.abs(den) > 1e-12) & (t >= -1e-6) & (t <= 1 + 1e-6) & (r > 0)
    r = np.where(good, r, -1.0)
    out = r.max(1)
    return out if (out > 0).all() else None


def wrap(B, tri_b, T, side_t, gap=0.0002, y_top=0.776, verbose=True, toes=False):
    """The stocking's vertices T laid on the skin B: returns the new T.
    (Not over the toes: there the row planes cut five separate toes and the hull of each cut changed from row to row - the
    surface folded over itself between the big toe and the second (335 flipped triangles, dark cracks); the toes' stand-off
    was 0.6 - 2 mm anyway. The wrap fades out from the ball of the foot, z -0.055 .. -0.075 m.)"""
    Tn = T.copy()
    tips = [T[side_t * s > 0, 2].min() for s in (1, -1)]
    sc = L.RHO * np.pi / 2 + (L.ZC - max(tips))
    s_rows = np.arange(0.002, sc + (y_top + 0.03 - L.YC), L.DS)
    th = (np.arange(NTH) + 0.5) / NTH * 2 * np.pi - np.pi
    for s in (1, -1):
        mt = side_t * s > 0
        St, at, Bt, _ = L.coords(T[mt], sc)
        # row centres: the stocking's own (as the lattice finds them), held past its ends
        s_lat = L.S0 + L.DS * np.arange(int(np.floor((sc + (y_top - L.YC) - L.S0) / L.DS + 1e-6)) + 1)
        ax, az = L.centres(St, at, Bt, s_lat, sc)
        cx = np.interp(s_rows, s_lat, ax); cz = np.interp(s_rows, s_lat, az)
        # the skin of this leg (a margin across the midline: sections near the top reach it)
        vb = (B[:, 0] * s > -0.002) & (B[:, 1] < y_top + 0.06)
        idx = np.full(len(B), -1); idx[vb] = np.arange(vb.sum())
        tb = tri_b[vb[tri_b].all(1)]; tb = idx[tb]; Pb = B[vb]
        Rh = np.full((len(s_rows), NTH), np.nan)
        for j, S in enumerate(s_rows):
            pts = _row_cut(Pb, tb, S, sc)
            pts = pts[pts[:, 0] * s > 0.0005]
            if len(pts) < 12: continue
            # a closed section of ONE leg: its points surround the centre and stay clear of the midline
            if S >= sc and np.abs(pts[:, 0]).min() < 0.003: continue
            c = np.array([cx[j], cz[j]])
            r = _hull_radius(pts, c, th)
            if r is not None: Rh[j] = r
        valid = ~np.isnan(Rh[:, 0])
        # (rows without a section: from the nearest that has one - they get no weight below)
        jj = np.arange(len(s_rows))
        for k in range(NTH): Rh[~valid, k] = np.interp(jj[~valid], jj[valid], Rh[valid, k])
        # never inside the skin where the section changes quickly from row to row: the larger of the row's own hull
        # and its neighbourhood's mean
        Rs = gaussian_filter1d(Rh, 0.8, axis=0, mode='nearest')
        Rh = np.maximum(Rh, Rs)
        # each vertex: along its ray in its row plane
        pax = np.interp(St, s_rows, cx); paz = np.interp(St, s_rows, cz)
        tht = np.arctan2(at - pax, Bt - paz); r_old = np.hypot(at - pax, Bt - paz)
        fj = np.clip((St - s_rows[0]) / L.DS, 0, len(s_rows) - 1.001); j0 = fj.astype(int); tj = fj - j0
        fk = ((tht + np.pi) / (2 * np.pi) * NTH - 0.5) % NTH; k0 = fk.astype(int) % NTH; tk = fk - np.floor(fk); k1 = (k0 + 1) % NTH
        r_new = ((1 - tj) * ((1 - tk) * Rh[j0, k0] + tk * Rh[j0, k1]) + tj * ((1 - tk) * Rh[j0 + 1, k0] + tk * Rh[j0 + 1, k1])) + gap
        vw = np.interp(St, s_rows, gaussian_filter1d(valid.astype(float), 2.0, mode='nearest') * valid)
        y = T[mt, 1]
        z = T[mt, 2]
        toew = smooth01(-0.055, -0.075, z) * smooth01(0.07, 0.05, y)          # 1 over the toes, 0 from the ball of the foot back
        # (toes=True: the hull goes over the toes too - a taut toe box spans them in every cross-section; the folds this made
        #  between the big toe and the second are smoothed out afterwards by toe_wrap's bridging, 2026-11-18)
        w = vw * smooth01(0.003, 0.009, St) * (1.0 - smooth01(y_top - 0.031, y_top, y)) * (St <= s_rows[-1]) * (1.0 if toes else (1.0 - toew))
        r = r_old + w * (r_new - r_old)
        Tn[mt] = L.to_mesh(St, pax + r * np.sin(tht), paz + r * np.cos(tht), sc)
        if verbose:
            m = w > 0.99
            print('wrap leg %+d: %d rows (%d with a section), moved %d vertices: by p50 %.2f p95 %.2f max %.2f mm inward' % (
                s, len(s_rows), valid.sum(), m.sum(), *np.percentile((r_old - r)[m], [50, 95]) * 1e3, (r_old - r)[m].max() * 1e3))
    return Tn


def toe_wrap(B, NB, T, tri_t, weld_t, gap=0.0002, iters=80, lam=0.45, shrink=0.35, bridge_iters=60, bridge_lam=0.6, verbose=True):
    # (iters=0: no shrink onto the toes - after wrap(toes=True) the knit already spans them; only the bridging smooths)
    """The stocking laid on the TOES (where wrap() fades out): the knit shrinks onto the skin while it smooths itself, so it
    touches the top of every toe and spans the clefts between them, as a taut tube-knit does - never inside the skin.
    (wrap() leaves the toes alone - cut plane by plane, the hull of five separate toes jumped from row to row and the
    surface folded between the big toe and the second - so the toe box kept the Blender build's loose bag, 1 - 4 mm off
    the skin, and where the wrap faded out a hard RIDGE crossed the top of the foot: a wide paddle with lumpy toes,
    independent review 2026-11-17.) Weight: 1 over the toes, fading in over the ball of the foot exactly where wrap() fades
    out, so the two meet without a step."""
    from scipy.spatial import cKDTree
    from scipy import sparse
    n = len(T)
    w_idx = weld_t[tri_t]
    i = np.concatenate([w_idx[:, 0], w_idx[:, 1], w_idx[:, 2], w_idx[:, 1], w_idx[:, 2], w_idx[:, 0]])
    j = np.concatenate([w_idx[:, 1], w_idx[:, 2], w_idx[:, 0], w_idx[:, 0], w_idx[:, 1], w_idx[:, 2]])
    A = sparse.coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr(); A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel(); rep = deg > 0
    Lm = sparse.diags(1.0 / np.maximum(deg, 1)) @ A
    y, z = T[:, 1], T[:, 2]
    w = smooth01(-0.055, -0.075, z) * smooth01(0.07, 0.05, y)                 # (= wrap()'s 'toes' weight)
    act = (w > 1e-3) & rep
    tree = cKDTree(B)
    T = T.copy()
    tri_n0 = np.cross(T[tri_t[:, 1]] - T[tri_t[:, 0]], T[tri_t[:, 2]] - T[tri_t[:, 0]])
    for it in range(iters):
        Ts = Lm @ T
        T[act] += (lam * w[act])[:, None] * (Ts[act] - T[act])
        _, idx = tree.query(T[act]); nb = NB[idx]
        h = ((T[act] - B[idx]) * nb).sum(1)
        push = np.maximum(gap - h, 0.0)
        pull = np.maximum(h - gap, 0.0) * shrink * w[act]
        T[act] += nb * (push - pull)[:, None]
        T = T[weld_t]
    # ... then it BRIDGES: relaxed with only the skin pushing it out, the knit lifts out of the clefts between the toes and
    # spans them (shrunk onto every toe it had dived into each cleft: five splayed fingers with dark cracks between them)
    Tpre = T.copy()
    for it in range(bridge_iters):
        Ts = Lm @ T
        T[act] += (bridge_lam * w[act])[:, None] * (Ts[act] - T[act])
        _, idx = tree.query(T[act]); nb = NB[idx]
        h = ((T[act] - B[idx]) * nb).sum(1)
        T[act] += nb * np.maximum(gap - h, 0.0)[:, None]
        T = T[weld_t]
    # (UN-FLIP: where the bridging folded a triangle over it faces inward - culled, a hole the skin showed through: pink
    #  flecks on the little toe, review 11. Its corners go back toward where the shrink had left them, a step at a time, and
    #  the skin pushes them out again)
    for it in range(16):
        tri_n1 = np.cross(T[tri_t[:, 1]] - T[tri_t[:, 0]], T[tri_t[:, 2]] - T[tri_t[:, 0]])
        flip = (tri_n0 * tri_n1).sum(1) < 0
        if not flip.any(): break
        vs = np.unique(weld_t[tri_t[flip].ravel()])
        T[vs] = 0.5 * (T[vs] + Tpre[vs])
        _, idx = tree.query(T[vs]); nb = NB[idx]
        h = ((T[vs] - B[idx]) * nb).sum(1)
        T[vs] += nb * np.maximum(gap - h, 0.0)[:, None]
        T = T[weld_t]
    tri_n1 = np.cross(T[tri_t[:, 1]] - T[tri_t[:, 0]], T[tri_t[:, 2]] - T[tri_t[:, 0]])
    flipped = int(((tri_n0 * tri_n1).sum(1) < 0).sum())
    if verbose:
        _, idx = tree.query(T[act]); h = ((T[act] - B[idx]) * NB[idx]).sum(1)
        full = w[act] > 0.99
        print('toe_wrap: %d vertices (%d fully), stand-off over the toes p05 %.2f p50 %.2f p95 %.2f max %.2f mm, %d triangles flipped' % (
            act.sum(), full.sum(), *np.percentile(h[full], [5, 50, 95]) * 1e3, h[full].max() * 1e3, flipped))
    return T
