# Preview renderer for the physics prototype (PyTorch): point splatting with a skin z-buffer and "yarn mass"
# splatting for the stocking: every lattice cell carries its natural (unstretched) area as yarn mass, the optical
# depth of a pixel is kappa * (natural area landing in the pixel) / (pixel footprint) -- stretch, grazing angle and
# multiple layers are then all handled by construction.  Good enough to judge shapes, contact lines and holes.
import math, numpy as np, torch
from PIL import Image

class Camera:
    def __init__(self, pos, target, lens_mm, W=540, H=945, device='cuda'):
        t = lambda a: torch.tensor(a, dtype=torch.float32, device=device)
        self.pos = t(pos); f = t(target) - self.pos; self.f = f / f.norm()
        up = t([0.0, 1.0, 0.0])
        r = torch.linalg.cross(up, self.f); self.r = r / r.norm(); self.u = torch.linalg.cross(self.f, self.r)
        self.k = lens_mm / 36.0; self.W, self.H = W, H; self.aspect = H / W; self.dev = device

    def project(self, p):
        d = p - self.pos
        z = (d * self.f).sum(-1)
        px = (0.5 + self.aspect * self.k * (d * self.r).sum(-1) / z) * self.W
        py = (0.5 - self.k * (d * self.u).sum(-1) / z) * self.H
        return px, py, z

VIEW01 = dict(pos=[0.0877, 0.4921, -1.2622], target=[0.1046, 0.5604, -0.0082], lens_mm=87.11)
VIEW02 = dict(pos=[-0.0495, 0.1862, -1.1030], target=[-0.0488, 0.1638, 0.0114], lens_mm=86.42)

def upsample_grid(X, K, periodic=True):
    """(NV, NU, C) node grid -> ((NV-1)*K, NU*K, C) samples at sub-cell centres (bilinear)."""
    NV, NU = X.shape[:2]
    s = (torch.arange(K, device=X.device, dtype=X.dtype) + 0.5) / K
    Xr = torch.roll(X, -1, 1)
    a = s.view(1, K, 1, 1, 1); b = s.view(1, 1, 1, K, 1)
    x00 = X[:-1].unsqueeze(1).unsqueeze(3); x01 = Xr[:-1].unsqueeze(1).unsqueeze(3)
    x10 = X[1:].unsqueeze(1).unsqueeze(3); x11 = Xr[1:].unsqueeze(1).unsqueeze(3)
    out = x00 * (1 - a) * (1 - b) + x01 * (1 - a) * b + x10 * a * (1 - b) + x11 * a * b     # (NV-1, K, NU, K, C)
    return out.reshape((NV - 1) * K, NU * K, -1)

def grid_normals(X):
    du = torch.roll(X, -1, 1) - torch.roll(X, 1, 1)
    dv = torch.zeros_like(X); dv[1:-1] = X[2:] - X[:-2]; dv[0] = X[1] - X[0]; dv[-1] = X[-1] - X[-2]
    n = torch.linalg.cross(dv, du)          # outward for theta = atan2(x, z) increasing with i
    return n / n.norm(dim=-1, keepdim=True).clamp_min(1e-12)

class Preview:
    def __init__(self, cam, skins, Ks=5):
        """skins: list of (NV, NU, 3) rest surfaces (the legs)."""
        self.cam = cam; W, H = cam.W, cam.H
        zb = torch.full((H * W,), 1e9, device=cam.dev); nb = torch.zeros(H * W, 3, device=cam.dev)
        for X in skins:
            X = torch.as_tensor(X, device=cam.dev, dtype=torch.float32)
            n = grid_normals(X)
            P = upsample_grid(X, Ks).reshape(-1, 3); Nn = upsample_grid(n, Ks).reshape(-1, 3)
            px, py, z = cam.project(P)
            ix = px.round().long(); iy = py.round().long()
            ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H) & (z > 0)
            idx = (iy * W + ix)[ok]; z = z[ok]; Nn = Nn[ok]
            zb = zb.scatter_reduce(0, idx, z, 'amin')
            win = z <= zb[idx] + 1e-6
            nb[idx[win]] = Nn[win]
        self.zskin = zb; self.nskin = nb
        light = torch.tensor([-0.35, 0.55, -0.75], device=cam.dev); self.light = light / light.norm()

    def render(self, cloths, kappa=1.7, Kc=6, bg=(0.82, 0.82, 0.84), skin=(0.86, 0.66, 0.56), nylon=(0.035, 0.035, 0.045), lad_mass=0.45):
        cam = self.cam; W, H = cam.W, cam.H
        tau = torch.zeros(H * W, device=cam.dev)
        for c in cloths:
            P = upsample_grid(torch.as_tensor(c.x, device=cam.dev), Kc).reshape(-1, 3)
            S = torch.as_tensor(c.S, device=cam.dev)
            mass = torch.as_tensor(c.area0, device=cam.dev) * torch.where(S == 0, 1.0, torch.where(S == 1, lad_mass, 0.0))
            mass = mass.repeat_interleave(Kc, 0).repeat_interleave(Kc, 1).reshape(-1) / (Kc * Kc)
            px, py, z = cam.project(P)
            foot = (z / (cam.k * H)) ** 2                               # pixel footprint (m^2) at that depth
            x0 = torch.floor(px - 0.5); y0 = torch.floor(py - 0.5); fx = px - 0.5 - x0; fy = py - 0.5 - y0
            for ox, oy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                ix = (x0 + ox).long(); iy = (y0 + oy).long()
                ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H) & (z > 0)
                idx = (iy * W + ix).clamp(0, H * W - 1)
                vis = ok & (z < self.zskin[idx] + 0.0015) & (mass > 0)
                tau.index_add_(0, idx[vis], (kappa * mass * w / foot)[vis])
        T = torch.exp(-tau)[:, None]
        has = (self.zskin < 1e8)[:, None]
        lam = (self.nskin * self.light).sum(-1, keepdim=True).clamp_min(0)
        sk = torch.tensor(skin, device=cam.dev) * (0.42 + 0.58 * lam)
        base = torch.where(has, sk, torch.tensor(bg, device=cam.dev).expand(H * W, 3))
        img = base * T + torch.tensor(nylon, device=cam.dev) * (1 - T)
        return (img.reshape(H, W, 3).clamp(0, 1) ** (1 / 2.2) * 255).byte().cpu().numpy()

def save(img, path): Image.fromarray(img).save(path)

def sheet(imgs, cols, path, scale=1.0):
    h, w = imgs[0].shape[:2]; rows = (len(imgs) + cols - 1) // cols
    S = Image.new('RGB', (cols * w, rows * h), (30, 30, 30))
    for k, im in enumerate(imgs): S.paste(Image.fromarray(im), ((k % cols) * w, (k // cols) * h))
    if scale != 1.0: S = S.resize((int(S.width * scale), int(S.height * scale)), Image.LANCZOS)
    S.save(path, quality=90)
