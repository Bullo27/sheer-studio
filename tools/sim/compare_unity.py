# Numerical check of the Unity compute cloth (SheerCloth.compute) against the reference (leash.py): the same grab,
# the same pinch position at every substep, node positions compared at a few checkpoints.
#   python3 tools/sim/compare_unity.py gen [dir]      write <dir>/path.bin and the expected states
#   (run Unity: -executeMethod SheerEditor.ClothTest.Run -sheerClothTest <dir>)
#   python3 tools/sim/compare_unity.py cmp [dir]      compare
import os, sys, struct, numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom, leash, run_leash

ROOT = geom.ROOT
DIR = os.path.join(ROOT, 'unity_logs', 'cloth_test')

def scenario():
    """The 'drag' scenario of run_leash.py: front of the thigh dragged 80 mm down the leg, held, released."""
    sc = run_leash.Scene('VIEW01')
    c = sc.cl[1]
    jg = int(round((0.60 - c.y0) / c.dy))
    px, py, z = sc.cam.project(c.X[jg]); ig = int(np.argmin(z.cpu().numpy()))
    sm = lambda u: (lambda v: v * v * (3 - 2 * v))(min(max(u, 0.0), 1.0))
    path = lambda t: (0.01 * sm(t / 0.5), 0.08 * sm(t / 0.5))
    return sc, c, jg, ig, path

def gen(d):
    os.makedirs(d, exist_ok=True)
    sc, c, jg, ig, path = scenario()
    P = c.P; rate = P.sub_rate; dt = 1.0 / rate
    t_hold, t_end = 0.6, 0.7
    nrel = int(round(t_hold * rate)); nsub = int(round(t_end * rate))
    checks = [64, 640, int(0.3 * rate), nrel, nrel + 64, nsub]
    c.grab(jg, ig)
    j0, j1 = max(jg - 4, 0), min(jg + 4, c.NV - 1)
    axis = np.array([float(c.ax[j1] - c.ax[j0]), (j1 - j0) * c.dy, float(c.az[j1] - c.az[j0])], np.float32)
    pull = run_leash.Pull(axis=axis)
    A_all = np.zeros((nsub, 3), np.float32); exp = {}
    for s in range(nsub):
        t = (s + 1) * dt
        if s == nrel: c.release()
        if s < nrel:
            dx, dy = path(t)
            S = pull.update(sc.screen_vec(dx, dy), dt)
            A = c.pinch_c + torch.as_tensor(S, device=c.dev)
            A, _ = c.collide(A.view(1, 3), margin=0.009)       # (the path only has to be a plausible pull: Unity replays these positions)
            c.pull = A[0] - c.pinch_c
            A_all[s] = A[0].cpu().numpy()
        c.step(1)
        if s + 1 in checks:
            exp[s + 1] = np.concatenate([c.x.cpu().numpy(), c.h.cpu().numpy()[..., None]], -1).astype(np.float32)
    with open(os.path.join(d, 'path.bin'), 'wb') as fh:
        fh.write(struct.pack('<6i', 1, jg, ig, nsub, nrel, len(checks)))
        fh.write(np.asarray(checks, '<i4').tobytes()); fh.write(A_all.astype('<f4').tobytes())
    np.savez(os.path.join(d, 'expected.npz'), **{str(k): v for k, v in exp.items()}, X=c.X.cpu().numpy())
    print('grab node (%d, %d), %d substeps, release at %d, checkpoints %s -> %s' % (jg, ig, nsub, nrel, checks, d))

def cmp(d):
    e = np.load(os.path.join(d, 'expected.npz')); X = e['X']; ok = True
    for k in sorted(int(k) for k in e.files if k != 'X'):
        f = os.path.join(d, 'unity_%d.bin' % k)
        if not os.path.exists(f): print('substep %5d: no Unity state' % k); ok = False; continue
        u = np.fromfile(f, '<f4').reshape(X.shape[0], X.shape[1], 4); r = e[str(k)]
        dr = np.linalg.norm(r[..., :3] - X, axis=-1); du = np.linalg.norm(u[..., :3] - X, axis=-1)
        diff = np.linalg.norm(u[..., :3] - r[..., :3], axis=-1)
        w = np.unravel_index(np.argmax(diff), diff.shape)
        print('substep %5d: displacement max ref %.2f mm unity %.2f mm | difference max %.4f mm (node %s) mean %.5f mm rms %.5f mm | lift diff max %.4f mm' % (
            k, dr.max() * 1e3, du.max() * 1e3, diff.max() * 1e3, w, diff.mean() * 1e3, np.sqrt((diff ** 2).mean()) * 1e3,
            np.abs(u[..., 3] - r[..., 3]).max() * 1e3))
        if diff.max() > 2e-3: ok = False
    print('MATCH' if ok else 'MISMATCH')
    return ok

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'gen'
    d = sys.argv[2] if len(sys.argv) > 2 else DIR
    sys.exit(0 if (gen(d) if mode == 'gen' else cmp(d)) is not False else 1)
