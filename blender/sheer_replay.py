# SHEER — replay of the original video's session: the player's cursor input (measured on the
# original) drives grabs/drags on the tights, the model flinches (knees together) after tears,
# the skirt is live cloth blown by a fan, and the camera reproduces the original's zooms and the
# VIEW 01 -> VIEW 02 move. Renders frames (resumable) + a per-frame UI log for compositing.
# Usage: blender -b scene.blend -P sheer_replay.py -- --out DIR [--fps 30] [--pct 100] [--spp 128]
#        [--only-frames 10,40] [--every N] [--no-cloth] [--dry] [--end N]
import bpy, sys, os, math, json, time, argparse, struct
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheer_damage as SD
import sheer_anim as SA
import sheer_story as STY
import sheer_skirt as SK

VIEWS = {'VIEW01': ((0.0843, -1.2612, 0.4868), (0.0955, 0.0, 0.5638), 87.4),
         'VIEW02': ((-0.0548, -1.1081, 0.1905), (-0.0430, 0.0, 0.1797), 85.2)}


def smooth01(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6 - 15) + 10)


# ------------------------------------------------------------------------------------ pose
class Pose:
    """Knee flinch (knees pressed together, feet planted) + idle balance sway."""
    def __init__(self, track):
        self.track = track

    def offset(self, P, t):
        z = P[:, 2]; x = P[:, 0]
        side = np.sign(x)
        k = self.track.knee(t)
        prof = np.where(z >= 0.47, SA.smoothstep(0.80, 0.47, z), SA.smoothstep(0.12, 0.47, z))
        K = np.where(side > 0, 0.010, 0.028)
        fade = SA.smoothstep(0.0, 0.035, np.abs(x))
        dx = -side * K * k * prof * fade
        sway = 0.0022 * math.sin(2 * math.pi * 0.23 * t) + 0.0012 * math.sin(2 * math.pi * 0.61 * t + 1.3)
        dx = dx + sway * SA.smoothstep(0.08, 0.9, z)
        out = np.zeros_like(P); out[:, 0] = dx
        return out


# ------------------------------------------------------------------------------------ camera
class CamRig:
    def __init__(self, scene):
        src = bpy.data.objects['VIEW01'].data
        cd = bpy.data.cameras.new('CAM')
        cd.sensor_fit = 'VERTICAL'; cd.sensor_height = 36.0; cd.sensor_width = 36.0
        cd.dof.use_dof = True; cd.dof.aperture_fstop = src.dof.aperture_fstop
        self.ob = bpy.data.objects.new('CAM', cd)
        scene.collection.objects.link(self.ob)
        scene.camera = self.ob
        self.focus = {n: bpy.data.objects[n].data.dof.focus_distance for n in VIEWS}

    @staticmethod
    def _lerp(a, b, w):
        return tuple(a[i] + (b[i] - a[i]) * w for i in range(len(a)))

    def params(self, t):
        a, b = STY.VIEW_SWITCH
        L1, T1, f1 = VIEWS['VIEW01']; L2, T2, f2 = VIEWS['VIEW02']
        w = smooth01((t - a) / (b - a))
        loc = Vector(self._lerp(L1, L2, w)); tgt = Vector(self._lerp(T1, T2, w)); lens = f1 + (f2 - f1) * w
        foc = self.focus['VIEW01'] + (self.focus['VIEW02'] - self.focus['VIEW01']) * w
        for (i0, i1, o0, o1, view, dolly, orbit) in STY.CAM_MOVES:
            if i0 <= t <= o1:
                m = smooth01((t - i0) / (i1 - i0)) if t < i1 else (1.0 if t < o0 else 1.0 - smooth01((t - o0) / (o1 - o0)))
                ang = math.radians(orbit) * m
                d = loc - tgt
                d = Vector((d.x * math.cos(ang) - d.y * math.sin(ang), d.x * math.sin(ang) + d.y * math.cos(ang), d.z))
                k = 1.0 + (dolly - 1.0) * m
                loc = tgt + d * k
                foc = foc * k
        return loc, tgt, lens, foc

    def apply(self, t):
        loc, tgt, lens, foc = self.params(t)
        self.ob.location = loc
        self.ob.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
        self.ob.data.lens = lens
        self.ob.data.dof.focus_distance = foc
        return loc, tgt

    def ray(self, t, x, y):
        """World ray through normalized game-view coords (x right, y down from the top)."""
        loc, tgt, lens, _ = self.params(t)
        f = (tgt - loc).normalized()
        r = f.cross(Vector((0, 0, 1))).normalized(); u = r.cross(f)
        k = lens / 36.0
        aspect = 1890 / 1080
        sx = (x - 0.5) / (aspect * k); sy = (0.5 - y) / k
        return loc, (f + r * sx + u * sy).normalized(), f


# ------------------------------------------------------------------------------------ deformation
class PosedDeformer(SA.TightsDeformer):
    def apply_posed(self, pulls, base):
        n = len(self.rest)
        disp = np.zeros((n, 3))
        for p in pulls:
            amp = p.amp_now
            if abs(amp) < 1e-4:
                continue
            g, ng, P, R, r0 = p.g, p.ng, p.P * amp, p.R, p.r0
            rel = self.rest - g
            r = np.linalg.norm(rel, axis=1)
            idx = np.nonzero((r < R * 1.02) & (self.side == p.side))[0]
            if len(idx) == 0:
                continue
            rr = r[idx]
            c = np.clip(self.rest_n[idx] @ ng, -1.0, 1.0)
            ph = np.arccos(c) * 0.5
            rg = np.where(ph > 1e-3, rr * ph / np.maximum(np.sin(ph), 1e-6), rr)
            f = self.profile(rg, R, r0)
            d = f[:, None] * P[None, :]
            t1 = np.cross(ng, [0.0, 0.0, 1.0]); t1 /= max(np.linalg.norm(t1), 1e-9)
            t2 = np.cross(ng, t1)
            phi = np.arctan2(rel[idx] @ t2, rel[idx] @ t1)
            env = SA.smoothstep(0.004, 0.18 * R, rg) * (1.0 - SA.smoothstep(0.35 * R, 0.8 * R, rg))
            fold = np.sin(13 * phi + 1.7 * np.sin(3 * phi + p.seed * 6.0)) * env
            A = 0.0018 * min(np.linalg.norm(P) / 0.05, 1.6)
            d += (fold * A)[:, None] * self.rest_n[idx]
            disp[idx] += d
        h = np.einsum('ij,ij->i', disp, self.rest_n)
        disp -= np.minimum(h, 0.0)[:, None] * self.rest_n
        pos = base + disp
        self.me.vertices.foreach_set('co', pos.astype(np.float32).ravel())
        ratio = SA.tri_area(pos, self.tri) / self.area0
        st = np.bincount(self.tri.ravel(), weights=np.repeat(ratio, 3), minlength=n) / self.cnt
        self.me.attributes['stretch'].data.foreach_set('value', st.astype(np.float32))
        self.me.update()
        return pos


class ReplayPull(SA.Pull):
    def __init__(self, sim, press, u, z, drag_fn, seed):
        super().__init__(sim, press['side'], u, z, (1.0, 0.0, 0.0), press['t0'], seed=seed)
        self.press = press
        self.drag_fn = drag_fn

    def step(self, t, dt):
        pr = self.press
        if self.state == 'wait':
            if t < self.t0:
                return
            self.state = 'held'
        if self.state != 'held':
            return SA.Pull.step(self, t, dt)
        target = self.drag_fn(t)
        kk = 160.0; c = 2 * math.sqrt(kk) * 0.9
        a = kk * (target - self.P) - c * self.Pv
        self.Pv += a * dt; self.P += self.Pv * dt
        pull = np.linalg.norm(self.P)
        self.R = min(0.028 + pull * 1.25, 0.18)
        self.amp_now = 1.0
        self.tension = pull / self.dTear
        self.max_t = max(self.max_t, self.tension)
        dmg = self.sim.damage[self.side]
        if (pr['pre'] or (pr['burst'] and t > pr['t1'] - 0.3)) and self.pre is None:
            self.pre = dmg.pre_run(self.u, self.z)
        if self.pre is not None and self.pre.pre:
            gx = max(self.tension - 0.4, 0.2)
            self.pre.dn['speed'] = max(self.pre.dn['speed'], gx * 0.25)
            self.pre.up['speed'] = max(self.pre.up['speed'], gx * 0.12)
            self.pre.ageT = 0.22 + gx * 0.3
        if t >= pr['t1']:
            if pr['burst']:
                dmg.burst(self.u, self.z, min(max(self.tension, 1.0), 1.6), self.pre)
                self._release(t, burst=True)
            else:
                if self.max_t > 0.35:
                    dmg.add_mark(self.u, self.z, min(self.R * 0.5, 0.045), min(0.75, (self.max_t - 0.3) * 0.9))
                if self.pre is not None:
                    self.pre.pre = False
                self._release(t, burst=False)


class ReplaySim:
    def __init__(self, deformer, damage, P, track, rig, pose):
        self.deformer, self.damage, self.P = deformer, damage, P
        self.track, self.rig, self.pose = track, rig, pose
        self.t = STY.PRESSES[0]['t0'] - 0.05
        self.pulls = []
        self.pending = list(enumerate(STY.PRESSES))
        self.grabs = []

    def _spawn(self, i, pr):
        t0 = pr['t0']
        base = self.deformer.rest + self.pose.offset(self.deformer.rest, t0)
        x, y, _ = self.track.cursor(t0)
        org, dirv, fwd = self.rig.ray(t0, x, y)
        hero = np.nonzero(self.deformer.side == pr['side'])[0]
        # closest hero-leg vertex to the cursor ray (in front of the camera)
        O = np.array(org); D = np.array(dirv)
        rel = base[hero] - O
        along = rel @ D
        perp = np.linalg.norm(rel - np.outer(along, D), axis=1)
        score = perp + 0.02 * np.maximum(along - along.min(), 0)      # prefer the near (visible) side
        j = hero[np.argmin(score)]
        u = float(self.deformer.tu[j]); z = float(self.deformer.rest[j, 2])
        h = Vector(base[j]); d0 = (h - org).dot(fwd)

        def world_at(t):
            xx, yy, _ = self.track.cursor(t)
            o, dv, fw = self.rig.ray(t, xx, yy)
            return o + dv * (d0 / max(dv.dot(fw), 1e-6)), o

        W0, _ = world_at(t0)

        def drag(t, W0=W0, h=h, k=pr['fwd']):
            W, o = world_at(min(t, pr['t1']))
            D = W - W0
            v = D + (o - h).normalized() * (k * D.length)
            cap = pr.get('cap', 0.11)
            if v.length > cap:
                v = v.normalized() * cap
            return np.array(v)

        p = ReplayPull(self, pr, u, z, drag, seed=0.13 + 0.37 * i)
        self.pulls.append(p)
        self.grabs.append(dict(i=i, t=t0, u=u, z=z, side=pr['side']))
        print('[replay] press %d at t=%.2f side %d u=%.3f z=%.3f (ray miss %.1f mm)' % (i, t0, pr['side'], u, z, float(perp.min()) * 1000), flush=True)

    def advance(self, t_target, dt=1.0 / 240.0):
        while self.t < t_target - 1e-9:
            h = min(dt, t_target - self.t)
            for item in list(self.pending):
                i, pr = item
                if self.t >= pr['t0'] - 1e-9:
                    self._spawn(i, pr)
                    self.pending.remove(item)
            for p in self.pulls:
                p.step(self.t + h, h)
            for d in self.damage.values():
                d.update(h)
            self.t += h

    def active(self):
        return [p for p in self.pulls if p.state in ('held', 'spring')]


# ------------------------------------------------------------------------------------ cloth
def write_pc2(path, frames):
    frames = np.asarray(frames, np.float32)
    ns, nv, _ = frames.shape
    with open(path, 'wb') as fh:
        fh.write(b'POINTCACHE2\0')
        fh.write(struct.pack('<iiffi', 1, nv, 1.0, 1.0, ns))
        fh.write(frames.tobytes())


def setup_live_skirt(scene, pose, n_frames, fps, cache_dir):
    proxy = bpy.data.objects['skirt_proxy']
    me = proxy.data
    rest = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', rest); rest = rest.reshape(-1, 3).astype(np.float64)
    frames = [rest + pose.offset(rest, (f - 1) / fps) for f in range(1, n_frames + 1)]
    pc2 = os.path.join(cache_dir, 'proxy_pose.pc2')
    write_pc2(pc2, frames)
    mc = proxy.modifiers.new('pose', 'MESH_CACHE')
    mc.cache_format = 'PC2'; mc.filepath = pc2
    mc.frame_start = 1.0; mc.play_mode = 'SCENE'; mc.time_mode = 'FRAME'
    while proxy.modifiers.find('pose') > 0:
        proxy.modifiers.move(proxy.modifiers.find('pose'), proxy.modifiers.find('pose') - 1)
    skirt = bpy.data.objects['skirt']
    cm = SK.setup_cloth(skirt, frame_end=n_frames)
    while skirt.modifiers.find(cm.name) > 0:
        skirt.modifiers.move(skirt.modifiers.find(cm.name), skirt.modifiers.find(cm.name) - 1)
    cm.point_cache.use_disk_cache = True
    cm.point_cache.name = 'skirt_live'
    # the fan: Blender's force fields don't reach the cloth in headless runs, so the breeze is applied
    # as a slowly wandering lateral component of the (cloth-only) gravity, with flutter and gusts
    amp = float(os.environ.get('SHEER_WIND', '1.0'))
    for f in range(1, n_frames + 1):
        t = (f - 1) / fps
        g = STY.wind_gain(t)
        wx = amp * g * (0.6 + 0.4 * math.sin(2 * math.pi * 0.21 * t + 0.3) + 0.25 * math.sin(2 * math.pi * 0.83 * t + 1.1)) \
            + 0.25 * amp * math.sin(2 * math.pi * 2.7 * t + 0.4)
        wy = amp * g * (0.5 + 0.35 * math.sin(2 * math.pi * 0.17 * t + 2.0)) + 0.2 * amp * math.sin(2 * math.pi * 2.3 * t + 1.7)
        gz = -9.81 + (g - 1.0) * 1.6
        scene.gravity = (wx, wy, gz)
        scene.keyframe_insert(data_path='gravity', frame=f)
    base_strength = amp
    print('[replay] live skirt: cloth + fan breeze (%.2f m/s^2) ; proxy pose cache %s' % (base_strength, pc2), flush=True)
    return skirt


# ------------------------------------------------------------------------------------ main
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--end', type=int, default=0)
    ap.add_argument('--pct', type=int, default=100)
    ap.add_argument('--spp', type=int, default=128)
    ap.add_argument('--every', type=int, default=1)
    ap.add_argument('--only-frames', default='')
    ap.add_argument('--no-cloth', action='store_true')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.resolution_percentage = a.pct
    scene.cycles.samples = a.spp
    scene.render.use_persistent_data = False
    scene.cycles.use_denoising = os.environ.get('SHEER_DENOISE', '0') == '1'   # previews only; finals render raw (knit/glints)
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == 'OPTIX')
    scene.cycles.device = 'GPU'

    P = json.loads(scene.get('tights_params', '{}'))
    tights = bpy.data.objects['tights']
    tables = eval(tights['sheer_tables'])
    deformer = PosedDeformer(tights)
    damage = {}
    for side in (1, -1):
        tb = tables[side]
        zc, circ = np.array(tb['zc']), np.array(tb['circ'])
        cmin = float(circ[(zc > 0.1) & (zc < 0.35)].min())
        damage[side] = SD.Damage(lambda z, zc=zc, circ=circ: float(np.interp(z, zc, circ)), P, seed=5 + side, cmin=cmin)
    images = {1: bpy.data.images['damage_L'], -1: bpy.data.images['damage_R']}
    track = STY.Track()
    pose = Pose(track)
    rig = CamRig(scene)
    body = bpy.data.objects['body']
    body_rest = np.empty(len(body.data.vertices) * 3, np.float32); body.data.vertices.foreach_get('co', body_rest)
    body_rest = body_rest.reshape(-1, 3).astype(np.float64)
    n_frames = a.end if a.end > 0 else int(STY.DURATION * a.fps)
    scene.frame_start = 1; scene.frame_end = n_frames
    scene.render.fps = a.fps
    if not a.no_cloth:
        setup_live_skirt(scene, pose, n_frames, a.fps, a.out)
    sim = ReplaySim(deformer, damage, P, track, rig, pose)
    only = set(int(x) for x in a.only_frames.split(',') if x.strip())
    log = []
    t_start = time.time()
    for f in range(1, n_frames + 1):
        t = (f - 1) / a.fps
        sim.advance(t)
        want = (not only or f in only) and ((f - 1) % a.every == 0)
        last_needed = max(only) if only else n_frames
        if f > last_needed:
            break
        act = sim.active()
        held = [p for p in act if p.state == 'held']
        cx, cy, vis = track.cursor(t)
        view = 'VIEW01' if t < STY.VIEW_SWITCH[0] - 0.05 else 'VIEW02'
        log.append(dict(f=f, t=round(t, 4), cursor=[round(cx, 4), round(cy, 4)], visible=vis, down=bool(held), view=view,
                        knee=round(track.knee(t), 3)))
        out = os.path.join(a.out, 'f_%04d.png' % f)
        need_cloth_step = not a.no_cloth
        if not want and not need_cloth_step:
            continue
        rig.apply(t)
        if want:
            body.data.vertices.foreach_set('co', (body_rest + pose.offset(body_rest, t)).astype(np.float32).ravel())
            body.data.update()
            deformer.apply_posed(act, deformer.rest + pose.offset(deformer.rest, t))
            for side, img in images.items():
                if damage[side].dirty or not damage[side].__dict__.get('_pushed'):
                    px = damage[side].render()
                    img.pixels.foreach_set(px.ravel()); img.update()
                    damage[side]._pushed = True
        scene.frame_set(f)
        if not want or a.dry or os.path.exists(out):
            continue
        scene.render.filepath = out
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print('[replay] frame %d/%d t=%.2fs %.1fs (elapsed %.0fs)' % (f, n_frames, t, time.time() - t0, time.time() - t_start), flush=True)
    with open(os.path.join(a.out, 'ui_log.json'), 'w') as fh:
        json.dump(dict(fps=a.fps, frames=log, presses=STY.PRESSES, grabs=sim.grabs), fh)
    print('[replay] done', flush=True)


if __name__ == '__main__':
    main()
