# SHEER — Cycles materials (node graphs built in code): skin, tights (damage-aware), skirt, floor.
import bpy
import numpy as np

DMG_RANGE = 0.012  # damage SDF encode range (+-12 mm)


class NB:
    """Tiny node-graph builder."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, typ, **kw):
        nd = self.nt.nodes.new(typ)
        nd.location = (self.x, 0)
        self.x += 10
        for k, v in kw.items():
            if k.startswith('in_'):
                continue
            setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.nt.links.new(a, b)

    def _set(self, sock, val):
        if hasattr(val, 'is_output') or hasattr(val, 'links'):
            self.link(val, sock)
        else:
            sock.default_value = val

    def math(self, op, a, b=None, c=None, clamp=False):
        nd = self.n('ShaderNodeMath', operation=op, use_clamp=clamp)
        self._set(nd.inputs[0], a)
        if b is not None:
            self._set(nd.inputs[1], b)
        if c is not None:
            self._set(nd.inputs[2], c)
        return nd.outputs[0]

    def add(self, a, b): return self.math('ADD', a, b)
    def sub(self, a, b): return self.math('SUBTRACT', a, b)
    def mul(self, a, b): return self.math('MULTIPLY', a, b)
    def div(self, a, b): return self.math('DIVIDE', a, b)
    def mx(self, a, b): return self.math('MAXIMUM', a, b)
    def mn(self, a, b): return self.math('MINIMUM', a, b)
    def pw(self, a, b): return self.math('POWER', a, b)

    def mad(self, a, b, c): return self.math('MULTIPLY_ADD', a, b, c)

    def smooth(self, e0, e1, x):
        """smoothstep(e0, e1, x) via Map Range (handles e0 > e1)."""
        nd = self.n('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        self._set(nd.inputs['Value'], x)
        if e0 <= e1:
            nd.inputs['From Min'].default_value = e0; nd.inputs['From Max'].default_value = e1
            nd.inputs['To Min'].default_value = 0.0; nd.inputs['To Max'].default_value = 1.0
        else:
            nd.inputs['From Min'].default_value = e1; nd.inputs['From Max'].default_value = e0
            nd.inputs['To Min'].default_value = 1.0; nd.inputs['To Max'].default_value = 0.0
        return nd.outputs['Result']

    def lerp(self, a, b, t):
        nd = self.n('ShaderNodeMix', data_type='FLOAT', clamp_factor=True)
        self._set(nd.inputs['Factor'], t)
        self._set(nd.inputs[2], a)  # A (float)
        self._set(nd.inputs[3], b)  # B (float)
        return nd.outputs[0]

    def lerp_col(self, a, b, t):
        nd = self.n('ShaderNodeMix', data_type='RGBA', clamp_factor=True)
        self._set(nd.inputs['Factor'], t)
        self._set(nd.inputs[6], a)
        self._set(nd.inputs[7], b)
        return nd.outputs[2]

    def attr(self, name, kind='GEOMETRY'):
        nd = self.n('ShaderNodeAttribute', attribute_type=kind, attribute_name=name)
        return nd

    def sep(self, vec):
        nd = self.n('ShaderNodeSeparateXYZ')
        self._set(nd.inputs[0], vec)
        return nd.outputs

    def vmath(self, op, a, b=None, scale=None):
        nd = self.n('ShaderNodeVectorMath', operation=op)
        self._set(nd.inputs[0], a)
        if b is not None:
            self._set(nd.inputs[1], b)
        if scale is not None:
            self._set(nd.inputs['Scale'], scale)
        return nd

    def combine(self, x, y, z=0.0):
        nd = self.n('ShaderNodeCombineXYZ')
        self._set(nd.inputs[0], x); self._set(nd.inputs[1], y); self._set(nd.inputs[2], z)
        return nd.outputs[0]


# ------------------------------------------------------------------------------------------- images
def knit_image(size=1536, loops=40, rows=30):
    """Weave map like the original: a fine grid of yarn 'ropes' — continuous horizontal courses
    (rounded thread profile, thin dark gaps) crossed by faint wales. Tileable.
    RGB = tangent-space normal, A = yarn coverage."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    gy = yy / (size / rows); gx = xx / (size / loops)
    # courses: slight per-course wobble so the lines are not ruler-straight
    k = np.floor(gy)
    wob = 0.06 * np.sin(2 * np.pi * (gx / loops) * 3 + k * 1.7)
    fy = gy + wob - np.floor(gy + wob) - 0.5
    course = np.clip(1.0 - (np.abs(fy) / 0.5) ** 2.2, 0.0, 1.0) ** 0.6     # rounded thread
    fx = gx - np.floor(gx) - 0.5
    wale = 0.5 + 0.5 * np.cos(2 * np.pi * fx)                              # faint crossing threads
    h = (0.85 * course + 0.15 * course * wale).astype(np.float32)
    cov = np.clip(0.55 + 0.45 * course * (0.85 + 0.15 * wale), 0.0, 1.0).astype(np.float32)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 2.2
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 2.2
    nx, ny, nz = -dx, -dy, np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    img = np.stack([nx / l * 0.5 + 0.5, ny / l * 0.5 + 0.5, nz / l * 0.5 + 0.5, cov], -1).astype(np.float32)
    im = bpy.data.images.new('knit', size, size, alpha=True, float_buffer=True)
    im.colorspace_settings.name = 'Non-Color'
    im.alpha_mode = 'CHANNEL_PACKED'
    im.pixels.foreach_set(img.ravel())
    im.pack()
    return im, float(cov.mean())


def damage_image(name, w=1024, h=2048):
    im = bpy.data.images.new(name, w, h, alpha=True, float_buffer=True)
    im.colorspace_settings.name = 'Non-Color'
    im.alpha_mode = 'CHANNEL_PACKED'
    px = np.zeros((h, w, 4), np.float32)
    px[..., 0] = 1.0; px[..., 1] = 1.0; px[..., 2] = 0.0; px[..., 3] = 1.0
    im.pixels.foreach_set(px.ravel())
    im.update()
    return im


# --------------------------------------------------------------------------------------------- skin
def make_skin(color=(0.95, 0.46, 0.38)):
    mat = bpy.data.materials.new('skin')
    b = NB(mat)
    out = b.n('ShaderNodeOutputMaterial')
    bsdf = b.n('ShaderNodeBsdfPrincipled', subsurface_method='RANDOM_WALK_SKIN')
    tc = b.n('ShaderNodeTexCoord')
    # colour variation (blotchy + fine), slightly rosier knees/heels
    n1 = b.n('ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = 18; n1.inputs['Detail'].default_value = 4
    b.link(tc.outputs['Object'], n1.inputs['Vector'])
    n2 = b.n('ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = 260; n2.inputs['Detail'].default_value = 2
    b.link(tc.outputs['Object'], n2.inputs['Vector'])
    base = b.lerp_col(color + (1,), (color[0] * 1.04, color[1] * 0.9, color[2] * 0.88, 1), b.mul(n1.outputs['Fac'], 1.0))
    base2 = b.lerp_col(base, (color[0] * 0.96, color[1] * 0.93, color[2] * 0.93, 1), b.mul(b.sub(n2.outputs['Fac'], 0.35), 0.6))
    sxz = b.sep(tc.outputs['Object'])
    knee = b.mul(b.smooth(0.42, 0.47, sxz[2]), b.smooth(0.58, 0.52, sxz[2]))
    front = b.smooth(-0.02, -0.06, sxz[1])
    rosy = b.mul(b.mul(knee, front), 0.6)
    base3 = b.lerp_col(base2, (color[0] * 1.02, color[1] * 0.78, color[2] * 0.76, 1), rosy)
    b.link(base3, bsdf.inputs['Base Color'])
    bsdf.inputs['Subsurface Weight'].default_value = 1.0
    bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.3, 0.18)
    bsdf.inputs['Subsurface Scale'].default_value = 0.0035
    bsdf.inputs['Subsurface IOR'].default_value = 1.4
    bsdf.inputs['Subsurface Anisotropy'].default_value = 0.8
    rough = b.lerp(0.36, 0.52, n2.outputs['Fac'])
    b.link(rough, bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.5
    bsdf.inputs['Coat Weight'].default_value = 0.08
    bsdf.inputs['Coat Roughness'].default_value = 0.35
    # pores / micro relief
    vor = b.n('ShaderNodeTexVoronoi', feature='F1'); vor.inputs['Scale'].default_value = 1400
    b.link(tc.outputs['Object'], vor.inputs['Vector'])
    n3 = b.n('ShaderNodeTexNoise'); n3.inputs['Scale'].default_value = 700; n3.inputs['Detail'].default_value = 3
    b.link(tc.outputs['Object'], n3.inputs['Vector'])
    hgt = b.add(b.mul(vor.outputs['Distance'], 0.6), b.mul(n3.outputs['Fac'], 0.4))
    bump = b.n('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.25; bump.inputs['Distance'].default_value = 0.0004
    b.link(hgt, bump.inputs['Height'])
    b.link(bump.outputs['Normal'], bsdf.inputs['Normal'])
    b.link(bsdf.outputs[0], out.inputs['Surface'])
    return mat


# -------------------------------------------------------------------------------------------- tights
def make_tights(name, dmg_img, knit_img, knit_mean, P):
    """P: parameter dict (same names as the original Unity inspector, see config)."""
    mat = bpy.data.materials.new(name)
    mat.blend_method = 'HASHED'
    b = NB(mat)
    out = b.n('ShaderNodeOutputMaterial')
    uvn = b.n('ShaderNodeUVMap', uv_map='tuv')
    uv = b.sep(uvn.outputs['UV'])
    U, Vz = uv[0], uv[1]          # u around (0..1), v = rest height (m)
    geo = b.n('ShaderNodeNewGeometry')
    tc = b.n('ShaderNodeTexCoord')
    rest = b.attr('rest')
    stretch = b.attr('stretch').outputs['Fac']
    pre = b.attr('prestretch').outputs['Fac']
    lift = b.attr('lift').outputs['Fac']

    # ---- damage field
    tex = b.n('ShaderNodeTexImage', image=dmg_img, interpolation='Linear', extension='REPEAT')
    b.link(uvn.outputs['UV'], tex.inputs['Vector'])
    sc = b.n('ShaderNodeSeparateColor'); b.link(tex.outputs['Color'], sc.inputs['Color'])
    holeSD = b.mul(b.sub(sc.outputs[0], 0.5), 2 * DMG_RANGE)
    runSD = b.mul(b.sub(sc.outputs[1], 0.5), 2 * DMG_RANGE)
    age = sc.outputs[2]
    bag = b.sub(1.0, tex.outputs['Alpha'])
    # ragged edges: 3D noise in rest space (sticks to the fabric)
    nz = b.n('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 650; nz.inputs['Detail'].default_value = 3; nz.inputs['Roughness'].default_value = 0.6
    b.link(rest.outputs['Vector'], nz.inputs['Vector'])
    nzc = b.n('ShaderNodeTexNoise'); nzc.inputs['Scale'].default_value = 140; nzc.inputs['Detail'].default_value = 2
    b.link(rest.outputs['Vector'], nzc.inputs['Vector'])
    holeSD = b.add(holeSD, b.add(b.mul(b.sub(nz.outputs['Fac'], 0.5), 0.0007), b.mul(b.sub(nzc.outputs['Fac'], 0.5), 0.0012)))
    runSD = b.add(runSD, b.mul(b.sub(nz.outputs['Fac'], 0.5), 0.0008))

    # ---- course ("rung") coordinate along the leg
    rc = b.add(b.div(Vz, P['rung_spacing']), b.mul(b.sub(nzc.outputs['Fac'], 0.5), 0.8))
    rk = b.math('FLOOR', rc)
    rf = b.math('ABSOLUTE', b.sub(b.math('FRACT', rc), 0.5))
    wn = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='1D'); b.link(rk, wn.inputs['W'])
    rh = wn.outputs['Value']
    wn2 = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='1D'); b.link(b.mul(rk, 3.71), wn2.inputs['W'])
    wn3 = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='1D'); b.link(b.add(b.mul(rk, 7.13), 0.7), wn3.inputs['W'])
    wn4 = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='1D'); b.link(b.add(b.mul(rk, 5.31), 9.2), wn4.inputs['W'])
    line = b.smooth(0.26, 0.15, rf)        # thread cross-section (1 at the line centre)
    thin = b.smooth(0.12, 0.06, rf)

    inRun = b.smooth(0.002, -0.002, runSD)                      # ladder fades into intact knit
    runOpen = b.smooth(0.3, 0.8, age)
    sparse = b.math('LESS_THAN', wn2.outputs['Value'], b.lerp(0.16, 1.0, runOpen))
    rung = b.mul(b.mul(line, sparse), b.math('GREATER_THAN', rh, 0.06))
    edgeIn = b.smooth(0.0, 0.008, b.mul(runSD, -1.0))            # soft-edged ladder band
    inHole = b.smooth(0.0002, -0.0002, holeSD)

    # ---- coverage
    bw = P.get('boundary_width_m', 0.0448)                      # 'Frost Boundary Width (px)'
    footMask = b.smooth(0.0775 + bw / 2, 0.0775 - bw / 2, Vz)
    # Unity's coverage is a single alpha-blend; a path tracer attenuates skin light twice (in & out
    # through the knit), so convert to the equivalent physical yarn coverage.
    phys = lambda c: c                                         # light-shadowed nylon: coverage = 'Frost Coverage'
    phys_foot = lambda c: 0.84 * c                               # reinforced but sheer enough for the toes to glow through
    cov0 = b.lerp(phys(P['frost_body']), phys_foot(P['frost_foot']), footMask)

    # total stretch = static (tube over the leg's girth & bulges, baked) x dynamic (pulls): drives 'Frost Clear At Stretch'
    # static fit on the leg (simulated tension, median 1) opens the knit gently; pulls open it steeply
    area = b.mx(stretch, 0.4)
    cov = b.div(cov0, b.mul(b.pw(b.mx(pre, 0.4), 0.8 * P['frost_clear']), b.pw(area, 1.5 * P['frost_clear'])))
    # knit micro coverage
    mp = b.n('ShaderNodeMapping', vector_type='POINT')
    b.link(uvn.outputs['UV'], mp.inputs['Vector'])
    # 'Weave Tiling' = weave-map tiles around the leg (30 courses per tile -> ~0.75 mm courses);
    # tiles are square at the calf in physical size
    mp.inputs['Scale'].default_value = (P['weave_tiling'], P['weave_tiling'] * 3.72, 1.0)
    wq = b.n('ShaderNodeTexNoise'); wq.inputs['Scale'].default_value = 1.6; wq.inputs['Detail'].default_value = 3
    wq.inputs['Roughness'].default_value = 0.6
    b.link(mp.outputs['Vector'], wq.inputs['Vector'])
    wqc = b.sep(wq.outputs['Color'])
    kuv = b.combine(b.add(b.sep(mp.outputs['Vector'])[0], b.mul(b.sub(wqc[0], 0.5), 0.045)),
                    b.add(b.sep(mp.outputs['Vector'])[1], b.mul(b.sub(wqc[1], 0.5), 0.06)))
    ktex = b.n('ShaderNodeTexImage', image=knit_img, interpolation='Cubic', extension='REPEAT')
    b.link(kuv, ktex.inputs['Vector'])
    yv = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='2D')     # per-loop yarn thickness variation
    b.link(b.combine(b.math('FLOOR', b.mul(b.sep(kuv)[0], 40.0)), b.math('FLOOR', b.mul(b.sep(kuv)[1], 30.0))), yv.inputs['Vector'])
    camd0 = b.n('ShaderNodeCameraData')
    near0 = b.smooth(1.1, 0.35, camd0.outputs['View Distance'])
    near0 = b.smooth(3.5, 2.2, camd0.outputs['View Distance'])   # only far-away (sub-pixel) knit fades out
    kvar = b.add(b.sub(ktex.outputs['Alpha'], knit_mean), b.mul(b.sub(yv.outputs['Value'], 0.5), 0.35))
    cov = b.math('ADD', cov, b.mul(b.mul(kvar, P['weave_contrast'] * 12.0), near0), clamp=True)
    pull = b.mul(b.smooth(P['pull_edge'], 0.0, holeSD), b.sub(1.0, inHole))
    cov = b.mul(cov, b.sub(1.0, b.mul(bag, 0.45)))
    cov = b.mul(cov, b.sub(1.0, b.mul(pull, 0.5)))              # stretched, thinner halo around holes
    # threads pulled concentrically around each hole (iso-lines of the hole distance field)
    ringf = b.add(0.5, b.mul(b.math('COSINE', b.mul(holeSD, 6.2831853 / 0.00065)), 0.5))
    ringBand = b.mul(b.smooth(0.0, 0.0003, holeSD), b.smooth(0.0045, 0.0015, holeSD))
    rings = b.mul(ringBand, b.smooth(0.6, 0.92, ringf))
    cov = b.lerp(cov, b.mul(cov, 0.8), b.mul(ringBand, b.sub(1.0, rings)))      # stretched slightly open between the loops
    cov = b.mx(cov, b.mul(rings, 0.9))
    # ladder band: only course threads remain
    streak_n = b.n('ShaderNodeTexNoise'); streak_n.inputs['Scale'].default_value = 3.0; streak_n.inputs['Detail'].default_value = 1
    b.link(b.combine(b.mul(U, 700.0), b.mul(Vz, 1.2)), streak_n.inputs['Vector'])
    streaks = b.smooth(0.45, 0.85, streak_n.outputs['Fac'])
    # exposed wales in a ladder: crisp vertical threads (phase-jittered so they wander slightly)
    sph = b.add(b.mul(U, 6.2831853 * 380.0), b.mul(streak_n.outputs['Fac'], 7.0))
    strandLine = b.smooth(0.55, 0.9, b.add(0.5, b.mul(b.math('COSINE', sph), 0.5)))
    runCov = b.lerp(b.add(b.mul(cov, 0.8), b.mul(strandLine, 0.15)), b.add(b.mul(rung, 0.5), b.mul(b.sub(1.0, rung), b.add(0.25, b.mul(strandLine, 0.7)))), edgeIn)
    cov = b.lerp(cov, runCov, b.mul(inRun, runOpen))
    edgeBunch = b.mul(b.mul(b.smooth(0.0012, 0.0, runSD), b.sub(1.0, inRun)), runOpen)
    cov = b.lerp(cov, b.mn(b.add(cov, 0.0), 0.99), edgeBunch)
    # holes: frayed thread ends + surviving threads crossing the hole + rolled rim
    flen = b.mul(b.add(0.2, b.mul(wn3.outputs['Value'], 0.8)), 0.0022 * P['threads'])
    fringe = b.mul(b.mul(b.mul(thin, b.math('LESS_THAN', b.mul(holeSD, -1.0), b.mul(flen, 0.25))), inHole), 0.0)
    span = b.mul(b.math('GREATER_THAN', wn4.outputs['Value'], 1.0 - 0.03 * P['threads']), b.smooth(-0.004, -0.0015, holeSD))
    brk_n = b.n('ShaderNodeTexNoise'); brk_n.inputs['Scale'].default_value = 1.0; brk_n.inputs['Detail'].default_value = 0
    b.link(b.combine(b.add(b.mul(U, 96.0), b.mul(rk, 0.37)), b.mul(rk, 0.013)), brk_n.inputs['Vector'])
    brk = b.math('GREATER_THAN', brk_n.outputs['Fac'], 0.42)
    threads = b.mul(b.mul(b.mul(b.mul(thin, span), brk), inRun), inHole)
    threadA = b.mx(fringe, threads)
    rimW = 0.00035
    rim = b.mul(b.smooth(rimW + 0.00012, rimW - 0.00012, holeSD), b.sub(1.0, inHole))
    cov = b.lerp(cov, b.mx(cov, 0.97), b.mul(rim, P['frost_bound']))
    tseam = b.attr('toeseam').outputs['Fac']
    seamLine = b.smooth(0.0016, 0.0005, b.math('ABSOLUTE', tseam))
    toePocket = b.smooth(0.0005, -0.0015, b.mul(tseam, -1.0))
    cov = b.mx(cov, b.mul(seamLine, 0.97))
    cov = b.lerp(cov, b.mn(b.add(cov, 0.06), 0.99), toePocket)
    cov = b.lerp(cov, 0.0, inHole)
    cov = b.mx(cov, b.mul(threadA, 0.9))
    cov = b.mul(cov, b.attr('capfade').outputs['Fac'])        # toe-cap cross-fade (no seam)

    # ---- opacity vs viewing angle (denier effect) — also applies to shadow rays
    ndv = b.vmath('DOT_PRODUCT', geo.outputs['Normal'], geo.outputs['Incoming']).outputs['Value']
    ndv = b.mx(b.math('ABSOLUTE', ndv), 0.02)
    expo = b.div(1.0, b.pw(ndv, P['angle_falloff']))
    alpha = b.sub(1.0, b.pw(b.mx(b.sub(1.0, cov), 0.0), expo))
    alpha = b.mx(alpha, b.mul(threadA, 0.9))

    # ---- normals: knit + ankle wrinkles
    nmap = b.n('ShaderNodeNormalMap', space='TANGENT', uv_map='tuv')
    camd = b.n('ShaderNodeCameraData')
    near = b.smooth(3.5, 2.2, camd.outputs['View Distance'])     # only far-away (sub-pixel) knit fades out
    tboost = b.add(1.0, b.mul(b.smooth(1.0, 1.6, b.mul(stretch, pre)), P['tension_normal_boost'] - 1.0))
    b.link(b.mul(b.mul(near, tboost), 1.3 * P['weave_normal'] * P['normal_strength']), nmap.inputs['Strength'])
    b.link(ktex.outputs['Color'], nmap.inputs['Color'])
    wave = b.n('ShaderNodeTexWave', wave_type='BANDS', bands_direction='Z', wave_profile='SIN')
    wave.inputs['Scale'].default_value = 190.0; wave.inputs['Distortion'].default_value = 2.5
    wave.inputs['Detail'].default_value = 0.0; wave.inputs['Detail Scale'].default_value = 1.0
    b.link(rest.outputs['Vector'], wave.inputs['Vector'])
    front = b.smooth(0.15, -0.6, b.math('COSINE', b.mul(U, 6.2831853)))
    ankleW = b.mul(b.mul(b.smooth(0.065, 0.09, Vz), b.smooth(0.15, 0.115, Vz)), front)
    bump = b.n('ShaderNodeBump'); bump.inputs['Distance'].default_value = 0.0012
    b.link(b.mul(ankleW, P['wrinkle_strength'] / 9.0), bump.inputs['Strength'])
    b.link(wave.outputs['Fac'], bump.inputs['Height'])
    b.link(nmap.outputs['Normal'], bump.inputs['Normal'])
    # rolled rim of holes: slight bevel
    rimb = b.n('ShaderNodeBump'); rimb.inputs['Distance'].default_value = 0.0004
    b.link(b.mul(rim, 0.8), rimb.inputs['Strength'])
    b.link(b.mul(holeSD, -1.0), rimb.inputs['Height'])
    b.link(bump.outputs['Normal'], rimb.inputs['Normal'])
    seamb = b.n('ShaderNodeBump'); seamb.inputs['Distance'].default_value = 0.0009
    b.link(b.mul(seamLine, 1.0), seamb.inputs['Strength'])
    b.link(seamLine, seamb.inputs['Height'])
    b.link(rimb.outputs['Normal'], seamb.inputs['Normal'])
    N = seamb.outputs['Normal']

    # ---- the yarn BSDF
    tan = b.n('ShaderNodeTangent', direction_type='UV_MAP', uv_map='tuv')
    fab = b.n('ShaderNodeBsdfPrincipled')
    fcol = P['fabric_color']
    rimdark = b.sub(1.0, b.mul(rim, 0.4 * P['frost_bound']))
    col = b.n('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY', clamp_factor=True)
    col.inputs['Factor'].default_value = 1.0
    frostcol = b.lerp_col(fcol + (1,), (0.11, 0.085, 0.095, 1), footMask)
    b.link(frostcol, col.inputs[6])
    b.link(b.combine(rimdark, rimdark, rimdark), col.inputs[7])
    b.link(col.outputs[2], fab.inputs['Base Color'])
    fab.inputs['Roughness'].default_value = 0.85 + (0.5 - 0.85) * P['frost_smooth']
    fab.inputs['IOR'].default_value = 1.53
    fab.inputs['Specular IOR Level'].default_value = 0.1 + 0.15 * P['pearl_spec']
    fab.inputs['Anisotropic'].default_value = 0.4
    b.link(tan.outputs['Tangent'], fab.inputs['Tangent'])
    # 'Pearl Strength' scales the pearly sheen; 'Pearl Edge Strength/Start/Width Power' shape its rim
    est = P.get('pearl_edge_start', 0.0)
    edge = b.pw(b.mx(b.div(b.sub(b.sub(1.0, ndv), est), max(1e-3, 1.0 - est)), 0.0), max(P.get('pearl_edge_power', 0.54), 1e-3))
    sheen = b.mul(b.add(0.5, b.mul(edge, 0.5 / 0.7)), 0.4 * P['pearl_edge'] * P.get('pearl_strength', 0.387) / 0.387)
    b.link(sheen, fab.inputs['Sheen Weight'])
    fab.inputs['Sheen Roughness'].default_value = 0.45
    fab.inputs['Sheen Tint'].default_value = (0.95, 0.9, 0.92, 1)
    fab.inputs['Thin Film Thickness'].default_value = 0.0
    fab.inputs['Thin Film IOR'].default_value = 1.45
    b.link(N, fab.inputs['Normal'])
    # rungs / threads catch more light
    fab_lit = b.n('ShaderNodeBsdfPrincipled')
    fab_lit.inputs['Base Color'].default_value = (0.07, 0.065, 0.07, 1)
    fab_lit.inputs['Roughness'].default_value = 0.42
    fab_lit.inputs['Anisotropic'].default_value = 0.8
    b.link(tan.outputs['Tangent'], fab_lit.inputs['Tangent'])
    fab_lit.inputs['Sheen Weight'].default_value = 0.25
    fab_lit.inputs['Sheen Tint'].default_value = (0.9, 0.9, 0.95, 1)
    fab_lit.inputs['Specular IOR Level'].default_value = 0.8
    b.link(N, fab_lit.inputs['Normal'])
    litMix = b.n('ShaderNodeMixShader')
    strands = b.mul(b.mul(strandLine, inRun), runOpen)
    b.link(b.mx(b.mx(b.mul(b.mul(rung, inRun), b.lerp(1.0, 0.7, runOpen)), threadA), b.mx(b.mul(rings, 0.85), b.mul(strands, 0.6))), litMix.inputs['Fac'])
    b.link(fab.outputs[0], litMix.inputs[1]); b.link(fab_lit.outputs[0], litMix.inputs[2])

    # ---- glints: a few fibres with random orientation flash when aligned with a light
    vor = b.n('ShaderNodeTexVoronoi', feature='F1', voronoi_dimensions='3D')
    vor.inputs['Scale'].default_value = P['pearl_grain_scale'] * 2.0     # 572 -> ~0.9 mm grain cells
    b.link(rest.outputs['Vector'], vor.inputs['Vector'])
    gsel = b.math('LESS_THAN', b.sep(vor.outputs['Color'])[0], P['glint_density'] * 0.25)   # 'Pearl Glint Density' -> ~1.4% of grains
    gspot = b.smooth(0.22, 0.12, vor.outputs['Distance'])      # one glinting grain ~0.15 mm
    gmask = b.mul(b.mul(gsel, gspot), b.sub(1.0, inHole))
    gdir = b.vmath('SUBTRACT', vor.outputs['Color'], (0.5, 0.5, 0.5))
    gn = b.vmath('ADD', geo.outputs['Normal'], b.vmath('SCALE', gdir.outputs[0], scale=1.4 * P.get('pearl_randomness', 0.435) / 0.435).outputs[0])
    gnn = b.vmath('NORMALIZE', gn.outputs[0])
    glossy = b.n('ShaderNodeBsdfGlossy', distribution='GGX')
    glossy.inputs['Roughness'].default_value = 0.08
    glossy.inputs['Color'].default_value = (1, 1, 1, 1)
    b.link(gnn.outputs[0], glossy.inputs['Normal'])
    gmix = b.n('ShaderNodeMixShader')
    b.link(b.mul(gmask, min(P['glint_strength'], 1.0)), gmix.inputs['Fac'])
    gem = b.n('ShaderNodeEmission'); gem.inputs['Color'].default_value = (1.0, 0.98, 0.97, 1); gem.inputs['Strength'].default_value = 0.0
    gadd = b.n('ShaderNodeAddShader'); b.link(glossy.outputs[0], gadd.inputs[0]); b.link(gem.outputs[0], gadd.inputs[1])
    b.link(litMix.outputs[0], gmix.inputs[1]); b.link(gadd.outputs[0], gmix.inputs[2])

    # ---- see-through: transparent where yarn doesn't cover; dyed nylon filters what passes (cool mauve)
    transp = b.n('ShaderNodeBsdfTransparent')
    yarnArea = b.mul(b.sub(1.0, inHole), b.sub(1.0, b.mul(b.mul(inRun, runOpen), 0.5)))
    b.link(b.lerp_col((1.0, 1.0, 1.0, 1), (0.80, 0.85, 0.96, 1), yarnArea), transp.inputs['Color'])
    final = b.n('ShaderNodeMixShader')
    # the nylon barely shades the skin (like the original's alpha-blended stocking): light shadow only
    lpS = b.n('ShaderNodeLightPath')
    b.link(b.lerp(alpha, b.mul(alpha, 0.3), lpS.outputs['Is Shadow Ray']), final.inputs['Fac'])
    b.link(transp.outputs[0], final.inputs[1]); b.link(gmix.outputs[0], final.inputs[2])
    b.link(final.outputs[0], out.inputs['Surface'])
    return mat


# --------------------------------------------------------------------------------------------- skirt
def make_skirt():
    """Charcoal wool-blend suiting like the original's skirt: a visible coarse twill (~1.2 mm), heathered
    yarns with light flecks, fuzzy sheen, slightly lighter worn fold edges (follows the pleats via UV)."""
    mat = bpy.data.materials.new('skirt')
    b = NB(mat)
    out = b.n('ShaderNodeOutputMaterial')
    bsdf = b.n('ShaderNodeBsdfPrincipled')
    uvn = b.n('ShaderNodeUVMap', uv_map='UVMap')
    uv = b.sep(uvn.outputs['UV'])
    s_th = 0.0012
    tu = b.div(uv[0], s_th); tv = b.div(uv[1], s_th)
    # 2/2 twill: diagonal ribs + crossing yarns
    diag = b.add(0.5, b.mul(b.math('SINE', b.mul(b.add(tu, tv), 3.14159265)), 0.5))
    warp = b.add(0.5, b.mul(b.math('COSINE', b.mul(tu, 6.2831853)), 0.5))
    weft = b.add(0.5, b.mul(b.math('COSINE', b.mul(tv, 6.2831853)), 0.5))
    hw = b.add(b.mul(diag, 0.55), b.mul(b.mul(warp, weft), 0.45))
    tc = b.n('ShaderNodeTexCoord')
    fz = b.n('ShaderNodeTexNoise'); fz.inputs['Scale'].default_value = 1400; fz.inputs['Detail'].default_value = 4
    b.link(tc.outputs['Object'], fz.inputs['Vector'])
    ht = b.add(b.mul(hw, 0.75), b.mul(fz.outputs['Fac'], 0.4))
    n1 = b.n('ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = 90; n1.inputs['Detail'].default_value = 8
    b.link(tc.outputs['Object'], n1.inputs['Vector'])
    fl = b.n('ShaderNodeTexWhiteNoise', noise_dimensions='3D')
    b.link(b.vmath('SCALE', tc.outputs['Object'], scale=900.0).outputs[0], fl.inputs['Vector'])
    fleck = b.smooth(0.86, 0.97, fl.outputs['Value'])                    # light heather fibres
    heather = b.add(b.mul(n1.outputs['Fac'], 0.5), b.mul(hw, 0.5))
    base = b.lerp_col((0.022, 0.022, 0.025, 1), (0.062, 0.062, 0.068, 1), heather)
    base = b.lerp_col(base, (0.20, 0.20, 0.21, 1), b.mul(fleck, 0.6))
    b.link(base, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.82
    bsdf.inputs['Sheen Weight'].default_value = 0.9
    bsdf.inputs['Sheen Roughness'].default_value = 0.35
    bsdf.inputs['Sheen Tint'].default_value = (0.8, 0.82, 0.86, 1)
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    bump = b.n('ShaderNodeBump'); bump.inputs['Strength'].default_value = 1.0; bump.inputs['Distance'].default_value = 0.0008
    b.link(ht, bump.inputs['Height'])
    b.link(bump.outputs['Normal'], bsdf.inputs['Normal'])
    b.link(bsdf.outputs[0], out.inputs['Surface'])
    return mat


def make_floor():
    """White cotton drop cloth (painter's canvas): high albedo, very rough, fabric sheen, fine weave
    and lint relief; a faint pink-violet tint on the left like the original's floor."""
    mat = bpy.data.materials.new('floor')
    b = NB(mat)
    out = b.n('ShaderNodeOutputMaterial')
    bsdf = b.n('ShaderNodeBsdfPrincipled')
    tc = b.n('ShaderNodeTexCoord')
    P = tc.outputs['Object']
    xyz = b.sep(P)
    n1 = b.n('ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = 4.0; n1.inputs['Detail'].default_value = 5
    b.link(P, n1.inputs['Vector'])
    base = b.lerp_col((0.50, 0.52, 0.64, 1), (0.86, 0.86, 0.93, 1), b.smooth(0.3, 0.7, n1.outputs['Fac']))
    dx = b.sub(xyz[0], -0.17); dy = b.mul(b.sub(xyz[1], 0.05), 0.8)
    dd = b.math('SQRT', b.add(b.mul(dx, dx), b.mul(dy, dy)))
    base = b.lerp_col(base, (0.70, 0.42, 0.60, 1), b.mul(b.smooth(0.36, 0.04, dd), 1.0))
    b.link(base, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.95
    bsdf.inputs['Sheen Weight'].default_value = 0.5
    bsdf.inputs['Sheen Roughness'].default_value = 0.5
    bsdf.inputs['Specular IOR Level'].default_value = 0.2
    weave = b.n('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X'); weave.inputs['Scale'].default_value = 900
    b.link(P, weave.inputs['Vector'])
    fz = b.n('ShaderNodeTexNoise'); fz.inputs['Scale'].default_value = 300; fz.inputs['Detail'].default_value = 4
    b.link(P, fz.inputs['Vector'])
    bump = b.n('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.3; bump.inputs['Distance'].default_value = 0.0008
    b.link(b.add(b.mul(weave.outputs['Fac'], 0.4), fz.outputs['Fac']), bump.inputs['Height'])
    b.link(bump.outputs['Normal'], bsdf.inputs['Normal'])
    dim = b.n('ShaderNodeBsdfDiffuse'); dim.inputs['Color'].default_value = (0.16, 0.16, 0.17, 1)
    lp = b.n('ShaderNodeLightPath')
    mixc = b.n('ShaderNodeMixShader')
    b.link(lp.outputs['Is Camera Ray'], mixc.inputs['Fac'])
    b.link(dim.outputs[0], mixc.inputs[1]); b.link(bsdf.outputs[0], mixc.inputs[2])
    b.link(mixc.outputs[0], out.inputs['Surface'])
    return mat
