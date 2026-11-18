# SHEER — studio: lights, world/backdrop, floor, skirt, cameras, render settings.
import bpy, math
import numpy as np
from mathutils import Vector
from sheer_materials import NB


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def area_light(name, loc, target, size, size_y, energy, color):
    d = bpy.data.lights.new(name, 'AREA')
    d.shape = 'RECTANGLE'
    d.size = size; d.size_y = size_y
    d.energy = energy; d.color = color
    d.spread = math.radians(110)
    o = bpy.data.objects.new(name, d)
    o.location = loc
    bpy.context.scene.collection.objects.link(o)
    look_at(o, target)
    return o


def setup_lights():
    """Key softbox front-left; teal rim strip almost directly behind the hero leg (opposite the
    camera) so only the silhouette catches it; faint cool back-left kicker and front fill.
    Rims are light-linked to body/tights/skirt so they don't bounce teal off the floor."""
    L = {}
    L['key'] = area_light('key', (-0.6, -2.1, 1.35), (0.04, 0.0, 0.5), 1.3, 1.7, 50, (1.0, 0.95, 0.9))
    L['lowfill'] = area_light('lowfill', (-0.45, -1.6, 0.45), (0.0, 0.0, 0.22), 1.4, 0.6, 7.0, (1.0, 0.96, 0.93))   # even light down to the feet (like the original)
    L['rim'] = area_light('rim', (0.32, 1.5, 0.95), (0.10, 0.0, 0.74), 0.35, 0.45, 40, (0.10, 0.85, 0.95))   # upper-thigh teal edge only
    L['rim3'] = area_light('rim3', (0.12, 1.2, 0.12), (-0.08, 0.0, 0.08), 0.2, 0.25, 2.5, (0.30, 0.86, 0.95))  # faint teal on the right ankle/foot (VIEW02)
    L['rim2'] = area_light('rim2', (-0.35, 1.5, 0.75), (0.0, 0.0, 0.5), 0.25, 1.4, 0.0, (0.55, 0.75, 1.0))   # off: the original's left edges stay dark
    L['top'] = area_light('top', (-0.9, -1.3, 1.1), (0.0, 0.3, 0.0), 1.2, 1.2, 34, (0.93, 0.95, 1.0))   # overhead softbox: lights the floor cloth
    L['fill'] = area_light('fill', (1.5, -1.5, 0.45), (0.05, 0.0, 0.4), 1.0, 1.0, 5, (0.75, 0.85, 1.0))
    for n, sp in (('rim', 11), ('rim2', 28), ('rim3', 30), ('fill', 70), ('lowfill', 50)):
        L[n].data.spread = math.radians(sp)
    return L


def link_rims(objs):
    rcv = bpy.data.collections.new('rim_receivers')
    for o in objs:
        rcv.objects.link(o)
    for n in ('rim', 'rim2', 'rim3'):
        bpy.data.objects[n].light_linking.receiver_collection = rcv


def link_lowfill(objs):
    rcv = bpy.data.collections.new('lowfill_receivers')
    for o in objs:
        rcv.objects.link(o)
    bpy.data.objects['lowfill'].light_linking.receiver_collection = rcv


def link_key(objs):
    rcv = bpy.data.collections.new('key_receivers')
    for o in objs:
        rcv.objects.link(o)
    bpy.data.objects['key'].light_linking.receiver_collection = rcv


def link_top(floor):
    rcv = bpy.data.collections.new('top_receivers')
    rcv.objects.link(floor)
    bpy.data.objects['top'].light_linking.receiver_collection = rcv


def setup_world():
    w = bpy.data.worlds.new('studio')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    lp = nt.nodes.new('ShaderNodeLightPath')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Window'], sep.inputs[0])
    # backdrop seen by the camera: vertical blue-grey gradient with a soft central glow
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (0.16, 0.28, 0.44, 1)
    ramp.color_ramp.elements[1].position = 1.0; ramp.color_ramp.elements[1].color = (0.035, 0.06, 0.09, 1)
    e = ramp.color_ramp.elements.new(0.45); e.color = (0.09, 0.14, 0.19, 1)
    nt.links.new(sep.outputs[1], ramp.inputs[0])
    # radial falloff toward the frame edges
    v2 = nt.nodes.new('ShaderNodeVectorMath'); v2.operation = 'SUBTRACT'
    nt.links.new(tc.outputs['Window'], v2.inputs[0]); v2.inputs[1].default_value = (0.5, 0.5, 0.0)
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; nt.links.new(v2.outputs[0], ln.inputs[0])
    vig = nt.nodes.new('ShaderNodeMapRange'); vig.inputs['From Min'].default_value = 0.25; vig.inputs['From Max'].default_value = 0.85
    vig.inputs['To Min'].default_value = 1.0; vig.inputs['To Max'].default_value = 0.55
    nt.links.new(ln.outputs['Value'], vig.inputs['Value'])
    mulc = nt.nodes.new('ShaderNodeMix'); mulc.data_type = 'RGBA'; mulc.blend_type = 'MULTIPLY'
    mulc.inputs['Factor'].default_value = 1.0
    nt.links.new(ramp.outputs['Color'], mulc.inputs[6])
    comb = nt.nodes.new('ShaderNodeCombineColor'); nt.links.new(vig.outputs['Result'], comb.inputs[0]); nt.links.new(vig.outputs['Result'], comb.inputs[1]); nt.links.new(vig.outputs['Result'], comb.inputs[2])
    nt.links.new(comb.outputs[0], mulc.inputs[7])
    bg_cam = nt.nodes.new('ShaderNodeBackground'); nt.links.new(mulc.outputs[2], bg_cam.inputs['Color']); bg_cam.inputs['Strength'].default_value = 1.0
    # lighting environment for everything else: dim cool studio ambience, brighter from above
    grad = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Generated'], grad.inputs[0])
    envr = nt.nodes.new('ShaderNodeValToRGB')
    envr.color_ramp.elements[0].position = 0.35; envr.color_ramp.elements[0].color = (0.006, 0.007, 0.008, 1)
    envr.color_ramp.elements[1].position = 0.75; envr.color_ramp.elements[1].color = (0.018, 0.024, 0.03, 1)
    nt.links.new(grad.outputs[2], envr.inputs[0])
    bg_env = nt.nodes.new('ShaderNodeBackground'); nt.links.new(envr.outputs['Color'], bg_env.inputs['Color'])
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(bg_env.outputs[0], mix.inputs[1]); nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    return w


def add_floor(mat, size=3.2, n=260, seed=7):
    """White cotton drop cloth on the studio floor (what the original model stands on): flat under
    the feet, soft folds further away (mostly running left-right). Out of focus it reads as the
    bright misty floor of the original."""
    from mathutils import noise
    rng = np.random.default_rng(seed)
    xs = np.linspace(-size / 2, size / 2, n)
    ys = np.linspace(-size / 2, 0.95, n)                  # the cloth ends ~0.95 m behind the model
    X, Y = np.meshgrid(xs, ys, indexing='xy')
    Z = np.zeros_like(X)
    off = rng.uniform(-50, 50, 3)
    for i in range(n):
        for j in range(n):
            p = Vector((X[i, j] * 2.2 + off[0], Y[i, j] * 7.0 + off[1], off[2]))
            q = Vector((X[i, j] * 6.0 + off[1], Y[i, j] * 16.0 + off[0], off[2] + 3.0))
            r3 = Vector((X[i, j] * 14.0 + off[2], Y[i, j] * 30.0 + off[0], off[1] + 7.0))
            Z[i, j] = 0.6 * noise.noise(p) + 0.28 * noise.noise(q) + 0.12 * noise.noise(r3)
    feet = np.minimum(np.hypot((X - 0.09) / 0.07, (Y + 0.02) / 0.15), np.hypot((X + 0.09) / 0.07, (Y + 0.02) / 0.15))
    amp = 0.06 * np.clip((feet - 1.0) / 0.8, 0.0, 1.0) ** 0.9
    Z = 0.0005 + amp * np.maximum(Z, -0.15)                # folds rise from the floor, never below it
    Z = np.maximum(Z, 0.0)
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    faces = [(i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j) for i in range(n - 1) for j in range(n - 1)]
    me = bpy.data.meshes.new('floor')
    me.from_pydata(verts.tolist(), [], faces)
    me.polygons.foreach_set('use_smooth', np.ones(len(faces), bool))
    ob = bpy.data.objects.new('floor', me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    return ob


def build_skirt(body, mat, z_top=1.04, z_hem=0.695, n_pleats=26, per_pleat=24, n_rings=72, seed=3):
    """Pleated mini skirt (plain charcoal, knife pleats) fitted to the hip envelope: pleats are
    stitched flat at the hip and open toward a flared hem, each with a crisp fold edge."""
    rng = np.random.default_rng(seed)
    n_around = n_pleats * per_pleat
    me_b = body.data
    co = np.empty(len(me_b.vertices) * 3, np.float32); me_b.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    th_bins = np.linspace(-np.pi, np.pi, n_around + 1)
    zs = np.linspace(z_top, z_hem, n_rings)
    rad = np.zeros((n_rings, n_around), np.float32)
    ycs = np.zeros(n_rings, np.float32)
    for i, z in enumerate(zs):
        m = np.abs(co[:, 2] - z) < 0.012
        if m.sum() < 20:
            rad[i] = rad[i - 1]; ycs[i] = ycs[i - 1]; continue
        p = co[m]
        yc = p[:, 1].mean(); ycs[i] = yc
        th = np.arctan2(p[:, 1] - yc, p[:, 0]); r = np.hypot(p[:, 0], p[:, 1] - yc)
        idx = np.clip(np.digitize(th, th_bins) - 1, 0, n_around - 1)
        rr = np.zeros(n_around, np.float32)
        np.maximum.at(rr, idx, r)
        for k in range(n_around):
            if rr[k] == 0:
                rr[k] = rr[k - 1]
        rr = np.convolve(np.concatenate([rr[-30:], rr, rr[:30]]), np.ones(61) / 61, mode='valid')
        rad[i] = rr
    env = np.maximum.accumulate(rad, axis=0)   # a skirt hangs: never narrower than anything above it
    yc0 = ycs[:8].mean()
    th_c = 0.5 * (th_bins[:-1] + th_bins[1:])
    ph0 = rng.uniform(0, 1)
    wob = rng.uniform(0, 2 * np.pi, 3)
    verts = []
    for i, z in enumerate(zs):
        t = i / (n_rings - 1)
        flare = 0.0 if t < 0.3 else 0.02 * ((t - 0.3) / 0.7) ** 1.25
        depth = 0.002 + 0.014 * min(1.0, max(0.0, (t - 0.12) / 0.88)) ** 1.1
        ph = (th_c * n_pleats / (2 * np.pi) + ph0) % 1.0
        saw = np.where(ph < 0.86, ph / 0.86, (1.0 - ph) / 0.14)        # knife pleat: long face, sharp return
        r = env[i] + 0.004 + flare + depth * (saw - 0.5)
        r = r * (1.0 + 0.012 * t * np.sin(3 * th_c + wob[0]))           # pleats never hang perfectly evenly
        for k in range(n_around):
            zz = z
            if i == n_rings - 1:
                zz = z + 0.004 * np.sin(2 * th_c[k] + wob[1]) + 0.0025 * np.sin(5 * th_c[k] + wob[2])
            verts.append((float(r[k] * np.cos(th_c[k])), float(yc0 + r[k] * np.sin(th_c[k])), float(zz)))
    faces = []
    for i in range(n_rings - 1):
        for k in range(n_around):
            a = i * n_around + k; b2 = i * n_around + (k + 1) % n_around
            faces.append((a, b2, b2 + n_around, a + n_around))
    me = bpy.data.meshes.new('skirt')
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set('use_smooth', np.ones(len(faces), bool))
    ob = bpy.data.objects.new('skirt', me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    sol = ob.modifiers.new('solid', 'SOLIDIFY'); sol.thickness = 0.0018; sol.offset = 1.0; sol.use_even_offset = True
    sub = ob.modifiers.new('subd', 'SUBSURF'); sub.levels = 1; sub.render_levels = 2
    return ob


def add_camera(name, pos, target, lens=85, fstop=4.0, focus_at=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_fit = 'VERTICAL'; cd.sensor_height = 36.0; cd.sensor_width = 36.0
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = fstop
    ob = bpy.data.objects.new(name, cd)
    ob.location = pos
    bpy.context.scene.collection.objects.link(ob)
    look_at(ob, target)
    cd.dof.focus_distance = (Vector(target) - Vector(pos)).length
    # focus on the hero leg's front surface (not its axis): the 0.8 mm knit must stay sharp
    dg = bpy.context.evaluated_depsgraph_get()
    ft = Vector(focus_at) if focus_at is not None else Vector(target)
    hit, loc, nrm, idx, hob, mtx = bpy.context.scene.ray_cast(dg, Vector(pos), (ft - Vector(pos)).normalized())
    if hit and hob is not None and hob.name in ('tights', 'body'):
        cd.dof.focus_distance = (loc - Vector(pos)).length
    print('[camera] %s focus %.3f m' % (name, cd.dof.focus_distance))
    return ob


def setup_cameras():
    v1 = add_camera('VIEW01', (0.0843, -1.2612, 0.4868), (0.0955, 0.0, 0.5638), lens=87.4, fstop=8.0)   # fitted to the original's silhouettes
    v2 = add_camera('VIEW02', (-0.0548, -1.1081, 0.1905), (-0.0430, 0.0, 0.1797), lens=85.2, fstop=11.0, focus_at=(-0.043, 0.0, 0.28))  # (fit_cameras.py, lowered 5.2 cm: whole foot in frame)
    bpy.context.scene.camera = v1
    return v1, v2


def setup_render(scene, res=(1080, 1890), samples=256, percent=100):
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == 'OPTIX')
    c = scene.cycles
    c.device = 'GPU'
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.02
    c.use_denoising = False   # the AI denoiser erases the knit courses and the pin-point glints
    c.denoiser = 'OPENIMAGEDENOISE'
    try:
        c.denoising_use_gpu = True
    except Exception:
        pass
    c.max_bounces = 8
    c.diffuse_bounces = 2
    c.glossy_bounces = 2
    c.transmission_bounces = 6
    c.transparent_max_bounces = 24
    c.volume_bounces = 0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 0.6
    c.sample_clamp_indirect = 6.0
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = percent
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Punchy'
    except Exception:
        pass
    scene.view_settings.exposure = 0.3
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '8'
