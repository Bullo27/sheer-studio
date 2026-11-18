# SHEER — damage engine (numpy). Holes, ladders ("runs"), snags and permanent stretch, evolving in
# time, rasterised every frame into a UV-space SDF texture per leg:
#   R = hole signed distance, G = run-band signed distance, B = run age, A = 1 - bagging
# u = angle around the leg (0..1, 0 = back), v = height z (meters, texture covers 0..1 m).
import math
import numpy as np

RANGE = 0.012
W, H = 1024, 2048


def wrapu(d):
    return d - np.floor(d + 0.5)


def smin(a, b, k):
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out_back(x):
    x = min(max(x, 0.0), 1.0)
    c1 = 1.4; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_out_cubic(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


class Hole:
    def __init__(self, u, z, rx, ry, rng, dur=0.16, creep=0.12, creep_dur=1.2, angle=None, rough=None):
        self.u, self.z = u, z
        self.rxT, self.ryT = rx, ry
        self.rx0, self.ry0 = 0.0005, 0.0007
        self.rx, self.ry = self.rx0, self.ry0
        self.angle = rng.uniform(-0.15, 0.15) if angle is None else angle
        self.rough = rng.uniform(0.03, 0.08) if rough is None else rough
        self.seed = rng.random()
        self.t = 0.0; self.dur = dur; self.creep = creep; self.creep_dur = creep_dur
        self.done = False

    def update(self, dt):
        if self.done:
            return False
        self.t += dt
        k = ease_out_back(self.t / self.dur)
        c = 1 + self.creep * ease_out_cubic(max(0.0, self.t - self.dur) / self.creep_dur)
        self.rx = (self.rx0 + (self.rxT - self.rx0) * k) * c
        self.ry = (self.ry0 + (self.ryT - self.ry0) * k) * c
        if self.t >= self.dur + self.creep_dur:
            self.done = True
        return True

    def extent(self):
        return max(self.rx, self.ry) * 1.5 + 0.004


class Run:
    def __init__(self, dmg, u, z, rng, hw0=0.0003, hw=None, age0=0.15, age=1.0, speed_up=None, speed_dn=None,
                 max_up=None, max_dn=None, holes=True, pre=False, jerk=1.0):
        P = dmg.P
        tend = P.get('run_tendency', 1.0)
        self.u, self.z0 = u, z
        self.lo, self.hi = z - 0.0008, z + 0.0008
        self.hw, self.hwT = hw0, (hw if hw is not None else rng.uniform(0.003, 0.0045))
        self.age, self.ageT = age0, age
        self.seed = rng.random()
        self.wobble = rng.uniform(0.0002, 0.0006)
        self.taper = rng.uniform(0.012, 0.03)
        mu = (max_up if max_up is not None else rng.uniform(0.06, 0.3)) * tend
        md = (max_dn if max_dn is not None else rng.uniform(0.06, 0.3)) * tend
        self.up = dict(speed=speed_up if speed_up is not None else rng.uniform(0.35, 0.8),
                       limit=min(dmg.top_z, z + mu), tau=rng.uniform(0.18, 0.55), acc=0.0, next=rng.uniform(0.02, 0.07), jerk=jerk)
        self.dn = dict(speed=speed_dn if speed_dn is not None else rng.uniform(0.35, 0.8),
                       limit=max(dmg.foot_z, z - md), tau=rng.uniform(0.18, 0.55), acc=0.0, next=rng.uniform(0.02, 0.07), jerk=jerk)
        if self.up['limit'] < z: self.up['speed'] = 0
        if self.dn['limit'] > z: self.dn['speed'] = 0
        self.holes = holes; self.pre = pre; self.done = False

    def extent_z(self):
        return self.lo - 0.004, self.hi + 0.004


class Mark:
    def __init__(self, u, z, radius, strength):
        self.u, self.z, self.radius = u, z, radius
        self.s, self.sT, self.t, self.done = 0.0, strength, 0.0, False


class Damage:
    def __init__(self, circ_fn, params, seed=1, foot_z=0.092, top_z=0.8, cmin=0.19):
        self.circ = circ_fn
        self.P = params
        self.rng = np.random.default_rng(seed)
        self.foot_z, self.top_z, self.cmin = foot_z, top_z, cmin
        self.U = ((np.arange(W) + 0.5) / W).astype(np.float32)
        self.Z = ((np.arange(H) + 0.5) / H).astype(np.float32)
        self.C = np.array([circ_fn(z) for z in self.Z], np.float32)
        self.base = np.zeros((H, W, 4), np.float32)
        self.base[..., 0] = RANGE; self.base[..., 1] = RANGE  # stored as raw metres; packed at output
        self.base[..., 3] = 0.0                                # mark (bagging) 0..1
        self.holes, self.runs, self.marks = [], [], []
        self.events = []   # (kind, value) for sound/notes
        self.dirty = True

    # ------------------------------------------------------------------ spawning
    def stretch_at(self, z):
        return max(self.circ(z) / self.cmin, 1.0)

    def add_hole(self, u, z, rx, ry, **kw):
        h = Hole(u, z, rx, ry, self.rng, **kw)
        self.holes.append(h); self.dirty = True
        return h

    def add_run(self, u, z, **kw):
        r = Run(self, u, z, self.rng, **kw)
        self.runs.append(r); self.dirty = True
        return r

    def add_mark(self, u, z, radius, strength):
        m = Mark(u, z, radius, strength)
        self.marks.append(m); self.dirty = True
        return m

    def hole_sd_at(self, u, z):
        best = 1.0
        C = self.circ(z)
        for h in self.holes:
            dx = (u - h.u - math.floor(u - h.u + 0.5)) * C; dy = z - h.z
            k = math.hypot(dx / max(h.rx, 1e-5), dy / max(h.ry, 1e-5))
            best = min(best, (k - 1) * min(h.rx, h.ry))
        return best

    def burst(self, u, z, intensity=1.0, pre_run=None):
        r = self.rng
        st = math.sqrt(self.stretch_at(z))
        size = self.P.get('hole_size', 1.0) * min(1.6, 0.8 + intensity * 0.25) * st
        # a new tear follows an existing ladder if one runs close by (the weakest line of the knit)
        C0 = self.circ(z)
        for run in self.runs:
            if run.pre:
                continue
            du = (u - run.u - math.floor(u - run.u + 0.5)) * C0
            if abs(du) < 0.035 and run.lo - 0.06 < z < run.hi + 0.06:
                u = run.u + r.uniform(-0.15, 0.15) * run.hwT / C0
                if pre_run is not None and pre_run is not run:
                    pre_run.u = run.u            # the pre-run joins the ladder it ran into
                break
        rx = r.uniform(0.0075, 0.011) * size
        ry = rx * r.uniform(1.0, 1.45)
        near = self.hole_sd_at(u, z) < 0.01
        self.add_hole(u, z, rx, ry, dur=r.uniform(0.12, 0.2), creep=r.uniform(0.08, 0.22))
        self.events.append(('tear', intensity))
        if r.random() < 0.45:                       # second lobe -> 'bowling pin'
            d = -1 if r.random() < 0.5 else 1
            off = ry * r.uniform(1.0, 1.25)
            sr = rx * r.uniform(0.5, 0.8)
            C = self.circ(z)
            self.add_hole(u + r.uniform(-0.4, 0.4) * rx / C, z + d * off, sr, sr * r.uniform(1.0, 1.4), dur=r.uniform(0.15, 0.3))
        tend = self.P.get('run_tendency', 1.0)
        if pre_run is not None and not pre_run.done:
            pre_run.ageT = 1.0
            pre_run.hwT = r.uniform(0.0095, 0.013)
            pre_run.pre = False
            pre_run.holes = True
            pre_run.up['speed'] = max(pre_run.up['speed'], r.uniform(0.5, 0.9))
            pre_run.dn['speed'] = max(pre_run.dn['speed'], r.uniform(0.5, 0.9))
            pre_run.up['limit'] = min(self.top_z, z + r.uniform(0.08, 0.3) * tend)
            pre_run.dn['limit'] = max(self.foot_z, z - r.uniform(0.08, 0.3) * tend)
            pre_run.up['jerk'] = pre_run.dn['jerk'] = 1.0
        elif not near or r.random() < 0.5:
            self.add_run(u, z, hw=r.uniform(0.0095, 0.013))

    def pre_run(self, u, z):
        return self.add_run(u, z, hw0=0.0003, hw=0.0014, age0=0.08, age=0.22, speed_up=0.05, speed_dn=0.08,
                            max_up=0.04, max_dn=0.06, holes=False, pre=True, jerk=0.0)

    def snag(self, u, z):
        r = self.rng
        self.add_hole(u, z, r.uniform(0.0008, 0.0014), r.uniform(0.0012, 0.002), dur=0.1, creep=0.3, creep_dur=2.0)
        self.add_run(u, z, holes=r.random() < 0.25, hw0=0.0003, hw=r.uniform(0.0022, 0.0042), age0=0.1, age=1.0,
                     speed_up=r.uniform(0.15, 0.45), speed_dn=r.uniform(0.2, 0.5), max_up=r.uniform(0.05, 0.35),
                     max_dn=r.uniform(0.08, 0.4))
        self.events.append(('snag', 1.0))

    # ------------------------------------------------------------------ dynamics
    def update(self, dt):
        changed = False
        zip_speed = 0.0
        for h in self.holes:
            changed |= h.update(dt)
        r = self.rng
        for run in self.runs:
            if run.done:
                continue
            changed = True
            for end, sign in ((run.up, 1), (run.dn, -1)):
                if end['speed'] <= 0:
                    continue
                step = end['speed'] * dt
                zip_speed += end['speed']
                if sign > 0:
                    run.hi = min(end['limit'], run.hi + step); at = run.hi
                    if at >= end['limit']: end['speed'] = 0
                else:
                    run.lo = max(end['limit'], run.lo - step); at = run.lo
                    if at <= end['limit']: end['speed'] = 0
                end['speed'] *= math.exp(-dt / end['tau'])
                if end['jerk'] and r.random() < dt * 2.2:
                    end['speed'] += r.uniform(0.1, 0.45) * end['jerk']
                if end['speed'] < 0.02:
                    end['speed'] = 0
                end['acc'] += step
                if run.holes and end['acc'] > end['next']:
                    end['acc'] = 0.0
                    st = self.stretch_at(at)
                    end['next'] = r.uniform(0.035, 0.08) / math.sqrt(st)
                    p = 0.36 * min(st, 2.2) * self.P.get('run_tendency', 1.0) * min(1.0, (run.hwT - 0.0015) / 0.0025)
                    if r.random() < p:
                        hz = at - sign * r.uniform(0.004, 0.012)
                        C = self.circ(hz)
                        rx = run.hwT * r.uniform(0.42, 0.8) * math.sqrt(st) * self.P.get('hole_size', 1.0)
                        ry = rx * r.uniform(1.05, 1.7)
                        hu = run.u + r.uniform(-0.25, 0.25) * run.hwT / C
                        if self.hole_sd_at(hu, hz) > ry * 1.15:          # keep holes distinct (no capsules)
                            self.add_hole(hu, hz, rx, ry, dur=r.uniform(0.12, 0.25), creep=r.uniform(0.05, 0.15))
                            self.events.append(('pop', rx))
            run.hw += (run.hwT - run.hw) * (1 - math.exp(-dt * 5))
            run.age += (run.ageT - run.age) * (1 - math.exp(-dt * 6))
            if (not run.pre and run.up['speed'] == 0 and run.dn['speed'] == 0
                    and abs(run.hw - run.hwT) < 3e-5 and abs(run.age - run.ageT) < 0.01):
                run.hw = run.hwT; run.age = run.ageT; run.done = True
        for m in self.marks:
            if m.done:
                continue
            m.t += dt; m.s = m.sT * ease_out_cubic(m.t / 0.4)
            if m.t >= 0.4: m.done = True
            changed = True
        self.zip_speed = zip_speed
        if changed:
            self.dirty = True
        return changed

    # ------------------------------------------------------------------ rasterisation
    def _rows(self, z0, z1):
        a = max(0, int(z0 * H) - 1); b = min(H, int(z1 * H) + 2)
        return slice(a, b)

    def _cols(self, u, half_u):
        if half_u >= 0.5:
            return np.arange(W)
        d = np.abs(wrapu(self.U - u))
        return np.nonzero(d <= half_u)[0]

    def render(self):
        """Returns (H, W, 4) float32 RGBA for the Blender image."""
        F = self.base.copy()
        hole = F[..., 0]; run = F[..., 1]; age = F[..., 2]; mark = F[..., 3]
        for h in self.holes:
            ext = h.extent()
            rs = self._rows(h.z - ext, h.z + ext)
            Cmax = float(self.C[rs].max())
            cols = self._cols(h.u, ext / max(Cmax, 1e-3) * 1.2)
            if len(cols) == 0:
                continue
            z = self.Z[rs][:, None]; C = self.C[rs][:, None]
            dx = wrapu(self.U[cols][None, :] - h.u) * C; dy = z - h.z
            ca, sa = math.cos(h.angle), math.sin(h.angle)
            qx = ca * dx + sa * dy; qy = -sa * dx + ca * dy
            ang = np.arctan2(qy, qx); s = h.seed * 2 * math.pi
            n = (0.5 * np.sin(2 * ang + s) + 0.35 * np.sin(3 * ang + s * 1.7) + 0.22 * np.sin(5 * ang + s * 2.3)
                 + 0.12 * np.sin(9 * ang + s * 3.1))
            rx = np.maximum(h.rx * (1 + n * h.rough), 1e-5); ry = np.maximum(h.ry * (1 + n * h.rough), 1e-5)
            k = np.sqrt((qx / rx) ** 2 + (qy / ry) ** 2)
            sd = (k - 1) * np.minimum(rx, ry)
            sub = hole[rs][:, cols]
            hole_block = smin(sub, sd.astype(np.float32), 0.0028)
            tmp = hole[rs]; tmp[:, cols] = hole_block; hole[rs] = tmp
        for r in self.runs:
            z0, z1 = r.extent_z()
            rs = self._rows(z0, z1)
            Cmax = float(self.C[rs].max())
            cols = self._cols(r.u, (r.hw * 2.2 + 0.006) / max(Cmax, 1e-3))
            if len(cols) == 0:
                continue
            z = self.Z[rs][:, None]; C = self.C[rs][:, None]
            tc = np.clip(z, r.lo, r.hi)
            wob = (np.sin(tc * 31.0 + r.seed * 40.0) * 0.6 + np.sin(tc * 87.0 + r.seed * 13.0) * 0.4) * r.wobble
            dx = wrapu(self.U[cols][None, :] - r.u) * C - wob
            e = np.minimum(tc - r.lo, r.hi - tc)
            hw = r.hw * (0.15 + 0.85 * smoothstep(0.0, r.taper, e)) * (1 + 0.12 * np.sin(tc * 23.0 + r.seed * 7.0))
            hw = hw * np.sqrt(np.maximum(C / 0.2, 1.0))
            sd = np.abs(dx) - hw
            dy = z - tc
            sd = np.where(np.abs(dy) > 0, np.sqrt(np.maximum(sd, 0) ** 2 + dy ** 2), sd)
            tmp = run[rs]; blk = tmp[:, cols]
            tmp[:, cols] = np.minimum(blk, sd.astype(np.float32)); run[rs] = tmp
            tmpa = age[rs]; blka = tmpa[:, cols]
            tmpa[:, cols] = np.where(sd < 0, np.maximum(blka, r.age), blka); age[rs] = tmpa
        for m in self.marks:
            rs = self._rows(m.z - m.radius, m.z + m.radius)
            Cmax = float(self.C[rs].max())
            cols = self._cols(m.u, m.radius / max(Cmax, 1e-3) * 1.2)
            z = self.Z[rs][:, None]; C = self.C[rs][:, None]
            d = np.hypot(wrapu(self.U[cols][None, :] - m.u) * C, z - m.z)
            w = 1 - smoothstep(0.0, m.radius, d)
            tmp = mark[rs]; blk = tmp[:, cols]
            tmp[:, cols] = 1 - (1 - blk) * (1 - w * w * m.s); mark[rs] = tmp
        out = np.empty_like(F)
        out[..., 0] = np.clip(hole / (2 * RANGE) + 0.5, 0, 1)
        out[..., 1] = np.clip(run / (2 * RANGE) + 0.5, 0, 1)
        out[..., 2] = np.clip(age, 0, 1)
        out[..., 3] = np.clip(1 - mark, 0, 1)
        self.dirty = False
        return out
