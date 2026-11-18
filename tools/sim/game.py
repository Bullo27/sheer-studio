# Game-like driver for the prototype: screen-space grabs and drags (as SheerInput / ReplayDriver do), hand with a
# force limit, damage updates between chunks of substeps, preview frames.
import os, sys, json, math, time, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import geom, cloth, render

ROOT = geom.ROOT

class Hand:
    """Pinch that follows a target with limited force (the fingers are not infinitely strong)."""
    k_c = 12.0          # commanded force per metre of lag between cursor and pinch
    F_max = 1.2
    gain = 0.004        # metres of hand travel per unit force error and chunk
    v_max = 0.006       # metres per chunk

    def __init__(self, c, p):
        self.c = c; self.g0 = c.grab(p); self.g = self.g0.copy(); self.t = 0.0; self.F = 0.0

    def update(self, target, nsub, dt):
        c = self.c
        if not c.grabbed: return False
        self.t += dt
        d = target - self.g; L = float(np.linalg.norm(d))
        new = self.g
        if L > 1e-6:
            e = d / L
            Fe = float(np.dot(c.hand_force, e))
            Fd = min(self.k_c * L, self.F_max)
            step = min(max(self.gain * (Fd - Fe), -self.v_max), self.v_max, L)
            new = self.g + e * step
        a = min(float(np.linalg.norm(new - self.g0)) / 0.012, 1.0)          # the pinch gathers as it lifts off
        c.gather_now = min(c.gather_now, 1.0 + (c.P.gather - 1.0) * a * a * (3 - 2 * a))
        c.step(nsub, self.g, new); self.g = new.astype(np.float32)
        self.F = float(np.linalg.norm(c.hand_force))
        return True

class Game:
    def __init__(self, view='VIEW01', W=540, H=945, prm=None, sub=96, chunk=8, fps=30, settle=400, cam=None, crop=None):
        self.legs = {s: geom.build_leg(s) for s in (1, -1)}
        self.cl = {s: cloth.Cloth(self.legs[s], prm) for s in (1, -1)}
        for c in self.cl.values(): c.step(settle); c.rest = c.x.copy(); c.torn_off = False
        self.cam = cam or render.Camera(W=W, H=H, **getattr(render, view))
        self.pv = render.Preview(self.cam, [self.cl[1].X, self.cl[-1].X])
        self.sub, self.chunk, self.fps = sub, chunk, fps
        self.hand = None; self.frames = []; self.log = []; self.t = 0.0; self.extra = []

    def pick(self, xn, yn):
        """Nearest camera-facing lattice node to the window point (xn right, yn down, 0..1)."""
        cam = self.cam; best = None
        pos = cam.pos.cpu().numpy(); r = cam.r.cpu().numpy(); u = cam.u.cpu().numpy(); f = cam.f.cpu().numpy()
        for s, c in self.cl.items():
            d = c.x - pos; z = d @ f
            px = 0.5 + cam.aspect * cam.k * (d @ r) / z; py = 0.5 - cam.k * (d @ u) / z
            # facing: radial direction against the view direction
            ax = c.axtex[:, None, 0]; az = c.axtex[:, None, 1]
            rad = np.stack([c.x[..., 0] - ax, np.zeros_like(ax + c.x[..., 0]), c.x[..., 2] - az], -1)
            facing = (rad * d).sum(-1) < 0
            live = (c.flags & 5) == 0
            e = np.hypot((px - xn) / cam.aspect, py - yn) + np.where(facing & live, 0, 1e3)
            k = np.unravel_index(np.argmin(e), e.shape)
            if best is None or e[k] < best[0]: best = (e[k], s, k, z[k])
        return best

    def world_at(self, xn, yn, depth):
        cam = self.cam
        pos = cam.pos.cpu().numpy(); r = cam.r.cpu().numpy(); u = cam.u.cpu().numpy(); f = cam.f.cpu().numpy()
        return pos + depth * (f + r * ((xn - 0.5) / (cam.aspect * cam.k)) + u * ((0.5 - yn) / cam.k))

    def press(self, xn, yn):
        e, s, k, z = self.pick(xn, yn)
        c = self.cl[s]
        self.hand = Hand(c, c.x[k].copy()); self.side = s; self.depth = z; self.c0 = (xn, yn)
        self.W0 = self.world_at(xn, yn, z); c.torn_off = False
        return s, k

    def drag_target(self, xn, yn, lift):
        W = self.world_at(xn, yn, self.depth); D = W - self.W0
        toc = self.cam.pos.cpu().numpy() - self.hand.g0; toc /= np.linalg.norm(toc)
        return (self.hand.g0 + D + toc * (lift * np.linalg.norm(D))).astype(np.float32)

    def release(self):
        if self.hand is not None:
            if self.hand.c.grabbed: self.hand.c.release()
            self.hand = None

    def frame(self, cursor=None, lift=0.3, render_it=True, active=(1, -1)):
        """Advance one frame; cursor = (xn, yn) while dragging."""
        dt = 1.0 / self.fps; nch = self.sub // self.chunk
        for k in range(nch):
            for s in active:
                c = self.cl[s]
                if self.hand is not None and self.hand.c is c and c.grabbed and cursor is not None:
                    self.hand.update(self.drag_target(cursor[0], cursor[1], lift), self.chunk, dt / nch)
                else:
                    c.step(self.chunk)
                if c.damage(): c.drop_islands()
        self.t += dt
        h = self.hand
        c = self.cl[self.side] if hasattr(self, 'side') else self.cl[1]
        self.log.append((self.t, h.F if h else 0.0, float(np.linalg.norm(h.g - h.g0)) if h else 0.0, int((c.S == 1).sum()), int((c.S == 2).sum())))
        if render_it: self.frames.append(self.pv.render([self.cl[1], self.cl[-1]]))
