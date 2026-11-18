# SHEER - the skirt's pleats made legible: crisp folds and shaded hollows, baked into the real-time skirt mesh.
#
# Side by side with the original in VIEW 01 (2026-11-17, frames 0.5 / 1.5 / 6 s, the skirt above both hems): the same
# overall brightness (median L 35 vs the original's 28 - 32), but a quarter of its fold contrast - L p10 / p90 33 / 38 vs
# 16 / 47, the spread of the column means across the pleats 1.4 - 1.8 vs 5.3 - 5.9. The skirt read as a flat dark felt
# panel with faint lines. Two causes:
#   - smooth normals across the folds: the Blender export averaged the normal over each fold, so a 110 deg knife-pleat
#     fold was shaded like a gentle bulge;
#   - no occlusion: the scene has no ambient occlusion, so the hollow of each pleat (where the face tucks under the next)
#     got the full sky light, as bright as the open face.
# Here (from the Blender export, unchanged positions / UVs / pin weights):
#   - the fold columns of the knife pleats (sheer_skirt.py: 16 pleats x 20 columns, the inner fold at column 0 of each
#     pleat, the outer fold at column 16) get SPLIT normals: each side of a fold its own (area-weighted) normal;
#   - the pleats made as shallow as pressed knife pleats are: the Blender asset's pleats stood 28 mm proud of their inner
#     folds at the hem (a sawtooth - the skirt's outside stood 3 - 9 cm off the body, a puffy shell; user, 2026-11-17: 'a
#     ghost's shell ... inflated by some divine inner force'); each vertex's height above its pleat's inner envelope is
#     scaled by DEPTH (the inner folds - and the real-time cloth sheet built from them - stay where they were);
#   - the hem gets the fabric's thickness and a turned-up hem inside it (a single surface read as a shell at the edge);
#   - every vertex gets the sky light its pleat lets through: a horizon in the ring's own cross-section (the folds are
#     vertical grooves), cosine-weighted, (cos thL + cos thR) / 2 -> uv0.z; how near it is to an outer fold (the fold's
#     edge, where a pressed pleat catches the light) -> uv0.w. The shader (SheerSurfaces.hlsl SheerSkirt_float) turns them
#     into ambient occlusion, a cavity and the folds' sheen (_SheerSkirtFold).
# Usage: python3 tools/skirt_folds.py          (reads the pristine export, writes unity/Assets/StreamingAssets/skirt_base.smesh)
import os, sys, struct
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'sim'))
import smesh

SRC = os.path.join(ROOT, 'drafts', 'backup_skirt_2026-11-17', 'skirt_base.smesh')     # blender/export_unity.py output
DST = os.path.join(ROOT, 'unity', 'Assets', 'StreamingAssets', 'skirt_base.smesh')
NA, PER, OUTER = 320, 20, 16           # columns round; columns per pleat; the outer fold's column within a pleat
K = 30                                 # neighbours scanned for the horizon (1.5 pleats)
SKIRT_Z = -0.007                       # the skirt's axis (SkirtCloth.SkirtZ), x = 0
DEPTH = 0.55                           # pleat depth kept (28 -> ~15 mm at the hem)
BULGE, WANDER = 0.0025, 0.0012         # a pleat face's bulge (m, x 0.6..1.4 per pleat); a pleat's sideways wander (m)
HEM_T, HEM_RINGS = 0.0016, 4           # the fabric's thickness at the hem (m); the turned-up hem: 4 rings (~23 mm) high


def write(path, nv, subs, chans):
    out = [b'SMSH', struct.pack('<III', 1, nv, len(subs))]
    for s in subs:
        s = np.ascontiguousarray(s, np.uint32).ravel(); out += [struct.pack('<I', len(s)), s.tobytes()]
    out.append(struct.pack('<I', len(chans)))
    for name, a in chans:
        typ = 1 if a.dtype == np.uint32 else 0
        out += [name.encode().ljust(16, b'\0'), struct.pack('<BBH', typ, a.shape[1], 0), np.ascontiguousarray(a).tobytes()]
    open(path, 'wb').write(b''.join(out))


def main():
    nv, subs, ch = smesh.load(SRC)
    tri = subs[0].astype(np.int64).reshape(-1, 3)
    P = ch['position'].astype(np.float64)
    src = ch['src'][:, 0].astype(np.int64); col = src % NA; ring = src // NA
    # shallower pleats: per ring, the pleats' inner envelope (the lowest radius within half a pleat either side, smoothed
    # round the ring) and each vertex's height above it x DEPTH
    nr = ring.max() + 1
    rad = np.hypot(P[:, 0], P[:, 2] - SKIRT_Z)
    R = np.zeros((nr, NA)); R[ring, col] = rad
    Rmin = np.min(np.stack([np.roll(R, d, 1) for d in range(-PER // 2, PER // 2 + 1)]), 0)
    Rin = np.mean(np.stack([np.roll(Rmin, d, 1) for d in range(-PER // 2, PER // 2 + 1)]), 0)
    rin = Rin[ring, col]
    rnew = rin + DEPTH * (rad - rin)
    k = (rnew / np.maximum(rad, 1e-9))[:, None]
    P[:, [0]] *= k[:, :1]; P[:, 2] = SKIRT_Z + (P[:, 2] - SKIRT_Z) * k[:, 0]
    ch['position'] = P.astype(np.float32)
    U1 = ch['uv1'].astype(np.float64).copy(); U1[:, 0] = P[:, 0]; U1[:, 2] = P[:, 2]; ch['uv1'] = U1.astype(np.float32)
    print('pleat depth at the hem ring: %.1f -> %.1f mm (max over the ring)' % ((R[-1] - Rmin[-1]).max() * 1e3, ((R[-1] - Rmin[-1]) * DEPTH).max() * 1e3))
    # variety: cloth is never ruled. Each pleat's face bulges a little between its folds (a pressed wool panel is not flat),
    # by its own amount, more or less down its length; and every pleat wanders sideways a little along its length, so its
    # folds are not ruled lines (all smooth: ~1 - 3 mm over 13 - 25 cm (2.5 mm over 7 - 13 cm read as rippled, not pressed))
    rng = np.random.default_rng(1117)
    npl = NA // PER
    amp = rng.uniform(0.6, 1.4, npl); ph1 = rng.uniform(0, 2 * np.pi, npl); ph2 = rng.uniform(0, 2 * np.pi, npl); ph3 = rng.uniform(0, 2 * np.pi, npl)
    pl = col // PER; phs = col % PER
    y = P[:, 1]; ytop, yhem = y.max(), y.min()
    down = np.clip((ytop - y) / (ytop - yhem), 0, 1)
    grow = down * down * (3 - 2 * down)                                    # nothing at the waistband, all of it at the hem
    face = np.where(phs <= OUTER, np.sin(np.pi * phs / OUTER), 0.0)
    along = 1.0 + 0.35 * np.sin(2 * np.pi * y / 0.11 + ph1[pl])
    rad2 = np.hypot(P[:, 0], P[:, 2] - SKIRT_Z)
    rad2 = rad2 + BULGE * face * amp[pl] * along * grow
    th = np.arctan2(P[:, 0], -(P[:, 2] - SKIRT_Z))
    wander = WANDER * grow * (0.6 * np.sin(2 * np.pi * y / 0.25 + ph2[pl]) + 0.4 * np.sin(2 * np.pi * y / 0.13 + ph3[pl]))
    th = th + wander / np.maximum(rad2, 1e-6)
    P[:, 0] = rad2 * np.sin(th); P[:, 2] = SKIRT_Z - rad2 * np.cos(th)
    ch['position'] = P.astype(np.float32)
    U1 = ch['uv1'].astype(np.float64).copy(); U1[:, 0] = P[:, 0]; U1[:, 2] = P[:, 2]; ch['uv1'] = U1.astype(np.float32)
    # each triangle's column cell (between column c and c + 1, round the seam 319 -> 0)
    tc = col[tri]
    wrap = (tc.max(1) == NA - 1) & (tc.min(1) == 0)
    cell = np.where(wrap, NA - 1, tc.min(1))
    # split the fold columns: the faces right of the fold (cell == the fold's column) get their own copy of its vertices
    fold = (col % PER == 0) | (col % PER == OUTER)
    extra = []
    tri_n = tri.copy()
    dup_of = {}
    for t in range(len(tri)):
        for k in range(3):
            v = tri[t, k]
            if fold[v] and col[v] != 0 and cell[t] == col[v]:          # (column 0 is already split by the UV seam)
                if v not in dup_of:
                    dup_of[v] = nv + len(extra); extra.append(v)
                tri_n[t, k] = dup_of[v]
    idx = np.concatenate([np.arange(nv), np.array(extra, np.int64)])
    N2 = len(idx)
    Pn = P[idx]
    # normals: area-weighted face normals per (new) vertex, oriented like the export's (outward)
    fn = np.cross(Pn[tri_n[:, 1]] - Pn[tri_n[:, 0]], Pn[tri_n[:, 2]] - Pn[tri_n[:, 0]])
    nrm = np.zeros((N2, 3))
    for k in range(3): np.add.at(nrm, tri_n[:, k], fn)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    n_old = ch['normal'].astype(np.float64)[idx]
    if (nrm * n_old).sum(1).mean() < 0: nrm = -nrm
    # (the export's normals point INTO the skirt - its outside is drawn as back faces, HDRP flips them. The horizon and the
    #  hem's inside layer need the OUTWARD normal: baked with the file's, the shadow went onto the pleats' ridges and the
    #  'inside' hem came out over the outside)
    rad_dir = np.stack([Pn[:, 0], np.zeros(N2), Pn[:, 2] - SKIRT_Z], 1)
    out_sign = 1.0 if (nrm * rad_dir).sum(1).mean() > 0 else -1.0
    nout = nrm * out_sign
    # the horizon of each vertex in its ring's cross-section (x, z), from the ring's profile (one point per column)
    prof = np.zeros((ring.max() + 1, NA, 2))
    prof[ring, col] = P[:, [0, 2]]
    cn, rn = col[idx], ring[idx]
    p2 = Pn[:, [0, 2]]
    n2 = nout[:, [0, 2]]; n2 /= np.maximum(np.linalg.norm(n2, axis=1, keepdims=True), 1e-9)
    t2 = np.stack([n2[:, 1], -n2[:, 0]], 1)
    thL = np.zeros(N2); thR = np.zeros(N2)
    for d in range(-K, K + 1):
        if d == 0: continue
        q = prof[rn, (cn + d) % NA]
        dv = q - p2
        h = (dv * n2).sum(1); s = (dv * t2).sum(1)
        el = np.where(h > 0, np.arctan2(h, np.maximum(np.abs(s), 1e-6)), 0.0)
        thL = np.where(s < 0, np.maximum(thL, el), thL); thR = np.where(s > 0, np.maximum(thR, el), thR)
    sky = 0.5 * (np.cos(thL) + np.cos(thR))
    # the outer fold's edge: 1 on the fold, gone two columns (~6 mm) away
    dc = np.abs(((cn - OUTER) + PER // 2) % PER - PER // 2).astype(np.float64)
    edge = np.exp(-(dc / 1.2) ** 2)
    uv0 = ch['uv0'][idx]
    uv0 = np.concatenate([uv0, sky[:, None], edge[:, None]], 1).astype(np.float32)
    tan = ch['tangent'][idx].astype(np.float64)
    t3 = tan[:, :3] - nrm * (tan[:, :3] * nrm).sum(1, keepdims=True)
    t3 /= np.maximum(np.linalg.norm(t3, axis=1, keepdims=True), 1e-12)
    tan = np.concatenate([t3, tan[:, 3:]], 1).astype(np.float32)
    pos = ch['position'][idx].astype(np.float64); u1 = ch['uv1'][idx]; u2 = ch['uv2'][idx]; srcn = ch['src'][idx]
    # ---- the hem: the fabric's edge (a strip HEM_T deep, facing down) and the turned-up hem inside (HEM_RINGS rings high)
    # the winding the export uses relative to its (outward) normals - new faces follow it
    gn = np.cross(Pn[tri_n[:, 1]] - Pn[tri_n[:, 0]], Pn[tri_n[:, 2]] - Pn[tri_n[:, 0]])
    s0 = np.sign((gn * (nrm[tri_n[:, 0]] + nrm[tri_n[:, 1]] + nrm[tri_n[:, 2]])).sum(1).mean())
    bottom = rn.max()
    e = np.sort(np.concatenate([tri_n[:, [0, 1]], tri_n[:, [1, 2]], tri_n[:, [2, 0]]]), 1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    bnd = ue[(cnt == 1) & (rn[ue[:, 0]] == bottom) & (rn[ue[:, 1]] == bottom)]
    newP, newN, newUV, newU1, newSrc, newTan, newTri = [], [], [], [], [], [], []
    base = N2
    def add(p, n, v, sky_):
        newP.append(p); newN.append(n); newUV.append([uv0[v, 0], p[1], sky_, 0.0]); newU1.append(p); newSrc.append(srcn[v, 0]); newTan.append(tan[v])
        return base + len(newP) - 1
    def allP(i): return pos[i] if i < N2 else newP[i - base]
    def tri_out(a, b, c, want):
        g = np.cross(allP(b) - allP(a), allP(c) - allP(a))
        if np.sign(np.dot(g, want)) != s0: b, c = c, b
        newTri.append([a, b, c])
    # the turned-up hem: the bottom HEM_RINGS rows of the outside, copied HEM_T inside it vertex by vertex (it follows every
    # curve of the outside - a flat strip from the edge to its top poked through it in patches), facing in
    band = tri_n[(rn[tri_n] >= bottom - HEM_RINGS).all(1)]
    vb = {}
    for t in band:
        for v in t:
            if v not in vb: vb[v] = add(pos[v] - nout[v] * HEM_T, -nrm[v], v, 0.3)
        newTri.append([vb[t[1]], vb[t[0]], vb[t[2]]])                          # (reversed: the inside, normals negated)
    # the edge: a strip HEM_T deep along the bottom, facing down
    vs = {}
    for a, b in bnd:
        for v in (a, b):
            if v not in vs:
                down = np.array([0.0, -1.0, 0.0])
                vs[v] = (add(pos[v], down, v, 0.6), add(pos[v] - nout[v] * HEM_T, down, v, 0.6))
        dn = np.array([0.0, -1.0, 0.0])
        tri_out(vs[a][0], vs[b][0], vs[b][1], dn); tri_out(vs[a][0], vs[b][1], vs[a][1], dn)
    nn = len(newP)
    pos = np.concatenate([pos, np.array(newP).reshape(-1, 3)])
    nrm2 = np.concatenate([nrm, np.array(newN).reshape(-1, 3)])
    nrm2 /= np.maximum(np.linalg.norm(nrm2, axis=1, keepdims=True), 1e-12)
    uv0 = np.concatenate([uv0, np.array(newUV, np.float32).reshape(-1, 4)])
    u1 = np.concatenate([u1, np.array(newU1, np.float32).reshape(-1, 3)])
    u2 = np.concatenate([u2, np.zeros((nn, 2), np.float32)])
    srcn = np.concatenate([srcn, np.array(newSrc, np.uint32).reshape(-1, 1)])
    tan = np.concatenate([tan, np.array(newTan, np.float32).reshape(-1, 4)])
    tris = np.concatenate([tri_n, np.array(newTri, np.int64).reshape(-1, 3)])
    chans = [('position', pos.astype(np.float32)), ('normal', nrm2.astype(np.float32)), ('tangent', tan.astype(np.float32)), ('uv0', uv0.astype(np.float32)),
             ('src', srcn.astype(np.uint32)), ('uv1', u1.astype(np.float32)), ('uv2', u2.astype(np.float32))]
    write(DST, len(pos), [tris.astype(np.uint32)], chans)
    print('skirt_folds: %d -> %d vertices (%d split at %d fold columns, %d at the hem: %d edges), %d triangles' % (
        nv, len(pos), len(extra), len(np.unique(col[np.array(extra)])) if extra else 0, nn, len(bnd), len(tris)))
    for lo, hi in ((0, 10), (10, 30), (30, 58)):
        m = (rn >= lo) & (rn < hi)
        print('  rings %2d-%2d: sky p5 %.2f p50 %.2f min %.2f' % (lo, hi, *np.percentile(sky[m], [5, 50]), sky[m].min()))
    return sky, rn, cn


if __name__ == '__main__':
    main()
