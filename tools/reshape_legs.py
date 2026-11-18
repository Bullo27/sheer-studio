#!/usr/bin/env python3
# SHEER - reshapes the legs (the character's build) and regularises the stocking shell, baking the result into the
# meshes the game loads. Reads the untouched meshes from tools/sim/ref_data/meshes_r16/ and writes
# unity/Assets/StreamingAssets/{body,tights}.smesh; then rebuild the cloth lattice (tools/sim/export_lattice.py).
#
# 1. SHELL: the stocking is laid ON the skin (tools/sim/wrap.py): in each cross-section of the tube the worn fabric is the
#    convex hull of the skin's section plus the fabric's own 0.2 mm - taut knit bridges only what is concave round the
#    tube (beside the Achilles tendon, between the toes). The Blender build's shell stood off 0.6 mm on shin and thigh,
#    1 - 3 mm round the knee and 5 - 17 mm round the ankle and instep: seen edge-on at a hole the fabric floated in the
#    air (user, 2026-11-17). (2026-11-16 this step only smoothed the stand-off round the knee - the outline's steps.)
# 2. BUILD: each leg's cross-sections are scaled about the leg's own axis by a profile of height measured on the original
#    (front-view width of the leg, original / ours, median of five quiet VIEW 01 frames: knee 0.87, lower thigh
#    0.91 - 0.96, 0.63 m and below the knee equal) - narrow knees, a thigh that tapers into them; the upper thigh under
#    the hem a little fuller (+3.5 %, user: thighs too thin).
# 3. ARCH: the medial arch of each foot filled in part (a softer, rounder foot; user: 'a little fattier on the arch').
# The same deformation goes to skin and stocking, so the shell keeps its stand-off. Heights do not change (uv0 / uv2 /
# damage coordinates stay valid); uv1.xyz (rest position) is rewritten.
#   python3 tools/reshape_legs.py [--no-build] [--no-shell] [--no-arch]
import os, sys, struct
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree
from scipy import sparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'sim'))
import geom                                   # leg_axis
import wrap                                   # the stocking laid on the skin
from smesh import load

ROOT = os.path.abspath(os.path.join(HERE, '..'))
SRC = os.path.join(ROOT, 'tools', 'sim', 'ref_data', 'meshes_r16')
DST = os.path.join(ROOT, 'unity', 'Assets', 'StreamingAssets')

# width ratio original / ours by height (m), measured (tools: <scratchpad>/pose/legw.py on 1.5, 2.0, 4.5, 16.8, 23.5 s)
RATIO = [(0.300, 1.000), (0.390, 1.000), (0.396, 1.000), (0.408, 0.976), (0.421, 0.960), (0.434, 0.950), (0.447, 0.941),
         (0.460, 0.924), (0.473, 0.888), (0.486, 0.872), (0.499, 0.867), (0.512, 0.873), (0.525, 0.898), (0.538, 0.908),
         (0.551, 0.920), (0.564, 0.931), (0.577, 0.941), (0.590, 0.956), (0.603, 0.965), (0.616, 0.976), (0.629, 0.998),
         (0.642, 1.006), (0.660, 1.025), (0.690, 1.035), (0.720, 1.035), (0.750, 1.020), (0.780, 1.000), (0.900, 1.000)]
GAP = 0.0002                                  # the worn fabric's stand-off from the skin (m): its own thickness
TOE_Z0, TOE_K = -0.062, 0.82                  # the toes: everything beyond z0 (the ball of the foot) drawn back to 82 %
TW_ITERS, TW_SHRINK, TW_BRIDGE = int(os.environ.get("TW_ITERS", 6)), float(os.environ.get("TW_SHRINK", 0.05)), int(os.environ.get("TW_BRIDGE", 90))   # the knit over the toes: dips part way into the clefts (shrink), then smoothed (bridge)
TOE_INF = float(os.environ.get("TOE_INF", 0.0027))                              # the toes: their skin moved out onto the surface this far outside it (2c)
TOE_BLUR = float(os.environ.get("TOE_BLUR", 1.4))   # the toes' distance field blurred over this many 0.6 mm voxels before the skin goes onto it: wider = the toes merge into one box
TOE_PAD = float(os.environ.get("TOE_PAD", 0.8))   # ... and this much more (x TOE_INF) at the very bottom, fading out 3 - 12 mm up: the pads fill out toward the floor
TOE_LIFT = 0.0                                # ... and their height above the sole x (1 + this), weighted along the foot (0.15 tried 2026-11-18: skin through the little toe, a crease across the forefoot - off)
SLIM = float(os.environ.get("SLIM", 0.26))                                  # the forefoot / toes narrower by this much at the toe tips (x about the foot's centre line)


def write_smesh(path, nv, subs, ch, types):
    out = bytearray(b'SMSH') + struct.pack('<III', 1, nv, len(subs))
    for s in subs:
        a = np.ascontiguousarray(s, np.uint32).ravel()
        out += struct.pack('<I', a.size) + a.tobytes()
    out += struct.pack('<I', len(ch))
    for name, arr in ch.items():
        typ = types[name]; arr = np.ascontiguousarray(arr, np.uint32 if typ else np.float32)
        out += name.encode().ljust(16, b'\0')[:16] + struct.pack('<BBH', typ, arr.shape[1], 0) + arr.tobytes()
    open(path, 'wb').write(bytes(out))


def smooth01(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0); return t * t * (3 - 2 * t)


def weld_index(P):
    """Index of the first vertex at the same position (seam duplicates)."""
    key = np.round(P / 1e-6).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return first[inv.ravel()]


def vertex_normals(P, tri, weld):
    a, b, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    fn = np.cross(b - a, c - a)                                   # area weighted
    N = np.zeros_like(P)
    for k in range(3): np.add.at(N, weld[tri[:, k]], fn)
    N = N[weld]
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def adjacency(tri, weld, n):
    w = weld[tri]
    i = np.concatenate([w[:, 0], w[:, 1], w[:, 2], w[:, 1], w[:, 2], w[:, 0]])
    j = np.concatenate([w[:, 1], w[:, 2], w[:, 0], w[:, 0], w[:, 1], w[:, 2]])
    A = sparse.coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    return sparse.diags(1.0 / np.maximum(deg, 1)) @ A


def axes(T, side_t):
    """Per leg: (ys, cx, cz) of the stocking's axis (geom.leg_axis, as the cloth lattice uses)."""
    out = {}
    for s in (1, -1):
        Q = T[(side_t * s > 0) & (T[:, 1] > 0.03) & (T[:, 1] < 0.85)]
        out[s] = geom.leg_axis(Q, 0.06, 0.82)
    return out


def scale_profile(h):
    hs = np.array([a for a, _ in RATIO]); rs = np.array([b for _, b in RATIO])
    return np.interp(h, hs, rs)


def widths(P, tri, side, ys):
    """Front-view (x) width of the leg on each side at the given heights: exact outline from the triangle edges."""
    E = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    out = {}
    for s in (1, -1):
        e = E[(side[E[:, 0]] * s > 0) & (side[E[:, 1]] * s > 0)]
        a, b = P[e[:, 0]], P[e[:, 1]]
        lo = np.minimum(a[:, 1], b[:, 1]); hi = np.maximum(a[:, 1], b[:, 1])
        keep = (hi > ys[0] - 0.01) & (lo < ys[-1] + 0.01) & (hi - lo > 1e-9)
        a, b, lo, hi = a[keep], b[keep], lo[keep], hi[keep]
        w = []
        for y in ys:
            m = (lo <= y) & (hi > y)
            t = (y - a[m, 1]) / (b[m, 1] - a[m, 1]); x = a[m, 0] + t * (b[m, 0] - a[m, 0])
            w.append(x.max() - x.min() if len(x) else np.nan)
        out[s] = np.array(w)
    return out


def radial_scale(P, side, ax, sfun):
    """Scale each leg's cross-sections about its axis by sfun(height); 1 near the midline (what joins the legs)."""
    Q = P.copy()
    for s in (1, -1):
        ys, cx, cz = ax[s]
        m = (side * s > 0) & (P[:, 1] > 0.28) & (P[:, 1] < 0.82)
        y = P[m, 1]; x0 = np.interp(y, ys, cx); z0 = np.interp(y, ys, cz)
        # (the fade only where the legs join the body: the knees too come within ~5 mm of the midline)
        mid = 1.0 - (1.0 - smooth01(0.003, 0.012, np.abs(P[m, 0]))) * smooth01(0.70, 0.74, y)
        k = 1.0 + (sfun(y) - 1.0) * mid
        Q[m, 0] = x0 + k * (P[m, 0] - x0); Q[m, 2] = z0 + k * (P[m, 2] - z0)
    return Q


def arch_fill(P, N, side, amount=0.0042):
    """Fill the medial arch of the foot in part: outward along the normal, a smooth bump over the arch."""
    Q = P.copy()
    for s in (1, -1):
        m = (side * s > 0) & (P[:, 1] < 0.05)
        p = P[m]; n = N[m]
        # medial = toward the midline: -s in x; the arch's surface faces medially and down
        face = smooth01(0.15, 0.55, -s * n[:, 0] - 0.6 * n[:, 1])
        wz = np.exp(-((p[:, 2] - (-0.004)) / 0.030) ** 2)            # midfoot, between heel and ball
        wy = smooth01(0.002, 0.009, p[:, 1]) * smooth01(0.040, 0.020, p[:, 1])
        Q[m] = p + n * (amount * (face * wz * wy))[:, None]
    return Q


def drop_small_components(P, subs, min_verts):
    """The triangle lists without the connected pieces of fewer than min_verts (welded) vertices."""
    from scipy.sparse.csgraph import connected_components
    T = np.concatenate([np.asarray(t).reshape(-1, 3) for t in subs]).astype(np.int64)
    w = weld_index(P)
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    A = sparse.coo_matrix((np.ones(len(e)), (w[e[:, 0]], w[e[:, 1]])), shape=(len(P), len(P)))
    _, lab = connected_components(A, directed=False)
    used = np.unique(w[T.ravel()]); size = np.bincount(lab[used], minlength=lab.max() + 1)
    out, dropped = [], 0
    for t in subs:
        t = np.asarray(t).reshape(-1, 3); keep = size[lab[w[t[:, 0]]]] >= min_verts
        dropped += (~keep).sum(); out.append(t[keep])
    print('body: dropped %d triangles of stray pieces' % dropped)
    return out


def cavity_ao(P, N, weld, scales=((0.002, 24, 2.2), (0.006, 24, 1.4)), floor=0.35):
    """Per vertex, how deep it sits in a hollow: at each scale the surface is resampled on a grid of `cell` (the mean of
    its points per cell), the centroid of the k samples nearest to the vertex is measured along its normal, divided by
    the radius they span. Above the surface (a hollow, or another leg close by) occludes: ao = 1 - sum(gain x that)."""
    from scipy.spatial import cKDTree
    U = np.unique(weld)
    Pu, Nu = P[U], N[U]
    occ = np.zeros(len(Pu))
    for cell, k, gain in scales:
        key = np.floor(Pu / cell).astype(np.int64)
        _, inv = np.unique(key, axis=0, return_inverse=True); inv = inv.ravel()
        cnt = np.bincount(inv).astype(np.float64)
        S = np.stack([np.bincount(inv, Pu[:, j]) for j in range(3)], 1) / cnt[:, None]
        d, idx = cKDTree(S).query(Pu, k=k, workers=-1)
        C = S[idx].mean(1)
        cav = ((C - Pu) * Nu).sum(1) / np.maximum(d[:, -1], 1e-6)
        occ += gain * np.clip(cav, 0.0, None)
    out = np.ones(len(P)); out[U] = np.clip(1.0 - occ, floor, 1.0)
    return out[weld]


def inflate_toes(B, tri, weld, side, r, h=0.0006, blur=1.4, z0=-0.046, z1=-0.066, lift=0.0, pad=0.0):
    """The skin of the toes moved onto the iso-surface at +r of its signed distance field (voxels of h, blurred by blur
    voxels): rounder, fuller toes, narrow clefts closed. Blended in from z0 to z1 (toward the toe tips) by z alone."""
    from scipy.spatial import cKDTree
    from scipy.ndimage import gaussian_filter, map_coordinates
    B = B.copy()
    N = vertex_normals(B, tri, weld)
    for s in (1.0, -1.0):
        reg = (side * s > 0) & (B[:, 1] < 0.07) & (B[:, 2] < z0 + 0.008)
        if not reg.any(): continue
        # dense samples of the surface (triangles with all corners in the region), with their normals
        tm = reg[tri].all(1); t = tri[tm]
        a, b, c = B[t[:, 0]], B[t[:, 1]], B[t[:, 2]]
        na, nb_, nc = N[t[:, 0]], N[t[:, 1]], N[t[:, 2]]
        g = np.linspace(0, 1, 5)
        uu, vv = np.meshgrid(g, g); m = (uu + vv) <= 1.0; uu = uu[m]; vv = vv[m]; ww = 1 - uu - vv
        S = (a[:, None] * ww[None, :, None] + b[:, None] * uu[None, :, None] + c[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN = (na[:, None] * ww[None, :, None] + nb_[:, None] * uu[None, :, None] + nc[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN /= np.maximum(np.linalg.norm(SN, axis=1, keepdims=True), 1e-12)
        lo = B[reg].min(0) - 6 * h - r; hi = B[reg].max(0) + 6 * h + r
        shape = np.ceil((hi - lo) / h).astype(int) + 1
        gx, gy, gz = [lo[k] + h * np.arange(shape[k]) for k in range(3)]
        Q = np.stack(np.meshgrid(gx, gy, gz, indexing='ij'), -1).reshape(-1, 3)
        tree = cKDTree(S)
        d, idx = tree.query(Q, workers=-1)
        sgn = np.sign(((Q - S[idx]) * SN[idx]).sum(1)); sgn[sgn == 0] = 1.0
        phi = gaussian_filter((d * sgn).reshape(shape), blur)
        def sample(P):
            co = ((P - lo) / h).T
            return map_coordinates(phi, co, order=1, mode='nearest')
        def grad(P):
            e = h * 0.5
            return np.stack([(sample(P + np.array(o) * e) - sample(P - np.array(o) * e)) / (2 * e) for o in ((1, 0, 0), (0, 1, 0), (0, 0, 1))], 1)
        P0 = B[reg].copy(); P = P0.copy()
        for _ in range(24):                                         # Newton steps onto phi = r, each <= 0.5 mm, in all <= 6 mm
            f = sample(P) - r * (1.0 + pad * smooth01(0.012, 0.003, P[:, 1])); gr = grad(P); gn = (gr * gr).sum(1) + 1e-12
            st = -(f / gn)[:, None] * gr
            sl = np.linalg.norm(st, axis=1, keepdims=True)
            P += st * np.minimum(1.0, 0.0005 / np.maximum(sl, 1e-12))
            Dd = P - P0; dl = np.linalg.norm(Dd, axis=1, keepdims=True)
            P = P0 + Dd * np.minimum(1.0, 0.006 / np.maximum(dl, 1e-12))
        w = smooth01(z0, z1, B[reg, 2])
        D = (P - B[reg]) * w[:, None]
        dn = np.linalg.norm(D, axis=1)
        print('toes (%+d): moved p50 %.2f p95 %.2f max %.2f mm' % (s, *np.percentile(dn[w > 0.5], [50, 95]) * 1e3, dn.max() * 1e3))
        B[reg] += D
        # ... and taller above the sole (the original's toe row seen from the front is ~110 px tall vs our 70): weighted by z
        # alone, like the inflation, so no ridge forms across the instep
        if lift > 0.0:
            yb = B[reg, 1]
            B[reg, 1] = yb + np.clip(yb - 0.004, 0.0, None) * lift * w
    return B[weld]


def close_toes(B, tri, weld, side, T, wt, r, gap, h=0.0005, z0=-0.050, z1=-0.068):
    """The STOCKING over the toes laid on the toes' morphological CLOSING (dilate by r, erode by r): the knit is a taut
    membrane - it spans every cleft narrower than ~2r and lies on the toes' tops, which the closing leaves where they are.
    (Inflating the skin onto its +r iso-surface instead made every toe r fatter: 'mashed potatoes', the user 2026-11-18.)
    The skin is not changed: through the sheer knit its clefts still show as soft dark lines. Blended in from z0 to z1."""
    from scipy.spatial import cKDTree
    from scipy.ndimage import gaussian_filter, map_coordinates, distance_transform_edt
    T = T.copy()
    N = vertex_normals(B, tri, weld)
    for s in (1.0, -1.0):
        reg = (side * s > 0) & (B[:, 1] < 0.075) & (B[:, 2] < z0 + 0.015)
        if not reg.any(): continue
        tm = reg[tri].all(1); t = tri[tm]
        a, b, c = B[t[:, 0]], B[t[:, 1]], B[t[:, 2]]
        na, nb_, nc = N[t[:, 0]], N[t[:, 1]], N[t[:, 2]]
        g = np.linspace(0, 1, 5)
        uu, vv = np.meshgrid(g, g); m = (uu + vv) <= 1.0; uu = uu[m]; vv = vv[m]; ww = 1 - uu - vv
        S = (a[:, None] * ww[None, :, None] + b[:, None] * uu[None, :, None] + c[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN = (na[:, None] * ww[None, :, None] + nb_[:, None] * uu[None, :, None] + nc[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN /= np.maximum(np.linalg.norm(SN, axis=1, keepdims=True), 1e-12)
        lo = B[reg].min(0) - (r + 8 * h); hi = B[reg].max(0) + (r + 8 * h)
        shape = np.ceil((hi - lo) / h).astype(int) + 1
        gx, gy, gz = [lo[k] + h * np.arange(shape[k]) for k in range(3)]
        Q = np.stack(np.meshgrid(gx, gy, gz, indexing='ij'), -1).reshape(-1, 3)
        d, idx = cKDTree(S).query(Q, workers=-1)
        sgn = np.sign(((Q - S[idx]) * SN[idx]).sum(1)); sgn[sgn == 0] = 1.0
        phi = (d * sgn).reshape(shape)
        dil = phi < r                                               # dilated by r
        phid = (distance_transform_edt(~dil) - distance_transform_edt(dil)) * h
        phic = gaussian_filter(phid + r, 1.0)                       # ... eroded by r: the closing (< 0 inside)
        def sample(P):
            return map_coordinates(phic, ((P - lo) / h).T, order=1, mode='nearest')
        def grad(P):
            e = h * 0.5
            return np.stack([(sample(P + np.array(o) * e) - sample(P - np.array(o) * e)) / (2 * e) for o in ((1, 0, 0), (0, 1, 0), (0, 0, 1))], 1)
        sel = np.where((np.sign(T[:, 0]) == s) & (T[:, 1] < 0.075) & (T[:, 2] < z0 + 0.012) & (wt == np.arange(len(T))))[0]
        P0 = T[sel].copy(); P = P0.copy()
        for _ in range(40):                                         # Newton steps onto phic = gap, each <= 0.5 mm, in all <= 8 mm
            f = sample(P) - gap; gr = grad(P); gn = (gr * gr).sum(1) + 1e-12
            st = -(f / gn)[:, None] * gr
            sl = np.linalg.norm(st, axis=1, keepdims=True)
            P += st * np.minimum(1.0, 0.0005 / np.maximum(sl, 1e-12))
            Dd = P - P0; dl = np.linalg.norm(Dd, axis=1, keepdims=True)
            P = P0 + Dd * np.minimum(1.0, 0.008 / np.maximum(dl, 1e-12))
        w = smooth01(z0, z1, P0[:, 2])
        # (never into the skin: only outward from where the stocking was, along the closing's normal)
        D = (P - P0) * w[:, None]
        T[sel] = P0 + D
        dn = np.linalg.norm(D, axis=1)
        if (w > 0.5).any():
            print('  toes closed (%+d, r %.1f mm): stocking moved p50 %.2f p95 %.2f max %.2f mm' % (s, r * 1e3, *np.percentile(dn[w > 0.5], [50, 95]) * 1e3, dn.max() * 1e3))
    return T[wt]


def close_skin(B, tri, weld, side, r, h=0.0005, z0=-0.046, z1=-0.066):
    """The SKIN of the toes on its own morphological closing (dilate r, erode r), outward only: the knit presses the toes
    together - every cleft narrower than ~2r filled, the toes' tops and nails where they were. Through the sheer knit the
    toes then read as one rounded box with soft bumps, as on a stockinged foot, instead of five separate digits with dark
    gaps (the stocking alone on the closing still showed the skin's clefts through it, 2026-11-18). Blended in from z0 to
    z1 by z (toward the toe tips)."""
    from scipy.spatial import cKDTree
    from scipy.ndimage import gaussian_filter, map_coordinates, distance_transform_edt
    B = B.copy()
    N = vertex_normals(B, tri, weld)
    rep = weld == np.arange(len(B))
    for s in (1.0, -1.0):
        reg = (side * s > 0) & (B[:, 1] < 0.075) & (B[:, 2] < z0 + 0.015)
        if not reg.any(): continue
        tm = reg[tri].all(1); t = tri[tm]
        a, b, c = B[t[:, 0]], B[t[:, 1]], B[t[:, 2]]
        na, nb_, nc = N[t[:, 0]], N[t[:, 1]], N[t[:, 2]]
        g = np.linspace(0, 1, 5)
        uu, vv = np.meshgrid(g, g); m = (uu + vv) <= 1.0; uu = uu[m]; vv = vv[m]; ww = 1 - uu - vv
        S = (a[:, None] * ww[None, :, None] + b[:, None] * uu[None, :, None] + c[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN = (na[:, None] * ww[None, :, None] + nb_[:, None] * uu[None, :, None] + nc[:, None] * vv[None, :, None]).reshape(-1, 3)
        SN /= np.maximum(np.linalg.norm(SN, axis=1, keepdims=True), 1e-12)
        lo = B[reg].min(0) - (r + 8 * h); hi = B[reg].max(0) + (r + 8 * h)
        shape = np.ceil((hi - lo) / h).astype(int) + 1
        gx, gy, gz = [lo[k] + h * np.arange(shape[k]) for k in range(3)]
        Q = np.stack(np.meshgrid(gx, gy, gz, indexing='ij'), -1).reshape(-1, 3)
        d, idx = cKDTree(S).query(Q, workers=-1)
        sgn = np.sign(((Q - S[idx]) * SN[idx]).sum(1)); sgn[sgn == 0] = 1.0
        phi = (d * sgn).reshape(shape)
        dil = phi < r
        phic = gaussian_filter((distance_transform_edt(~dil) - distance_transform_edt(dil)) * h + r, 1.0)
        def sample(P):
            return map_coordinates(phic, ((P - lo) / h).T, order=1, mode='nearest')
        def grad(P):
            e = h * 0.5
            return np.stack([(sample(P + np.array(o) * e) - sample(P - np.array(o) * e)) / (2 * e) for o in ((1, 0, 0), (0, 1, 0), (0, 0, 1))], 1)
        sel = np.where(reg & rep)[0]
        P0 = B[sel].copy(); P = P0.copy()
        for _ in range(40):                                         # onto phic = 0, only from inside it (outward)
            f = np.minimum(sample(P), 0.0); gr = grad(P); gn = (gr * gr).sum(1) + 1e-12
            st = -(f / gn)[:, None] * gr
            sl = np.linalg.norm(st, axis=1, keepdims=True)
            P += st * np.minimum(1.0, 0.0005 / np.maximum(sl, 1e-12))
            Dd = P - P0; dl = np.linalg.norm(Dd, axis=1, keepdims=True)
            P = P0 + Dd * np.minimum(1.0, 0.008 / np.maximum(dl, 1e-12))
        w = smooth01(z0, z1, P0[:, 2])
        D = (P - P0) * w[:, None]
        B[sel] = P0 + D
        dn = np.linalg.norm(D, axis=1)
        if (w > 0.5).any():
            print('skin toes closed (%+d, r %.1f mm): moved p50 %.2f p95 %.2f max %.2f mm' % (s, r * 1e3, *np.percentile(dn[w > 0.5], [50, 95]) * 1e3, dn.max() * 1e3))
    return B[weld]


def main():
    do_build = '--no-build' not in sys.argv; do_shell = '--no-shell' not in sys.argv; do_arch = '--no-arch' not in sys.argv
    nvb, subs_b, chb = load(os.path.join(SRC, 'body.smesh'))
    nvt, subs_t, cht = load(os.path.join(SRC, 'tights.smesh'))
    types_b = {k: (1 if v.dtype == np.uint32 else 0) for k, v in chb.items()}
    types_t = {k: (1 if v.dtype == np.uint32 else 0) for k, v in cht.items()}
    chb = {k: np.array(v) for k, v in chb.items()}; cht = {k: np.array(v) for k, v in cht.items()}
    B = chb['position'].astype(np.float64); T = cht['position'].astype(np.float64)
    T_src = T.copy()                                        # (the asset's own stocking: its triangles' orientation, for the un-flip)
    B_src = B.copy()                                        # (the asset's own skin: the foot goes back to it, step 5b)
    side_b = np.where(B[:, 0] >= 0, 1.0, -1.0); side_t = np.sign(cht['uv2'][:, 0]).astype(np.float64)
    tri_b = np.concatenate(subs_b).reshape(-1, 3).astype(np.int64); tri_t = np.concatenate(subs_t).reshape(-1, 3).astype(np.int64)
    wb = weld_index(B); wt = weld_index(T)
    NB = vertex_normals(B, tri_b, wb); NT = vertex_normals(T, tri_t, wt)

    ys = np.arange(0.28, 0.80, 0.002)
    W_cur = widths(T, tri_t, side_t, ys)                          # the stocking as measured against the original
    # ---- 1. shell: laid on the skin - here to know how much narrower that makes the outline (the build step makes it
    #      good); the stocking is laid on the FINAL skin once more at the end
    if do_shell:
        T = wrap.wrap(B, tri_b, T, side_t, gap=GAP)

    # ---- 2. build
    if do_build:
        ax = axes(T, side_t)
        # target width = ratio x the width that was measured; laying the shell on the skin has taken some off, most round the knee
        W_reg = widths(T, tri_t, side_t, ys)
        k = 0.5 * (W_cur[1] / W_reg[1] + W_cur[-1] / W_reg[-1])
        k = np.where(np.isfinite(k), k, 1.0)
        sc = gaussian_filter1d(scale_profile(ys) * k, 4)          # (8 mm)
        grid = np.arange(0.0, 1.0, 0.001)
        sg = np.interp(grid, ys, sc, left=1.0, right=1.0)
        sg = np.where((grid < 0.30) | (grid > 0.79), 1.0, sg)
        sg = gaussian_filter1d(sg, 6)
        sm = lambda y: sg[np.clip((y * 1000).astype(int), 0, 999)]
        for h in (0.40, 0.44, 0.47, 0.50, 0.53, 0.56, 0.60, 0.64, 0.68, 0.72, 0.76):
            i = int((h - ys[0]) / 0.002)
            print('  h %.2f  shell x %.3f  ratio %.3f  -> scale %.3f' % (h, k[i], scale_profile(h), sm(np.array([h]))[0]))
        B = radial_scale(B, side_b, ax, sm); T = radial_scale(T, side_t, ax, sm)
        W_new = widths(T, tri_t, side_t, ys)
        for h in (0.40, 0.44, 0.47, 0.50, 0.53, 0.56, 0.60, 0.64, 0.68, 0.72):
            i = int((h - ys[0]) / 0.002)
            print('  h %.2f  width L %.1f -> %.1f mm (x%.3f, target x%.3f)' % (h, W_cur[1][i] * 1e3, W_new[1][i] * 1e3, W_new[1][i] / W_cur[1][i], scale_profile(h)))
        for s in (1, -1):
            print('axis leg %+d at 0.47 m: x %.4f z %.4f' % (s, np.interp(0.47, ax[s][0], ax[s][1]), np.interp(0.47, ax[s][0], ax[s][2])))

    # ---- 2b. a slimmer forefoot, the toes closer together (independent review 2026-11-17: ours a wide paddle, the
    #      original's a slim foot): x about each foot's own centre line, from the ball of the foot to the toe tips
    if '--no-slim' not in sys.argv:
        for P_, sd in ((B, side_b), (T, side_t)):
            for s_ in (1, -1):
                m = (sd * s_ > 0) & (P_[:, 1] < 0.07) & (P_[:, 2] < -0.02)
                if not m.any(): continue
                zz = P_[m, 2]
                # the foot's centre line: the mean x of the skin per 5 mm of z (the stocking uses the skin's)
                Bm = (side_b * s_ > 0) & (B[:, 1] < 0.07) & (B[:, 2] < -0.02)
                zb = np.arange(B[Bm, 2].min(), -0.02 + 1e-6, 0.005)
                cx = np.array([B[Bm & (np.abs(B[:, 2] - z0) < 0.004), 0].mean() if (Bm & (np.abs(B[:, 2] - z0) < 0.004)).any() else np.nan for z0 in zb])
                ok = np.isfinite(cx); cx = np.interp(zz, zb[ok], gaussian_filter1d(cx[ok], 2))
                k = 1.0 - SLIM * smooth01(-0.03, -0.075, zz)
                P_[m, 0] = cx + (P_[m, 0] - cx) * k
        print('forefoot slimmed by up to %.0f %%' % (SLIM * 100))
        # (and the toes shorter, drawn back toward the ball of the foot: the base mesh's toes are long flat digits along the
        #  floor - under the knit a row of lumps, 'melted wax', independent review 3; the original's toes are short and
        #  bunched under a round toe box)
        for P_, sd in ((B, side_b), (T, side_t)):
            m = (P_[:, 1] < 0.07) & (P_[:, 2] < TOE_Z0)
            P_[m, 2] = TOE_Z0 + (P_[m, 2] - TOE_Z0) * TOE_K
        print('toes shortened to %.0f %% beyond z %.3f' % (TOE_K * 100, TOE_Z0))

    # ---- 2c. fuller toes: the base mesh's are thin flat digits (the big toe 18 x 22 mm in section, the others 12 x 15 mm, a
    #      3 - 5 mm cleft between each two) - under the knit a frill of little lumps along the floor in front of a flat
    #      slab of a toe box (independent review 4, the most visible defect of VIEW 02). The skin of the toes is moved out
    #      onto the surface TOE_INF outside it, of a smoothed signed distance field: every toe rounder and fuller, clefts
    #      narrower than 2 x TOE_INF closed (as a stocking squeezes the toes together). (Pushed along the vertex normals
    #      instead, the webbing between the toes - normals every which way - tore into shards that came through the knit,
    #      and a weight cut off by height drew a U-shaped step round the forefoot.) Weighted by the distance along the
    #      foot only.
    if '--no-plump' not in sys.argv:
        B = inflate_toes(B, tri_b, wb, side_b, TOE_INF, lift=TOE_LIFT, pad=TOE_PAD, blur=TOE_BLUR)
    tcs = float(os.environ.get("TOE_CLOSE_SKIN", 0.0))     # m: the skin's toes pressed together (close_skin); 0 = off
    if tcs > 0.0:
        B = close_skin(B, tri_b, wb, side_b, tcs)

    # ---- 3. arch (skin, then the stocking over it with the same push)
    if do_arch:
        NB = vertex_normals(B, tri_b, wb); NT = vertex_normals(T, tri_t, wt)
        B2 = arch_fill(B, NB, side_b); T2 = arch_fill(T, NT, side_t)
        print('arch: skin max %.1f mm, stocking max %.1f mm' % (np.linalg.norm(B2 - B, axis=1).max() * 1e3, np.linalg.norm(T2 - T, axis=1).max() * 1e3))
        B, T = B2, T2

    # ---- 3b. THE FOOT AS THE MODEL CAME. The user, 2026-11-18: 'the foot is still horrible, it does not resemble a human
    #      foot. Why are you not using the original one that came with the model body? It was more than fine.' Every toe
    #      step above (shortening, slimming, inflating, pads, the arch fill) was made to answer reviews and together they
    #      turned the toes into swollen lumps. Below the ankle the SKIN goes back to the source mesh exactly (SRC = the
    #      model's 13 Nov export), blended into the reshaped leg between 11 and 7 cm - and so does the stocking's own shape,
    #      so that its lattice coordinates are the model's; step 4 then lays it ON that skin. (Restored after step 4 it
    #      was the model's own stocking again, floating millimetres off the heel and ankle - the user, 2026-11-18, and on
    #      11-17: 'floating ultra distant from the foot'.) ORIG_FOOT=0 keeps the reshaped foot, for experiments only.
    if os.environ.get("ORIG_FOOT", "1") != "0":
        wB = smooth01(0.11, 0.07, B_src[:, 1]); wT = smooth01(0.11, 0.07, T_src[:, 1])
        B = B + (B_src - B) * wB[:, None]
        T = T + (T_src - T) * wT[:, None]
        print("foot: the model's own below 7 cm (skin %d, stocking %d vertices; blended up to 11 cm), the stocking laid on it below" % ((wB > 0.999).sum(), (wT > 0.999).sum()))

    # ---- 4. the stocking on the final skin
    if do_shell:
        T = wrap.wrap(B, tri_b, T, side_t, gap=GAP, toes=True)
        NB = vertex_normals(B, tri_b, wb)
        if '--no-toes' not in sys.argv:
            T = wrap.toe_wrap(B, NB, T, tri_t, wt, gap=GAP, iters=TW_ITERS, shrink=TW_SHRINK, bridge_iters=TW_BRIDGE, bridge_lam=0.6)
        # (TOE BOX: the stocking's toe is one smooth bag over the toes - a taut tube-knit does not follow each toe, it squeezes
        #  them together and spans them: smoothed hard beyond the ball, then pushed back out of the skin (0.2 mm). Following
        #  every toe it read as 'five separate sausage toes under a groove', reviews 10 - 13. TOE_BOX iterations; 0 = off)
        tb_it = int(os.environ.get("TOE_BOX", 0))         # (40 explicit passes tried 2026-11-18: no visible change - far too few for a mesh this dense)
        # (TOE SHRINK-WRAP (2026-11-18, the user: 'mashed potatoes, not toes'): the knit over the toes is a taut membrane - it
        #  spans the clefts and lies on the toes' tops, so the toes show as soft bumps under one smooth box. Implicit smoothing
        #  ((I + lam (I - W)) x = x0, W the neighbours' average, lam ~ the squared reach in vertex rings) then pushed back out of
        #  the skin, TOE_WRAP_N times: the result settles on the toes' envelope without the high-frequency crumple that
        #  following every bump of the inflated skin left. TOE_WRAP_N 0 = off)
        tw_n = int(os.environ.get("TOE_WRAP_N", 0)); tw_lam = float(os.environ.get("TOE_WRAP_LAM", 120.0))
        if tw_n > 0 or tb_it > 0:
            from scipy import sparse as _sp2
            from scipy.sparse.linalg import spsolve
            wi2 = wt[tri_t]
            i2 = np.concatenate([wi2[:, 0], wi2[:, 1], wi2[:, 2], wi2[:, 1], wi2[:, 2], wi2[:, 0]])
            j2 = np.concatenate([wi2[:, 1], wi2[:, 2], wi2[:, 0], wi2[:, 0], wi2[:, 1], wi2[:, 2]])
            A2 = _sp2.coo_matrix((np.ones(len(i2)), (i2, j2)), shape=(len(T), len(T))).tocsr(); A2.data[:] = 1.0
            deg = np.asarray(A2.sum(1)).ravel()
            Wn = _sp2.diags(1.0 / np.maximum(deg, 1)) @ A2
            wbox = smooth01(-0.050, -0.068, T[:, 2]) * smooth01(0.050, 0.035, T[:, 1]) * smooth01(0.0, 0.006, T[:, 1])
            rep = (wt == np.arange(len(T)))                         # the welded representatives carry the mesh
            act2 = (wbox > 1e-3) & rep & (deg > 0)
            treeB = cKDTree(B)
            if tw_n > 0:
                ia = np.where(act2)[0]; pos = -np.ones(len(T), np.int64); pos[ia] = np.arange(len(ia))
                Wa = Wn[ia][:, ia]                                   # neighbours inside the region
                Wb = Wn[ia]                                          # all neighbours (the ring outside is held: Dirichlet)
                lam = tw_lam * wbox[ia]
                M = (_sp2.identity(len(ia)) + _sp2.diags(lam) - _sp2.diags(lam) @ Wa).tocsc()
                for it in range(tw_n):
                    x0 = T[ia].copy()
                    out = Wb @ T - Wa @ T[ia]                        # the held outside neighbours' contribution
                    rhs = x0 + lam[:, None] * out
                    X = np.stack([spsolve(M, rhs[:, k]) for k in range(3)], 1)
                    T[ia] = X
                    _, idx = treeB.query(T[ia]); nb = NB[idx]
                    h = ((T[ia] - B[idx]) * nb).sum(1)
                    T[ia] += nb * np.maximum(GAP - h, 0.0)[:, None]
                    T = T[wt]
                print('  toe shrink-wrap: %d stocking vertices, lam %.0f x %d' % (len(ia), tw_lam, tw_n))
            for it in range(tb_it):
                Ts = Wn @ T
                T[act2] += (0.5 * wbox[act2])[:, None] * (Ts[act2] - T[act2])
                _, idx = treeB.query(T[act2]); nb = NB[idx]
                h = ((T[act2] - B[idx]) * nb).sum(1)
                T[act2] += nb * np.maximum(GAP - h, 0.0)[:, None]
                T = T[wt]
        tc_r = float(os.environ.get("TOE_CLOSE", 0.0))     # m: the stocking on the toes' closing (close_toes); 0 = off
        if tc_r > 0.0:
            T = close_toes(B, tri_b, wb, side_b, T, wt, tc_r, GAP)
        # (UN-FLIP against the asset's own orientation: where the toes were filled out (TOE_PAD) a few hundred tiny triangles
        #  of the stocking ended up folded over - inward-facing, culled: holes the skin showed through, pink flecks on the little
        #  toe, review 11. Their corners relax toward their neighbours, a little at a time, and the skin pushes them out again)
        tree = cKDTree(B)
        n_src = np.cross(T_src[tri_t[:, 1]] - T_src[tri_t[:, 0]], T_src[tri_t[:, 2]] - T_src[tri_t[:, 0]])
        from scipy import sparse as _sp
        wi = wt[tri_t]
        ii = np.concatenate([wi[:, 0], wi[:, 1], wi[:, 2], wi[:, 1], wi[:, 2], wi[:, 0]])
        jj = np.concatenate([wi[:, 1], wi[:, 2], wi[:, 0], wi[:, 0], wi[:, 1], wi[:, 2]])
        Aj = _sp.coo_matrix((np.ones(len(ii)), (ii, jj)), shape=(len(T), len(T))).tocsr(); Aj.data[:] = 1.0
        Lm = _sp.diags(1.0 / np.maximum(np.asarray(Aj.sum(1)).ravel(), 1)) @ Aj
        for it in range(150):
            n1 = np.cross(T[tri_t[:, 1]] - T[tri_t[:, 0]], T[tri_t[:, 2]] - T[tri_t[:, 0]])
            flip = (n_src * n1).sum(1) < 0
            if it == 0: print('  un-flip: %d stocking triangles folded over' % flip.sum())
            if not flip.any(): break
            vs = np.unique(wt[tri_t[flip].ravel()])
            if it >= 30:                                        # (stubborn ones: their neighbours relax with them)
                ring = np.zeros(len(T), bool); ring[vs] = True
                ring = np.asarray((Aj @ ring.astype(np.float64)) > 0).ravel() | ring
                vs = np.unique(wt[np.nonzero(ring)[0]])
            Ts = Lm @ T
            T[vs] = 0.5 * T[vs] + 0.5 * Ts[vs]
            _, idx = tree.query(T[vs]); nb = NB[idx]
            h = ((T[vs] - B[idx]) * nb).sum(1)
            T[vs] += nb * np.maximum(GAP - h, 0.0)[:, None]
            T = T[wt]
        n1 = np.cross(T[tri_t[:, 1]] - T[tri_t[:, 0]], T[tri_t[:, 2]] - T[tri_t[:, 0]])
        print('  un-flip: %d left' % ((n_src * n1).sum(1) < 0).sum())
        _, idx = tree.query(T, k=1)
        g = np.einsum('ij,ij->i', T - B[idx], NB[idx])
        for lo, hi, name in ((0.0, 0.06, 'foot'), (0.06, 0.14, 'ankle'), (0.14, 0.40, 'shin'), (0.40, 0.56, 'knee'), (0.56, 0.745, 'thigh')):
            m = (T[:, 1] >= lo) & (T[:, 1] < hi)
            print('  stand-off %-5s p05 %.2f p50 %.2f p95 %.2f max %.2f mm' % (name, *np.percentile(g[m], [5, 50, 95]) * 1e3, g[m].max() * 1e3))

    # ---- 5. the body's stray pieces: two loose bits of the asset (84 / 78 vertices) floating beside the waist at 1.08 m -
    #      pink slivers above the skirt in any wide view (2026-11-17): their triangles are dropped
    subs_b = drop_small_components(B, subs_b, 1000)

    # ---- 6. the worn stocking's cavities, baked into its uv0.w (1 = open; it was the unused toe-cap fade, 1 everywhere):
    #      the clefts between the toes, the knee pit, the front of the ankle, where the thighs meet - lit less. The
    #      original's toes stand apart by their dark clefts; ours read as flat clay (tonal spread over the toes 11 vs the
    #      original's 22 - 28, independent review 4). SheerTights.hlsl darkens by it, fading it out where fabric lifts.
    if '--no-cavity' not in sys.argv:
        NT = vertex_normals(T, tri_t, wt)
        u0 = cht['uv0'].copy(); u0[:, 3] = cavity_ao(T, NT, wt); cht['uv0'] = u0
        for lo, hi, name in ((0.0, 0.06, 'foot'), (0.06, 0.14, 'ankle'), (0.14, 0.40, 'shin'), (0.40, 0.56, 'knee'), (0.56, 0.80, 'thigh')):
            m = (T[:, 1] >= lo) & (T[:, 1] < hi)
            print('  cavity %-5s p05 %.2f p50 %.2f min %.2f, below 0.9: %.1f %%' % (name, *np.percentile(u0[m, 3], [5, 50]), u0[m, 3].min(), (u0[m, 3] < 0.9).mean() * 100))

    # ---- write
    for P, tri, w, ch, nv, subs, types, name in ((B, tri_b, wb, chb, nvb, subs_b, types_b, 'body.smesh'),
                                                (T, tri_t, wt, cht, nvt, subs_t, types_t, 'tights.smesh')):
        N = vertex_normals(P, tri, w)
        tg = ch['tangent'].astype(np.float64)
        t3 = tg[:, :3] - N * np.einsum('ij,ij->i', tg[:, :3], N)[:, None]
        t3 /= np.maximum(np.linalg.norm(t3, axis=1, keepdims=True), 1e-12)
        ch['position'] = P.astype(np.float32); ch['normal'] = N.astype(np.float32)
        ch['tangent'] = np.concatenate([t3, tg[:, 3:4]], 1).astype(np.float32)
        u1 = ch['uv1'].copy(); u1[:, :3] = P; ch['uv1'] = u1.astype(np.float32)
        write_smesh(os.path.join(DST, name), nv, subs, ch, types)
        print('wrote', os.path.join(DST, name))


if __name__ == '__main__':
    main()
