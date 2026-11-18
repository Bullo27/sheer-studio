# python3 tools/sim/run_drag.py <name> x0 y0 x1 y1 [lift] [t_pull] [t_hold] [view]
import os, sys, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import game, render

def smooth(t): t = min(max(t, 0.0), 1.0); return t * t * (3 - 2 * t)

def drag(g, x0, y0, x1, y1, lift=0.3, t_pull=0.6, t_hold=0.3, t_rel=0.6, every=2, verbose=True):
    s, k = g.press(x0, y0)
    c = g.cl[s]
    if verbose: print('grab side %+d node %s y %.3f theta %.0f' % (s, k, c.x[k][1], k[1] * 360.0 / c.NU))
    n1 = int((t_pull + t_hold) * g.fps); n2 = int(t_rel * g.fps)
    for f in range(n1 + n2):
        t = (f + 1) / g.fps
        if f < n1:
            a = smooth(t / t_pull)
            g.frame((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), lift, render_it=f % every == 0)
        else:
            if f == n1: g.release()
            g.frame(None, render_it=f % every == 0 or f == n1 + n2 - 1)
        if verbose and (f % 3 == 0 or f == n1 + n2 - 1):
            t_, F, d, nl, nh = g.log[-1]
            cu, cv, fu, fv, fl = c.cell_loads(); m = c.S == 0
            print('  t %.2f F %.3f pull %.1f mm  ladder %d hole %d  max lam_u %.2f lam_v %.2f  lifted %.1f%%%s' % (
                t_, F, d * 1e3, nl, nh, cu[m].max(), cv[m].max(), 100 * (c.Nn < 0).mean(), '  [torn off]' if c.torn_off else ''))
    return c

if __name__ == '__main__':
    a = sys.argv
    name = a[1]; x0, y0, x1, y1 = [float(v) for v in a[2:6]]
    lift = float(a[6]) if len(a) > 6 else 0.3
    t_pull = float(a[7]) if len(a) > 7 else 0.6; t_hold = float(a[8]) if len(a) > 8 else 0.3
    view = a[9] if len(a) > 9 else 'VIEW01'
    out = os.path.join(os.environ.get('SCRATCH', '/tmp'), 'sim_' + name); os.makedirs(out, exist_ok=True)
    g = game.Game(view=view)
    c = drag(g, x0, y0, x1, y1, lift, t_pull, t_hold)
    render.sheet(g.frames, min(len(g.frames), 12), os.path.join(out, 'sheet.jpg'), scale=0.6)
    render.save(g.frames[-1], os.path.join(out, 'last.png'))
    np.save(os.path.join(out, 'S.npy'), c.S)
