# SHEER — export the scene's game assets for the Unity (HDRP) real-time simulator.
# Usage: blender -b scene.blend -P export_unity.py -- <out_dir>
# Writes FBX meshes (body, tights, skirt base mesh for real-time cloth, floor), the knit weave map (EXR),
# and sheer_scene.json (cameras, lights, inspector values, session replay data). Tights per-vertex data
# is packed into UV channels: UV0 = (u around, v height) 'tuv'; UV1 = (static stretch, toe pocket);
# UV2 = (toe seam distance, leg side). Coordinates in the JSON are Blender's (Z up, metres).
import bpy, sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheer_params as SPRM
import sheer_story as STY

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)


def attr(me, name):
    a = me.attributes[name]
    v = np.empty(len(a.data), np.float32); a.data.foreach_get('value', v)
    return v


def add_uv(me, name, a, b):
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
    uv = me.uv_layers.get(name) or me.uv_layers.new(name=name)
    uv.data.foreach_set('uv', np.stack([a[lv], b[lv]], 1).astype(np.float32).ravel())


t = bpy.data.objects['tights']; me = t.data
for l in [l for l in me.uv_layers if l.name != 'tuv']:
    me.uv_layers.remove(l)          # weave/tear UVs must be channel 0
add_uv(me, 'uv_pre_toe', attr(me, 'prestretch'), attr(me, 'toe'))
add_uv(me, 'uv_seam_side', attr(me, 'toeseam'), attr(me, 'legside'))
me.uv_layers['tuv'].active = True
if me.uv_layers[0].name != 'tuv':
    print('[export] WARNING first UV layer is', me.uv_layers[0].name)


def export(name, modifiers=True):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob = bpy.data.objects[name]
    ob.hide_set(False); ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    fp = os.path.join(out, name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=fp, use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Z', axis_up='Y', use_mesh_modifiers=modifiers, mesh_smooth_type='OFF',
                             add_leaf_bones=False, bake_anim=False, use_custom_props=False, path_mode='STRIP')
    print('[export] %s -> %s (%.1f MB)' % (name, fp, os.path.getsize(fp) / 1e6))


for name, mods in (('body', True), ('tights', True), ('skirt', False), ('floor', True)):
    export(name, mods)

# ------------------------------------------------------------------------------------------ .smesh
# Exact binary meshes for the real-time build (float32, Unity axes, no importer conversions):
#   Unity (x, y, z) = Blender (x, z, y); the swap mirrors handedness, so triangle winding is reversed
#   and the tangent's bitangent sign is negated. Vertices are split where a UV map is discontinuous
#   (seams); channel 'src' keeps the original vertex index so the simulation can weld them.
# Layout: b'SMSH', u32 version, u32 nverts, u32 nsub, per sub (u32 count, u32 idx[count]),
#         u32 nchan, per channel (16-byte name, u8 type 0=f32 1=u32, u8 dim, u16 pad, data[nverts*dim]).
import struct


def to_unity(a):
    a = np.asarray(a, np.float32)
    return np.stack([a[:, 0], a[:, 2], a[:, 1]], 1)


def write_smesh(path, nverts, subs, channels):
    with open(path, 'wb') as f:
        f.write(b'SMSH'); f.write(struct.pack('<III', 1, nverts, len(subs)))
        for idx in subs:
            idx = np.ascontiguousarray(idx, np.uint32)
            f.write(struct.pack('<I', len(idx))); f.write(idx.tobytes())
        f.write(struct.pack('<I', len(channels)))
        for name, arr in channels:
            arr = np.ascontiguousarray(arr)
            dim = 1 if arr.ndim == 1 else arr.shape[1]
            typ = 1 if arr.dtype == np.uint32 else 0
            if typ == 0:
                arr = arr.astype(np.float32)
            assert len(arr) == nverts, (name, len(arr), nverts)
            f.write(name.encode().ljust(16, b'\0')); f.write(struct.pack('<BBH', typ, dim, 0)); f.write(arr.tobytes())
    print('[export] %s: %d verts, %s tris, %d channels (%.1f MB)' % (os.path.basename(path), nverts,
          '+'.join(str(len(s_) // 3) for s_ in subs), len(channels), os.path.getsize(path) / 1e6))


def smesh_object(name, path, uvname=None, use_mods=False, pos_attr=None, nrm_attr=None, extra=None, planar_uv=False):
    ob = bpy.data.objects[name]
    if use_mods:
        dg = bpy.context.evaluated_depsgraph_get()
        me = ob.evaluated_get(dg).to_mesh()
    else:
        me = ob.data
    me.calc_loop_triangles()
    nv, nl = len(me.vertices), len(me.loops)
    lv = np.empty(nl, np.int32); me.loops.foreach_get('vertex_index', lv)
    if pos_attr:
        P = np.empty(nv * 3, np.float32); me.attributes[pos_attr].data.foreach_get('vector', P); P = P.reshape(-1, 3)
    else:
        P = np.empty(nv * 3, np.float32); me.vertices.foreach_get('co', P); P = P.reshape(-1, 3)
    if nrm_attr:
        N = np.empty(nv * 3, np.float32); me.attributes[nrm_attr].data.foreach_get('vector', N); N = N.reshape(-1, 3)
    else:
        N = np.empty(nv * 3, np.float32); me.vertices.foreach_get('normal', N); N = N.reshape(-1, 3)
    if planar_uv:
        luv = P[lv][:, :2].copy()
    elif uvname:
        luv = np.empty(nl * 2, np.float32); me.uv_layers[uvname].data.foreach_get('uv', luv); luv = luv.reshape(-1, 2)
    else:
        luv = np.zeros((nl, 2), np.float32)
    # faces whose u wraps around (0.99 -> 0.01 inside one face): unwrap them (textures use REPEAT)
    if uvname and not planar_uv:
        me.calc_loop_triangles()
        tl_ = np.empty(len(me.loop_triangles) * 3, np.int32); me.loop_triangles.foreach_get('loops', tl_); tl_ = tl_.reshape(-1, 3)
        uu = luv[tl_, 0]
        wrap = (uu.max(1) - uu.min(1)) > 0.5
        fix = np.unique(tl_[wrap][uu[wrap] < 0.5])
        luv[fix, 0] += 1.0
        if len(fix):
            print('[export] %s: unwrapped %d loops of %d wrapping triangles' % (name, len(fix), int(wrap.sum())))
    # split where the UV is discontinuous
    q = np.round(luv * 2.0e5).astype(np.int64)
    key = np.stack([lv.astype(np.int64), q[:, 0], q[:, 1]], 1)
    uniq, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    src = lv[first].astype(np.uint32)
    n = len(first)
    # triangles (split-vertex indices, Blender winding)
    nt = len(me.loop_triangles)
    tl = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get('loops', tl); tl = tl.reshape(-1, 3)
    tm = np.empty(nt, np.int32); me.loop_triangles.foreach_get('material_index', tm)
    tri0 = inv[tl]
    # tangents from the UV map (works on n-gons too): per-triangle dP/du, dP/dv accumulated per vertex
    Pv = P[src].astype(np.float64); Nv = N[src].astype(np.float64); UVv = luv[first].astype(np.float64)
    if uvname or planar_uv:
        a, b_, c = tri0[:, 0], tri0[:, 1], tri0[:, 2]
        e1, e2 = Pv[b_] - Pv[a], Pv[c] - Pv[a]
        d1, d2 = UVv[b_] - UVv[a], UVv[c] - UVv[a]
        det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        ok = np.abs(det) > 1e-14
        r = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)[:, None]
        ft = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r
        fb = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
        T = np.zeros((n, 3)); Bt = np.zeros((n, 3))
        for k in range(3):
            np.add.at(T, tri0[:, k], ft); np.add.at(Bt, tri0[:, k], fb)
    else:
        T = np.tile([1.0, 0.0, 0.0], (n, 1)); Bt = np.tile([0.0, 1.0, 0.0], (n, 1))
    T = T - Nv * np.einsum('ij,ij->i', T, Nv)[:, None]              # Gram-Schmidt against the normal
    bad = np.linalg.norm(T, axis=1) < 1e-12
    T[bad] = np.cross(Nv[bad], [0.0, 0.0, 1.0]) + 1e-9
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    sign = np.where(np.einsum('ij,ij->i', np.cross(Nv, T), Bt) >= 0, 1.0, -1.0)
    # triangles grouped by material slot, winding reversed for Unity
    tri = tri0[:, [0, 2, 1]]
    du = UVv[tri0][:, :, 0].max(1) - UVv[tri0][:, :, 0].min(1)
    print('[export] %s: %d triangles span > 0.5 in u (UV wrap problems)' % (name, int((du > 0.5).sum())))
    nsub = max(1, len(me.materials))
    subs = [tri[tm == k].ravel() for k in range(nsub)]
    chans = [('position', to_unity(P[src])), ('normal', to_unity(N[src])),
             ('tangent', np.concatenate([to_unity(T), (-sign)[:, None]], 1)),
             ('uv0', luv[first]), ('src', src)]
    if extra:
        ex = dict(extra(me, src, luv[first]))
        chans = [(k, ex.pop(k, v)) for k, v in chans] + list(ex.items())     # extra overrides same-named channels
    write_smesh(path, n, subs, chans)
    if use_mods:
        ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    return n


def point_attr(me, name, dim=1):
    a = me.attributes[name]
    v = np.empty(len(a.data) * dim, np.float32)
    a.data.foreach_get('vector' if dim == 3 else 'value', v)
    return v.reshape(-1, dim) if dim > 1 else v


def tights_extra(me, src, uv):
    pre = point_attr(me, 'prestretch')[src]; cap = point_attr(me, 'capfade')[src]
    rest = to_unity(point_attr(me, 'rest', 3)[src]); seam = point_attr(me, 'toeseam')[src]
    side = point_attr(me, 'legside')[src]; toe = point_attr(me, 'toe')[src]
    return [('uv0', np.concatenate([uv, pre[:, None], cap[:, None]], 1)),
            ('uv1', np.concatenate([rest, seam[:, None]], 1)),
            ('uv2', np.stack([side, toe], 1))]


smesh_dir = os.path.join(out, 'StreamingAssets'); os.makedirs(smesh_dir, exist_ok=True)
tm_ = bpy.data.objects['tights'].data
print('[export] tights material slots:', [m.name for m in tm_.materials])
smesh_object('tights', os.path.join(smesh_dir, 'tights.smesh'), uvname='tuv', pos_attr='rest', nrm_attr='rest_n', extra=tights_extra)
def rest_extra(me, src, uv):
    # rest position (Unity axes) for procedural textures that must stick to deforming skin/cloth
    P = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', P)
    return [('uv1', to_unity(P.reshape(-1, 3)[src]))]


smesh_object('body', os.path.join(smesh_dir, 'body.smesh'), uvname='UVMap', extra=rest_extra)
def skirt_extra(me, src, uv):
    # cloth pin weight (vertex group 'pin': waistband held by the body) -> uv2.x
    ob = bpy.data.objects['skirt']
    w = np.zeros(len(me.vertices), np.float32)
    vg = ob.vertex_groups.get('pin')
    if vg is not None:
        for v in me.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    w[v.index] = g.weight
    print('[export] skirt pin group:', 'missing' if vg is None else '%d pinned verts' % int((w > 0.5).sum()))
    return rest_extra(me, src, uv) + [('uv2', np.stack([w[src], np.zeros(len(src), np.float32)], 1))]


smesh_object('skirt', os.path.join(smesh_dir, 'skirt_base.smesh'), uvname='UVMap', use_mods=False, extra=skirt_extra)
smesh_object('skirt', os.path.join(smesh_dir, 'skirt_render.smesh'), uvname='UVMap', use_mods=True, extra=rest_extra)
smesh_object('skirt_proxy', os.path.join(smesh_dir, 'collider_proxy.smesh'))
smesh_object('floor', os.path.join(smesh_dir, 'floor.smesh'), planar_uv=True)

# weave map (RGB tangent normal, A coverage) as float EXR
knit = bpy.data.images.get('knit')
if knit:
    knit.filepath_raw = os.path.join(out, 'knit_weave.exr'); knit.file_format = 'OPEN_EXR'
    knit.save()
    print('[export] knit_weave.exr')

sc = bpy.context.scene
cams = {}
for n in ('VIEW01', 'VIEW02'):
    c = bpy.data.objects[n]
    cams[n] = dict(location=list(c.location), rotation_euler=list(c.rotation_euler), lens=c.data.lens,
                   sensor_height=c.data.sensor_height, fstop=c.data.dof.aperture_fstop, focus=c.data.dof.focus_distance)
lights = {}
for o in bpy.data.objects:
    if o.type == 'LIGHT':
        d = o.data
        lights[o.name] = dict(type=d.type, location=list(o.location), rotation_euler=list(o.rotation_euler), energy_w=d.energy,
                              color=list(d.color), size=getattr(d, 'size', 0.0), size_y=getattr(d, 'size_y', 0.0),
                              spread_deg=float(np.degrees(getattr(d, 'spread', 0.0))),
                              receivers=[x.name for x in (o.light_linking.receiver_collection.objects if o.light_linking.receiver_collection else [])])
data = dict(
    units='metres, Blender axes (Z up, -Y toward the camera)',
    cameras=cams, lights=lights,
    inspector=SPRM.defaults(), inspector_sections=[(zh, en, [f[:2] for f in fs]) for zh, en, fs in SPRM.SECTIONS],
    shading=json.loads(sc.get('tights_params', '{}')),
    story=dict(duration=STY.DURATION, view_switch=STY.VIEW_SWITCH, presses=STY.PRESSES, pre_cursor=STY.PRE_CURSOR,
               cam_moves=STY.CAM_MOVES, wind_gusts=STY.WIND_GUSTS),
    replay_views={'VIEW01': ((0.0843, -1.2612, 0.4868), (0.0955, 0.0, 0.5638), 87.4),
                  'VIEW02': ((-0.0548, -1.1081, 0.1905), (-0.0430, 0.0, 0.1797), 85.2)},
    tights_uv_channels={'UV0': 'tuv (u around 0..1, v = height m)', 'UV1': '(static stretch, toe pocket)',
                        'UV2': '(toe seam signed distance m, leg side +1/-1)'},
)
json.dump(data, open(os.path.join(out, 'sheer_scene.json'), 'w'), indent=1)
print('[export] sheer_scene.json')
