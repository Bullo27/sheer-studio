# SHEER — stocking toe box.
# A knit stocking never dips between the toes: stretched fabric bridges every concavity narrower
# than ~1 cm. We model exactly that as a morphological CLOSING of the forefoot volume (dilate by R,
# erode by R) on a 0.5 mm voxel grid, re-mesh the closed toe box (surface nets on a signed
# distance field that equals the exact body distance wherever the closing changed nothing) and
# stitch it back into the body mesh with a narrow triangle band. Skin and tights are then derived
# from one continuous toe surface: no toe pockets, no crevices, no seams.
import bpy, bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _ball_fft(fshape, r):
    rr = int(np.ceil(r))
    d = np.arange(-rr, rr + 1)
    dx, dy, dz = np.meshgrid(d, d, d, indexing='ij')
    m = dx ** 2 + dy ** 2 + dz ** 2 <= r * r
    K = np.zeros(fshape, np.float64)
    K[dx[m] % fshape[0], dy[m] % fshape[1], dz[m] % fshape[2]] = 1.0
    return np.fft.rfftn(K), float(m.sum())


def _conv(A, FK, fshape):
    out = np.fft.irfftn(np.fft.rfftn(A.astype(np.float64), s=fshape) * FK, s=fshape)
    return out[:A.shape[0], :A.shape[1], :A.shape[2]]


def _blur(A, sigma, fshape):
    F = np.fft.rfftn(A.astype(np.float64), s=fshape)
    fx = np.fft.fftfreq(fshape[0])[:, None, None]
    fy = np.fft.fftfreq(fshape[1])[None, :, None]
    fz = np.fft.rfftfreq(fshape[2])[None, None, :]
    F *= np.exp(-2.0 * np.pi ** 2 * sigma ** 2 * (fx ** 2 + fy ** 2 + fz ** 2))
    out = np.fft.irfftn(F, s=fshape)
    return out[:A.shape[0], :A.shape[1], :A.shape[2]]


def _ray_hits(bvh, x, z, y0, y1):
    hits = []
    y = y0
    d = Vector((0.0, 1.0, 0.0))
    while len(hits) < 64:
        loc, nrm, idx, dist = bvh.ray_cast(Vector((x, y, z)), d, y1 - y)
        if loc is None:
            break
        hits.append(loc.y)
        y = loc.y + 1e-7
    return hits


def _trilinear(G, lo, h, p):
    f = (p - lo) / h
    i0 = np.clip(np.floor(f).astype(np.int64), 0, np.array(G.shape) - 2)
    t = np.clip(f - i0, 0.0, 1.0)
    i, j, k = i0[:, 0], i0[:, 1], i0[:, 2]
    tx, ty, tz = t[:, 0], t[:, 1], t[:, 2]
    c00 = G[i, j, k] * (1 - tx) + G[i + 1, j, k] * tx
    c10 = G[i, j + 1, k] * (1 - tx) + G[i + 1, j + 1, k] * tx
    c01 = G[i, j, k + 1] * (1 - tx) + G[i + 1, j, k + 1] * tx
    c11 = G[i, j + 1, k + 1] * (1 - tx) + G[i + 1, j + 1, k + 1] * tx
    return (c00 * (1 - ty) + c10 * ty) * (1 - tz) + (c01 * (1 - ty) + c11 * ty) * tz


def surface_nets(S, lo, h):
    """Naive surface nets: one vertex per sign-changing cell (mean of its edge crossings),
    one quad per sign-changing interior grid edge. Quads are wound with normals toward S > 0."""
    sh = S.shape
    csh = (sh[0] - 1, sh[1] - 1, sh[2] - 1)
    ncell = csh[0] * csh[1] * csh[2]

    def cid(c):
        return (c[:, 0] * csh[1] + c[:, 1]) * csh[2] + c[:, 2]

    acc = np.zeros((ncell, 3)); cnt = np.zeros(ncell)
    quads = []
    for ax, (o1, o2) in enumerate(((1, 2), (2, 0), (0, 1))):
        a = [slice(None)] * 3; b = [slice(None)] * 3
        a[ax] = slice(0, -1); b[ax] = slice(1, None)
        s0 = S[tuple(a)]; s1 = S[tuple(b)]
        cross = (s0 < 0) != (s1 < 0)
        idx = np.argwhere(cross)
        v0 = s0[cross]; v1 = s1[cross]
        t = v0 / (v0 - v1)
        p = idx.astype(np.float64); p[:, ax] += t
        p = lo + h * p
        for d1 in (-1, 0):
            for d2 in (-1, 0):
                c = idx.copy(); c[:, o1] += d1; c[:, o2] += d2
                ok = (c[:, o1] >= 0) & (c[:, o1] < csh[o1]) & (c[:, o2] >= 0) & (c[:, o2] < csh[o2])
                ci = cid(c[ok])
                np.add.at(acc, ci, p[ok]); np.add.at(cnt, ci, 1.0)
        ok = (idx[:, o1] >= 1) & (idx[:, o1] < csh[o1]) & (idx[:, o2] >= 1) & (idx[:, o2] < csh[o2])
        e = idx[ok]; out_up = v0[ok] < 0          # inside -> outside along +ax: normal +ax
        cs = []
        for d1, d2 in ((-1, -1), (0, -1), (0, 0), (-1, 0)):
            c = e.copy(); c[:, o1] += d1; c[:, o2] += d2
            cs.append(cid(c))
        q = np.stack(cs, 1)
        q[~out_up] = q[~out_up][:, ::-1]
        quads.append(q)
    quads = np.concatenate(quads, 0)
    active = cnt > 0
    vid = -np.ones(ncell, np.int64); vid[active] = np.arange(int(active.sum()))
    verts = acc[active] / cnt[active, None]
    return verts, vid[quads]


def _closed_field(bvh, co, s, R, h, back):
    m = (co[:, 0] * s > 0) & (co[:, 2] < 0.12)
    ymin = co[m, 1].min()
    ycut = ymin + back
    reg = m & (co[:, 1] < ycut + 0.02)
    lo = co[reg].min(0) - 0.003
    hi = co[reg].max(0) + 0.003
    hi[1] = ycut + 0.012
    shape = tuple(int(np.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
    shape = tuple(n + (n % 2) for n in shape)            # even, for the 2x coarse grid
    xs = lo[0] + h * np.arange(shape[0]); ys = lo[1] + h * np.arange(shape[1]); zs = lo[2] + h * np.arange(shape[2])
    # 1) exact inside/outside at voxel centres: ray parity along +y through the whole foot
    occ = np.zeros(shape, bool)
    y0 = lo[1] - 0.01; y1 = co[m, 1].max() + 0.05
    bad = 0
    for i, x in enumerate(xs):
        for k, z in enumerate(zs):
            hits = _ray_hits(bvh, x, z, y0, y1)
            if len(hits) % 2:
                hits = _ray_hits(bvh, x + 1.3e-6, z - 0.7e-6, y0, y1)
                if len(hits) % 2:
                    bad += 1
                    hits = hits[:-1]
            if hits:
                occ[i, :, k] = (np.searchsorted(np.asarray(hits), ys) % 2) == 1
    fsh = tuple(n + 16 for n in shape)
    # 2) exact signed distance in a +-1.5 mm band around the skin
    FKs, ns = _ball_fft(fsh, 3.0)
    cs = _conv(occ, FKs, fsh)
    band = (cs > 0.5) & (cs < ns - 0.5)
    S0 = np.where(occ, -1.6e-3, 1.6e-3)
    bi = np.argwhere(band)
    pts = lo + h * bi
    dist = np.empty(len(bi))
    for n_, p in enumerate(pts):
        loc = bvh.find_nearest(Vector(p))[0]
        dist[n_] = (Vector(p) - loc).length if loc is not None else 1.6e-3
    S0[band] = np.where(occ[band], -dist, dist)
    # 3) closing (dilate R, erode R) on a 2x coarser, R-padded grid -> crevices bridged
    h2 = 2 * h
    occ2 = occ.reshape(shape[0] // 2, 2, shape[1] // 2, 2, shape[2] // 2, 2).mean((1, 3, 5)) > 0.5
    pc = int(np.ceil(R / h2)) + 3
    occ2 = np.pad(occ2, pc)
    lo2 = lo + 0.5 * h - pc * h2
    fsh2 = tuple(n + pc for n in occ2.shape)
    FK, nk = _ball_fft(fsh2, R / h2)
    dil = _conv(occ2, FK, fsh2) > 0.5
    closed2 = (_conv(dil, FK, fsh2) > nk - 0.5) | occ2
    del dil
    sig2 = 2.5          # taut fabric smooths everything below ~5 mm (nail edges, knuckle creases)
    Sc2 = (0.5 - _blur(closed2, sig2, fsh2)) * sig2 * h2 * np.sqrt(2 * np.pi)
    gi = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2]), indexing='ij'), -1).reshape(-1, 3)
    Sc = np.empty(len(gi))
    for c0 in range(0, len(gi), 2000000):
        Sc[c0:c0 + 2000000] = _trilinear(Sc2, lo2, h2, lo + h * gi[c0:c0 + 2000000])
    Sc = Sc.reshape(shape)
    del gi
    changed = (Sc < 0) & ~occ
    w = np.ones(shape)
    # no change near the stitch: the patch must coincide exactly with the body there
    t = ((ys - (ycut - 0.006)) / (-0.018)).clip(0, 1)
    w *= (t * t * (3 - 2 * t))[None, :, None]
    S = (1.0 - w) * S0 + w * Sc
    print('[toebox] side %d grid %s (coarse %s), parity fixes %d, band %d, filled %.1f cm3' % (
        s, shape, occ2.shape, bad, len(bi), changed.sum() * h ** 3 * 1e6))
    return S, lo, ycut


def _patch_mesh(S, lo, h, ycut, delta, iters=8):
    verts, quads = surface_nets(S, lo, h)
    # relax + re-project onto the iso-surface (removes the voxel imprint)
    gx, gy, gz = np.gradient(S, h)
    e = np.concatenate([quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]], 0)
    e = np.unique(np.sort(e, 1), axis=0)
    n = len(verts)
    deg = np.maximum(np.bincount(e[:, 0], minlength=n) + np.bincount(e[:, 1], minlength=n), 1)

    def project(p):
        for _ in range(3):
            sv = _trilinear(S, lo, h, p)
            g = np.stack([_trilinear(gx, lo, h, p), _trilinear(gy, lo, h, p), _trilinear(gz, lo, h, p)], 1)
            g2 = np.maximum((g * g).sum(1), 1e-6)
            p = p - (sv / g2)[:, None] * g
        return p

    p = project(verts)
    for _ in range(iters):
        acc = np.zeros_like(p)
        np.add.at(acc, e[:, 0], p[e[:, 1]]); np.add.at(acc, e[:, 1], p[e[:, 0]])
        p = p + 0.5 * (acc / deg[:, None] - p)
        p = project(p)
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in p]
    for q in quads:
        try:
            bm.faces.new([vs[i] for i in q])
        except ValueError:
            pass
    bm.normal_update()
    bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
    # orientation sanity (normals must point to S > 0)
    fc = np.array([f.calc_center_median() for f in bm.faces[:2000]])
    fn = np.array([f.normal for f in bm.faces[:2000]])
    g = np.stack([_trilinear(gx, lo, h, fc), _trilinear(gy, lo, h, fc), _trilinear(gz, lo, h, fc)], 1)
    if (fn * g).sum(1).mean() < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    ycp = ycut - delta
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-9, plane_co=(0, ycp, 0), plane_no=(0, 1, 0), clear_outer=True)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    out_v = np.array([v.co[:] for v in bm.verts])
    for i, v in enumerate(bm.verts):
        v.index = i
    out_f = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return out_v, out_f


def _loop(edges):
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    if not adj or any(len(v) != 2 for v in adj.values()):
        raise RuntimeError('toe box: boundary is not a simple loop (%d verts, degrees %s)' % (
            len(adj), sorted(set(len(v) for v in adj.values()))))
    start = next(iter(adj))
    loop = [start]; prev = None; cur = start
    while True:
        nxt = adj[cur][0] if adj[cur][0] is not prev else adj[cur][1]
        if nxt is start:
            break
        loop.append(nxt); prev, cur = cur, nxt
    if len(loop) != len(adj):
        raise RuntimeError('toe box: %d boundary loops' % (1 + (len(adj) > len(loop))))
    return loop


def _zip(bm, P, Q):
    cx = np.mean([v.co.x for v in P]); cz = np.mean([v.co.z for v in P])

    def prep(L):
        a = np.array([np.arctan2(v.co.z - cz, v.co.x - cx) for v in L])
        da = (np.diff(np.append(a, a[0])) + np.pi) % (2 * np.pi) - np.pi
        if da.sum() < 0:
            L = L[::-1]; a = a[::-1]
        i0 = int(np.argmin(a))
        L = L[i0:] + L[:i0]
        a = np.unwrap(np.concatenate([a[i0:], a[:i0]]))
        return L, np.append(a, a[0] + 2 * np.pi)

    P, tP = prep(P); Q, tQ = prep(Q)
    nP, nQ = len(P), len(Q)
    # orientation from the body face that owns the first P edge
    e0 = bm.edges.get((P[0], P[1]))
    f0 = e0.link_faces[0]
    same = any(l.edge == e0 and l.vert == P[0] for l in f0.loops)
    i = j = 0
    new = []
    while i < nP or j < nQ:
        if j >= nQ or (i < nP and tP[i + 1] <= tQ[j + 1]):
            tri = (P[i % nP], P[(i + 1) % nP], Q[j % nQ]); i += 1
        else:
            tri = (P[i % nP], Q[(j + 1) % nQ], Q[j % nQ]); j += 1
        if same:
            tri = tri[::-1]
        try:
            new.append(bm.faces.new(tri))
        except ValueError:
            pass
    return new


def close_forefoot(body, R=0.04, h=0.0005, back=0.08, delta=0.0025):
    me = body.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3).astype(np.float64)
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    patches = {}
    for s in (1, -1):
        S, lo, ycut = _closed_field(bvh, co, s, R, h, back)
        pv, pf = _patch_mesh(S, lo, h, ycut, delta)
        patches[s] = (pv, pf, ycut)
        del S
    bm = bmesh.new(); bm.from_mesh(me)
    for s, (pv, pf, ycut) in patches.items():
        sel = [f for f in bm.faces if f.calc_center_median().x * s > 0 and f.calc_center_median().z < 0.13
               and f.calc_center_median().y < ycut + 0.02]
        geom = list({x for f in sel for x in list(f.verts) + list(f.edges)}) + sel
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-9, plane_co=(0, ycut, 0), plane_no=(0, 1, 0))
        kill = [f for f in bm.faces if f.calc_center_median().x * s > 0 and f.calc_center_median().z < 0.13
                and f.calc_center_median().y < ycut]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        P = _loop([e for e in bm.edges if e.is_boundary and all(abs(v.co.y - ycut) < 1e-6 and v.co.x * s > 0 and v.co.z < 0.13 for v in e.verts)])
        vs = [bm.verts.new(v) for v in pv]
        for f in pf:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
        vset = set(vs)
        Q = _loop([e for e in bm.edges if e.is_boundary and e.verts[0] in vset and e.verts[1] in vset])
        band = _zip(bm, P, Q)
        open_e = sum(1 for e in bm.edges if e.is_boundary and e.verts[0].co.z < 0.13 and e.verts[0].co.x * s > 0)
        print('[toebox] side %d: patch %d verts, seam band %d tris (P %d / Q %d), open edges left %d' % (
            s, len(pv), len(band), len(P), len(Q), open_e))
    for f in bm.faces:
        f.smooth = True
    bm.normal_update()
    bm.to_mesh(me); bm.free(); me.update()
    print('[toebox] body verts', len(me.vertices))
