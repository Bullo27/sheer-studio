# Principal stretches (as the Resolve kernel of SheerCloth.compute computes them) of the thigh / calf / drag scenarios:
# how far from the grab the fabric is stretched / squeezed / lifted. Used to place the shader's thresholds.
import os, sys, numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leash, run_leash

def principal(c):
    x, X = c.x, c.X
    sh = c.shift
    du = torch.roll(x, -1, 1) - torch.roll(x, 1, 1); dv = sh(x, 1, 0) - sh(x, -1, 0)
    dU = torch.roll(X, -1, 1) - torch.roll(X, 1, 1); dV = sh(X, 1, 0) - sh(X, -1, 0)
    lU = dU.norm(dim=-1).clamp_min(1e-9); eu = dU / lU.unsqueeze(-1)
    a2u = (dV * eu).sum(-1); a2 = dV - a2u.unsqueeze(-1) * eu; a2v = a2.norm(dim=-1).clamp_min(1e-9)
    Fu = du / lU.unsqueeze(-1); Fv = (dv - a2u.unsqueeze(-1) * Fu) / a2v.unsqueeze(-1)
    c11 = (Fu * Fu).sum(-1); c22 = (Fv * Fv).sum(-1); c12 = (Fu * Fv).sum(-1)
    tr = c11 + c22; df = c11 - c22; disc = torch.sqrt((df * df + 4 * c12 * c12).clamp_min(0))
    return torch.sqrt((0.5 * (tr + disc)).clamp_min(0)), torch.sqrt((0.5 * (tr - disc)).clamp_min(0))

def report(c, jg, ig, name):
    l1, l2 = principal(c); h = c.h.clamp_min(0)
    th = torch.arange(c.NU, device=c.dev).float() * (2 * np.pi / c.NU)
    dth = torch.remainder(th - th[ig] + np.pi, 2 * np.pi) - np.pi
    g = torch.sqrt((c.R * dth.view(1, -1)) ** 2 + (c.X[..., 1] - c.X[jg, ig, 1]) ** 2) * 1e3      # mm from the grab
    print(name)
    for lo, hi in ((0, 10), (10, 20), (20, 35), (35, 50), (50, 70), (70, 100), (100, 150)):
        m = (g >= lo) & (g < hi)
        q = lambda a, p: float(torch.quantile(a[m], p))
        print('  %3d-%3d mm: l1 med %.2f p90 %.2f | l2 med %.2f p10 %.2f | J med %.2f p10 %.2f p90 %.2f | lift med %.1f p90 %.1f mm' % (
            lo, hi, q(l1, .5), q(l1, .9), q(l2, .5), q(l2, .1), q(l1 * l2, .5), q(l1 * l2, .1), q(l1 * l2, .9), q(h, .5) * 1e3, q(h, .9) * 1e3))

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'thigh'
    sc = run_leash.Scene('VIEW01'); c = sc.cl[1]
    if what == 'thigh':
        G = (451, 694); mmpp = 0.24; t_press = 12.767
        jg = int(round((0.615 - c.y0) / c.dy))
        px, py, z = sc.cam.project(c.X[jg]); px = px.cpu().numpy()
        rad = torch.stack([c.X[jg, :, 0] - c.ax[jg], c.X[jg, :, 2] - c.az[jg]], -1); view = (c.X[jg] - sc.cam.pos)[:, [0, 2]]
        facing = ((rad * view).sum(-1) < 0).cpu().numpy()
        ig = int(np.argmin(np.abs(px - (px[facing].max() - (28.0 / mmpp) / 2)) + np.where(facing, 0, 1e6)))
        ts, xy = run_leash.track_path('p5', G, mmpp)
        path = lambda t: (np.interp(t + t_press, ts, xy[:, 0]), np.interp(t + t_press, ts, xy[:, 1]))
        run_leash.run(sc, 1, jg, ig, path, 13.1 - t_press, [13.1 - t_press], verbose=False)
        report(c, jg, ig, 'thigh tent at 13.1 s')
    else:
        jg = int(round((0.60 - c.y0) / c.dy))
        px, py, z = sc.cam.project(c.X[jg]); ig = int(np.argmin(z.cpu().numpy()))
        sm = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.0), 1.0))
        path = lambda t: (0.01 * sm(t / 0.5), 0.08 * sm(t / 0.5))
        run_leash.run(sc, 1, jg, ig, path, 0.6, [0.6], verbose=False)
        report(c, jg, ig, 'drag down the thigh at 0.6 s')
