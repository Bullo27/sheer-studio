# SHEER — tights mesh: a skin-tight copy of the body below the waist, bridged over the toes,
# offset 0.6 mm, with a per-leg (around, along) parameterisation used by the damage system:
#   u = angle around the leg axis / 2pi (0 = back of the leg), v = height z (meters).
# Wales of a knitted stocking run along v (lines of constant u are vertical planes through the
# leg axis), courses run around u — exactly how ladders propagate in real hosiery.
import bpy, bmesh, os
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

TOP_Z = 0.99       # waistband height (hidden under the skirt)
OFFSET = 0.0006    # fabric distance from skin (m)
V_SCALE = 1.0      # texture v covers z in [0, V_SCALE]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mesh_arrays(me):
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32); me.vertices.foreach_get('co', co)
    nr = np.empty(n * 3, np.float32); me.vertex_normals.foreach_get('vector', nr)
    ed = np.empty(len(me.edges) * 2, np.int32); me.edges.foreach_get('vertices', ed)
    return co.reshape(-1, 3), nr.reshape(-1, 3), ed.reshape(-1, 2)


def laplacian(co, edges, mask, iters=12, lam=0.5):
    n = len(co)
    a, b = edges[:, 0], edges[:, 1]
    deg = np.bincount(a, minlength=n) + np.bincount(b, minlength=n)
    deg = np.maximum(deg, 1).astype(np.float32)
    out = co.copy()
    for _ in range(iters):
        acc = np.zeros_like(out)
        np.add.at(acc, a, out[b]); np.add.at(acc, b, out[a])
        avg = acc / deg[:, None]
        out[mask] += lam * (avg[mask] - out[mask])
    return out


def _gauss_smooth(arr, sigma_bins):
    r = int(3 * sigma_bins) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_bins) ** 2); k /= k.sum()
    return np.convolve(np.pad(arr, r, mode='edge'), k, mode='valid')


def taubin(co, edges, iters=24, lam=0.5, mu=-0.53):
    """Low-pass smoothing without shrinkage (alternating lambda/mu Laplacian steps)."""
    n = len(co)
    a, b = edges[:, 0], edges[:, 1]
    deg = (np.bincount(a, minlength=n) + np.bincount(b, minlength=n)).astype(np.float32)
    deg = np.maximum(deg, 1)
    out = co.astype(np.float64).copy()
    for it in range(iters * 2):
        acc = np.zeros_like(out)
        np.add.at(acc, a, out[b]); np.add.at(acc, b, out[a])
        f = lam if it % 2 == 0 else mu
        out += f * (acc / deg[:, None] - out)
    return out.astype(np.float32)


def smooth_scalar(x, edges, iters=10):
    n = len(x)
    a, b = edges[:, 0], edges[:, 1]
    deg = np.maximum(np.bincount(a, minlength=n) + np.bincount(b, minlength=n), 1).astype(np.float32)
    out = x.astype(np.float32).copy()
    for _ in range(iters):
        acc = np.zeros_like(out)
        np.add.at(acc, a, out[b]); np.add.at(acc, b, out[a])
        out = np.maximum(out, 0.5 * out + 0.5 * acc / deg)   # spread pushes, never reduce them
    return out


def side_of(co):
    return np.where(co[:, 0] >= 0, 1, -1)


def hull_depth(co, idx):
    """Distance of each region vertex below the convex hull of the region (0 on convex parts)."""
    bm = bmesh.new()
    for p in co[idx]:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts[:])
    hull = BVHTree.FromBMesh(bm)
    bm.free()
    return np.array([(Vector(co[i]) - hull.find_nearest(Vector(co[i]))[0]).length for i in idx], np.float32)


def relax_crevices(ob, iters=200, lam=1.0):
    """Melt the inter-toe crevices into one continuous toe surface: Blender's Laplacian Smooth
    (volume preserving, normalized) weighted over the toe area only."""
    me = ob.data
    co, nr, ed = mesh_arrays(me)
    sides = side_of(co)
    w = np.zeros(len(co), np.float32)
    for s in (1, -1):
        idx, ymin = toe_region(co, sides, s, depth=0.095, zmax=0.065)
        if len(idx) < 50:
            continue
        w[idx] = smoothstep(ymin + 0.095, ymin + 0.06, co[idx, 1]) * smoothstep(0.065, 0.045, co[idx, 2])
    vg = ob.vertex_groups.new(name='toes')
    q = np.round(w * 32) / 32
    for val in np.unique(q):
        if val > 0:
            vg.add(np.nonzero(q == val)[0].tolist(), float(val), 'REPLACE')
    mod = ob.modifiers.new('toe_relax', 'SMOOTH')
    mod.factor = lam; mod.iterations = iters
    mod.vertex_group = 'toes'
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = ob.evaluated_get(dg)
    em = ev.to_mesh()
    out = np.empty(len(em.vertices) * 3, np.float32); em.vertices.foreach_get('co', out)
    ev.to_mesh_clear()
    ob.modifiers.remove(mod); ob.vertex_groups.remove(vg)
    out = out.reshape(-1, 3)
    me.vertices.foreach_set('co', out.ravel())
    me.update()
    print('[%s] toe relax: %d verts, max move %.1f mm' % (ob.name, int((w > 0).sum()), float(np.linalg.norm(out - co, axis=1).max() * 1000)))


def toe_region(co, sides, s, depth=0.095, zmax=0.06, zmin=-1.0):
    m = sides == s
    ymin = co[m, 1].min()
    idx = np.nonzero(m & (co[:, 1] < ymin + depth) & (co[:, 2] < zmax) & (co[:, 2] > zmin))[0]
    return idx, ymin


def squeeze_toes(body, r=0.0021):
    """A stocking foot: toes pressed together under the knit. Fatten the toe area outward along
    the normals so the narrow inter-toe gaps close (toes merge into one rounded toe box with soft
    bumps, like the reference); the tights are then derived from this continuous shape."""
    me = body.data
    co, nr, ed = mesh_arrays(me)
    sides = side_of(co)
    w = np.zeros(len(co), np.float32)
    for s in (1, -1):
        idx, ymin = toe_region(co, sides, s, depth=0.095, zmax=0.06)
        if len(idx) < 50:
            continue
        w[idx] = smoothstep(ymin + 0.085, ymin + 0.055, co[idx, 1]) * smoothstep(0.004, 0.0, co[idx, 2] - 0.05)
    out = co + nr * (r * w)[:, None]
    mask = w > 0
    sub = ed[mask[ed[:, 0]] | mask[ed[:, 1]]]
    out = laplacian(out, sub, mask, iters=6, lam=0.4)
    me.vertices.foreach_set('co', out.ravel()); me.update()
    print('[body] toes pressed together: %d verts' % int(mask.sum()))


def build_toe_caps(body, tights, mats, skin_mat=None, y_back=0.06, d_max=0.0012, voxel=0.0012):
    """Stocking toe: a new surface stretched across the toes. Convex hull of the toes -> voxel
    remesh (even quads) -> each vertex pushed inward along the hull normal until it meets the skin
    (+offset) but never more than d_max: hugs toe tops/fronts, spans the gaps between toes."""
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg)
    cb = np.empty(len(body.data.vertices) * 3, np.float32); body.data.vertices.foreach_get('co', cb); cb = cb.reshape(-1, 3)
    caps = []
    cut_y = {}
    for s, mat in ((1, mats[0]), (-1, mats[1])):
        m = (cb[:, 0] * s > 0)
        ymin = cb[m, 1].min()
        ycut = ymin + y_back
        cut_y[s] = ycut
        pts = cb[m & (cb[:, 1] < ycut + 0.006) & (cb[:, 2] < 0.075)]
        bm = bmesh.new()
        for p in pts:
            bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=bm.verts[:])
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        me = bpy.data.meshes.new('toecap_tmp')
        bm.to_mesh(me); bm.free()
        tmp = bpy.data.objects.new('toecap_tmp', me)
        bpy.context.scene.collection.objects.link(tmp)
        rm = tmp.modifiers.new('rm', 'REMESH'); rm.mode = 'VOXEL'; rm.voxel_size = voxel
        dg.update()
        ev = tmp.evaluated_get(dg)
        cap_me = bpy.data.meshes.new_from_object(ev)
        bpy.data.objects.remove(tmp); bpy.data.meshes.remove(me)
        # keep the front/top/sides only: drop the back (cut plane) and the sole contact
        bm = bmesh.new(); bm.from_mesh(cap_me)
        bm.normal_update()
        kill = [f for f in bm.faces if f.calc_center_median().y > ycut - 0.001 or f.calc_center_median().z < 0.004 or f.normal.z < -0.3]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.normal_update()
        for v in bm.verts:
            n = v.normal
            hit = bvh.ray_cast(v.co + n * 0.0005, -n, 0.05)
            if hit[0] is not None:
                t = (hit[0] - v.co).length
                v.co = v.co - n * max(min(t - OFFSET, d_max), -0.001)
        for _ in range(5):
            bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if not v.is_boundary], factor=0.5,
                                  use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.to_mesh(cap_me); bm.free()
        cap_me.name = 'toecap_%s' % ('L' if s == 1 else 'R')
        ob = bpy.data.objects.new(cap_me.name, cap_me)
        bpy.context.scene.collection.objects.link(ob)
        cap_me.materials.append(mat)
        cap_me.polygons.foreach_set('use_smooth', np.ones(len(cap_me.polygons), bool))
        cap_me.update()
        # attributes / uv expected by the tights shader
        n = len(cap_me.vertices)
        co = np.empty(n * 3, np.float32); cap_me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        nr = np.empty(n * 3, np.float32); cap_me.vertex_normals.foreach_get('vector', nr)
        capfade = smoothstep(ycut - 0.0005, ycut - 0.0065, co[:, 1]).astype(np.float32)
        for name, typ, data in (('rest', 'FLOAT_VECTOR', co), ('rest_n', 'FLOAT_VECTOR', nr),
                                ('prestretch', 'FLOAT', np.full(n, 1.15, np.float32)), ('stretch', 'FLOAT', np.ones(n, np.float32)),
                                ('lift', 'FLOAT', np.zeros(n, np.float32)), ('toe', 'FLOAT', np.ones(n, np.float32)),
                                ('capfade', 'FLOAT', capfade)):
            a = cap_me.attributes.new(name, typ, 'POINT')
            a.data.foreach_set('vector' if typ == 'FLOAT_VECTOR' else 'value', np.asarray(data).ravel())
        uvl = cap_me.uv_layers.new(name='tuv')
        lv = np.empty(len(cap_me.loops), np.int32); cap_me.loops.foreach_get('vertex_index', lv)
        cx = co[:, 0].mean()
        u = (np.arctan2(co[:, 0] - cx, co[:, 2] - 0.0) / (2 * np.pi)) % 1.0
        uv = np.stack([u[lv] * 0.25, co[lv, 2] / V_SCALE], 1).astype(np.float32)
        uvl.data.foreach_set('uv', uv.ravel())
        caps.append(ob)
        print('[toecap] side', s, 'verts', n)
        # smooth skin shell under the cap (toes squeezed together by the hosiery)
        if skin_mat is not None:
            sk_me = cap_me.copy()
            sk_me.name = 'toeskin_%s' % ('L' if s == 1 else 'R')
            for nm in ('rest', 'rest_n', 'prestretch', 'stretch', 'lift', 'toe', 'capfade'):
                if nm in sk_me.attributes:
                    sk_me.attributes.remove(sk_me.attributes[nm])
            sco = co - nr.reshape(-1, 3) * (OFFSET + 0.0004)
            sk_me.vertices.foreach_set('co', sco.astype(np.float32).ravel())
            sk_me.materials.clear(); sk_me.materials.append(skin_mat)
            sk_me.update()
            sk = bpy.data.objects.new(sk_me.name, sk_me)
            bpy.context.scene.collection.objects.link(sk)
            caps.append(sk)
    # remove the tights' own toe faces (the cap takes over; 2 mm overlap at the seam)
    me = tights.data
    bm = bmesh.new(); bm.from_mesh(me)
    kill = []
    for f in bm.faces:
        c = f.calc_center_median()
        s = 1 if c.x >= 0 else -1
        if c.y < cut_y[s] - 0.003 and c.z < 0.075:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(me); bm.free(); me.update()
    print('[toecap] removed tights toe faces:', len(kill))
    # cross-fade attribute on the tights: fades out where the cap takes over (no double layer)
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    sd = np.where(co[:, 0] >= 0, 1, -1)
    yc = np.where(sd == 1, cut_y[1], cut_y[-1])
    fade = smoothstep(yc - 0.0065, yc - 0.0005, co[:, 1])
    fade = np.where(co[:, 2] < 0.075, fade, 1.0).astype(np.float32)
    a = me.attributes.new('capfade', 'FLOAT', 'POINT'); a.data.foreach_set('value', fade)
    # remove the skin's own toes under the shell
    if skin_mat is not None:
        bme = bmesh.new(); bme.from_mesh(body.data)
        killb = []
        for f in bme.faces:
            c = f.calc_center_median()
            s = 1 if c.x >= 0 else -1
            if c.y < cut_y[s] - 0.004 and c.z < 0.075:
                killb.append(f)
        bmesh.ops.delete(bme, geom=killb, context='FACES')
        bme.to_mesh(body.data); bme.free(); body.data.update()
        print('[toecap] removed skin toe faces:', len(killb))
    return caps


def bridge_concavities(co, nr, side_v, bvh, z0=0.33, z1=0.68, R=0.055, h=0.002):
    """A stocking does not follow the skin into hollows: it spans them (back of the knee, sides of the
    knee). Per leg, close the leg volume with a ball of radius R; tights vertices lying inside the
    added (bridged) volume are marched outward along their normals until they leave it."""
    import sheer_toebox as TB
    out = co.copy()
    disp = np.zeros(len(co))
    for s in (1, -1):
        m = (side_v == s) & (co[:, 2] > z0 - 0.05) & (co[:, 2] < z1 + 0.05)
        if m.sum() < 100:
            continue
        lo = co[m].min(0) - (R + 0.008); hi = co[m].max(0) + (R + 0.008)
        shape = tuple(int(np.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
        xs = lo[0] + h * np.arange(shape[0]); ys = lo[1] + h * np.arange(shape[1]); zs = lo[2] + h * np.arange(shape[2])
        occ = np.zeros(shape, bool)
        for i, x in enumerate(xs):
            for k, z in enumerate(zs):
                hits = TB._ray_hits(bvh, x, z, lo[1] - 0.05, hi[1] + 0.05)
                if len(hits) % 2:
                    hits = hits[:-1]
                if hits:
                    occ[i, :, k] = (np.searchsorted(np.asarray(hits), ys) % 2) == 1
        occ[(xs * s) <= 0.0, :, :] = False                 # this leg only: never bridge to the other knee
        pc = int(np.ceil(R / h)) + 3
        fsh = tuple(n + pc for n in shape)
        FK, nk = TB._ball_fft(fsh, R / h)
        dil = TB._conv(occ, FK, fsh) > 0.5
        closed = (TB._conv(dil, FK, fsh) > nk - 0.5) | occ
        added = TB._blur(closed & ~occ, 1.5, fsh)
        Bc = TB._blur(closed, 1.0, fsh)
        idx = np.nonzero(m & (co[:, 2] > z0) & (co[:, 2] < z1))[0]
        p = co[idx].astype(np.float64).copy(); n = nr[idx].astype(np.float64)
        act = TB._trilinear(Bc, lo, h, p) > 0.5        # fabric inside the closed (spanned) shape
        for _ in range(38):                                   # march out of the bridged volume (0.4 mm steps, <= 15 mm)
            if not act.any():
                break
            inside = act & (TB._trilinear(Bc, lo, h, p) > 0.5)
            if not inside.any():
                break
            p[inside] += n[inside] * 0.0004
        d = np.linalg.norm(p - co[idx], axis=1)
        w = smoothstep(z0, z0 + 0.05, co[idx, 2]) * smoothstep(z1, z1 - 0.05, co[idx, 2])
        disp[idx] = d * w
        print('[tights] bridged side %d: %d verts lifted, max %.1f mm' % (s, int((d > 0.0005).sum()), d.max() * 1000))
    return disp


ZA = float(os.environ.get('SETTLE_ZA', '0.05'))


def span_slices(co, side_v, z0=0.065, z1=0.24, band=0.002, amount=0.85):
    """Tensioned nylon runs straight across the hollows of a cross-section (beside the Achilles tendon,
    behind the ankle bones): per horizontal slice of each leg, lift the fabric radially toward the slice's
    convex envelope. Returns per-vertex outward displacement vectors (horizontal)."""
    disp = np.zeros_like(co)

    def hull(P):
        P = sorted(map(tuple, P))
        if len(P) < 3:
            return np.array(P)
        cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo_, up_ = [], []
        for p in P:
            while len(lo_) >= 2 and cr(lo_[-2], lo_[-1], p) <= 0: lo_.pop()
            lo_.append(p)
        for p in reversed(P):
            while len(up_) >= 2 and cr(up_[-2], up_[-1], p) <= 0: up_.pop()
            up_.append(p)
        return np.array(lo_[:-1] + up_[:-1])
    for s in (1, -1):
        for zb in np.arange(z0, z1, band):
            m = np.nonzero((side_v == s) & (co[:, 2] >= zb) & (co[:, 2] < zb + band))[0]
            if len(m) < 12:
                continue
            P = co[m, :2]; c = P.mean(0)
            H = hull(P)
            if len(H) < 3:
                continue
            # radial distance from the centroid to the hull boundary along each vertex direction
            d = P - c; r = np.linalg.norm(d, axis=1); u = d / np.maximum(r, 1e-9)[:, None]
            A = H - c; B = np.roll(H, -1, 0) - c
            best = np.full(len(m), np.inf)
            for k in range(len(H)):
                e = B[k] - A[k]
                den = u[:, 0] * e[1] - u[:, 1] * e[0]
                ok = np.abs(den) > 1e-12
                t = np.where(ok, (A[k, 0] * e[1] - A[k, 1] * e[0]) / np.where(ok, den, 1), np.inf)
                sp = np.where(ok, (A[k, 0] * u[:, 1] - A[k, 1] * u[:, 0]) / np.where(ok, den, 1), -1)
                hit = ok & (t > 0) & (sp >= -1e-6) & (sp <= 1 + 1e-6)
                best = np.where(hit, np.minimum(best, t), best)
            gap = np.where(np.isfinite(best), np.maximum(best - r, 0.0), 0.0) * amount
            w = smoothstep(z0, z0 + 0.03, zb) * smoothstep(z1, z1 - 0.04, zb)
            disp[m, :2] = u * (gap * w)[:, None]
    return disp


def span_profiles(co, side_v, z0=0.02, z1=0.68, Rv=0.12, dz=0.002, sectors=72, amount=0.85):
    """Lengthwise tension: along the leg the stocking cannot follow profile dips tighter than ~Rv; it runs
    straight from calf to heel, across the ankle crease and behind the knee. Per angular sector around the
    leg axis, close the radial profile r(z) with a disc of radius Rv; lift the fabric radially onto it."""
    disp = np.zeros_like(co)
    zb = np.arange(z0 - 0.05, z1 + 0.05, dz); nz = len(zb)
    K = int(Rv / dz)
    off = np.arange(-K, K + 1) * dz
    cj = np.sqrt(np.maximum(Rv * Rv - off * off, 0.0)) - Rv          # disc profile (<= 0)
    for s in (1, -1):
        zc, cx, cy, _ = leg_axis_tables(co, s)
        m = np.nonzero((side_v == s) & (co[:, 2] > zb[0]) & (co[:, 2] < zb[-1]))[0]
        ax = np.interp(co[m, 2], zc, cx); ay = np.interp(co[m, 2], zc, cy)
        dx, dy = co[m, 0] - ax, co[m, 1] - ay
        r = np.hypot(dx, dy); th = np.arctan2(dx, dy)
        ti = ((th + np.pi) / (2 * np.pi) * sectors).astype(int) % sectors
        zi = np.clip(((co[m, 2] - zb[0]) / dz).astype(int), 0, nz - 1)
        R = np.full((sectors, nz), -1.0)
        np.maximum.at(R, (ti, zi), r)
        for t in range(sectors):                                    # fill empty bins
            row = R[t]; ok = row > 0
            if ok.sum() < 4:
                R[t] = 0.0; continue
            R[t] = np.interp(np.arange(nz), np.nonzero(ok)[0], row[ok])
        P = np.pad(R, ((0, 0), (K, K)), mode='edge')
        D = np.full_like(R, -1e9)
        for j in range(2 * K + 1):
            D = np.maximum(D, P[:, j:j + nz] + cj[j])
        PD = np.pad(D, ((0, 0), (K, K)), mode='edge')
        C = np.full_like(R, 1e9)
        for j in range(2 * K + 1):
            C = np.minimum(C, PD[:, j:j + nz] - cj[j])
        lift = np.maximum(C - R, 0.0)
        # smooth across sectors a little (fabric is continuous around the leg)
        lift = (np.roll(lift, 1, 0) + 2 * lift + np.roll(lift, -1, 0)) / 4
        lv = lift[ti, zi] * amount
        w = smoothstep(z0, z0 + 0.03, co[m, 2]) * smoothstep(z1, z1 - 0.05, co[m, 2])
        u = np.stack([dx, dy], 1) / np.maximum(r, 1e-9)[:, None]
        disp[m, :2] = u * (lv * w)[:, None]
    return disp


def tension_settle(ob, sm, ed, body, shrink=0.12, iters=900, ratio=0.08):
    """Real tights are knitted smaller than the leg and pulled on, so they are under tension everywhere:
    they span sharp concave corners (ankle hollows, back of the knee, between the toes) and stretch most
    over bulges. Solved directly (position-based relaxation on a decimated proxy): every edge wants to be
    `shrink` shorter than now; vertices are projected outside the skin (exact nearest-surface test), held
    at the waistband and the sole, and lightly anchored in height (friction against the leg).
    Returns full-res settled positions and the fabric's areal stretch vs its relaxed (knitted) size."""
    from mathutils.kdtree import KDTree
    scene = bpy.context.scene
    me = ob.data
    me.vertices.foreach_set('co', sm.astype(np.float32).ravel()); me.update()
    dg = bpy.context.evaluated_depsgraph_get()
    o = bpy.data.objects.new('tights_proxy', me.copy()); scene.collection.objects.link(o)
    d_ = o.modifiers.new('dec', 'DECIMATE'); d_.ratio = ratio
    dg.update()
    pm = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    bpy.data.objects.remove(o)
    n = len(pm.vertices)
    P0 = np.empty(n * 3, np.float32); pm.vertices.foreach_get('co', P0); P0 = P0.reshape(-1, 3).astype(np.float64)
    pe = np.empty(len(pm.edges) * 2, np.int32); pm.edges.foreach_get('vertices', pe); pe = pe.reshape(-1, 2)
    pm.calc_loop_triangles()
    tri = np.empty(len(pm.loop_triangles) * 3, np.int32); pm.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1, 3)
    bpy.data.meshes.remove(pm)
    bvh = BVHTree.FromObject(body, dg)
    a_, b_ = pe[:, 0], pe[:, 1]
    L0 = np.linalg.norm(P0[b_] - P0[a_], axis=1) * (1.0 - shrink)
    deg = np.maximum(np.bincount(a_, minlength=n) + np.bincount(b_, minlength=n), 1).astype(np.float64)
    pin = (P0[:, 2] > 0.955) | (P0[:, 2] < 0.004)
    x = P0.copy()
    for it in range(iters):
        dv = x[b_] - x[a_]
        ln = np.maximum(np.linalg.norm(dv, axis=1), 1e-9)
        corr = ((ln - L0) / ln)[:, None] * dv * 0.5
        acc = np.zeros_like(x)
        np.add.at(acc, a_, corr); np.add.at(acc, b_, -corr)
        x += 0.8 * acc / deg[:, None]
        x[:, 2] += ZA * (P0[:, 2] - x[:, 2])             # friction: the fabric barely slides along the leg
        x[pin] = P0[pin]
        if it % 2 == 0 or it > iters - 20:               # keep the fabric outside the skin
            for i in range(n):
                q = bvh.find_nearest(Vector(x[i]))
                if q[0] is None:
                    continue
                sd = (Vector(x[i]) - q[0]).dot(q[1])
                if sd < OFFSET:
                    x[i] += np.array(q[1]) * (OFFSET - sd)
    def areas(P):
        return 0.5 * np.linalg.norm(np.cross(P[tri[:, 1]] - P[tri[:, 0]], P[tri[:, 2]] - P[tri[:, 0]]), axis=1)
    ratio_f = areas(x) / np.maximum(areas(P0) * (1.0 - shrink) ** 2, 1e-12)
    cnt = np.maximum(np.bincount(tri.ravel(), minlength=n), 1)
    str_v = np.bincount(tri.ravel(), weights=np.repeat(ratio_f, 3), minlength=n) / cnt
    for _ in range(40):                                   # tension varies smoothly over centimetres
        acc1 = np.zeros(n); np.add.at(acc1, a_, str_v[b_]); np.add.at(acc1, b_, str_v[a_])
        str_v = 0.5 * str_v + 0.5 * acc1 / deg
    kd = KDTree(n)
    for i, p in enumerate(P0):
        kd.insert(p, i)
    kd.balance()
    D = x - P0
    out = sm.astype(np.float64).copy(); S = np.ones(len(sm))
    for i, p in enumerate(sm):
        nb = kd.find_n(p, 6)
        w = np.array([1.0 / max(dd, 1e-5) for (_, _, dd) in nb]); w /= w.sum()
        idx = [j for (_, j, _) in nb]
        out[i] += (D[idx] * w[:, None]).sum(0)
        S[i] = (str_v[idx] * w).sum()
    dm = np.linalg.norm(D, axis=1)
    print('[tights] tension solve: shrink %.0f%%, proxy %d verts, %d iters, moved max %.1f mm (mean %.2f), stretch p2 %.2f median %.2f p98 %.2f' % (
        shrink * 100, n, iters, dm.max() * 1000, dm.mean() * 1000, np.percentile(S, 2), np.median(S), np.percentile(S, 98)))
    return out, S


def leg_axis_tables(co, side, zmax=1.0, step=0.002, sectors=48):
    """Robust per-height leg axis & circumference: radius averaged per angular sector, then
    Gaussian-smoothed along the leg (noise here would show up as coverage banding)."""
    zb = np.arange(0.0, zmax + step, step)
    zc = 0.5 * (zb[:-1] + zb[1:])
    cx = np.full(len(zc), np.nan); cy = np.full(len(zc), np.nan); circ = np.full(len(zc), np.nan)
    sel = co[:, 0] * side > 0.0
    for i, (z0, z1) in enumerate(zip(zb[:-1], zb[1:])):
        m = sel & (co[:, 2] >= z0 - 0.003) & (co[:, 2] < z1 + 0.003)
        if m.sum() < 24:
            continue
        x, y = co[m, 0], co[m, 1]
        x0, y0 = 0.5 * (x.min() + x.max()), 0.5 * (y.min() + y.max())
        th = np.arctan2(x - x0, y - y0)
        r = np.hypot(x - x0, y - y0)
        sec = ((th + np.pi) / (2 * np.pi) * sectors).astype(int) % sectors
        rs = np.bincount(sec, weights=r, minlength=sectors) / np.maximum(np.bincount(sec, minlength=sectors), 1)
        ok = rs > 0
        if ok.sum() < sectors * 0.6:
            continue
        ang = (np.arange(sectors) + 0.5) / sectors * 2 * np.pi - np.pi
        px = x0 + np.sin(ang[ok]) * rs[ok]; py = y0 + np.cos(ang[ok]) * rs[ok]
        cx[i], cy[i] = px.mean(), py.mean()
        circ[i] = 2 * np.pi * rs[ok].mean()
    idx = np.arange(len(zc)); ok = ~np.isnan(cx)
    for arr in (cx, cy, circ):
        arr[:] = np.interp(idx, idx[ok], arr[ok])
    cx[:] = _gauss_smooth(cx, 6); cy[:] = _gauss_smooth(cy, 6)
    circ[:] = _gauss_smooth(circ, 8)
    return zc, cx, cy, circ


def build_tights(body, name='tights', collider=None):
    scene = bpy.context.scene
    bm = bmesh.new(); bm.from_mesh(body.data)
    kill = [f for f in bm.faces if f.calc_center_median().z > TOP_Z]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    co, nr, ed = mesh_arrays(me)

    # --- bridge over the toes (a stocking does not dip between toes), then offset outward
    toe = np.zeros(len(co), bool)
    for side in (1, -1):
        s = co[:, 0] * side > 0
        ymin = co[s, 1].min()
        toe |= s & (co[:, 2] < 0.05) & (co[:, 1] < ymin + 0.08)
    # (the toe box is already closed geometrically by sheer_toebox — no crevices left to smooth)
    sm = co.copy()
    # stretched nylon smooths over skin micro-relief: Taubin low-pass (no shrinkage). This also
    # removes sculpt micro-ripples that a glossy yarn highlight would reveal as banding.
    sm = taubin(sm, ed, iters=24)
    me.vertices.foreach_set('co', sm.ravel()); me.update()
    _, nsm, _ = mesh_arrays(me)
    sm = sm + nsm * OFFSET
    # residual penetrations (concave spots): push out with a smoothed push field (no re-rippling)
    bvh = BVHTree.FromObject(collider or body, bpy.context.evaluated_depsgraph_get())   # e.g. the real toes
    push = np.zeros(len(sm), np.float32)
    for i in range(len(sm)):
        p = Vector(sm[i])
        hit = bvh.find_nearest(p)
        if hit[0] is None:
            continue
        d = (p - hit[0]).dot(hit[1])
        if d < OFFSET:
            push[i] = OFFSET - d
    push = smooth_scalar(push, ed, iters=24)
    sm = sm + nsm * push[:, None]
    print('[tights] max push %.2f mm, pushed verts %d' % (push.max() * 1000, int((push > 1e-5).sum())))
    # span the hollows (back of the knee): smooth lift field along the normals
    # less total fabric than skin: settle a pre-tensioned stocking against the leg (spans corners)
    sm, sim_stretch = tension_settle(ob, sm, ed, body)
    # stronger span over the sharpest corners (ankle crease / malleoli / Achilles, back of the knee):
    # morphological closing of each leg's volume there; fabric inside the added volume is lifted onto it
    me.vertices.foreach_set('co', sm.astype(np.float32).ravel()); me.update()
    _, nb_, _ = mesh_arrays(me)
    sidev = np.where(sm[:, 0] >= 0, 1, -1)
    if os.environ.get('SHEER_BRIDGE', '1') == '1':
        lift = bridge_concavities(sm, nb_, sidev, bvh, z0=0.03, z1=0.17, R=float(os.environ.get('SHEER_ANKLE_R', '0.06')), h=0.0015)
        lift = np.maximum(lift, bridge_concavities(sm, nb_, sidev, bvh, z0=0.38, z1=0.6, R=0.08, h=0.002))
        a3, b3 = ed[:, 0], ed[:, 1]
        dg3 = np.maximum(np.bincount(a3, minlength=len(lift)) + np.bincount(b3, minlength=len(lift)), 1)
        for _ in range(8):
            acc3 = np.zeros(len(lift)); np.add.at(acc3, a3, lift[b3]); np.add.at(acc3, b3, lift[a3])
            lift = np.maximum(lift, 0.5 * lift + 0.5 * acc3 / dg3) * 0.0 + (0.5 * lift + 0.5 * acc3 / dg3)
        sm = sm + nb_ * lift[:, None]
        sd = span_profiles(sm, sidev, Rv=float(os.environ.get('SHEER_SPAN_R', '0.25')))
        a4, b4 = ed[:, 0], ed[:, 1]
        dg4 = np.maximum(np.bincount(a4, minlength=len(sm)) + np.bincount(b4, minlength=len(sm)), 1)[:, None]
        for _ in range(12):                                # smooth the span field (no ridges)
            acc4 = np.zeros_like(sd); np.add.at(acc4, a4, sd[b4]); np.add.at(acc4, b4, sd[a4])
            sd = 0.5 * sd + 0.5 * acc4 / dg4
        sm = sm + sd
        print('[tights] profile spans: max %.1f mm, %d verts > 1 mm' % (np.linalg.norm(sd, axis=1).max() * 1000, int((np.linalg.norm(sd, axis=1) > 0.001).sum())))
        print('[tights] corner spans: max lift %.1f mm, %d verts > 1 mm' % (lift.max() * 1000, int((lift > 0.001).sum())))
    me.vertices.foreach_set('co', sm.astype(np.float32).ravel()); me.update()
    _, nsm2, _ = mesh_arrays(me)
    push2 = np.zeros(len(sm), np.float32)
    for i in range(len(sm)):
        p = Vector(sm[i]); hit = bvh.find_nearest(p)
        if hit[0] is not None:
            d = (p - hit[0]).dot(hit[1])
            if d < OFFSET:
                push2[i] = OFFSET - d
    push2 = smooth_scalar(push2, ed, iters=24)
    sm = (sm + nsm2 * push2[:, None]).astype(np.float32)
    print('[tights] post-settle push max %.2f mm' % (push2.max() * 1000))
    me.vertices.foreach_set('co', sm.ravel())
    me.update()
    co = sm

    # --- per-leg axis tables, parameterisation & attributes
    tables = {s: leg_axis_tables(co, s) for s in (1, -1)}
    u = np.zeros(len(co), np.float32)
    pre = np.ones(len(co), np.float32)
    circ_v = np.ones(len(co), np.float32)
    side_v = np.where(co[:, 0] >= 0, 1, -1).astype(np.int32)
    ankle_z = 0.095
    for s in (1, -1):
        zc, cx, cy, circ = tables[s]
        m = side_v == s
        z = np.clip(co[m, 2], ankle_z, 0.99)
        ax = np.interp(z, zc, cx); ay = np.interp(z, zc, cy)
        th = np.arctan2(co[m, 0] - ax, co[m, 1] - ay)  # 0 = back (+Y), pi/2 = +X
        u[m] = (th / (2 * np.pi)) % 1.0
        c = np.interp(co[m, 2], zc, circ)
        cmin = circ[(zc > 0.1) & (zc < 0.35)].min()
        pre[m] = np.power(np.maximum(c / cmin, 1.0), 0.3)
        circ_v[m] = c
    v = co[:, 2] / V_SCALE

    # UV map (per corner) with seam fix
    uvl = me.uv_layers.new(name='tuv')
    nl = len(me.loops)
    lv = np.empty(nl, np.int32); me.loops.foreach_get('vertex_index', lv)
    luv = np.stack([u[lv], v[lv]], 1)
    ls = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_start', ls)
    lt = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_total', lt)
    for pi in range(len(ls)):
        sl = slice(ls[pi], ls[pi] + lt[pi])
        uu = luv[sl, 0]
        if uu.max() - uu.min() > 0.5:
            uu = np.where(uu < 0.5, uu + 1.0, uu)
            luv[sl, 0] = uu
    uvl.data.foreach_set('uv', luv.astype(np.float32).ravel())
    me.uv_layers.active = uvl

    def attr(name, typ, data):
        a = me.attributes.new(name, typ, 'POINT')
        a.data.foreach_set('vector' if typ == 'FLOAT_VECTOR' else 'value', np.asarray(data).ravel())
    toe_w = np.zeros(len(co), np.float32)
    for s_ in (1, -1):
        m = side_v == s_
        ymin = co[m, 1].min()
        # reinforced toe pocket: front ~5.5 cm of the foot, boundary slanting up over the instep
        edge = ymin + 0.055 + 0.25 * np.clip(co[m, 2] - 0.02, 0, None)
        toe_w[m] = (smoothstep(edge + 0.003, edge - 0.003, co[m, 1]) * smoothstep(0.075, 0.06, co[m, 2])).astype(np.float32)
    attr('toe', 'FLOAT', toe_w)
    # local static stretch: the knitted tube stretches more over bulges (kneecap...) than over a plain cylinder
    n_ = len(co); a_, b_ = ed[:, 0], ed[:, 1]
    deg_ = np.maximum(np.bincount(a_, minlength=n_) + np.bincount(b_, minlength=n_), 1).astype(np.float64)
    acc_ = np.zeros((n_, 3)); np.add.at(acc_, a_, co[b_]); np.add.at(acc_, b_, co[a_])
    elen = np.linalg.norm(co[a_] - co[b_], axis=1)
    el_ = (np.bincount(a_, weights=elen, minlength=n_) + np.bincount(b_, weights=elen, minlength=n_)) / deg_
    _, nrc, _ = mesh_arrays(me)
    Hm = -2.0 * np.einsum('ij,ij->i', acc_ / deg_[:, None] - co, nrc) / np.maximum(el_ ** 2, 1e-10)
    Hm = smooth_scalar(np.clip(Hm, -200, 200).astype(np.float32) + 200.0, ed, iters=0) - 200.0
    for _ in range(25):                                   # denoise the curvature estimate
        acc1 = np.zeros(n_); np.add.at(acc1, a_, Hm[b_]); np.add.at(acc1, b_, Hm[a_])
        Hm = 0.5 * Hm + 0.5 * acc1 / deg_
    Hcyl = np.pi / np.maximum(circ_v, 0.05)
    lstr = 1.0 + np.clip((Hm - Hcyl) * 0.012, 0.0, 0.6)
    lstr = np.where(co[:, 2] > 0.12, lstr, 1.0)          # (feet: reinforced, no extra clearing)
    pre = (pre * lstr).astype(np.float32)
    ss = sim_stretch.astype(np.float64).copy()
    a2, b2 = ed[:, 0], ed[:, 1]
    dg2 = np.maximum(np.bincount(a2, minlength=len(ss)) + np.bincount(b2, minlength=len(ss)), 1)
    for _ in range(30):
        acc2 = np.zeros(len(ss)); np.add.at(acc2, a2, ss[b2]); np.add.at(acc2, b2, ss[a2])
        ss = 0.5 * ss + 0.5 * acc2 / dg2
    pre = np.clip(ss / np.median(ss), 0.75, 1.6).astype(np.float32)          # simulated fabric stretch (median 1)
    print('[tights] static stretch (sim): p5 %.2f p50 %.2f p95 %.2f p99.5 %.2f' % tuple(np.percentile(pre, [5, 50, 95, 99.5])))
    print('[tights] curvature stretch: max x%.2f, >5%% on %d verts' % (lstr.max(), int((lstr > 1.05).sum())))
    # toe seam ('cucitura'): signed distance to the seam line across the toes, 1 m elsewhere
    seam = np.ones(len(co), np.float32)
    for s_ in (1, -1):
        m = (side_v == s_)
        ymin = co[m & (co[:, 2] < 0.08), 1].min()
        # the toe seam wraps around the front of the toes ~1.5 cm above the floor, rising slightly toward the back
        sz = 0.015 + 0.15 * np.clip(co[:, 1] - ymin, 0, None)
        sel = m & (co[:, 2] < 0.045) & (co[:, 1] < ymin + 0.045)
        seam[sel] = (co[sel, 2] - sz[sel]).astype(np.float32)
    attr('toeseam', 'FLOAT', seam)
    attr('capfade', 'FLOAT', np.ones(len(co), np.float32))
    attr('tu', 'FLOAT', u)
    attr('prestretch', 'FLOAT', pre)
    attr('circ', 'FLOAT', circ_v)
    attr('stretch', 'FLOAT', np.ones(len(co), np.float32))
    attr('lift', 'FLOAT', np.zeros(len(co), np.float32))
    attr('legside', 'FLOAT', side_v.astype(np.float32))
    attr('rest', 'FLOAT_VECTOR', co)
    _, nr2, _ = mesh_arrays(me)
    attr('rest_n', 'FLOAT_VECTOR', nr2)

    # material slots: 0 = left leg (x>0), 1 = right leg
    fc = np.empty(len(me.polygons) * 3, np.float32); me.polygons.foreach_get('center', fc); fc = fc.reshape(-1, 3)
    me.polygons.foreach_set('material_index', (fc[:, 0] < 0).astype(np.int32))
    me.polygons.foreach_set('use_smooth', np.ones(len(me.polygons), bool))
    me.update()
    info = {s: {'zc': tables[s][0].tolist(), 'cx': tables[s][1].tolist(), 'cy': tables[s][2].tolist(), 'circ': tables[s][3].tolist()} for s in (1, -1)}
    ob['sheer_tables'] = str(info)
    print('[tights] verts', len(co), 'faces', len(me.polygons))
    return ob, tables
