# Drive the leashed-cloth prototype with cursor paths measured in the original video and render comparison sheets.
#   python3 tools/sim/run_leash.py thigh|calf|drag [out_dir]
import os, sys, json, math, time, numpy as np, torch
sys.path.insert(0, os.path.dirname(__file__))
import geom, leash, render
from PIL import Image

PINCH_LIFT = float(os.environ.get('PINCH_LIFT', '0.009'))
SNAP = os.environ.get('SNAP', '1') == '1'       # hand mapping: the patch slides on the leg under the cursor (see snap())
SCR = os.environ.get('SCRATCH', os.path.join(os.path.dirname(os.path.abspath(__file__)), '_scratch'))
REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref_data')      # cursor tracks + frames of the original (kept in the project)
if not os.path.isdir(REF): REF = SCR

class Pull:
    """Cursor drag -> pinch offset.  Measured in the original (presses 5 and 9, two different views): across the leg the
    pinch follows the cursor 1:1, along the leg it only gets ~0.57 of the cursor's travel (the fabric is held along its
    length), and the offset saturates at r_max.  Past that the pinch only creeps after the hand, and it follows again
    as soon as the hand comes back inside the pulled length."""
    def __init__(self, r_max=0.085, tau=0.03, tau_locked=0.6, along=0.57, axis=None, r_max_on=0.073, around_on=0.6):
        self.r_air, self.tau, self.tau_locked, self.along = r_max, tau, tau_locked, along
        self.r_on, self.around_on = r_max_on, around_on; self.r_max = r_max
        self.axis = None if axis is None else np.asarray(axis, np.float32) / np.linalg.norm(axis)
        self.S = np.zeros(3, np.float32)

    def update(self, C, dt, on_leg=0.0):
        """on_leg: 1 while the cursor is over the leg (the patch is dragged over the skin: there it is the turn around the leg
        that binds, measured on the original's thigh drag), 0 once it is past the outline."""
        if self.axis is not None:
            al = float(C @ self.axis) * self.axis; ar = C - al
            C = al * (self.along + (1 - self.along) * on_leg) + ar * (1 + (self.around_on - 1) * on_leg)
        self.r_max = self.r_air + (self.r_on - self.r_air) * on_leg
        L = float(np.linalg.norm(C)); s = float(np.linalg.norm(self.S))
        T = C * min(1.0, self.r_max / max(L, 1e-9))
        sat = min(max((s / self.r_max - 0.7) / 0.3, 0.0), 1.0); sat = sat * sat * (3 - 2 * sat)
        if L < s: sat = 0.0
        tau = self.tau + (self.tau_locked - self.tau) * sat
        self.S = self.S + (T - self.S) * (1 - math.exp(-dt / tau))
        return self.S

def snap(c, eye, W, want_q=False):
    """Where the hand holds the pinched patch, for a cursor ray eye -> W.  Measured in the original: its sails lie
    entirely beyond the leg's outline and a tent only shows once the hand has travelled the distance to the outline, so
    the patch slides along the skin while the cursor is over the leg and leaves the leg sideways, in the plane of the
    leg axis facing the viewer.  p0 = the point of the ray closest to the axis, m its distance from it, R the leg's
    radius in that (sideways) direction: the patch is put at p0 moved toward the viewer by 0.9 R (1 - (m / R)^2) - a
    parabola instead of the leg's own outline, so that it does not race around the leg as the cursor nears the
    silhouette - and the leg collision then pushes it out onto the skin."""
    d = W - eye; d = d / d.norm()
    p0 = W
    for _ in range(2):
        f = float(((p0[1] - c.y0) / c.dy).clamp(0, c.NV - 1.001)); j0 = int(f); a = f - j0
        A0 = torch.stack([c.ax[j0] * (1 - a) + c.ax[j0 + 1] * a, p0[1], c.az[j0] * (1 - a) + c.az[j0 + 1] * a])
        u = torch.tensor([0.0, 1.0, 0.0], device=c.dev)        # vertical: the fitted axis leans sharply near the foot
        w0 = eye - A0; b = float((d * u).sum()); dd = float((d * w0).sum()); e = float((u * w0).sum())
        p0 = eye + ((b * e - dd) / max(1 - b * b, 1e-6)) * d
    R, dx, dz = c.radius(p0.view(1, 3))
    q = float(torch.sqrt(dx * dx + dz * dz)[0] / R[0])
    if want_q: return q
    q = min(q, 1.0)
    return p0 - d * (0.9 * float(R[0]) * (1 - q * q))

class Scene:
    def __init__(self, view='VIEW01', W=535, H=950, zoom=1.0, prm=None, NU=256, NV=320):
        self.legs = {s: geom.build_leg(s, NU=NU, NV=NV) for s in (1, -1)}
        self.cl = {s: leash.Cloth(self.legs[s], prm) for s in (1, -1)}
        V = dict(getattr(render, view)); V['lens_mm'] = V['lens_mm'] * zoom
        self.V = V; self.W, self.H = W, H
        self.set_cam(V)

    def set_cam(self, V):
        self.cam = render.Camera(W=self.W, H=self.H, **V)
        self.pv = render.Preview(self.cam, [self.cl[1].X, self.cl[-1].X])

    def node_px(self, side, j, i):
        px, py, z = self.cam.project(self.cl[side].X[j, i]); return float(px), float(py), float(z)

    def aim(self, side, j, i, px, py):
        """Slide the camera in its own plane until node (j, i) lands on the pixel (px, py)."""
        for _ in range(3):
            x, y, z = self.node_px(side, j, i)
            m = z / (self.cam.k * self.H)                       # metres per pixel at that depth
            d = (self.cam.r * ((x - px) * m) - self.cam.u * ((y - py) * m)).cpu().numpy()
            self.V['pos'] = (np.asarray(self.V['pos']) + d).tolist(); self.V['target'] = (np.asarray(self.V['target']) + d).tolist()
            self.set_cam(self.V)

    def screen_vec(self, dx_m, dy_m):
        """World vector for a displacement in the screen plane (right, down) in metres."""
        return (self.cam.r * dx_m - self.cam.u * dy_m).cpu().numpy().astype(np.float32)

    def render(self): return self.pv.render([leash.View(self.cl[1]), leash.View(self.cl[-1])])

def strain_map(c, jg, ig, path, title=''):
    """Lattice-space picture of the strains (u, v), the area ratio and the lift, centred on the grab column."""
    su, sv, ar = c.strains()
    roll = lambda a: np.roll(a, c.NU // 2 - ig, 1)[::-1]
    ar = torch.cat([ar, ar[-1:]], 0)
    su = roll(su.cpu().numpy()); sv = roll(sv.cpu().numpy()); ar = roll(ar.cpu().numpy()); h = roll(c.h.cpu().numpy())
    def pane(a, lo, hi):
        t = np.clip((a - lo) / (hi - lo), 0, 1)
        return (np.stack([t, 1 - np.abs(2 * t - 1), 1 - t], -1) * 255).astype(np.uint8)
    img = np.concatenate([pane(su, -1, 2), pane(sv, -1, 2), pane(ar, 0, 3), pane(h, 0, 0.06)], 1)
    Image.fromarray(img).save(path)
    for name, a in (('su', su), ('sv', sv)):
        k = np.unravel_index(np.argmax(a), a.shape)
        print('   %s %s max %.2f at row %d (%.0f mm from grab row) col %+d' % (title, name, a[k], c.NV - 1 - k[0], (c.NV - 1 - k[0] - jg) * c.dy * 1e3, k[1] - c.NU // 2))

def run(sc, side, j, i, path, t_end, shots, pull=None, sub_rate=None, verbose=True, t_release=None, diag=None):
    """path(t) -> (dx, dy) of the cursor from the press point, metres in the screen plane."""
    c = sc.cl[side]; P = c.P
    rate = sub_rate or P.sub_rate
    c.grab(j, i)
    j0, j1 = max(j - 4, 0), min(j + 4, c.NV - 1)
    axis = np.array([float(c.ax[j1] - c.ax[j0]), (j1 - j0) * c.dy, float(c.az[j1] - c.az[j0])], np.float32)
    pull = pull or Pull(axis=axis)
    # the column of fabric between the patch and the held ankle / top rows cannot get longer than its locked length
    jf = [P.pin_rows + P.pin_fade, c.NV - 1 - P.pin_rows - P.pin_fade]
    fix = [(c.X[min(max(jq, 0), c.NV - 1), i], max(float((c.X[j, i] - c.X[min(max(jq, 0), c.NV - 1), i]).norm()), 0.002) * (1 + P.lock_v)) for jq in jf]
    marks = {}
    frames = {}; log = []
    n = int(round(t_end * rate)); dt = 1.0 / rate; t0 = time.time(); shots = sorted(shots); k = 0
    dev = c.dev
    for s in range(n):
        t = (s + 1) * dt
        if t_release is not None and t >= t_release:
            if c.pinch_w is not None: c.release()
        else:
            dx, dy = path(t)
            Cv = sc.screen_vec(dx, dy); on = 0.0
            if SNAP:
                qc = snap(c, sc.cam.pos, c.pinch_c + torch.as_tensor(Cv, device=dev), want_q=True)
                u = min(max((qc - 0.9) / 0.2, 0.0), 1.0); on = 1.0 - u * u * (3 - 2 * u)
            S = pull.update(Cv, dt, on)
            A = c.pinch_c + torch.as_tensor(S, device=dev)
            if SNAP:
                # (over the first 2 cm the patch simply leaves the grab point in the screen plane: the snapped path does not
                #  pass through the grab point itself, and the fabric must not jump at the touch)
                u = min(float(np.linalg.norm(S)) / 0.02, 1.0); wS = u * u * (3 - 2 * u)
                A = A + (snap(c, sc.cam.pos, A) - A) * wS
            A = A.clone(); A[1] = A[1].clamp(c.y0 - 0.06, c.y0 + (c.NV - 2 - P.pin_rows) * c.dy)
            for Pf, Rf in fix:
                dv = A - Pf; ln = float(dv.norm())
                if ln > Rf: A = Pf + dv * (Rf / ln)
            uL = min(float(np.linalg.norm(S)) / 0.012, 1.0)             # the fingers hold a fold of fabric off the skin
            A, _ = c.collide(A.view(1, 3), margin=0.001 + (PINCH_LIFT - 0.001) * uL * uL * (3 - 2 * uL))
            c.pull = A[0] - c.pinch_c
        c.step(1)
        while k < len(shots) and t >= shots[k] - 1e-9:
            frames[shots[k]] = sc.render()
            px, py, _ = sc.cam.project((c.pinch_c + c.pull).view(1, 3)); marks[shots[k]] = (float(px[0]), float(py[0]))
            if diag and abs(shots[k] - diag[0]) < 1e-6: strain_map(c, j, i, diag[1], 't %.3f' % shots[k])
            su, sv, ar = c.strains()
            d = (c.x - c.X).norm(dim=-1)
            lifted = d > 0.002
            rows = lifted.any(1).nonzero().flatten(); cols = lifted.sum(1).max()
            log.append((shots[k], float(torch.as_tensor(pull.S).norm()), float(d.max()), float(su.max()), float(sv.max()), float(ar.max()), float(ar.min()),
                        (int(rows.min()), int(rows.max())) if len(rows) else (0, 0), int(cols)))
            k += 1
    if verbose:
        print('%d substeps in %.1f s' % (n, time.time() - t0))
        for (t, s, d, a, b, e, f, rr, cc) in log:
            print('  t %.3f pinch %.1f mm maxdisp %.1f mm strain u %.2f v %.2f area max %.2f min %.2f rows %s (%.0f mm) cols %d' % (
                t, s * 1e3, d * 1e3, a, b, e, f, rr, (rr[1] - rr[0]) * c.dy * 1e3, cc))
    run.marks = marks
    return frames, log

def track_path(name, G, mm_per_px, lag=0.0):
    rows = json.load(open(os.path.join(REF, 'track', name + '.json')))
    ts = np.array([r['t'] for r in rows if r['cur']]); xy = np.array([r['cur'] for r in rows if r['cur']], np.float64)
    return ts, (xy - np.asarray(G)) * mm_per_px * 1e-3

def orig_frame(name, t0, t, size):
    k = int(round((t - t0) * 60)) + 1
    f = os.path.join(REF, 'forensic', name, 'f_%03d.jpg' % k)
    return np.asarray(Image.open(f).convert('RGB').resize(size, Image.LANCZOS))

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'thigh'
    out = os.path.join(SCR, 'leash'); os.makedirs(out, exist_ok=True)
    prm = leash.Params(); tag = ''
    for a in sys.argv[2:]:                                   # overrides: name=value
        k, v = a.split('='); setattr(prm, k, type(getattr(prm, k))(float(v))); tag += '_' + a
    if what == 'thigh':
        G = (451, 694); mmpp = 0.24; t_press = 12.767
        sc = Scene('VIEW01', zoom=0.274 / mmpp, prm=prm)
        c = sc.cl[1]
        # grab: thigh, ~14.5 cm above the knee, ~28 mm inside the screen-right silhouette
        jg = int(round((0.615 - c.y0) / c.dy))
        px, py, z = sc.cam.project(c.X[jg]); px = px.cpu().numpy()
        rad = torch.stack([c.X[jg, :, 0] - c.ax[jg], c.X[jg, :, 2] - c.az[jg]], -1); view = (c.X[jg] - sc.cam.pos)[:, [0, 2]]
        facing = ((rad * view).sum(-1) < 0).cpu().numpy()
        edge = px[facing].max(); want = edge - (28.0 / mmpp) / 2
        ig = int(np.argmin(np.abs(px - want) + np.where(facing, 0, 1e6)))
        sc.aim(1, jg, ig, G[0] / 2, G[1] / 2)
        ts, xy = track_path('p5', G, mmpp)
        path = lambda t: (np.interp(t + t_press, ts, xy[:, 0]), np.interp(t + t_press, ts, xy[:, 1]))
        shots_abs = [12.917, 12.95, 12.983, 13.033, 13.1, 13.2, 13.233, 13.25, 13.267, 13.35]
        frames, log = run(sc, 1, jg, ig, path, 13.4 - t_press, [t - t_press for t in shots_abs], t_release=13.24 - t_press, diag=(13.1 - t_press, os.path.join(out, 'thigh_strain%s.png' % tag)))
        tiles = []
        for t in shots_abs:
            o = orig_frame('p5', 12.55, t, (535, 950)); m = frames[t - t_press]
            tiles.append(np.concatenate([o[150:650], m[150:650]], 0))
        render.sheet(tiles, len(tiles), os.path.join(out, 'thigh_cmp%s.jpg' % tag), scale=0.6)
        Image.fromarray(np.concatenate([orig_frame('p5', 12.55, 13.1, (535, 950)), frames[13.1 - t_press]], 1)).save(os.path.join(out, 'thigh_13.1%s.jpg' % tag), quality=92)

    if what == 'calf':
        G = (365, 1040); mmpp = 0.24; t_press = 26.85
        sc = Scene('VIEW02', zoom=0.241 / mmpp, prm=prm)
        c = sc.cl[-1]
        circ = c.L[0].sum(1).cpu().numpy(); ja = int(np.argmin(circ[:80]))
        print('ankle row', ja, 'y %.3f circumference %.3f' % (c.y0 + ja * c.dy, circ[ja]))
        jg = ja + int(round(0.065 / c.dy))
        px, py, z = sc.cam.project(c.X[jg]); px = px.cpu().numpy()
        rad = torch.stack([c.X[jg, :, 0] - c.ax[jg], c.X[jg, :, 2] - c.az[jg]], -1); view = (c.X[jg] - sc.cam.pos)[:, [0, 2]]
        facing = ((rad * view).sum(-1) < 0).cpu().numpy()
        edge = px[facing].min(); want = edge + (31.0 / mmpp) / 2
        ig = int(np.argmin(np.abs(px - want) + np.where(facing, 0, 1e6)))
        sc.aim(-1, jg, ig, G[0] / 2, G[1] / 2)
        ts, xy = track_path('p9', G, mmpp)
        path = lambda t: (np.interp(t + t_press, ts, xy[:, 0]), np.interp(t + t_press, ts, xy[:, 1]))
        shots_abs = [26.95, 27.0, 27.05, 27.1, 27.2, 27.4, 27.7, 28.0, 28.083, 28.117, 28.15, 28.25]
        frames, log = run(sc, -1, jg, ig, path, 28.3 - t_press, [t - t_press for t in shots_abs], t_release=28.09 - t_press, diag=(27.4 - t_press, os.path.join(out, 'calf_strain%s.png' % tag)))
        tiles = []
        for t in shots_abs:
            o = orig_frame('p9', 26.85, t, (535, 950)); m = frames[t - t_press]
            tiles.append(np.concatenate([o[250:900], m[250:900]], 0))
        render.sheet(tiles, len(tiles), os.path.join(out, 'calf_cmp%s.jpg' % tag), scale=0.6)
        Image.fromarray(np.concatenate([orig_frame('p9', 26.85, 27.4, (535, 950)), frames[27.4 - t_press]], 1)).save(os.path.join(out, 'calf_27.4%s.jpg' % tag), quality=92)
    if what == 'drag':
        # front of the thigh, dragged 80 mm down the leg and held, then released
        sc = Scene('VIEW01', prm=prm)
        c = sc.cl[1]
        jg = int(round((0.60 - c.y0) / c.dy))
        px, py, z = sc.cam.project(c.X[jg]); z = z.cpu().numpy(); ig = int(np.argmin(z))
        sm = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.0), 1.0))
        path = lambda t: (0.01 * sm(t / 0.5), 0.08 * sm(t / 0.5))
        shots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 0.82, 0.85, 1.0]
        frames, log = run(sc, 1, jg, ig, path, 1.05, shots, t_release=0.8, diag=(0.5, os.path.join(out, 'drag_strain%s.png' % tag)))
        render.sheet([frames[t][100:700] for t in shots], len(shots), os.path.join(out, 'drag%s.jpg' % tag), scale=0.7)
        Image.fromarray(np.concatenate([frames[t][180:560, 60:420] for t in (0.3, 0.5, 0.8)], 1)).resize((1620, 570), Image.LANCZOS).save(os.path.join(out, 'drag_0.5%s.jpg' % tag), quality=92)
