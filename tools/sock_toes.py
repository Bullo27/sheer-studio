#!/usr/bin/env python3
# NOT APPLIED (2026-11-14): the exported stocking mesh already bridges the toes (toe box); the toes showed only because the
# HDRP foot was too sheer (fixed in SheerTights.hlsl: foot coverage = Frost Foot Coverage). Also note the stocking mesh's
# triangle winding gives inward normals here, so this script as written moves the yarn INTO the toes. Kept for reference.
# SHEER — reinforced toe box: the stocking's toe region bridges the gaps between the toes like real hosiery (the
# original's feet read as a smooth sock, ours outlined every toe). Outward-only Laplacian flow on the stocking mesh in
# the toe region: valleys between toes fill (the yarn spans them), toe tops never move inwards (no penetration).
# Vertices duplicated at UV seams move together (welded by position). Normals are recomputed where positions changed.
# Usage: python3 tools/sock_toes.py SRC_DIR [DST_DIR ...]   (reads SRC_DIR/tights.smesh, writes tights.smesh in each DST)
#        the untouched original is kept as unity_export/backup/tights.smesh.orig (never inside StreamingAssets)
import os, shutil, sys
import numpy as np
from scipy.sparse import coo_matrix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_proto as C
from add_body_legcoords import write_smesh

BLEND = 0.8


def weights(P):
    """toe-box weight from Blender-axis positions (x lateral, y depth (-y = front), z up)"""
    y, z = P[:, 1], P[:, 2]
    def sm(e0, e1, x):
        t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)
    return sm(-0.035, -0.065, y) * sm(0.05, 0.035, z)


def vertex_normals(P, tris):
    n = np.zeros_like(P)
    fn = np.cross(P[tris[:, 1]] - P[tris[:, 0]], P[tris[:, 2]] - P[tris[:, 0]])
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def main():
    src = sys.argv[1]; dsts = sys.argv[2:] or [src]
    root = os.path.dirname(os.path.abspath(__file__)) + '/..'
    bdir = os.path.join(root, 'unity_export', 'backup'); os.makedirs(bdir, exist_ok=True)
    orig = os.path.join(bdir, 'tights.smesh.orig')
    if not os.path.exists(orig):
        shutil.copyfile(os.path.join(src, 'tights.smesh'), orig)
    nv, subs, ch = C.load_smesh(orig)                      # always start from the untouched mesh
    PU = ch['position'].astype(np.float64)                 # Unity axes
    P = PU[:, [0, 2, 1]].copy()                            # Blender axes
    tris = np.concatenate([np.asarray(s, np.int64).reshape(-1, 3) for s in subs])
    # weld seam duplicates
    key = np.round(P / 1e-6).astype(np.int64)
    _, weld, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    weld = weld.ravel(); nw = weld.max() + 1
    Pw = np.zeros((nw, 3)); np.add.at(Pw, weld, P); Pw /= np.bincount(weld, minlength=nw)[:, None]
    tw = weld[tris]
    e = np.concatenate([tw[:, [0, 1]], tw[:, [1, 2]], tw[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nw, nw)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    w = weights(Pw)
    act = w > 1e-3
    print('toe-box vertices: %d of %d (welded)' % (act.sum(), nw))
    N0 = vertex_normals(Pw, tw)
    X = Pw.copy()
    # per foot: convex hull of the toe region; every toe-box vertex moves out along its normal to the hull (x BLEND), so
    # the yarn spans the gaps between the toes and toe tops stay where they are
    from scipy.spatial import ConvexHull
    for sd in (1, -1):
        m = act & (np.sign(Pw[:, 0]) == sd)
        idx = np.flatnonzero(m)
        H = ConvexHull(Pw[idx])
        nf, df = H.equations[:, :3], -H.equations[:, 3]        # inside: nf . x <= df
        pts, nrm = Pw[idx], N0[idx]
        t = np.full(len(idx), np.inf)
        for f0 in range(0, len(nf), 512):
            nfb, dfb = nf[f0:f0 + 512], df[f0:f0 + 512]
            den = nrm @ nfb.T                                   # (V, F)
            num = dfb[None, :] - pts @ nfb.T
            with np.errstate(divide='ignore', invalid='ignore'):
                tt = np.where(den > 1e-6, num / den, np.inf)
            t = np.minimum(t, tt.min(1))
        t = np.clip(np.nan_to_num(t, posinf=0.0), 0.0, 0.008)  # never more than 8 mm
        X[idx] = pts + (BLEND * w[idx] * t)[:, None] * nrm
    moved = np.linalg.norm(X - Pw, axis=1)
    print('moved: max %.2f mm, mean over toe box %.2f mm' % (moved.max() * 1000, moved[act].mean() * 1000))
    Pn = X[weld]
    Nn = vertex_normals(Pn, tris)
    newPU = Pn[:, [0, 2, 1]]
    newNU = Nn[:, [0, 2, 1]]
    chg = np.linalg.norm(Pn - P, axis=1) > 1e-7
    ch = dict(ch)
    pos = ch['position'].copy(); pos[:] = newPU.astype(np.float32); ch['position'] = pos
    nrm = ch['normal'].copy(); nrm[chg] = newNU[chg].astype(np.float32); ch['normal'] = nrm
    if 'tangent' in ch:                                     # re-orthogonalise the tangents against the new normals
        t = ch['tangent'].copy().astype(np.float64)
        tv = t[:, :3] - np.einsum('ij,ij->i', t[:, :3], newNU)[:, None] * newNU
        tv /= np.maximum(np.linalg.norm(tv, axis=1, keepdims=True), 1e-12)
        t[chg, :3] = tv[chg]; ch['tangent'] = t.astype(np.float32)
    types = {k: (1 if v.dtype == np.uint32 else 0) for k, v in ch.items()}
    for d in dsts:
        write_smesh(os.path.join(d, 'tights.smesh'), nv, subs, ch, types)
        print('wrote', os.path.join(d, 'tights.smesh'))


if __name__ == '__main__':
    main()
