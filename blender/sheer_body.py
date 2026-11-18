# SHEER — body preparation (CC0 Blender Studio "Human Base Meshes", realistic female).
# Bakes the multires sculpt, trims everything above the waist (never in frame; covered by skirt),
# and reshapes the legs toward a slimmer, longer "fashion model" silhouette.
import bpy, bmesh
import numpy as np
from mathutils import Vector

BODY_NAME = 'GEO-body_female_realistic'


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def import_body(bundle_path, level=3):
    with bpy.data.libraries.load(bundle_path, link=False) as (src, dst):
        dst.objects = [BODY_NAME]
    body = dst.objects[0]
    bpy.context.scene.collection.objects.link(body)
    body.location = (0, 0, 0)
    mr = [m for m in body.modifiers if m.type == 'MULTIRES']
    if mr:
        m = mr[0]
        lvl = min(level, m.total_levels)
        m.levels = m.render_levels = m.sculpt_levels = lvl
        print('[body] multires total', m.total_levels, '-> baking level', lvl)
    # bake evaluated mesh (multires applied) into a plain mesh
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=False, depsgraph=dg)
    old = body.data
    body.modifiers.clear()
    body.data = me
    bpy.data.meshes.remove(old)
    body.name = 'body'
    me.name = 'body'
    # the base mesh ships authored split normals; once we reshape the legs they no longer match the
    # geometry and show up as shading bands -> drop them and use true geometric normals
    if 'custom_normal' in me.attributes:
        me.attributes.remove(me.attributes['custom_normal'])
    print('[body] custom normals:', me.has_custom_normals)
    print('[body] baked verts', len(me.vertices), 'faces', len(me.polygons))
    return body


def trim_upper(body, z_cut=1.06, arm_x=0.2, arm_z=0.48):
    """Delete torso/arms/head (not needed: legs-only framing, skirt covers the hips)."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    kill = [f for f in bm.faces
            if (f.calc_center_median().z > z_cut) or
               (abs(f.calc_center_median().x) > arm_x and f.calc_center_median().z > arm_z)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    # drop loose bits (e.g. fingers detached by the cut)
    bm.verts.ensure_lookup_table()
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    print('[body] trimmed verts', len(body.data.vertices))


def _gauss(arr, sigma_bins):
    r = int(3 * sigma_bins) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_bins) ** 2); k /= k.sum()
    return np.convolve(np.pad(arr, r, mode='edge'), k, mode='valid')


def leg_axes(co, z_bins, sigma_m=0.02):
    """Smooth per-height axis of each leg (x>0 = character's left, x<0 = right).
    Per-slice centroids are noisy; scaling slices around a jittery centre would stack them like
    slightly offset rings, so the axis is Gaussian-smoothed along the leg (sigma ~2 cm)."""
    out = {}
    step = z_bins[1] - z_bins[0]
    for side in (1, -1):
        cx, cy = [], []
        for z0, z1 in zip(z_bins[:-1], z_bins[1:]):
            m = (co[:, 2] >= z0) & (co[:, 2] < z1) & (co[:, 0] * side > 0.0)
            if m.sum() < 8:
                cx.append(np.nan); cy.append(np.nan); continue
            # bounding-box centre is far less noisy than the vertex mean (uneven vertex density)
            cx.append(0.5 * (co[m, 0].min() + co[m, 0].max())); cy.append(0.5 * (co[m, 1].min() + co[m, 1].max()))
        cx = np.array(cx); cy = np.array(cy)
        idx = np.arange(len(cx)); ok = ~np.isnan(cx)
        cx = np.interp(idx, idx[ok], cx[ok]); cy = np.interp(idx, idx[ok], cy[ok])
        sig = sigma_m / step
        out[side] = (_gauss(cx, sig), _gauss(cy, sig))
    return out


def reshape_legs(body, thigh_slim=0.92, calf_slim=0.97, lengthen=1.035, crotch_z=0.76):
    """Slim thighs (tapering to no change at the knee), slightly slimmer calves, longer legs."""
    me = body.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    zb = np.linspace(0.0, 1.1, 221)
    axes = leg_axes(co, zb)
    zc = 0.5 * (zb[:-1] + zb[1:])
    knee_z = 0.47
    out = co.copy()
    for side in (1, -1):
        cx, cy = axes[side]
        m = co[:, 0] * side > 0.0
        z = co[m, 2]
        ax = np.interp(z, zc, cx); ay = np.interp(z, zc, cy)
        # radial scale profile along the leg
        s_th = 1.0 - (1.0 - thigh_slim) * smoothstep(knee_z + 0.03, knee_z + 0.16, z) * (1.0 - smoothstep(crotch_z - 0.02, crotch_z + 0.1, z))
        s_ca = 1.0 - (1.0 - calf_slim) * smoothstep(0.12, 0.25, z) * (1.0 - smoothstep(0.38, knee_z, z))
        s = s_th * s_ca
        # fade the effect out toward the body's midline at the crotch so the legs stay joined
        out[m, 0] = ax + (co[m, 0] - ax) * s
        out[m, 1] = ay + (co[m, 1] - ay) * s
    # lengthen legs below the hips (keeps the feet on the floor)
    z = out[:, 2]
    zz = np.where(z < crotch_z, z * lengthen, crotch_z * lengthen + (z - crotch_z))
    out[:, 2] = zz
    me.vertices.foreach_set('co', out.ravel())
    me.update()
    print('[body] reshaped legs: thigh x%.2f calf x%.2f length x%.3f' % (thigh_slim, calf_slim, lengthen))


def widen_upper_thigh(body, k=0.07, z0=0.56, z1=0.70, z2=0.78, z3=0.86):
    """The original's thighs are fuller at the top (measured: ~9% wider just under the hem)."""
    me = body.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    zb = np.linspace(0.0, 1.1, 221); zc = 0.5 * (zb[:-1] + zb[1:])
    axes = leg_axes(co, zb)
    for side in (1, -1):
        cx, cy = axes[side]
        m = co[:, 0] * side > 0.0
        z = co[m, 2]
        sc = 1.0 + k * smoothstep(z0, z1, z) * (1.0 - smoothstep(z2, z3, z))
        ax = np.interp(z, zc, cx); ay = np.interp(z, zc, cy)
        fade = smoothstep(0.0, 0.03, np.abs(co[m, 0]))
        sc = 1.0 + (sc - 1.0) * fade
        co[m, 0] = ax + (co[m, 0] - ax) * sc
        co[m, 1] = ay + (co[m, 1] - ay) * sc
    me.vertices.foreach_set('co', co.ravel()); me.update()
    print('[body] upper thigh x%.2f' % (1 + k))


def slim_hips(body, s=0.9, z0=0.74, z1=0.84):
    """Narrower pelvis like the original's slim model (the skirt then hangs close to the thighs)."""
    me = body.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    f = 1.0 - (1.0 - s) * smoothstep(z0, z1, co[:, 2])
    co[:, 0] *= f
    me.vertices.foreach_set('co', co.ravel()); me.update()
    print('[body] hips x%.2f above z=%.2f' % (s, z1))


def feet(body, rot_deg=9.0, scale=0.92, z0=0.10, z1=0.17):
    """Feet of the original: pointing straight ahead (no outward splay) and a little smaller.
    Rotates/scales each foot about the floor point under its ankle; blends out above the ankle."""
    me = body.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    for s in (1, -1):
        m = co[:, 0] * s > 0
        ring = m & (np.abs(co[:, 2] - z0) < 0.006)
        ax, ay = 0.5 * (co[ring, 0].min() + co[ring, 0].max()), 0.5 * (co[ring, 1].min() + co[ring, 1].max())
        w = m * (1.0 - smoothstep(z0, z1, co[:, 2]))
        th = -np.radians(rot_deg) * s * w         # toes of the +X foot splay toward +X: rotate them back to -Y
        x, y = co[:, 0] - ax, co[:, 1] - ay
        xr = x * np.cos(th) - y * np.sin(th); yr = x * np.sin(th) + y * np.cos(th)
        k = 1.0 - (1.0 - scale) * w
        co[:, 0] = np.where(m, ax + xr * k, co[:, 0]); co[:, 1] = np.where(m, ay + yr * k, co[:, 1])
        co[:, 2] = np.where(m, co[:, 2] * k + (1 - k) * 0.0, co[:, 2])
    me.vertices.foreach_set('co', co.ravel()); me.update()
    print('[body] feet: rotated %.0f deg inward, scale %.2f' % (rot_deg, scale))


def stance(body, D_knee=0.048, D_ankle=0.03, z_hip=0.82, z_knee=0.47, z_ankle=0.09):
    """Stance of the original model: knees almost touching, lower legs splaying out to the feet
    (an 'A' below the knee). Each leg is sheared toward the midline, pivoting at the hip;
    nothing moves at the body's midline (crotch)."""
    me = body.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    z = co[:, 2]
    thigh = np.clip((z_hip - z) / (z_hip - z_knee), 0.0, 1.0) * D_knee
    lower = D_knee + (D_ankle - D_knee) * np.clip((z_knee - z) / (z_knee - z_ankle), 0.0, 1.0)
    shift = np.where(z >= z_knee, thigh, lower)
    fade = smoothstep(0.0, 0.035, np.abs(co[:, 0]))
    co[:, 0] -= np.sign(co[:, 0]) * shift * fade
    me.vertices.foreach_set('co', co.ravel()); me.update()
    print('[body] stance: knees %.1f cm / ankles %.1f cm closer' % (D_knee * 100, D_ankle * 100))


def shade_smooth(ob):
    me = ob.data
    me.polygons.foreach_set('use_smooth', np.ones(len(me.polygons), bool))
    me.update()
