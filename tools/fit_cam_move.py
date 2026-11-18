#!/usr/bin/env python3
# SHEER — camera moves (player orbit + zoom) as an orbit about a pivot ON the view axis at distance Dp from the camera
# (the base framing is unchanged), angle th (deg, about the vertical) and dolly k (distance to the pivot x k).
# Fits (Dp, th, k) to the original frame at the move's hold. Usage: fit_cam_move.py VIEW01|VIEW02 T ORIG th0 k0
import json, os, sys
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_proto as C
from fit_camera import leg_edges, our_edges


def cam_at(base, Dp, th, k):
    loc, tgt, lens = np.array(base[0]), np.array(base[1]), base[2]
    f = (tgt - loc) / np.linalg.norm(tgt - loc)
    P = loc + f * Dp
    d = loc - P
    a = np.radians(th)
    d = np.array([d[0] * np.cos(a) - d[1] * np.sin(a), d[0] * np.sin(a) + d[1] * np.cos(a), d[2]])   # Blender rig sense
    return np.concatenate([P + d * k, P, [lens]])


def main():
    view, t, orig, th0, k0 = sys.argv[1], float(sys.argv[2]), sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'unity', 'Assets', 'StreamingAssets', 'replay_session.json')))
    tt = np.array(d['t']); knee = float(np.array(d['knee'])[int(np.argmin(np.abs(tt - t)))])
    nv, subs, ch = C.load_smesh(os.path.join(C.SA, 'tights.smesh'))
    P = ch['position'][:, [0, 2, 1]].astype(np.float64); side = np.sign(ch['uv2'][:, 0])
    P[:, 0] += C.pose_dx(P, t, knee)
    rows = list(np.linspace(0.25, 0.66, 18)) if view == 'VIEW01' else list(np.linspace(0.05, 0.62, 18))
    ref = leg_edges(orig, rows)
    base = {'VIEW01': C.VIEWS[0], 'VIEW02': C.VIEWS[1]}[view]
    D0 = np.linalg.norm(np.array(base[1]) - np.array(base[0]))

    def err(z):
        Dp, th, k = z
        cam = cam_at(base, Dp, th, k)
        ours = our_edges(P, side, cam, rows); e, n = 0.0, 0
        for y in rows:
            R, O = ref[y], ours[y]
            for (a0, a1) in R:
                if not O: e += 0.05; n += 1; continue
                best = min(O, key=lambda o: abs(0.5 * (o[0] + o[1]) - 0.5 * (a0 + a1)))
                if a0 > 0.02: e += (best[0] - a0) ** 2; n += 1
                if a1 < 0.98: e += (best[1] - a1) ** 2; n += 1
        return e / max(n, 1)

    best = None
    for Dp0 in (D0, D0 * 1.3, D0 * 1.6, D0 * 2.2):          # multi-start: the pivot depth is the ambiguous one
        r = minimize(err, [Dp0, th0, k0], method='Nelder-Mead', options=dict(maxiter=600, xatol=1e-4, fatol=1e-10))
        print('start Dp %.2f -> Dp %.3f th %.2f k %.3f  rms %.4f' % (Dp0, r.x[0], r.x[1], r.x[2], np.sqrt(r.fun)))
        if best is None or r.fun < best.fun: best = r
    print('rms with the old orbit-about-target: %.4f' % np.sqrt(err([D0, th0, k0])))
    print(json.dumps({'Dp': round(float(best.x[0]), 4), 'Dp_over_target': round(float(best.x[0] / D0), 3), 'orbit': round(float(best.x[1]), 2), 'dolly': round(float(best.x[2]), 4), 'rms': round(float(np.sqrt(best.fun)), 4)}))


if __name__ == '__main__':
    main()
