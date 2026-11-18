import os, sys, numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leash, run_leash, render
from PIL import Image
prm = leash.Params()
for a in sys.argv[1:]:
    k, v = a.split('='); setattr(prm, k, type(getattr(prm, k))(float(v)))
sc = run_leash.Scene('VIEW01', prm=prm)
c = sc.cl[1]
jg = int(round((0.60 - c.y0) / c.dy))
px, py, z = sc.cam.project(c.X[jg]); z = z.cpu().numpy(); ig = int(np.argmin(z))
sm = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.0), 1.0))
path = lambda t: (0.01 * sm(t / 0.5), 0.08 * sm(t / 0.5))
frames, log = run_leash.run(sc, 1, jg, ig, path, 0.5, [0.5], verbose=False)
x = c.x; X = c.X
# orientation of every cell relative to the outward radial direction
a = x[:-1]; b = torch.roll(x, -1, 1)[:-1]; d = x[1:]
n = torch.linalg.cross(d - a, b - a)
_, dx, dz = c.radius(a)
rad = torch.stack([dx, torch.zeros_like(dx), dz], -1)
flip = ((n * rad).sum(-1) < 0)
print('flipped cells', int(flip.sum()))
A = (c.pinch_c + c.pull)
print('pinch target', A.cpu().numpy(), 'height above leg %.2f mm' % float(c.collide(A.view(1, 3))[1] * 1e3))
h = c.h.cpu().numpy() * 1e3
np.set_printoptions(linewidth=250, precision=1, suppress=True)
# where are the grabbed nodes now (lattice index of nearest rest node to the pinch target)
dist = (X - A).norm(dim=-1); k = int(dist.argmin()); jn, in_ = k // c.NU, k % c.NU
print('grab node', jg, ig, 'pinch is now over rest node', jn, in_)
rows = range(jg + 6, jg - 34, -2); cols = [(ig + o) % c.NU for o in range(-20, 21, 2)]
print('height above leg (mm), rows', list(rows)[0], '..', list(rows)[-1], ' cols', -20, '..', 20)
print(h[np.ix_(list(rows), cols)])
su, sv, ar = c.strains(); ar = ar.cpu().numpy()
print('area ratio'); print(ar[np.ix_(list(rows), cols)])
fl = flip.cpu().numpy().astype(int)
print('flipped'); print(fl[np.ix_(list(rows), cols)])
dsp = ((x - X)[..., 1]).cpu().numpy() * 1e3
print('dy (mm)'); print(dsp[np.ix_(list(rows), cols)])
# side view render
V = dict(render.VIEW01); 
import copy
sc2 = copy.copy(sc); 
