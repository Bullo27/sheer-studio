#!/usr/bin/env python3
"""SHEER - a FREE-PLAY SWEEP session (INPUT ONLY; CLAUDE.md: test free play directly): generic pulls at random spots on
the stocking, both legs, both views. Grab points are sampled from leg masks, stratified by height; drag direction /
length / hold (short, medium, long, tear, tap) are random. Writes the session and a pulls table for tools/sweep_sheets.py.

  1. leg masks - one frame of each view with a green stocking (the body held still):
       echo '{"denier":120,"color":{"r":0,"g":1,"b":0,"a":1},"finish":0}' > green.json
       Sheer.x86_64 -batchmode -sheerReplay -sheerSession tools/sim/ref_data/test_sessions/idle.json -sheerStill \
         -sheerLook green.json -sheerCapture v1 -sheerFrom 1.0 -sheerTo 1.07 -sheerCapScale 1     (VIEW 01; v2: 36.0-36.07)
       python3 tools/sweep_session.py masks v1/u_0002.png v2/u_0002.png OUTDIR
  2. python3 tools/sweep_session.py make OUTDIR/mask_v1.npy OUTDIR/mask_v2.npy sweep.json [seed]
  3. capture it at 30 fps (-sheerSession sweep.json -sheerStill -sheerCapture DIR -sheerCapScale 1 -sheerCapFps 30),
     then python3 tools/sweep_sheets.py DIR sweep_pulls.json PREFIX
Orbited views (free play orbits +-55 deg): test_sessions/orbit_views.json holds VIEW 01 / VIEW 02 at +-50 deg (camMoves)
for the masks; test_sessions/orbit_sweep.json (+ _pulls) is a 24-pull sweep in them. A press's 'side' only tells the
replay which leg to pick: in an orbited view take it from a first run (a wrong side shows as a large '[replay] ... ray
miss' and grabs the other leg far from the cursor).
"""
import json, os, sys
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_test_sessions import session, press  # noqa: E402

if len(sys.argv) > 1 and sys.argv[1] == 'masks':
    from PIL import Image
    for name, f in (('v1', sys.argv[2]), ('v2', sys.argv[3])):
        im = np.asarray(Image.open(f).convert('RGB')).astype(int)
        m = (im[..., 1] > im[..., 0] + 25) & (im[..., 1] > im[..., 2] + 25)
        lab, n = ndimage.label(m); sizes = ndimage.sum(m, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s > 2000]
        # components ordered by size: 1 = the near leg, 2 = the other leg's visible part
        order = sorted(keep, key=lambda k: -sizes[k - 1]); out = np.zeros_like(lab)
        for r, k in enumerate(order[:2]): out[lab == k] = r + 1
        np.save(os.path.join(sys.argv[4], 'mask_%s.npy' % name), out); print('mask', name, [int(sizes[k - 1]) for k in order[:2]])
    sys.exit(0)
if len(sys.argv) > 1 and sys.argv[1] == 'make': sys.argv.pop(1)
m1, m2, out = sys.argv[1], sys.argv[2], sys.argv[3]
rng = np.random.default_rng(int(sys.argv[4]) if len(sys.argv) > 4 else 7)


def points(mask_file, n, comps_side, y_lo, y_hi):
    lab = np.load(mask_file)
    H, W = lab.shape
    pts = []
    for comp, side, share in comps_side:
        m = ndimage.binary_erosion(lab == comp, iterations=14)
        m[:int(H * y_lo)] = False; m[int(H * y_hi):] = False
        ys, xs = np.where(m)
        k = max(1, int(round(n * share)))
        # stratified by height
        bands = np.linspace(ys.min(), ys.max() + 1, k + 1)
        for i in range(k):
            sel = np.where((ys >= bands[i]) & (ys < bands[i + 1]))[0]
            if len(sel) == 0: continue
            j = rng.choice(sel)
            pts.append((xs[j] / W, ys[j] / H, side))
    rng.shuffle(pts)
    return pts, W, H


def pulls_for(pts, W, H, t_start):
    P = []
    t = t_start
    for (x, y, side) in pts:
        kind = rng.choice(['short', 'medium', 'long', 'tear', 'tap'], p=[0.25, 0.3, 0.2, 0.15, 0.1])
        ang = rng.uniform(0, 2 * np.pi)
        L = {'short': 50, 'medium': 110, 'long': 190, 'tear': 170, 'tap': 0}[kind] * rng.uniform(0.8, 1.25)   # px (540 wide)
        dx, dy = np.cos(ang) * L / W, np.sin(ang) * L / H
        tx, ty = float(np.clip(x + dx, 0.02, 0.98)), float(np.clip(y + dy, 0.02, 0.98))
        drag = {'short': 0.45, 'medium': 0.6, 'long': 0.8, 'tear': 0.6, 'tap': 0.0}[kind]
        hold = {'short': 0.5, 'medium': 0.7, 'long': 0.9, 'tear': 2.6, 'tap': 0.25}[kind]
        t0 = round(t + 0.45, 3); t1 = round(t0 + drag + hold, 3)
        keys = [(t0 - 0.45, x, y), (t0, x, y)]
        if drag > 0: keys.append((t0 + drag, tx, ty))
        keys.append((t1, tx, ty))
        P.append(dict(t0=t0, t1=t1, side=int(side), x=float(x), y=float(y), tx=tx, ty=ty, kind=str(kind), keys=keys))
        t = t1 + 0.9
    return P, t


v1, W, H = points(m1, 18, [(1, 1, 0.8), (2, -1, 0.2)], 0.33, 0.98)
P1, t = pulls_for(v1, W, H, 0.6)
switch = (t + 0.6, t + 2.1)
v2, W2, H2 = points(m2, 18, [(1, -1, 0.8), (2, 1, 0.2)], 0.03, 0.88)
P2, t = pulls_for(v2, W2, H2, switch[1] + 0.8)
dur = round(t + 0.6, 2)
P = P1 + P2
keys = [(0.0, 0.93, 0.30, 1)]
for p in P:
    for k in p['keys']: keys.append((k[0], k[1], k[2], 1))
    keys.append((p['t1'] + 0.45, 0.97, 0.12, 1))         # the hand leaves to the side between pulls
keys.append((dur, 0.97, 0.12, 1))
keys.sort(key=lambda k: k[0])
s = session(dur, switch, [press(p['t0'], p['t1'], p['side']) for p in P], keys)
json.dump(s, open(out, 'w'))
json.dump([{k: v for k, v in p.items() if k != 'keys'} | {'view': 1 if i < len(P1) else 2} for i, p in enumerate(P)],
          open(out.replace('.json', '_pulls.json'), 'w'), indent=1)
print('wrote', out, 'duration', dur, 'switch', switch, 'pulls', len(P1), '+', len(P2))
for i, p in enumerate(P):
    print(i, 'V%d' % (1 if i < len(P1) else 2), p['kind'], 'side', p['side'], '(%.2f,%.2f)->(%.2f,%.2f)' % (p['x'], p['y'], p['tx'], p['ty']), p['t0'], p['t1'])
