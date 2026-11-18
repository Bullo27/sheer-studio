#!/usr/bin/env python3
# SHEER — fits a camera (position, target, focal length) so that the silhouettes of our legs match the original
# frame: per image row, the left/right edges of each leg in the original (leg pixels vs the blue backdrop) against
# the min/max of our projected stocking vertices (+ body for the feet). Blender axes, vertical 36 mm sensor,
# 1080 x 1890 game window. Usage: python3 tools/fit_camera.py ORIGINAL.png VIEW01|VIEW02 [--rows 0.05:0.68] [--knee K]
import argparse, json, os, sys
import numpy as np
from PIL import Image
from scipy.optimize import minimize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_proto as C

ASPECT = 1890 / 1080


def leg_edges(path, rows):
    im = np.asarray(Image.open(path).convert('RGB').resize((540, 945))).astype(np.float64)
    H, W, _ = im.shape
    out = {}
    for y in rows:
        r = im[int(y * H)]
        bg = (r[:, 2] > r[:, 0] + 12)                            # backdrop: blue clearly above red
        leg = ~bg
        leg[:4] = False; leg[-4:] = False                         # frame borders
        # runs of leg pixels
        runs, i = [], 0
        while i < W:
            if leg[i]:
                j = i
                while j < W and leg[j]:
                    j += 1
                if j - i > 6 and i / W < 0.95:                  # ignore the game-view border strip
                    runs.append((i / W, j / W))
                i = j
            else:
                i += 1
        out[y] = runs
    return out


def project(P, cam):
    loc, tgt, lens = cam[:3], cam[3:6], cam[6]
    f = tgt - loc; f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1.0]); r /= np.linalg.norm(r); u = np.cross(r, f)
    q = P - loc; zc = q @ f; k = lens / 36.0
    return 0.5 + (q @ r) / zc * ASPECT * k, 0.5 - (q @ u) / zc * k


def our_edges(P, side, cam, rows, band=0.004):
    x, y = project(P, cam)
    out = {}
    for yy in rows:
        m = np.abs(y - yy) < band
        res = []
        for s in (-1, 1):
            mm = m & (side == s)
            if mm.sum() > 3:
                res.append((x[mm].min(), x[mm].max()))
        out[yy] = sorted(res)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('orig'); ap.add_argument('view')
    ap.add_argument('--rows', default='0.05:0.66')
    ap.add_argument('--knee', type=float, default=0.0)
    ap.add_argument('--t', type=float, default=0.0)
    a = ap.parse_args()
    r0, r1 = (float(v) for v in a.rows.split(':'))
    rows = list(np.linspace(r0, r1, 24))
    ref = leg_edges(a.orig, rows)
    nv, subs, ch = C.load_smesh(os.path.join(C.SA, 'tights.smesh'))
    P = ch['position'][:, [0, 2, 1]].astype(np.float64)
    side = np.sign(ch['uv2'][:, 0])
    P[:, 0] += C.pose_dx(P, a.t, a.knee)
    v = {'VIEW01': C.VIEWS[0], 'VIEW02': C.VIEWS[1]}[a.view]
    cam0 = np.array(list(v[0]) + list(v[1]) + [v[2]], np.float64)

    def err(cam, verbose=False):
        ours = our_edges(P, side, cam, rows)
        e, n = 0.0, 0
        for y in rows:
            R, O = ref[y], ours[y]
            for (a0, a1) in R:                                      # each original run vs the nearest projected leg
                if not O:
                    e += 0.05; n += 1; continue
                best = min(O, key=lambda o: abs(0.5 * (o[0] + o[1]) - 0.5 * (a0 + a1)))
                # edges touching the frame border only constrain the inner edge
                if a0 > 0.02:
                    e += (best[0] - a0) ** 2; n += 1
                if a1 < 0.98:
                    e += (best[1] - a1) ** 2; n += 1
        if verbose:
            print('rms edge error %.4f (%d edges)' % (np.sqrt(e / max(n, 1)), n))
        return e / max(n, 1)

    print('start:', cam0.round(4)); err(cam0, True)
    # optimise position, target and lens (scaled so the simplex steps are comparable)
    scale = np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 5.0])
    res = minimize(lambda z: err(cam0 + z * scale), np.zeros(7), method='Nelder-Mead',
                   options=dict(maxiter=3000, xatol=1e-4, fatol=1e-9, initial_simplex=None))
    cam = cam0 + res.x * scale
    print('fit:  ', cam.round(4)); err(cam, True)
    print(json.dumps({'loc': cam[:3].round(4).tolist(), 'target': cam[3:6].round(4).tolist(), 'lens': round(float(cam[6]), 2)}))
    # report the edges for a few rows
    ours = our_edges(P, side, cam, rows)
    for y in rows[::4]:
        print('y %.3f orig %s ours %s' % (y, [(round(p, 3), round(q, 3)) for p, q in ref[y]], [(round(p, 3), round(q, 3)) for p, q in ours[y]]))


if __name__ == '__main__':
    main()
