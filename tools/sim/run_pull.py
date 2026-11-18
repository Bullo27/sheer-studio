# Scripted pull scenarios for the prototype:  python3 tools/sim/run_pull.py <name> [out_dir]
import os, sys, time, math, numpy as np, torch
sys.path.insert(0, os.path.dirname(__file__))
import geom, cloth, render

def smooth(t): t = min(max(t, 0.0), 1.0); return t * t * (3 - 2 * t)

def make(side=1, prm=None, settle=400):
    legs = {s: geom.build_leg(s) for s in (1, -1)}
    c = cloth.Cloth(legs[side], prm); o = cloth.Cloth(legs[-side], prm)
    t0 = time.time(); c.step(settle); dt = (time.time() - t0) / settle
    return c, o, dt

def run(name='knee', out=None, sub=96, chunk=8, fps=30, prm=None, pull=0.08, grab_y=0.47, grab_th=180.0, direction=(0.35, 0.05, -1.0),
        t_pull=1.0, t_hold=0.4, t_rel=0.8, side=1, view='VIEW01', W=540, H=945, extra_cam=True, verbose=True, every=3, hook=None):
    out = out or os.path.join(os.environ.get('SCRATCH', '/tmp'), 'sim_' + name); os.makedirs(out, exist_ok=True)
    c, other, dt_sub = make(side, prm)
    cam = render.Camera(W=W, H=H, **getattr(render, view))
    pv = render.Preview(cam, [c.X, other.X])
    disp = np.linalg.norm(c.x - c.X, axis=-1)
    if verbose: print('settle: %.3f ms/substep, max disp %.2f mm, mean %.3f mm, lifted %.1f%%' % (dt_sub * 1e3, disp.max() * 1e3, disp.mean() * 1e3, 100 * (c.Nn < 0).mean()))
    rest = c.x.copy()
    j = int(round((grab_y - c.y0) / c.dy)); i = int(round(grab_th / 360.0 * c.NU)) % c.NU
    p0 = c.x[j, i].copy()
    d = np.asarray(direction, np.float32); d /= np.linalg.norm(d)
    cams = [pv]
    if extra_cam:
        sc = render.Camera(pos=[float(p0[0]) + side * 1.0, float(p0[1]), float(p0[2]) - 0.02], target=[float(p0[0]), float(p0[1]), float(p0[2]) - 0.02], lens_mm=150.0, W=W, H=H)
        cams.append(render.Preview(sc, [c.X, other.X]))
        tc = render.Camera(pos=[float(p0[0]), float(p0[1]) + 1.0, float(p0[2]) - 0.25], target=[float(p0[0]), float(p0[1]), float(p0[2]) - 0.02], lens_mm=150.0, W=W, H=H)
        cams.append(render.Preview(tc, [c.X, other.X]))
    centre = c.grab(p0)
    frames = [[] for _ in cams]; log = []
    nf = int((t_pull + t_hold + t_rel) * fps); t0 = time.time()
    hand = centre.copy()
    for f in range(nf):
        t = f / fps
        for s in range(0, sub, chunk):
            ts = t + (s + chunk) / (sub * fps)
            if ts <= t_pull + t_hold:
                a = smooth(ts / t_pull)
                new = centre + d * (pull * a)
                c.gather_now = 1.0 + (c.P.gather - 1.0) * min(ts / 0.15, 1.0)
                c.step(chunk, hand, new); hand = new
            else:
                if c.grabbed: c.release()
                c.step(chunk)
            if hook: hook(c, ts)
        log.append((t, float(np.linalg.norm(c.hand_force)), float((c.Nn < 0).mean()), float(np.linalg.norm(c.x - rest, axis=-1).max())))
        if f % every == 0 or f == nf - 1:
            for k, p in enumerate(cams): frames[k].append(p.render([c, other]))
    if verbose:
        print('sim+render %.1f s for %d frames' % (time.time() - t0, nf))
        for (t, hf, lift, md) in log[::max(1, len(log) // 16)]: print('  t %.2f hand force %.4f lifted %.2f%% max disp %.1f mm' % (t, hf, 100 * lift, md * 1e3))
        resid = np.linalg.norm(c.x - rest, axis=-1)
        print('residual displacement after release: max %.2f mm mean %.3f mm' % (resid.max() * 1e3, resid.mean() * 1e3))
    for k in range(len(cams)):
        render.sheet(frames[k], min(len(frames[k]), 11), os.path.join(out, 'sheet_cam%d.jpg' % k), scale=0.5 if len(frames[k]) > 8 else 1.0)
    return c, frames, log

if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'knee'
    run(name, sys.argv[2] if len(sys.argv) > 2 else None)
