# Fit VIEW01 / VIEW02 cameras so the projected leg silhouettes match the ones measured on the
# original game-view frames (tools/leg_edges.py). Nelder-Mead over camera position, look-at, lens.
import bpy, numpy as np, json
me = bpy.data.objects['body'].data
co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3).astype(np.float64)
co = co[co[:, 2] < 0.86]
ASPECT = 1890 / 1080
import os
ZR = {1: (0.45, 0.8), -1: tuple(float(v) for v in os.environ.get('ZR2', '0.18,0.45').split(','))}
FOOTW = float(os.environ.get('FOOTW', '4.0'))   # camera height limits per view (no low upward angles)
# rows: y -> ((hero_left, hero_right), other_inner_edge)
T01 = {0.30: ((0.230, 0.669), 0.164), 0.35: ((0.233, 0.651), 0.130), 0.40: ((0.237, 0.634), 0.117),
       0.50: ((0.226, 0.592), 0.116), 0.60: ((0.221, 0.552), 0.126), 0.70: ((0.223, 0.547), 0.119),
       0.95: ((0.299, 0.630), 0.041)}
T02 = {0.03: ((0.284, 0.643), 0.692), 0.10: ((0.233, 0.599), 0.732), 0.20: ((0.179, 0.547), 0.757),
       0.30: ((0.170, 0.530), 0.777), 0.40: ((0.186, 0.491), 0.816), 0.50: ((0.204, 0.457), 0.847),
       0.60: ((0.219, 0.434), 0.873), 0.70: ((0.221, 0.417), 0.887)}

def project(P, C, T, lens):
    f = T - C; f /= np.linalg.norm(f)
    r = np.cross(f, (0, 0, 1)); r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = P - C
    z = d @ f
    k = lens / 36.0
    return 0.5 + ASPECT * k * (d @ r) / z, 0.5 - k * (d @ u) / z

def cost(p, targets, hero_side):
    C = p[0:3]; T = np.array([p[3], 0.0, p[4]]); lens = p[5]
    if not (40 < lens < 160) or C[1] > -0.4:
        return 1e9
    zlo, zhi = ZR[hero_side]
    if not (zlo <= C[2] <= zhi):
        return 1e9
    xi, yi = project(co, C, T, lens)
    hero = co[:, 0] * hero_side > 0
    err = 0.0
    for y, ((l, r_), oth) in targets.items():
        m = np.abs(yi - y) < 0.004
        mh = m & hero; mo = m & ~hero
        if mh.sum() < 3:
            err += 1.0; continue
        err += (xi[mh].min() - l) ** 2 + (xi[mh].max() - r_) ** 2
        if oth is not None:
            if mo.sum() < 3:
                err += 0.05
            else:
                e = xi[mo].max() if hero_side == 1 else xi[mo].min()
                err += 0.5 * (e - oth) ** 2
    if hero_side == -1:      # original VIEW02: hero toe tips touch the floor at y = 0.962, foot spans x 0.20-0.47
        mf = hero & (co[:, 2] < 0.03)
        err += FOOTW * (yi[mf].max() - 0.962) ** 2
        mf2 = hero & (np.abs(yi - 0.90) < 0.004)
        if mf2.sum() > 3 and FOOTW > 0:
            err += (xi[mf2].min() - 0.18) ** 2 + (xi[mf2].max() - 0.47) ** 2
    return err

def nelder_mead(f, x0, step, iters=600):
    n = len(x0)
    pts = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[i] * step[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for it in range(iters):
        o = np.argsort(vals); pts = [pts[i] for i in o]; vals = [vals[i] for i in o]
        c = np.mean(pts[:-1], 0)
        xr = c + (c - pts[-1]); fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1]); fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c); fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    i = int(np.argmin(vals))
    return pts[i], vals[i]

res = {}
for name, tg, side, x0 in (('VIEW01', T01, 1, [0.12, -1.15, 0.55, 0.065, 0.6, 85.0]),
                            ('VIEW02', T02, -1, [-0.04, -1.1, float(os.environ.get('Z2', '0.28')), -0.04, 0.22, 85.0])):
    best = None
    for lens0 in (60.0, 85.0, 110.0):
        x0_ = list(x0); x0_[5] = lens0
        x0_[1] = x0[1] * lens0 / 85.0
        p, v = nelder_mead(lambda p: cost(p, tg, side), x0_, [0.03, 0.15, 0.05, 0.02, 0.05, 10.0])
        p, v = nelder_mead(lambda p: cost(p, tg, side), p, [0.01, 0.05, 0.02, 0.01, 0.02, 4.0])
        print('FIT %s lens0 %.0f -> cost %.5f  C=(%.4f, %.4f, %.4f) T=(%.4f, 0, %.4f) lens %.1f' % (name, lens0, v, *p))
        if best is None or v < best[1]:
            best = (p, v)
    p = best[0]
    xi, yi = project(co, p[0:3], np.array([p[3], 0, p[4]]), p[5])
    hero = co[:, 0] * side > 0
    for y, ((l, r_), oth) in tg.items():
        m = (np.abs(yi - y) < 0.004) & hero
        print('   row %.2f target %.3f-%.3f got %.3f-%.3f' % (y, l, r_, xi[m].min(), xi[m].max()))
    mf = hero & (co[:, 2] < 0.03)
    print('   toe tip y_img %.3f (orig 0.962)' % yi[mf].max())
    res[name] = [float(x) for x in p]
json.dump(res, open(os.environ.get('SHEER_CAMFIT', 'camfit.json'), 'w'), indent=1)
print('CAMFIT', json.dumps(res))
