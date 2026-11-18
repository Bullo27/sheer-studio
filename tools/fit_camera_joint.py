#!/usr/bin/env python3
# SHEER — joint camera fit over several frames of one view (each with its own pose: replay time + knee value):
# minimises the summed silhouette edge error of fit_camera.py. Usage: fit_camera_joint.py VIEW01 T1:ORIG1 T2:ORIG2 ...
import json, os, sys
import numpy as np
from scipy.optimize import minimize
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_proto as C
from fit_camera import leg_edges, our_edges


def main():
    view = sys.argv[1]
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'unity', 'Assets', 'StreamingAssets', 'replay_session.json')))
    tt = np.array(d['t']); kn = np.array(d['knee'])
    nv, subs, ch = C.load_smesh(os.path.join(C.SA, 'tights.smesh'))
    P0 = ch['position'][:, [0, 2, 1]].astype(np.float64)
    side = np.sign(ch['uv2'][:, 0])
    rows = list(np.linspace(0.25, 0.66, 18))
    sets = []
    for arg in sys.argv[2:]:
        t, f = arg.split(':', 1); t = float(t)
        knee = float(kn[int(np.argmin(np.abs(tt - t)))])
        P = P0.copy(); P[:, 0] += C.pose_dx(P, t, knee)
        sets.append((t, leg_edges(f, rows), P))
    v = {'VIEW01': C.VIEWS[0], 'VIEW02': C.VIEWS[1]}[view]
    cam0 = np.array(list(v[0]) + list(v[1]) + [v[2]], np.float64)

    def err(cam, per=False):
        tot, out = 0.0, []
        for t, ref, P in sets:
            ours = our_edges(P, side, cam, rows); e, n = 0.0, 0
            for y in rows:
                R, O = ref[y], ours[y]
                for (a0, a1) in R:
                    if not O: e += 0.05; n += 1; continue
                    best = min(O, key=lambda o: abs(0.5 * (o[0] + o[1]) - 0.5 * (a0 + a1)))
                    if a0 > 0.02: e += (best[0] - a0) ** 2; n += 1
                    if a1 < 0.98: e += (best[1] - a1) ** 2; n += 1
            out.append(np.sqrt(e / max(n, 1))); tot += e / max(n, 1)
        return (tot / len(sets), out) if per else tot / len(sets)

    e0, per0 = err(cam0, True)
    print('start rms per frame:', [round(x, 4) for x in per0])
    scale = np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 5.0])
    res = minimize(lambda z: err(cam0 + z * scale), np.zeros(7), method='Nelder-Mead', options=dict(maxiter=1500, xatol=1e-4, fatol=1e-10))
    cam = cam0 + res.x * scale
    e1, per1 = err(cam, True)
    print('fit   rms per frame:', [round(x, 4) for x in per1])
    print(json.dumps({'loc': cam[:3].round(4).tolist(), 'target': cam[3:6].round(4).tolist(), 'lens': round(float(cam[6]), 2)}))


if __name__ == '__main__':
    main()
