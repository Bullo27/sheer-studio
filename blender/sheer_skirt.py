# SHEER — pleated skirt as real cloth: a knife-pleated wool skirt (plain charcoal) built around the
# hip envelope, pinned at the waistband and simulated with Blender cloth against a decimated body
# proxy, so the pleats fall onto the thighs under their own weight. The same setup is reused by the
# animation (wind from a fan + reaction to the legs' motion).
import bpy, bmesh
import numpy as np
from mathutils import Vector


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def build_skirt_mesh(body, z_top=1.0, z_hem=0.672, n_pleats=16, n_rings=58, seed=11):
    rng = np.random.default_rng(seed)
    me_b = body.data
    co = np.empty(len(me_b.vertices) * 3, np.float32); me_b.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    zs = np.linspace(z_top, z_hem, n_rings)
    th_bins = np.linspace(-np.pi, np.pi, 361)
    yc0 = co[np.abs(co[:, 2] - z_top) < 0.01, 1].mean()
    env = np.zeros((n_rings, 360), np.float32)
    for i, z in enumerate(zs):
        m = np.abs(co[:, 2] - z) < 0.01
        p = co[m]
        th = np.arctan2(p[:, 1] - yc0, p[:, 0]); r = np.hypot(p[:, 0], p[:, 1] - yc0)
        idx = np.clip(np.digitize(th, th_bins) - 1, 0, 359)
        rr = np.zeros(360, np.float32); np.maximum.at(rr, idx, r)
        for k in range(360):
            if rr[k] == 0:
                rr[k] = rr[k - 1]
        rr = np.convolve(np.concatenate([rr[-12:], rr, rr[:12]]), np.ones(25) / 25, mode='valid')
        env[i] = rr
    env = np.maximum.accumulate(env, axis=0)          # hangs: never narrower than above
    # per-pleat irregularity
    p_depth = rng.uniform(0.8, 1.2, n_pleats)
    p_w = rng.uniform(0.9, 1.1, n_pleats); p_w /= p_w.mean()
    p_drop = rng.normal(0.0, 0.004, n_pleats)
    edges = np.concatenate([[0], np.cumsum(p_w)]) / n_pleats * 2 * np.pi - np.pi + rng.uniform(0, 0.2)
    verts, uvs = [], []
    # explicit samples per pleat: F on the flat face, R on the return; fold lines are exact columns
    F, R = 16, 4
    th_list, pk_list, ph_list, fold_cols = [], [], [], []
    for k in range(n_pleats):
        e0, e1 = edges[k], edges[k + 1]
        for j in range(F):
            ph_ = 0.88 * j / F
            if j == 0:
                fold_cols.append(len(th_list))
            th_list.append(e0 + ph_ * (e1 - e0)); pk_list.append(k); ph_list.append(ph_)
        for j in range(R):
            ph_ = 0.88 + 0.12 * j / R
            if j == 0:
                fold_cols.append(len(th_list))
            th_list.append(e0 + ph_ * (e1 - e0)); pk_list.append(k); ph_list.append(ph_)
    th_c = np.array(th_list); pk = np.array(pk_list); ph = np.array(ph_list)
    n_around = len(th_c)
    for i, z in enumerate(zs):
        t = i / (n_rings - 1)
        r_env = np.interp((th_c + np.pi) / (2 * np.pi) * 360, np.arange(360), env[i], period=360)
        depth = (0.003 + 0.026 * smoothstep(0.08, 0.7, t)) * p_depth[pk]
        saw = np.where(ph < 0.88, ph / 0.88, (1.0 - ph) / 0.12)     # knife pleat: flat face, sharp return
        flare = 0.034 * smoothstep(0.2, 1.0, t) ** 1.2
        r = r_env + 0.006 + flare + depth * (saw - 0.35)
        zz = z + p_drop[pk] * t
        for k in range(n_around):
            verts.append((r[k] * np.cos(th_c[k]), yc0 + r[k] * np.sin(th_c[k]), zz[k]))
    faces = []
    for i in range(n_rings - 1):
        for k in range(n_around):
            a = i * n_around + k; b2 = i * n_around + (k + 1) % n_around
            faces.append((a, b2, b2 + n_around, a + n_around))
    me = bpy.data.meshes.new('skirt')
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set('use_smooth', np.ones(len(faces), bool))
    # UV: arc length around (m) x height (m) -> the weave follows the pleats
    V = np.array(verts).reshape(n_rings, n_around, 3)
    seg = np.linalg.norm(np.roll(V, -1, 1) - V, axis=2)
    arc = np.concatenate([np.zeros((n_rings, 1)), np.cumsum(seg, 1)[:, :-1]], 1)
    uvl = me.uv_layers.new(name='UVMap')
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
    ring, col = lv // n_around, lv % n_around
    u = arc[ring, col]; v = V[ring, col, 2]
    # seam: faces wrapping from the last column to the first get u + total arc
    ls = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get('loop_start', ls)
    tot = arc[:, -1] + seg[:, -1]
    for pi_, l0 in enumerate(ls):
        cols = col[l0:l0 + 4]
        if cols.max() == n_around - 1 and cols.min() == 0:
            for j in range(4):
                if col[l0 + j] == 0:
                    u[l0 + j] += tot[ring[l0 + j]]
    uvl.data.foreach_set('uv', np.stack([u, v], 1).astype(np.float32).ravel())
    ed = np.empty(len(me.edges) * 2, np.int32); me.edges.foreach_get('vertices', ed); ed = ed.reshape(-1, 2)
    fc = np.zeros(n_around, bool); fc[fold_cols] = True
    ca, cb = ed[:, 0] % n_around, ed[:, 1] % n_around
    vertical = (ca == cb) & fc[ca]
    cr = me.attributes.new('crease_edge', 'FLOAT', 'EDGE')
    cr.data.foreach_set('value', vertical.astype(np.float32) * 0.9)
    ob = bpy.data.objects.new('skirt', me)
    bpy.context.scene.collection.objects.link(ob)
    # pin the waistband (top 3 rings)
    vg = ob.vertex_groups.new(name='pin')
    vg.add(list(range(3 * n_around)), 1.0, 'REPLACE')
    print('[skirt] %d pleats, %d verts, hem z %.3f' % (n_pleats, len(verts), z_hem))
    return ob


def make_proxy(body, z0=0.45, z1=1.06, ratio=0.06):
    bm = bmesh.new(); bm.from_mesh(body.data)
    kill = [f for f in bm.faces if not (z0 < f.calc_center_median().z < z1)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    me = bpy.data.meshes.new('skirt_proxy'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('skirt_proxy', me)
    bpy.context.scene.collection.objects.link(ob)
    dec = ob.modifiers.new('dec', 'DECIMATE'); dec.ratio = ratio
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    me2 = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear(); old = ob.data; ob.data = me2; bpy.data.meshes.remove(old)
    col = ob.modifiers.new('collision', 'COLLISION')
    ob.collision.thickness_outer = 0.0035
    ob.collision.thickness_inner = 0.004
    ob.collision.cloth_friction = 8.0
    ob.hide_render = True
    print('[skirt] collision proxy faces', len(ob.data.polygons))
    return ob


def setup_cloth(skirt, frame_end=90):
    scene = bpy.context.scene
    cm = skirt.modifiers.new('cloth', 'CLOTH')
    st = cm.settings
    st.quality = int(__import__('os').environ.get('SHEER_CLOTH_Q', '10'))
    st.mass = 0.35                      # medium-weight wool suiting
    st.air_damping = 3.0
    st.tension_stiffness = 30; st.compression_stiffness = 30
    st.shear_stiffness = 12
    st.bending_stiffness = 80.0         # pressed (heat-set) pleats keep their crease angles
    st.bending_model = 'ANGULAR'
    st.tension_damping = 5; st.compression_damping = 5; st.shear_damping = 5; st.bending_damping = 0.5
    st.vertex_group_mass = 'pin'
    st.pin_stiffness = 1.0
    cs = cm.collision_settings
    cs.use_collision = True
    cs.distance_min = 0.003
    cs.collision_quality = 4
    cs.use_self_collision = False
    pc = cm.point_cache
    pc.frame_start = 1; pc.frame_end = frame_end
    return cm


def drape(skirt, frames=90, apply=True):
    """Let the skirt settle under gravity and keep the draped shape (for stills / as rest state)."""
    scene = bpy.context.scene
    f0 = scene.frame_current
    for f in range(1, frames + 1):
        scene.frame_set(f)
    if apply:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(skirt.evaluated_get(dg))
        skirt.modifiers.clear()
        old = skirt.data; skirt.data = me
        bpy.data.meshes.remove(old)
    scene.frame_set(f0)
    co = np.empty(len(skirt.data.vertices) * 3, np.float32); skirt.data.vertices.foreach_get('co', co)
    print('[skirt] draped %d frames, hem min z %.3f' % (frames, co.reshape(-1, 3)[:, 2].min()))


def finish(skirt, mat):
    skirt.data.materials.clear(); skirt.data.materials.append(mat)
    sol = skirt.modifiers.new('solid', 'SOLIDIFY'); sol.thickness = 0.0018; sol.offset = 1.0; sol.use_even_offset = True
    sub = skirt.modifiers.new('subd', 'SUBSURF'); sub.levels = 1; sub.render_levels = 2
