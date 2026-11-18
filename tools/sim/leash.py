# Leashed stocking cloth, written the way the Unity compute shader runs it: one Jacobi pass per substep over a
# per-leg lattice (NU around x NV along), every node reading only its 8 neighbours.
#   * tension-only knit springs (they fold under compression) with a soft range and a lock (strain limit),
#   * the leg as a radial height field R(theta, y) about the leg axis,
#   * a weak leash back to the worn rest position (what friction and the knit's pre-tension do on a real leg),
#   * pinned ankle / top rows, a kinematic pinch.
# The knit is pre-stretched: its natural size is smaller than the leg (`shrink`), so every thread carries tension at
# rest.  The part of that rest tension the leg does not carry by contact (friction holds it on a real leg) is
# subtracted for fabric lying on the leg, so the worn rest state is an exact equilibrium and an untouched leg is asleep.
import math, numpy as np, torch

class Params:
    sub_rate = 3840.0        # substeps per second (64 per 60 Hz frame)
    damp = 0.985             # velocity kept per substep
    k_soft = 0.30            # fraction of a stretched edge's error removed per pass (the elastic range)
    lock_u = 0.90            # strain where the knit locks, around the leg
    lock_v = 0.90            #   along the leg (0.55 made a 7 cm drag over the thigh stretch the fabric 13 cm away, at the knee)
    lock_d = 1.20            #   diagonals (shear)
    k_diag = 0.35            # diagonal springs relative to the structural ones
    k_comp = 0.02            # resistance to compression (keeps the lattice regular; the folds are drawn by the shader)
    k_leash = 0.0015         # pull back to the rest position per substep, for fabric lying on the leg (friction)
    slip = 0.0004             # friction saturates (Coulomb): beyond this displacement (m) the leash force stops growing; 0 = linear
    h0 = 0.0005              # fabric lifted more than h1 above the leg is free (no friction in the air),
    h1 = 0.0030              #   with a smooth transition from h0
    k_rel = 0.0025           # after release everything is drawn back to rest, critically damped:
    damp_rel = 0.90          #   damp_rel = 1 - 2 sqrt(k_rel)
    lra = 1                  # tether to the pinch on / off
    omega = 1.5              # Jacobi over-relaxation
    pin_rows = 3             # rows at the ankle / top that do not move
    pin_fade = 4             # rows over which the leash stiffens towards the pins
    pinch_r = 0.006          # radius of the pinched patch (m)
    gather = 0.35            # the pinch gathers the patch to this fraction of its size
    reach = 1.0              # scales the locks used by the tether to the pinch (1 = same as the knit locks)
    jam = 0.35               # fabric lying on the leg cannot fold over itself: neighbours keep their order around / along the
                             #   leg, and cannot be gathered below this fraction of their worn spacing (it rucks up ahead of a drag)
    fold = 0.05              #   ... and lifted fabric not below this (it bunches against the fingers instead of folding under them)
    order_h0 = 0.015         # the order is only kept near the leg (lift < h0 .. h1, m): a sail pulled well off the leg may
    order_h1 = 0.030         #   hang below the fabric it came from (the original's ankle sails reach down to the floor)
    shrink_u = 0.50          # pre-stretch: the knit's natural (unworn) length is (1 - shrink) of its worn length, around /
    shrink_v = 0.25          #   along the leg / diagonally.  This is what keeps a pulled sail taut and flat.
    shrink_d = 0.30
    k_cs = 0.30              # fabric lying on the leg resists compression (it rucks up, it cannot fold away) ...

OFFS = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]     # (dj along, di around)

class Cloth:
    def __init__(self, leg, prm=None, device='cuda'):
        self.P = prm or Params(); P = self.P
        t = lambda a: torch.as_tensor(np.asarray(a), dtype=torch.float32, device=device)
        self.dev = device
        self.X = t(leg['X']); self.NV, self.NU = self.X.shape[:2]
        self.R = t(leg['R']); self.ax = t(leg['ax']); self.az = t(leg['az'])
        self.y0 = float(leg['y'][0]); self.dy = float(leg['y'][1] - leg['y'][0])
        self.x = self.X.clone(); self.xp = self.X.clone()
        NV, NU = self.NV, self.NU
        # rest lengths / locks / weights for the 8 neighbours
        self.L = []; self.lock = []; self.kw = []; self.valid = []; self.shrink = []
        j = torch.arange(NV, device=device).view(NV, 1).expand(NV, NU)
        for (dj, di) in OFFS:
            Xn = self.shift(self.X, dj, di)
            self.L.append((Xn - self.X).norm(dim=-1))
            self.valid.append(((j + dj >= 0) & (j + dj < NV)).float())
            if dj == 0: self.lock.append(P.lock_u); self.kw.append(1.0); self.shrink.append(P.shrink_u)
            elif di == 0: self.lock.append(P.lock_v); self.kw.append(1.0); self.shrink.append(P.shrink_v)
            else: self.lock.append(P.lock_d); self.kw.append(P.k_diag); self.shrink.append(P.shrink_d)
        # rest tension: what the pre-stretched threads pull with in the worn state.  Its inward radial part is carried
        # by the leg (collision); the rest (F0) is what friction holds, and is subtracted while the fabric is in contact.
        F0 = torch.zeros_like(self.X)
        for k, (dj, di) in enumerate(OFFS):
            D = self.shift(self.X, dj, di) - self.X
            c0 = self.kw[k] * P.k_soft * self.shrink[k] * self.L[k]
            F0 += (0.5 * c0 * self.valid[k] / self.L[k].clamp_min(1e-9)).unsqueeze(-1) * D
        dx = self.X[..., 0] - self.ax.view(-1, 1); dz = self.X[..., 2] - self.az.view(-1, 1)
        rho = torch.sqrt(dx * dx + dz * dz).clamp_min(1e-9)
        nr = torch.stack([dx / rho, torch.zeros_like(dx), dz / rho], -1)
        fr = (F0 * nr).sum(-1)
        self.F0 = F0 - fr.clamp_max(0).unsqueeze(-1) * nr
        self.F0_stats = (float(F0.norm(dim=-1).mean()), float(self.F0.norm(dim=-1).mean()), float((fr > 0).float().mean()))
        # leash: stiff at the pinned rows, weak elsewhere
        r = torch.minimum(j, NV - 1 - j).float()
        f = ((r - P.pin_rows) / P.pin_fade).clamp(0, 1); f = f * f * (3 - 2 * f)
        self.pin = (r < P.pin_rows)
        self.leash_pin = (1 - f) * 0.2
        self.free = f                                # 0 at the pinned ankle / top rows -> 1: how far the tether may drag a node
        self.h = torch.zeros(NV, NU, device=device); self.held = False
        self.pinch_w = None; self.pinch_off = None; self.pull = torch.zeros(3, device=device)
        # cell rest areas (for the preview renderer)
        a = self.X[:-1]; b = torch.roll(self.X, -1, 1)[:-1]; c = self.X[1:]
        self.area0 = torch.linalg.cross(b - a, c - a).norm(dim=-1).cpu().numpy()
        self.S = np.zeros((NV - 1, NU), np.uint8)

    def shift(self, A, dj, di):
        """A[j + dj, i + di] with clamped rows and periodic columns."""
        B = torch.roll(A, -di, 1) if di else A
        if dj > 0: B = torch.cat([B[dj:], B[-1:].expand(dj, *B.shape[1:])], 0)
        elif dj < 0: B = torch.cat([B[:1].expand(-dj, *B.shape[1:]), B[:dj]], 0)
        return B

    # ---------------------------------------------------------------- leg collision
    def radius(self, p):
        """Leg radius and axis at the points p (..., 3)."""
        f = ((p[..., 1] - self.y0) / self.dy).clamp(0, self.NV - 1.001)
        j0 = f.floor().long(); a = f - j0
        axx = self.ax[j0] * (1 - a) + self.ax[j0 + 1] * a; azz = self.az[j0] * (1 - a) + self.az[j0 + 1] * a
        dx = p[..., 0] - axx; dz = p[..., 2] - azz
        th = torch.atan2(dx, dz) / (2 * math.pi); g = (th - th.floor()) * self.NU
        i0 = g.floor().long() % self.NU; b = g - g.floor(); i1 = (i0 + 1) % self.NU
        R = (self.R[j0, i0] * (1 - a) * (1 - b) + self.R[j0, i1] * (1 - a) * b
             + self.R[j0 + 1, i0] * a * (1 - b) + self.R[j0 + 1, i1] * a * b)
        return R, dx, dz

    def collide(self, p, margin=0.0):
        R, dx, dz = self.radius(p)
        rho = torch.sqrt(dx * dx + dz * dz).clamp_min(1e-9)
        pen = (R + margin - rho).clamp_min(0) / rho
        q = p.clone(); q[..., 0] += dx * pen; q[..., 2] += dz * pen
        return q, (rho - R)

    # ---------------------------------------------------------------- the hand
    def grab(self, j, i):
        P = self.P
        c = self.X[j, i].clone()
        # rest distances from the grab point, around (su) and along (sv) the leg, as the shader computes them:
        # su = R * wrapped angle, sv = height difference
        th = torch.arange(self.NU, device=self.dev).float() * (2 * math.pi / self.NU)
        dth = torch.remainder(th - th[i] + math.pi, 2 * math.pi) - math.pi
        su = self.R * dth.view(1, -1)
        sv = (self.X[..., 1] - c[1])
        g = torch.sqrt(su * su + sv * sv)
        self.pinch_w = (g < P.pinch_r)
        self.pinch_w[j, i] = True
        k = ((g - P.pinch_r) / g.clamp_min(1e-9)).clamp_min(0)
        self.t_k = k * torch.sqrt(((1 + P.lock_u * P.reach) * su) ** 2 + ((1 + P.lock_v * P.reach) * sv) ** 2)
        self.grab_d = self.X - c
        self.pinch_base = self.X.clone()
        self.pinch_c = c; self.pull = torch.zeros(3, device=self.dev); self.held = True
        return c

    def release(self): self.pinch_w = None; self.held = False

    # ---------------------------------------------------------------- one substep = one Jacobi pass
    def step(self, n=1):
        P = self.P
        for _ in range(n):
            x = self.x
            cw = ((self.h - P.h0) / (P.h1 - P.h0)).clamp(0, 1); cw = 1 - cw * cw * (3 - 2 * cw)      # 1 on the leg, 0 in the air
            y = x + (x - self.xp) * (P.damp if self.held else P.damp_rel)
            d = self.X - y
            if self.held:
                lw = P.k_leash * cw
                if P.slip > 0: lw = lw / (1 + d.norm(dim=-1) / P.slip)
                lw = lw + self.leash_pin
            else: lw = self.leash_pin + P.k_rel
            y = y + d * lw.unsqueeze(-1)
            corr = -self.F0 * cw.unsqueeze(-1)
            lift = 1 - cw
            for k, (dj, di) in enumerate(OFFS):
                d = self.shift(y, dj, di) - y
                ln = d.norm(dim=-1).clamp_min(1e-9)
                wl = 0.5 * (lift + self.shift(lift, dj, di))                 # how far this thread is off the leg
                e = ln - self.L[k] * (1 - self.shrink[k])
                over = ln - self.L[k] * (1 + self.lock[k])
                kc = (P.k_comp + P.k_cs * (1 - wl)) * self.kw[k]
                c = self.kw[k] * P.k_soft * e.clamp_min(0) + kc * e.clamp_max(0) + (1 - P.k_soft * self.kw[k]) * over.clamp_min(0)
                corr += (0.5 * c * self.valid[k] / ln).unsqueeze(-1) * d
            y = y + corr * (P.omega / 8.0)
            if P.jam > 0:
                # order: (height, angle about the leg axis) of neighbours stays monotonic (the knit cannot pass through
                # itself), and fabric lying on the leg cannot be gathered below `jam` of its worn spacing
                _, dx, dz = self.radius(y)
                rho = torch.sqrt(dx * dx + dz * dz).clamp_min(1e-9)
                near = ((P.order_h1 - self.h) / (P.order_h1 - P.order_h0)).clamp(0, 1); near = near * near * (3 - 2 * near)
                mv = P.fold + (P.jam - P.fold) * cw * self.shift(cw, 1, 0)
                pv = (mv * self.dy - (self.shift(y, 1, 0)[..., 1] - y[..., 1])).clamp_min(0) * 0.5 * self.valid[2] * torch.minimum(near, self.shift(near, 1, 0))
                dyv = self.shift(pv, -1, 0) * self.valid[3] - pv
                dxb = torch.roll(dx, -1, 1); dzb = torch.roll(dz, -1, 1)
                arc = (dxb * dz - dzb * dx) / rho
                mu = P.fold + (P.jam - P.fold) * cw * torch.roll(cw, -1, 1)
                pu = (mu * self.L[0] - arc).clamp_min(0) * 0.5 * torch.minimum(near, torch.roll(near, -1, 1))
                dth = (torch.roll(pu, 1, 1) - pu) / rho
                y = torch.stack([y[..., 0] + dz * dth, y[..., 1] + dyv, y[..., 2] - dx * dth], -1)
            if self.pinch_w is not None:
                # tether to the pinch: no thread can be longer than its locked length
                A = self.pinch_c + self.pull
                # the fingers close on the fabric as they start to pull (no dimple at the mere touch)
                u = min(float(self.pull.norm()) / 0.012, 1.0); ge = 1 + (P.gather - 1) * (u * u * (3 - 2 * u))
                if P.lra:
                    d = y - A; ln = d.norm(dim=-1).clamp_min(1e-9)
                    yt = A + d * (torch.minimum(ln, ge * P.pinch_r + self.t_k) / ln).unsqueeze(-1)
                    y = y + (yt - y) * self.free.unsqueeze(-1)
                tgt = A + (self.pinch_base - self.pinch_c) * ge
                y = torch.where(self.pinch_w.unsqueeze(-1), tgt, y)
            y, self.h = self.collide(y)
            y = torch.where(self.pin.unsqueeze(-1), self.X, y)
            self.xp = x; self.x = y

    # ---------------------------------------------------------------- diagnostics
    def strains(self):
        """Strain of the +u and +v edges and the areal stretch of every cell."""
        x = self.x
        su = (torch.roll(x, -1, 1) - x).norm(dim=-1) / self.L[0] - 1
        sv = (self.shift(x, 1, 0) - x).norm(dim=-1) / self.L[2].clamp_min(1e-9) - 1
        a = x[:-1]; b = torch.roll(x, -1, 1)[:-1]; c = x[1:]
        area = torch.linalg.cross(b - a, c - a).norm(dim=-1)
        return su, sv, area / torch.as_tensor(self.area0, device=self.dev)

class View:
    """What the preview renderer needs from a cloth."""
    def __init__(self, c): self.x = c.x.detach().cpu().numpy(); self.S = c.S; self.area0 = c.area0
