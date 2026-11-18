#!/usr/bin/env python3
# SHEER — prototype of the tights cloth model (to be ported to Burst C#): each leg of the stocking is a tube grid
# in (theta around the leg axis, height z), simulated with XPBD (unit masses, small substeps, coloured
# Gauss-Seidel): pre-stretched elastic edges (the stocking is knitted smaller than the leg -> tension) with a hard
# strain limit (knit locks up), weak bending, collision with the leg as a radial height field around the posed leg
# axis, Coulomb friction against the skin, a weak rest attachment (elastic recovery), and the grab as a pinched
# disc following the cursor in the plane facing the camera (like the original's drag).
# Validated against the original video frame by frame (renders the projected cloth over the original frame).
# Usage: python3 tools/cloth_proto.py --press 9 --times 26.95,27.25,27.55 --out DIR [--param k=v ...]
import argparse, json, math, os, struct
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SA = os.path.join(ROOT, 'unity_export', 'StreamingAssets')

DEFAULTS = dict(
    NT=64, Z0=0.09, Z1=0.80, DZ=0.006,           # grid
    HZ=480.0, ITERS=3,                            # substep rate, solver iterations per substep
    pre_c=0.18, pre_v=0.06,                       # at-rest strain (knitted smaller than the leg)
    lim_c=0.35, lim_v=0.025, lim_s=0.20,           # extra strain where the knit locks (hard limit), shear
    comp_s=2e-6,                                  # stretch compliance (soft region)
    comp_b=2e-3,                                  # bending (skip-one) compliance
    comp_att=0.5,                                 # rest attachment compliance (slow elastic recovery)
    k_grab=3000.0, grab_r=0.010, grab_pinch=0.5,  # the hand: a damped spring force (1/s^2) toward the cursor point
    comp_fric=1e-6, slip=0.004, anchor_tau=0.6,   # stick-slip grip on the skin: elastic up to 'slip', then slides
    grip_around=1.0,                              # grip scale around the leg (tube rotation) vs along it

    damp=6.0, gravity=9.81,
    fwd=0.0, cap=0.15,                            # drag mapping: lift toward the viewer, max pull
)


# ------------------------------------------------------------------------------------------ data
def load_smesh(path):
    b = open(path, 'rb').read(); o = 4
    assert b[:4] == b'SMSH'
    ver, nv, ns = struct.unpack_from('<III', b, o); o += 12
    subs = []
    for _ in range(ns):
        (c,) = struct.unpack_from('<I', b, o); o += 4
        subs.append(np.frombuffer(b, np.uint32, c, o).reshape(-1, 3)); o += 4 * c
    (nc,) = struct.unpack_from('<I', b, o); o += 4
    ch = {}
    for _ in range(nc):
        name = b[o:o + 16].rstrip(b'\0').decode(); o += 16
        typ, dim, _ = struct.unpack_from('<BBH', b, o); o += 4
        ch[name] = np.frombuffer(b, np.uint32 if typ else np.float32, nv * dim, o).reshape(nv, dim); o += 4 * nv * dim
    return nv, subs, ch


def gauss_smooth(arr, sigma):
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    return np.convolve(np.pad(arr, r, mode='edge'), k, mode='valid')


def axis_tables(co, side, step=0.002):
    """Per-height leg axis (same construction as blender/sheer_tights.leg_axis_tables)."""
    zb = np.arange(0.0, 1.0 + step, step); zc = 0.5 * (zb[:-1] + zb[1:])
    cx = np.full(len(zc), np.nan); cy = np.full(len(zc), np.nan)
    sel = co[:, 0] * side > 0.0
    for i, (z0, z1) in enumerate(zip(zb[:-1], zb[1:])):
        m = sel & (co[:, 2] >= z0 - 0.003) & (co[:, 2] < z1 + 0.003)
        if m.sum() < 24:
            continue
        x, y = co[m, 0], co[m, 1]
        x0, y0 = 0.5 * (x.min() + x.max()), 0.5 * (y.min() + y.max())
        th = np.arctan2(x - x0, y - y0); r = np.hypot(x - x0, y - y0)
        sec = ((th + np.pi) / (2 * np.pi) * 48).astype(int) % 48
        rs = np.bincount(sec, weights=r, minlength=48) / np.maximum(np.bincount(sec, minlength=48), 1)
        ok = rs > 0
        if ok.sum() < 29:
            continue
        ang = (np.arange(48) + 0.5) / 48 * 2 * np.pi - np.pi
        cx[i] = (x0 + np.sin(ang[ok]) * rs[ok]).mean(); cy[i] = (y0 + np.cos(ang[ok]) * rs[ok]).mean()
    idx = np.arange(len(zc)); ok = ~np.isnan(cx)
    cx = np.interp(idx, idx[ok], cx[ok]); cy = np.interp(idx, idx[ok], cy[ok])
    return zc, gauss_smooth(cx, 6), gauss_smooth(cy, 6)


class Leg:
    """Radial height field R(z, theta) of the stocking's rest surface around the leg axis."""
    def __init__(self, co, u, side, z0=0.05, z1=0.88, dzt=0.003, nth=128):
        self.side = side
        self.zc, self.cx, self.cy = axis_tables(co, side)
        m = (np.sign(co[:, 0]) == side) & (co[:, 2] > z0) & (co[:, 2] < z1)
        p = co[m]; th = (u[m] * 2 * np.pi) % (2 * np.pi)
        ax = np.interp(p[:, 2], self.zc, self.cx); ay = np.interp(p[:, 2], self.zc, self.cy)
        rho = np.hypot(p[:, 0] - ax, p[:, 1] - ay)
        self.z0, self.dzt, self.nth = z0, dzt, nth
        nz = int((z1 - z0) / dzt) + 1
        iz = np.clip(((p[:, 2] - z0) / dzt).astype(int), 0, nz - 1); it = (th / (2 * np.pi) * nth).astype(int) % nth
        k = iz * nth + it
        s = np.bincount(k, weights=rho, minlength=nz * nth); c = np.bincount(k, minlength=nz * nth)
        R = np.where(c > 0, s / np.maximum(c, 1), np.nan).reshape(nz, nth)
        for _ in range(200):                                   # fill holes
            bad = np.isnan(R)
            if not bad.any():
                break
            Rp = np.pad(np.where(bad, 0, R), ((1, 1), (0, 0)), mode='edge'); W = np.pad((~bad).astype(float), ((1, 1), (0, 0)), mode='edge')
            acc = Rp[:-2] + Rp[2:] + np.roll(Rp[1:-1], 1, 1) + np.roll(Rp[1:-1], -1, 1)
            wac = W[:-2] + W[2:] + np.roll(W[1:-1], 1, 1) + np.roll(W[1:-1], -1, 1)
            R = np.where(bad & (wac > 0), acc / np.maximum(wac, 1e-9), R)
        for _ in range(12):                                    # smoothing (mesh sampling noise -> ripples)
            Rp = np.pad(R, ((1, 1), (0, 0)), mode='edge')
            R = 0.4 * R + 0.15 * (Rp[:-2] + Rp[2:] + np.roll(R, 1, 1) + np.roll(R, -1, 1))
        self.R = R

    def axis(self, z):
        return np.interp(z, self.zc, self.cx), np.interp(z, self.zc, self.cy)

    def radius(self, z, th):
        fz = np.clip((z - self.z0) / self.dzt, 0, self.R.shape[0] - 1.001); ft = (th % (2 * np.pi)) / (2 * np.pi) * self.nth
        i0 = fz.astype(int); a = fz - i0; j0 = ft.astype(int) % self.nth; j1 = (j0 + 1) % self.nth; b = ft - np.floor(ft)
        R = self.R
        return (R[i0, j0] * (1 - a) * (1 - b) + R[i0 + 1, j0] * a * (1 - b) + R[i0, j1] * (1 - a) * b + R[i0 + 1, j1] * a * b)


# ------------------------------------------------------------------------------------------ session / camera
class Session:
    def __init__(self):
        s = json.load(open(os.path.join(SA, 'replay_session.json')))
        self.s = s
        self.t = np.array(s['t']); self.x = np.array(s['x']); self.y = np.array(s['y']); self.knee_v = np.array(s['knee'])
        self.presses = s['presses']; self.vs = s['viewSwitch']; self.moves = s['camMoves']

    def cursor(self, t):
        return float(np.interp(t, self.t, self.x)), float(np.interp(t, self.t, self.y))

    def knee(self, t):
        return float(np.interp(t, self.t, self.knee_v))


VIEWS = [((0.0877, -1.2622, 0.4921), (0.1046, -0.0082, 0.5604), 87.11), ((-0.0495, -1.1030, 0.1862), (-0.0488, 0.0114, 0.1638), 86.42)]


def smoother(x):
    x = min(max(x, 0.0), 1.0); return x * x * x * (x * (x * 6 - 15) + 10)


def cam_params(S, t):
    w = smoother((t - S.vs[0]) / (S.vs[1] - S.vs[0]))
    (L1, T1, f1), (L2, T2, f2) = VIEWS
    loc = np.array(L1) + (np.array(L2) - np.array(L1)) * w; tgt = np.array(T1) + (np.array(T2) - np.array(T1)) * w
    lens = f1 + (f2 - f1) * w
    for m in S.moves:
        if m['i0'] <= t <= m['o1']:
            mm = smoother((t - m['i0']) / (m['i1'] - m['i0'])) if t < m['i1'] else (1.0 if t < m['o0'] else 1.0 - smoother((t - m['o0']) / (m['o1'] - m['o0'])))
            ang = math.radians(m['orbit']) * mm; d = loc - tgt
            d = np.array([d[0] * math.cos(ang) - d[1] * math.sin(ang), d[0] * math.sin(ang) + d[1] * math.cos(ang), d[2]])
            loc = tgt + d * (1.0 + (m['dolly'] - 1.0) * mm)
    return loc, tgt, lens


def cam_frame(loc, tgt):
    f = (tgt - loc); f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r); u = np.cross(r, f)
    return f, r, u


ASPECT = 1890 / 1080


def ray(S, t, x, y):
    loc, tgt, lens = cam_params(S, t); f, r, u = cam_frame(loc, tgt); k = lens / 36.0
    d = f + r * ((x - 0.5) / (ASPECT * k)) + u * ((0.5 - y) / k)
    return loc, d / np.linalg.norm(d), f


def project(S, t, P):
    loc, tgt, lens = cam_params(S, t); f, r, u = cam_frame(loc, tgt); k = lens / 36.0
    q = P - loc; zc = q @ f
    return 0.5 + (q @ r) / zc * ASPECT * k, 0.5 - (q @ u) / zc * k, zc


# ------------------------------------------------------------------------------------------ pose (knee flinch + sway)
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0); return t * t * (3 - 2 * t)


def pose_dx(P, t, knee):
    z = P[:, 2]; side = np.sign(P[:, 0])
    prof = np.where(z >= 0.47, smoothstep(0.80, 0.47, z), smoothstep(0.12, 0.47, z))
    K = np.where(side > 0, 0.010, 0.028)
    dx = -side * K * knee * prof * smoothstep(0.0, 0.035, np.abs(P[:, 0]))
    sway = 0.0022 * math.sin(2 * math.pi * 0.23 * t) + 0.0012 * math.sin(2 * math.pi * 0.61 * t + 1.3)
    return dx + sway * smoothstep(0.08, 0.9, z)


# ------------------------------------------------------------------------------------------ cloth
class Cloth:
    def __init__(self, leg, prm):
        self.leg, self.p = leg, prm
        NT = int(prm['NT']); z = np.arange(prm['Z0'], prm['Z1'] + 1e-9, prm['DZ']); NZ = len(z)
        self.NT, self.NZ = NT, NZ
        th = np.arange(NT) / NT * 2 * np.pi
        Z, TH = np.meshgrid(z, th, indexing='ij')
        ax, ay = leg.axis(Z.ravel()); R = leg.radius(Z.ravel(), TH.ravel())
        self.rest = np.stack([ax + R * np.sin(TH.ravel()), ay + R * np.cos(TH.ravel()), Z.ravel()], 1)
        self.th = TH.ravel(); n = NZ * NT
        self.x = self.rest.copy(); self.v = np.zeros_like(self.x)
        self.w = np.ones(n); self.w[:NT] = 0; self.w[-NT:] = 0           # pinned rows (waist side / ankle)
        idx = np.arange(n).reshape(NZ, NT)
        self.groups = []

        def add(a, b, pre, lim, comp, kind):
            a = a.ravel(); b = b.ravel()
            L = np.linalg.norm(self.rest[b] - self.rest[a], axis=1)
            self.groups.append(dict(a=a, b=b, L=L / (1 + pre), Lmax=L * (1 + lim), comp=comp, kind=kind, lam=np.zeros(len(a))))
        c, v, s = prm['pre_c'], prm['pre_v'], 0.5 * (prm['pre_c'] + prm['pre_v'])
        for par in (0, 1):                                                  # around (wraps), 2 colours
            add(idx[:, par::2], np.roll(idx, -1, 1)[:, par::2], c, prm['lim_c'], prm['comp_s'], 'c')
        for par in (0, 1):                                                  # along
            add(idx[par:-1:2, :], idx[par + 1::2, :][:len(idx[par:-1:2, :])], v, prm['lim_v'], prm['comp_s'], 'v')
        for par in (0, 1):                                                  # shear, both diagonals
            add(idx[par:-1:2, :], np.roll(idx, -1, 1)[par + 1::2, :][:len(idx[par:-1:2, :])], s, prm['lim_s'], prm['comp_s'], 's')
            add(np.roll(idx, -1, 1)[par:-1:2, :], idx[par + 1::2, :][:len(idx[par:-1:2, :])], s, prm['lim_s'], prm['comp_s'], 's')
        for par in (0, 1):                                                  # bending (skip one), around
            sel = idx[:, [j for j in range(NT) if (j % 4) // 2 == par]]
            add(sel, np.roll(idx, -2, 1)[:, [j for j in range(NT) if (j % 4) // 2 == par]], 0.0, 9.0, prm['comp_b'], 'b')
        for par in (0, 1):                                                  # bending, along
            rows = [i for i in range(NZ - 2) if (i % 4) // 2 == par]
            add(idx[rows, :], idx[[i + 2 for i in rows], :], 0.0, 9.0, prm['comp_b'], 'b')
        self.grab = None
        self.A = self.rest.copy()                                           # skin anchors (rest space)
        self.area0 = self.cell_area(self.rest)

    def posed_rest(self, t, knee):
        r = self.rest.copy(); r[:, 0] += pose_dx(self.rest, t, knee); return r

    def cell_area(self, X):
        NZ, NT = self.NZ, self.NT
        P = X.reshape(NZ, NT, 3); Q = np.roll(P, -1, 1)
        a = np.cross(Q[:-1] - P[:-1], P[1:] - P[:-1]); b = np.cross(np.roll(P, -1, 1)[1:] - Q[:-1], P[1:] - Q[:-1])
        return 0.5 * (np.linalg.norm(a, axis=2) + np.linalg.norm(b, axis=2))

    def step(self, dt, t, knee, target):
        p = self.p
        r_prev = getattr(self, '_rposed', None)
        rp = self.posed_rest(t, knee); self._rposed = rp
        if r_prev is None:
            r_prev = rp
        x0 = self.x.copy()
        self.v[:, 2] -= p['gravity'] * dt
        self.v *= math.exp(-p['damp'] * dt)
        self.hand_force = 0.0
        if self.grab is not None and target is not None:               # the hand pulls (a force, not a constraint)
            gi, off = self.grab
            k = p['k_grab']; c = 2.0 * math.sqrt(k)
            dev = (target + off) - self.x[gi]
            self.v[gi] += (k * dev - c * self.v[gi]) * dt
            self.hand_force = float(np.linalg.norm(dev, axis=1).mean() * k)   # per-particle accel, ~ tension proxy
        x = self.x + self.v * dt
        x[self.w == 0] = rp[self.w == 0]
        dt2 = dt * dt
        for g in self.groups:
            g['lam'][:] = 0
        self._flip = not getattr(self, '_flip', False)
        order = self.groups if self._flip else self.groups[::-1]
        for it in range(int(p['ITERS'])):
            for g in order:
                a, b = g['a'], g['b']
                d = x[b] - x[a]; ln = np.maximum(np.linalg.norm(d, axis=1), 1e-9); n = d / ln[:, None]
                wa, wb = self.w[a], self.w[b]; ws = wa + wb
                at = g['comp'] / dt2
                C = ln - g['L']
                if g['kind'] == 'b':
                    C = np.minimum(C, 0.0)                                   # bending pairs only resist folding in
                dl = (-C - at * g['lam']) / (ws + at)
                g['lam'] += dl
                x[a] -= (wa * dl)[:, None] * n; x[b] += (wb * dl)[:, None] * n
                if g['kind'] != 'b':                                        # hard strain limit (the knit locks up)
                    d = x[b] - x[a]; ln = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
                    over = np.maximum(ln - g['Lmax'], 0.0)
                    kk = over / np.maximum(ws, 1e-9)
                    n = d / ln[:, None]
                    x[a] += (wa * kk)[:, None] * n; x[b] -= (wb * kk)[:, None] * n
            # rest attachment (elastic recovery), zero-length XPBD
            at = p['comp_att'] / dt2
            x += (rp - x) * (self.w / (self.w + at))[:, None]
        # --- collision with the leg (radial height field around the posed axis) + friction
        z = x[:, 2]; ax, ay = self.leg.axis(z); ax = ax + pose_dx(np.stack([ax, ay, z], 1), t, knee)
        dx_, dy_ = x[:, 0] - ax, x[:, 1] - ay; rho = np.maximum(np.hypot(dx_, dy_), 1e-9)
        th = np.arctan2(dx_, dy_); R = self.leg.radius(z, th)
        pen = np.maximum(R - rho, 0.0)
        nx, ny = dx_ / rho, dy_ / rho
        x[:, 0] += nx * pen; x[:, 1] += ny * pen
        # stick-slip grip: particles touching the skin are held (elastically) to a skin anchor; the anchor slides
        # once the tangential shift exceeds 'slip' and slowly creeps back to rest (the knit relaxes)
        rho2 = np.maximum(np.hypot(x[:, 0] - ax, x[:, 1] - ay), 1e-9)
        cont = (rho2 - R) < 0.0004
        if self.grab is not None:
            cont[self.grab[0]] = False                                      # pinched by the fingers, not on the skin
        Ap = self.A + (rp - self.rest)
        e = x - Ap
        nrm = np.stack([nx, ny, np.zeros_like(nx)], 1)
        tc = np.stack([ny, -nx, np.zeros_like(nx)], 1)                     # around the leg (tangent of the circle)
        ea = (e * tc).sum(1); ez = e[:, 2]                                   # shift around / along
        # anisotropic stick-slip: rotating the tube locally is easy, sliding it along the leg is not
        sa = p['slip'] / max(p['grip_around'], 1e-6); sz = p['slip']
        oa = cont & (np.abs(ea) > sa); oz = cont & (np.abs(ez) > sz)
        if oa.any():
            k = (np.abs(ea[oa]) - sa) * np.sign(ea[oa]); self.A[oa] += tc[oa] * k[:, None]; ea[oa] -= k
        if oz.any():
            k = (np.abs(ez[oz]) - sz) * np.sign(ez[oz]); self.A[oz, 2] += k; ez[oz] -= k
        at = p['comp_fric'] / dt2
        ga = 1.0 / (1.0 + at / max(p['grip_around'], 1e-6)); gz = 1.0 / (1.0 + at)
        x[cont] -= tc[cont] * (ea[cont] * ga)[:, None]
        x[cont, 2] -= ez[cont] * gz
        self.A += (self.rest - self.A) * min(dt / p['anchor_tau'], 1.0)
        x[self.w == 0] = rp[self.w == 0]
        self.v = (x - x0) / dt
        self.x = x

    def settle(self, dt, t, knee, seconds=0.6):
        """Equilibrium of the pre-stretched tube on the leg without skin grip; becomes the rest state."""
        mf = self.p['comp_fric']; self.p['comp_fric'] = 1e9
        ma = self.p['comp_att']; self.p['comp_att'] = 1e9
        for _ in range(int(seconds / dt)):
            self.step(dt, t, 0.0, None)
        self.p['comp_fric'] = mf; self.p['comp_att'] = ma
        self.rest = self.x.copy(); self.A = self.rest.copy(); self.v[:] = 0
        self._rposed = None
        self.area0 = self.cell_area(self.rest)

    def start_grab(self, g):
        p = self.p
        d = np.linalg.norm(self.x - g, axis=1)
        gi = np.nonzero((d < p['grab_r']) & (self.w > 0))[0]
        if len(gi) == 0:
            gi = np.array([np.argmin(d)])
        c = self.x[gi].mean(0)
        self.grab = (gi, (self.x[gi] - c) * p['grab_pinch'])
        return c

    def stretch(self):
        return self.cell_area(self.x) / self.area0


# ------------------------------------------------------------------------------------------ run + visualise
def run(args, prm):
    nv, subs, ch = load_smesh(os.path.join(SA, 'tights.smesh'))
    P = ch['position'][:, [0, 2, 1]].astype(np.float64)
    u = ch['uv0'][:, 0].astype(np.float64) % 1.0
    S = Session()
    pr = S.presses[args.press]
    side = pr['side']
    leg = Leg(P, u, side)
    other = Leg(P, u, -side)
    cl = Cloth(leg, prm)
    oc = Cloth(other, prm)
    print('[proto] leg side %d: grid %d x %d = %d particles, %d constraint groups' % (side, cl.NZ, cl.NT, cl.NZ * cl.NT, len(cl.groups)))
    times = sorted(float(s) for s in args.times.split(','))
    t = pr['t0'] - 0.3; dt = 1.0 / prm['HZ']
    cl.settle(dt, t, S.knee(t))
    # run in at rest
    for _ in range(int(0.3 * prm['HZ'])):
        cl.step(dt, t, S.knee(t), None); t += dt
    W0 = None; out = []
    while t < times[-1] + 1e-9:
        target = None
        if t >= pr['t0'] and cl.grab is None and not getattr(cl, '_grabbed', False):
            o, dvec, f = ray(S, t, *S.cursor(t))
            rel = cl.x - o; along = rel @ dvec; perp = np.linalg.norm(rel - np.outer(along, dvec), axis=1)
            score = perp + 0.02 * np.maximum(along - along.min(), 0)
            j = int(np.argmin(score))
            g = cl.start_grab(cl.x[j]); depth = (g - o) @ f
            W0 = g.copy(); cl._depth = depth; cl._grabbed = True
            print('[proto] grab at t=%.2f particle %d z=%.3f (ray miss %.1f mm)' % (t, j, g[2], perp[j] * 1000))
        if cl.grab is not None and t <= pr['t1']:
            o, dvec, f = ray(S, t, *S.cursor(t))
            W = o + dvec * (cl._depth / max(dvec @ f, 1e-6))
            if not hasattr(cl, '_W0c'):
                cl._W0c = W
            D = W - cl._W0c
            vv = D + (o - W0) / np.linalg.norm(o - W0) * (prm['fwd'] * np.linalg.norm(D))
            if np.linalg.norm(vv) > prm['cap']:
                vv = vv / np.linalg.norm(vv) * prm['cap']
            target = W0 + vv
        elif cl.grab is not None and t > pr['t1']:
            cl.grab = None
        cl.step(dt, t, S.knee(t), target)
        t += dt
        while times and t >= times[0] - 1e-9:
            tt = times.pop(0)
            st = cl.stretch()
            out.append((tt, cl.x.copy(), st, target))
            print('[proto] t=%.2f  hand %.0f  max disp %.1f mm  stretch max %.2f  grab target %s' % (
                tt, getattr(cl, 'hand_force', 0.0), np.linalg.norm(cl.x - cl._rposed, axis=1).max() * 1000, st.max(),
                None if target is None else np.round(target, 3)))
        if not times:
            break
    return S, cl, oc, out


def render(S, cl, oc, frames, out_dir, video):
    import subprocess
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    W, H = 540, 945
    for (t, X, st, target) in frames:
        orig = os.path.join(out_dir, 'orig_%.2f.png' % t)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '%.3f' % t, '-i', video, '-frames:v', '1', '-vf',
                        'crop=1150:2010:20:150,scale=%d:%d' % (W, H), orig], check=True)
        bg = Image.open(orig).convert('RGB')
        img = Image.new('RGB', (W, H), (20, 26, 34)); dr = ImageDraw.Draw(img, 'RGBA')
        loc, tgt, lens = cam_params(S, t)
        polys = []
        for c, XX, ss in ((oc, oc.x, None), (cl, X, st)):
            P = XX.reshape(c.NZ, c.NT, 3)
            px, py, pz = project(S, t, XX)
            px = px.reshape(c.NZ, c.NT) * W; py = py.reshape(c.NZ, c.NT) * H; pz = pz.reshape(c.NZ, c.NT)
            for i in range(c.NZ - 1):
                for j in range(c.NT):
                    j1 = (j + 1) % c.NT
                    q = [(px[i, j], py[i, j]), (px[i, j1], py[i, j1]), (px[i + 1, j1], py[i + 1, j1]), (px[i + 1, j], py[i + 1, j])]
                    a = P[i, j1] - P[i, j]; b = P[i + 1, j] - P[i, j]; n = np.cross(b, a); nn = np.linalg.norm(n)
                    if nn < 1e-12:
                        continue
                    n /= nn; vdir = loc - P[i, j]; vdir /= np.linalg.norm(vdir)
                    facing = n @ vdir
                    s = 1.0 if ss is None else ss[i, j]
                    polys.append((pz[i, j], q, facing, s))
        polys.sort(key=lambda e: -e[0])
        for z, q, facing, s in polys:
            fa = abs(facing)
            # sheer: darker at grazing angles (more yarn in the line of sight), lighter where stretched
            cov = min(0.95, 0.55 + 0.4 * (1 - fa) ** 0.7) / max(s, 0.5) ** 0.75
            base = np.array([196, 128, 112]) * (0.35 + 0.65 * fa)
            col = base * (1 - cov) + np.array([12, 10, 12]) * cov
            dr.polygon(q, fill=tuple(int(v) for v in col) + (255,))
        comp = Image.blend(bg, img, 0.5)
        Image.fromarray(np.concatenate([np.array(bg), np.array(img), np.array(comp)], 1)).save(os.path.join(out_dir, 'cmp_%.2f.png' % t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--press', type=int, default=9)
    ap.add_argument('--times', default='26.95,27.25,27.55,27.85')
    ap.add_argument('--out', required=True)
    ap.add_argument('--video', default='')
    ap.add_argument('--param', nargs='*', default=[])
    args = ap.parse_args()
    prm = dict(DEFAULTS)
    for kv in args.param:
        k, v = kv.split('='); prm[k] = float(v)
    S, cl, oc, frames = run(args, prm)
    if args.video:
        render(S, cl, oc, frames, args.out, args.video)


if __name__ == '__main__':
    main()
