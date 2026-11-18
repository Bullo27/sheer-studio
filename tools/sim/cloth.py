# SHEER physics prototype: the stocking as a pre-stretched orthotropic spring net on a frictional leg.
# Python side (setup, damage -> spring coefficients, hand); the substep kernel is tools/sim/sheer_cloth.c.
# One lattice per leg: NV rows (along the leg, the knit's wale direction) x NU columns (around, course direction).
import os, math, ctypes, subprocess, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

class CParams(ctypes.Structure):
    _fields_ = [('NV', ctypes.c_int), ('NU', ctypes.c_int)] + [(n, ctypes.c_float) for n in (
        'y0', 'dy', 'lock_u', 'lock_v', 'lock_d', 'Su', 'Sv', 'Sd', 'comp', 'lad_slack', 'lad_k', 'lad_lock', 'Sl',
        'mu_s', 'mu_k', 'alpha', 'damp', 'visc', 'quench', 'mix', 'cfl', 'kfloor', 'trust', 'gather')] + [('hand', ctypes.c_float * 3)]

class Params:
    # --- fabric (stiffnesses are relative: only ratios matter, the masses are fictitious)
    girth0 = 0.150; girth1 = 0.245        # knitted tube girth (m) at the bottom / top row (linear in between)
    lam_v = 1.22                          # lengthwise wearing stretch
    Eu = 1.0; Ev = 0.9; Gd = 0.22         # course / wale / shear moduli
    lock_u = 2.75; lock_v = 1.62; lock_d = 2.3   # stretch (vs natural) where the knit locks
    Su = 91.0; Sv = 200.0; Sd = 60.0      # lock stiffening: f = (lam - 1) + S * max(0, lam - lock)^2
    comp = 0.04                           # compressive stiffness fraction (wrinkling membrane)
    # a dropped wale leaves the course yarn of its loops as straight floats (the rungs of a ladder): slack until the
    # cell is lad_slack x its natural width, then a straight yarn; almost nothing left along the wale or in shear
    lad_slack = 3.3; lad_k = 0.6; lad_lock = 1.0; Sl = 150.0; lad_v = 0.03; lad_d = 0.02
    # --- failure (same units as the law f): yarn breaks -> hole; loops unravel along the wale -> ladder
    # a worn stocking is nowhere near breaking: the yarn takes ~30x the hoop load it carries on the thigh
    str_u = 30.0; str_v = 30.0; str_l = 50.0
    f_run = 1.25                          # hoop load that pulls the next loop of a damaged wale out
    nz_str = 0.22; nz_run = 0.22          # log-normal scatter of strength / run resistance
    # --- contact
    mu_s = 0.45; mu_k = 0.38
    # --- solver
    alpha = 1.0; damp = 0.012; visc = 0.08
    quench = 0.5; mix = 0.1; cfl = 0.3; kfloor = 0.25; trust = 0.03    # per-node FIRE quench / steering, travel limit (x shortest thread)
    # --- hand
    hand_radius = 0.0075; gather = 0.3

_lib = None
def lib():
    global _lib
    if _lib is None:
        so = os.path.join(HERE, 'libsheer.so'); src = os.path.join(HERE, 'sheer_cloth.c')
        if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
            subprocess.check_call(['gcc', '-O3', '-march=native', '-ffast-math', '-fopenmp', '-shared', '-fPIC', '-o', so, src, '-lm'])
        _lib = ctypes.CDLL(so)
    return _lib

def fp(a): return a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

class Cloth:
    def __init__(self, geom, prm=None):
        self.P = P = prm or Params()
        f32 = lambda a: np.ascontiguousarray(a, dtype=np.float32)
        self.X = X = f32(geom['X'])
        self.NV, self.NU = X.shape[:2]; NV, NU = self.NV, self.NU
        self.y0 = float(geom['y'][0]); self.dy = float(geom['y'][1] - geom['y'][0])
        R = geom['R'].astype(np.float64); dth = 2 * math.pi / NU
        Rt = (np.roll(R, -1, 1) - np.roll(R, 1, 1)) / (2 * dth)
        Ry = np.gradient(R, self.dy, axis=0)
        self.Rtex = f32(np.stack([R, Rt, Ry], -1))                        # (NV, NU, 3)
        self.axtex = f32(np.stack([geom['ax'], geom['az'], np.gradient(geom['ax'], self.dy), np.gradient(geom['az'], self.dy)], -1))
        Xd = X.astype(np.float64)
        du = np.linalg.norm(np.roll(Xd, -1, 1) - Xd, axis=-1); dv = np.linalg.norm(Xd[1:] - Xd[:-1], axis=-1)
        self.girth = du.sum(1)
        nat = P.girth0 + (P.girth1 - P.girth0) * np.linspace(0, 1, NV)
        self.lam_u_row = self.girth / nat
        Lu0 = du / self.lam_u_row[:, None]; Lv0 = dv / P.lam_v
        wu = 0.5 * (Lu0[:-1] + Lu0[1:]); wv = 0.5 * (Lv0 + np.roll(Lv0, -1, 1))
        Ld0 = np.sqrt(wu ** 2 + wv ** 2)
        self.Lu0 = f32(Lu0); self.Lv0 = f32(np.concatenate([Lv0, Lv0[-1:]])); self.Ld0 = f32(np.concatenate([Ld0, Ld0[-1:]]))
        self.wu = wu; self.wv = wv; self.kd_geo = Ld0 ** 3 / (2 * wu * wv); self.area0 = (wu * wv).astype(np.float32)
        self.x = X.copy(); self.v = np.zeros_like(X); self.xb = X.copy(); self.vb = np.zeros_like(X)
        self.S = np.zeros((NV - 1, NU), np.uint8)
        self.flags = np.zeros((NV, NU), np.uint8); self.flags[0] = 1; self.flags[-1] = 1
        self.off = np.zeros_like(X); self.Nn = np.zeros((NV, NU), np.float32)
        self.hand = np.zeros(3, np.float32); self.hand_force = np.zeros(3, np.float32)
        self.gather_now = 1.0; self.grabbed = False
        rng = np.random.default_rng(1234 + int(1000 * abs(float(X[0, 0, 0]))))
        from scipy.ndimage import gaussian_filter
        def corr(sig):
            g = gaussian_filter(rng.standard_normal((NV - 1, NU)), sig, mode=('nearest', 'wrap')); return g / g.std()
        self.nzs = np.exp(P.nz_str * (0.7 * corr(4.0) + 0.5 * corr(1.2) + 0.5 * rng.standard_normal((NV - 1, NU))))
        colr = gaussian_filter(rng.standard_normal((NV - 1, NU)), (10.0, 0.0), mode='nearest'); colr /= colr.std()
        self.nzr = np.exp(P.nz_run * (0.8 * colr + 0.6 * rng.standard_normal((NV - 1, NU))))
        self.events = 0
        self.refresh_state()
        r = lambda a, dj, di: np.roll(np.roll(a, dj, 0), di, 1)
        ku = self.Au_i / self.Lu0; kv = self.Av / self.Lv0; kd = self.Ad / self.Ld0
        kv[-1] = 0; kd[-1] = 0
        self.K0 = np.ascontiguousarray(ku + r(ku, 0, 1) + kv + r(kv, 1, 0) + kd + r(kd, 0, 1) + r(kd, 1, 0) + r(kd, 1, 1), np.float32)

    def cparams(self):
        P = self.P; c = CParams()
        c.NV, c.NU, c.y0, c.dy = self.NV, self.NU, self.y0, self.dy
        for n in ('lock_u', 'lock_v', 'lock_d', 'Su', 'Sv', 'Sd', 'comp', 'lad_slack', 'lad_k', 'lad_lock', 'Sl', 'mu_s', 'mu_k', 'alpha', 'damp', 'visc', 'quench', 'mix', 'cfl', 'kfloor', 'trust'):
            setattr(c, n, getattr(P, n))
        c.gather = self.gather_now
        return c

    # ---- damage state -> spring coefficients
    def refresh_state(self):
        P = self.P; S = self.S; NU = self.NU
        intact = (S == 0).astype(np.float64); lad = (S == 1).astype(np.float64)
        z = np.zeros((1, NU))
        wi = self.wv * intact; wl = self.wv * lad
        self.Au_i = np.ascontiguousarray(P.Eu * 0.5 * (np.concatenate([z, wi]) + np.concatenate([wi, z])), np.float32)
        self.Au_l = np.ascontiguousarray(P.Eu * 0.5 * (np.concatenate([z, wl]) + np.concatenate([wl, z])), np.float32)
        ci = self.wu * (intact + P.lad_v * lad)
        Av = P.Ev * 0.5 * (np.roll(ci, 1, 1) + ci)
        self.Av = np.ascontiguousarray(np.concatenate([Av, z]), np.float32)
        Ad = P.Gd * self.kd_geo * (intact + P.lad_d * lad)
        self.Ad = np.ascontiguousarray(np.concatenate([Ad, z]), np.float32)
        live = S != 2; lz = np.zeros((1, NU), bool)
        a = np.concatenate([lz, live]); b = np.concatenate([live, lz])
        orphan = ~(a | b | np.roll(a, 1, 1) | np.roll(b, 1, 1))
        self.flags = (self.flags & 3) | (orphan.astype(np.uint8) * 4)
        self.flags = np.ascontiguousarray(self.flags)

    def step(self, nsub, hand0=None, hand1=None):
        if hand0 is None: hand0 = self.hand
        if hand1 is None: hand1 = hand0
        h0 = np.ascontiguousarray(hand0, np.float32); h1 = np.ascontiguousarray(hand1, np.float32)
        c = self.cparams()
        lib().sheer_step(ctypes.byref(c), ctypes.c_int(nsub), fp(self.x), fp(self.v), fp(self.xb), fp(self.vb),
                         fp(self.Lu0), fp(self.Lv0), fp(self.Ld0), fp(self.Au_i), fp(self.Au_l), fp(self.Av), fp(self.Ad), fp(self.K0),
                         self.flags.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), fp(self.off), fp(self.Rtex), fp(self.axtex),
                         fp(self.Nn), fp(h0), fp(h1), fp(self.hand_force))
        self.hand = h1.copy()

    # ---- hand
    def grab(self, p, radius=None):
        r = radius or self.P.hand_radius
        d = np.linalg.norm(self.x - np.asarray(p, np.float32), axis=-1)
        sel = (d < r) & ((self.flags & 1) == 0)
        if not sel.any(): sel = np.zeros_like(sel); sel.flat[np.argmin(d + (self.flags & 1) * 1e3)] = True
        c = self.x[sel].mean(0)
        self.off[:] = 0; self.off[sel] = self.x[sel] - c
        self.flags = np.ascontiguousarray((self.flags & ~np.uint8(2)) | (sel.astype(np.uint8) * 2))
        self.hand = c.astype(np.float32).copy(); self.gather_now = 1.0; self.grabbed = True
        return c

    def release(self):
        held = (self.flags & 2) != 0; self.v[held] = 0; self.vb[held] = 0
        self.flags = np.ascontiguousarray(self.flags & ~np.uint8(2)); self.grabbed = False; self.hand_force[:] = 0

    # ---- diagnostics
    def stretches(self):
        """Edge stretches relative to the natural lengths: lam_u (NV, NU), lam_v (NV-1, NU)."""
        x = self.x.astype(np.float64)
        lu = np.linalg.norm(np.roll(x, -1, 1) - x, axis=-1) / self.Lu0
        lv = np.linalg.norm(x[1:] - x[:-1], axis=-1) / self.Lv0[:-1]
        return lu, lv

    # ---- damage: local rules on the cells (GPU-portable: each cell reads its own edges and its 8 neighbours)
    @staticmethod
    def law_np(lam, lock, S):
        o = np.maximum(lam - lock, 0.0)
        return np.maximum(lam - 1.0, 0.0) + S * o * o

    def cell_loads(self):
        P = self.P
        lu, lv = self.stretches()
        cu = 0.5 * (lu[:-1] + lu[1:]); cv = 0.5 * (lv + np.roll(lv, -1, 1))
        return cu, cv, self.law_np(cu, P.lock_u, P.Su), self.law_np(cv, P.lock_v, P.Sv), self.law_np(cu / P.lad_slack, P.lad_lock, P.Sl)

    def damage(self):
        """One damage update (call every few substeps). Returns the number of cells that changed."""
        from scipy.ndimage import maximum_filter
        P = self.P; S = self.S
        cu, cv, fu, fv, fl = self.cell_loads()
        intact = S == 0; lad = S == 1; hole = S == 2
        q = np.where(intact, np.maximum(fu / P.str_u, fv / P.str_v), np.where(lad, fl / P.str_l, 0.0)) / self.nzs
        brk = (q > 1.0) & (q >= maximum_filter(q, size=3, mode=('nearest', 'wrap')))
        # a float that is broken anywhere carries nothing: ladder cells beside a hole in the same course
        lat = lad & (np.roll(hole, 1, 1) | np.roll(hole, -1, 1))
        dmg = S >= 1
        nb = np.zeros_like(dmg); nb[1:] |= dmg[:-1]; nb[:-1] |= dmg[1:]
        run = intact & nb & (fu > P.f_run * self.nzr) & ~brk
        n = int(run.sum() + brk.sum() + lat.sum())
        if n and getattr(self, 'dbg', None) is not None:
            bu = brk & intact & (fu / P.str_u >= fv / P.str_v)
            self.dbg.append(dict(bu=np.argwhere(bu), bv=np.argwhere(brk & intact & ~bu), bl=np.argwhere(brk & lad), lat=np.argwhere(lat), run=np.argwhere(run),
                                 qmax=float(q.max())))
        if n:
            S[run] = 1; S[brk | lat] = 2
            self.events += n
            self.refresh_state()
        return n

    def islands(self):
        """Pieces of fabric no longer connected to the pinned rows: returns a bool cell mask."""
        from scipy.ndimage import label
        live = self.S != 2
        ext = np.concatenate([live, live[:, :1]], 1)                      # close the seam for the labelling
        lab, n = label(ext)
        # merge labels across the periodic seam
        par = np.arange(n + 1)
        def find(a):
            while par[a] != a: par[a] = par[par[a]]; a = par[a]
            return a
        for a, b in zip(lab[:, 0], lab[:, -1]):
            if a and b:
                ra, rb = find(a), find(b)
                if ra != rb: par[ra] = rb
        root = np.array([find(a) for a in range(n + 1)])
        lab = root[lab[:, :-1]]
        keep = np.zeros(n + 1, bool); keep[np.unique(lab[0])] = True; keep[np.unique(lab[-1])] = True; keep[0] = True
        return live & ~keep[lab]

    def drop_islands(self):
        isl = self.islands()
        if not isl.any(): return False
        # is the hand holding a detached piece?
        held = (self.flags & 2) != 0
        if held.any():
            a = isl; hc = np.zeros_like(held)
            hc[:-1] |= a; hc[1:] |= a; hc[:-1] |= np.roll(a, 1, 1); hc[1:] |= np.roll(a, 1, 1)
            if (held & hc).any() and not (held & ~hc).any(): self.release(); self.torn_off = True
        self.S[isl] = 2; self.refresh_state()
        return True
