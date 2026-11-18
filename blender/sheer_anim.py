# SHEER — animation driver: scripted interaction timeline -> per-frame tights deformation,
# damage textures, camera cuts, cursor log, and Cycles rendering (resumable).
# Usage: blender -b scene.blend -P sheer_anim.py -- --out DIR [--fps 24] [--start 1] [--end N]
#        [--pct 100] [--spp 128] [--every 1] [--dry] [--only-frames 10,40,80]
import bpy, sys, os, math, json, time, argparse
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheer_damage as SD


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def get_attr(me, name, dim):
    a = me.attributes[name]
    out = np.empty(len(a.data) * dim, np.float32)
    a.data.foreach_get('vector' if dim == 3 else 'value', out)
    return out.reshape(-1, dim) if dim == 3 else out


def tri_area(P, tri):
    a = P[tri[:, 1]] - P[tri[:, 0]]; b = P[tri[:, 2]] - P[tri[:, 0]]
    return 0.5 * np.linalg.norm(np.cross(a, b), axis=1)


# ------------------------------------------------------------------------------------ deformation
class TightsDeformer:
    def __init__(self, ob):
        me = ob.data
        self.me = me
        self.rest = get_attr(me, 'rest', 3).astype(np.float64)
        self.rest_n = get_attr(me, 'rest_n', 3).astype(np.float64)
        self.side = get_attr(me, 'legside', 1)
        self.tu = get_attr(me, 'tu', 1)
        me.calc_loop_triangles()
        tri = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get('vertices', tri)
        self.tri = tri.reshape(-1, 3)
        self.area0 = np.maximum(tri_area(self.rest, self.tri), 1e-12)
        self.cnt = np.maximum(np.bincount(self.tri.ravel(), minlength=len(self.rest)), 1).astype(np.float64)
        self.last_moved = False

    def grab_point(self, side, u, z):
        m = np.nonzero((self.side == side) & (np.abs(self.rest[:, 2] - z) < 0.004))[0]
        du = np.abs(self.tu[m] - u - np.floor(self.tu[m] - u + 0.5))
        i = m[np.argmin(du)]
        return self.rest[i].copy(), self.rest_n[i].copy()

    @staticmethod
    def profile(r, R, r0):
        fl = np.where(r <= r0, 1.0, np.log(R / np.maximum(r, 1e-6)) / math.log(R / r0))
        fc = 1.0 - np.maximum(r - r0, 0.0) / (R - r0)
        e = r / R
        f = (0.45 * fl + 0.55 * fc * fc * (1.6 - 0.6 * fc)) * (1.0 - e ** 3)
        return np.where(r >= R, 0.0, np.clip(f, 0.0, 1.0))

    def apply(self, pulls):
        n = len(self.rest)
        disp = np.zeros((n, 3))
        moved = False
        for p in pulls:
            amp = p.amp_now
            if abs(amp) < 1e-4:
                continue
            moved = True
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
            # radial folds converging on the pinch (hoop compression of the pulled membrane)
            t1 = np.cross(ng, [0.0, 0.0, 1.0]); t1 /= max(np.linalg.norm(t1), 1e-9)
            t2 = np.cross(ng, t1)
            phi = np.arctan2(rel[idx] @ t2, rel[idx] @ t1)
            env = smoothstep(0.004, 0.18 * R, rg) * (1.0 - smoothstep(0.35 * R, 0.8 * R, rg))
            fold = np.sin(13 * phi + 1.7 * np.sin(3 * phi + p.seed * 6.0)) * env
            A = 0.0018 * min(np.linalg.norm(P) / 0.05, 1.6)
            d += (fold * A)[:, None] * self.rest_n[idx]
            disp[idx] += d
        h = np.einsum('ij,ij->i', disp, self.rest_n)
        disp -= np.minimum(h, 0.0)[:, None] * self.rest_n
        pos = self.rest + disp
        if moved or self.last_moved:
            self.me.vertices.foreach_set('co', pos.astype(np.float32).ravel())
            ratio = tri_area(pos, self.tri) / self.area0
            st = np.bincount(self.tri.ravel(), weights=np.repeat(ratio, 3), minlength=n) / self.cnt
            self.me.attributes['stretch'].data.foreach_set('value', st.astype(np.float32))
            self.me.update()
        self.last_moved = moved
        return pos


# ------------------------------------------------------------------------------------ interaction
class Pull:
    """A pinch-and-pull: scripted target magnitude along a world direction; tears at tension 1."""

    def __init__(self, sim, side, u, z, direction, t0, ramp=1.8, overshoot=1.25, release_at=None, seed=0.0):
        self.sim = sim
        self.side, self.u, self.z = side, u, z
        self.g, self.ng = sim.deformer.grab_point(side, u, z)
        d = np.array(direction, float); self.dir = d / np.linalg.norm(d)
        self.t0, self.ramp, self.overshoot, self.release_at = t0, ramp, overshoot, release_at
        self.seed = seed
        dmg = sim.damage[side]
        C = dmg.circ(z)
        pre = max(C / dmg.cmin, 1.0) ** 0.55
        rng = np.random.default_rng(int(seed * 1000) + 7)
        denierK = 0.75 + min(max((sim.P.get('denier', 20) - 8) / 70, 0), 1) * 0.9
        self.dTear = 0.085 * denierK * sim.P.get('fabric_strength', 1.0) * rng.uniform(0.9, 1.1) / math.sqrt(pre)
        near = dmg.hole_sd_at(u, z)
        if near < 0.012:
            self.dTear *= 0.45 + 0.55 * max(near, 0) / 0.012
        self.state = 'wait'
        self.P = np.zeros(3); self.Pv = np.zeros(3)
        self.R, self.r0 = 0.028, 0.0045
        self.amp_now = 0.0
        self.pre = None
        self.tension = 0.0
        self.max_t = 0.0

    def tip(self):
        return self.g + self.P * self.amp_now

    def step(self, t, dt):
        if self.state == 'wait':
            if t >= self.t0:
                self.state = 'held'
            else:
                return
        if self.state == 'held':
            k = min(max((t - self.t0) / self.ramp, 0.0), 1.0)
            mag = self.dTear * self.overshoot * (k * k * (1.5 - 0.5 * k))
            target = self.dir * mag
            kk = 140.0; c = 2 * math.sqrt(kk) * 0.9
            a = kk * (target - self.P) - c * self.Pv
            self.Pv += a * dt; self.P += self.Pv * dt
            pull = np.linalg.norm(self.P)
            self.R = min(0.028 + pull * 1.25, 0.18)
            self.amp_now = 1.0
            self.tension = pull / self.dTear
            self.max_t = max(self.max_t, self.tension)
            dmg = self.sim.damage[self.side]
            if self.tension > 0.58 and self.pre is None:
                self.pre = dmg.pre_run(self.u, self.z)
            if self.pre is not None and self.pre.pre:
                gx = max(self.tension - 0.58, 0)
                self.pre.dn['speed'] = max(self.pre.dn['speed'], gx * 0.25)
                self.pre.up['speed'] = max(self.pre.up['speed'], gx * 0.12)
                self.pre.ageT = 0.22 + gx * 0.3
            if self.tension >= 1.0:
                dmg.burst(self.u, self.z, min(self.tension, 1.6), self.pre)
                self._release(t, burst=True)
            elif self.release_at is not None and t >= self.release_at:
                if self.max_t > 0.35:
                    dmg.add_mark(self.u, self.z, min(self.R * 0.5, 0.045), min(0.75, (self.max_t - 0.3) * 0.9))
                if self.pre is not None:
                    self.pre.pre = False
                self._release(t, burst=False)
            return
        if self.state == 'spring':
            st = t - self.t_rel
            w = 2 * math.pi * 2.2                           # critically damped: settles back, no bounce
            self.amp_now = (1.0 + w * st) * math.exp(-w * st)
            if st > 0.9:
                self.state = 'idle'; self.amp_now = 0.0

    def _release(self, t, burst):
        self.state = 'spring'; self.t_rel = t; self.burst = burst


class Sim:
    def __init__(self, deformer, damage, P, story):
        self.deformer, self.damage, self.P = deformer, damage, P
        self.t = 0.0
        self.pulls = []
        self.story = story
        self.fired = set()

    def advance(self, t_target, dt=1.0 / 240.0):
        while self.t < t_target - 1e-9:
            h = min(dt, t_target - self.t)
            for i, ev in enumerate(self.story['events']):
                if i not in self.fired and self.t >= ev['t'] - 1e-9:
                    self.fired.add(i)
                    if ev['kind'] == 'pull':
                        self.pulls.append(Pull(self, ev['side'], ev['u'], ev['z'], ev['dir'], ev['t'], ev.get('ramp', 1.8),
                                               ev.get('overshoot', 1.25), ev.get('release_at'), seed=ev.get('seed', i * 0.37)))
                    elif ev['kind'] == 'snag':
                        self.damage[ev['side']].snag(ev['u'], ev['z'])
            for p in self.pulls:
                p.step(self.t + h, h)
            for d in self.damage.values():
                d.update(h)
            self.t += h

    def active(self):
        return [p for p in self.pulls if p.state in ('held', 'spring')]


# ------------------------------------------------------------------------------------ storyboard
def cam_dirs(cam_name, target):
    cam = bpy.data.objects[cam_name]
    f = (Vector(target) - cam.location).normalized()
    right = f.cross(Vector((0, 0, 1))).normalized()
    to_cam = -f
    return np.array(right), np.array(to_cam)


def storyboard():
    r1, c1 = cam_dirs('VIEW01', (0.092, -0.01, 0.565))
    r2, c2 = cam_dirs('VIEW02', (0.095, -0.05, 0.175))
    up = np.array([0, 0, 1.0])
    n = lambda v: list(v / np.linalg.norm(v))
    ev = [
        # VIEW 01 — knee pinch toward the camera: radial folds, sheer knee, tears into a hole + ladder
        dict(t=0.7, kind='pull', side=1, u=0.47, z=0.50, dir=n(c1 * 0.85 + r1 * 0.3 - up * 0.1), ramp=1.9, seed=0.11),
        # thigh: big sideways tent, bursts, long ladder with holes
        dict(t=3.5, kind='pull', side=1, u=0.27, z=0.64, dir=n(r1 * 0.88 + c1 * 0.42 + up * 0.04), ramp=2.2, seed=0.53),
        # pull right next to the new hole: it tears further
        dict(t=6.7, kind='pull', side=1, u=0.37, z=0.715, dir=n(r1 * 0.6 + c1 * 0.65 + up * 0.25), ramp=1.5, seed=0.91),
        # fingernail snag on the other leg: a ladder zips
        dict(t=8.7, kind='snag', side=1, u=0.62, z=0.6),
        # VIEW 02 — shin: sideways tent, ladder runs down to the reinforced foot
        dict(t=11.4, kind='pull', side=1, u=0.36, z=0.27, dir=n(r2 * 0.72 + c2 * 0.6), ramp=2.0, seed=0.27),
        # ankle pinch toward the camera
        dict(t=14.6, kind='pull', side=1, u=0.47, z=0.165, dir=n(c2 * 0.8 + r2 * 0.45 + up * 0.1), ramp=1.6, seed=0.71),
    ]
    cams = [(0.0, 'VIEW01'), (10.6, 'VIEW02')]
    return dict(events=ev, cams=cams, duration=19.0)


def camera_at(story, t):
    name = story['cams'][0][1]
    for t0, nm in story['cams']:
        if t >= t0:
            name = nm
    return name


# ------------------------------------------------------------------------------------ main
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--start', type=int, default=1)
    ap.add_argument('--end', type=int, default=0)
    ap.add_argument('--pct', type=int, default=100)
    ap.add_argument('--spp', type=int, default=128)
    ap.add_argument('--every', type=int, default=1)
    ap.add_argument('--only-frames', default='')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.resolution_percentage = a.pct
    scene.cycles.samples = a.spp
    scene.render.use_persistent_data = False  # persistent data caches the per-frame damage images
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == 'OPTIX')
    scene.cycles.device = 'GPU'

    P = json.loads(scene.get('tights_params', '{}'))
    tights = bpy.data.objects['tights']
    tables = eval(tights['sheer_tables'])
    deformer = TightsDeformer(tights)
    damage = {}
    for side in (1, -1):
        tb = tables[side]
        zc, circ = np.array(tb['zc']), np.array(tb['circ'])
        cmin = float(circ[(zc > 0.1) & (zc < 0.35)].min())
        damage[side] = SD.Damage(lambda z, zc=zc, circ=circ: float(np.interp(z, zc, circ)), P, seed=5 + side, cmin=cmin)
    images = {1: bpy.data.images['damage_L'], -1: bpy.data.images['damage_R']}
    story = storyboard()
    sim = Sim(deformer, damage, P, story)
    n_frames = a.end if a.end > 0 else int(story['duration'] * a.fps)
    only = set(int(x) for x in a.only_frames.split(',') if x.strip())
    log = []
    t_start = time.time()
    for f in range(1, n_frames + 1):
        t = (f - 1) / a.fps
        sim.advance(t)
        if f < a.start:
            continue
        want = (not only or f in only) and ((f - a.start) % a.every == 0)
        cam_name = camera_at(story, t)
        scene.camera = bpy.data.objects[cam_name]
        act = sim.active()
        held = [p for p in act if p.state == 'held']
        cur = None
        if held:
            co = Vector(held[0].tip())
            v = world_to_camera_view(scene, scene.camera, co)
            cur = dict(x=v.x, y=v.y, down=True)
        log.append(dict(f=f, t=round(t, 4), cam=cam_name, cursor=cur,
                        tension=round(max([p.tension for p in held], default=0.0), 3)))
        if not want:
            continue
        out = os.path.join(a.out, 'f_%04d.png' % f)
        deformer.apply(act)
        for side, img in images.items():
            if damage[side].dirty or f == a.start:
                px = damage[side].render()
                img.pixels.foreach_set(px.ravel())
                img.update()
                if os.environ.get('SHEER_DEBUG'):
                    print('[dmg] side', side, 'holes', len(damage[side].holes), 'runs', len(damage[side].runs),
                          'minR %.3f minG %.3f' % (px[..., 0].min(), px[..., 1].min()), flush=True)
        if a.dry or os.path.exists(out):
            continue
        scene.render.filepath = out
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        el = time.time() - t_start
        print('[anim] frame %d/%d t=%.2fs cam=%s %.1fs (elapsed %.0fs)' % (f, n_frames, t, cam_name, time.time() - t0, el), flush=True)
    with open(os.path.join(a.out, 'cursor_log.json'), 'w') as fh:
        json.dump(dict(fps=a.fps, frames=log, events=story['events'], cams=story['cams']), fh)
    print('[anim] done', flush=True)


if __name__ == '__main__':
    main()
