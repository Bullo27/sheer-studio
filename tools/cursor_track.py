# Track the white mouse-cursor arrow in game-view frames (fps given), print t, x, y (normalized).
import sys, glob, numpy as np
from PIL import Image
files = sorted(glob.glob(sys.argv[1] + '/m_*.png')); fps = float(sys.argv[2])
for i, f in enumerate(files):
    im = np.asarray(Image.open(f).convert('RGB')).astype(np.int16)
    H, W, _ = im.shape
    wh = (im.min(-1) >= 248)
    wh[int(0.86 * H):, :int(0.25 * W)] = False          # VIEW buttons
    ys, xs = np.nonzero(wh)
    if len(xs) == 0:
        print('%5.2f  -' % (i / fps)); continue
    # cluster: keep the densest small blob (cursor ~ 10x16 px at this scale)
    best = None
    for k in range(0, len(xs), max(1, len(xs) // 200)):
        m = (np.abs(xs - xs[k]) < 8) & (np.abs(ys - ys[k]) < 12)
        if best is None or m.sum() > best[0]:
            best = (m.sum(), xs[m].min(), ys[m].min(), xs[m].max() - xs[m].min(), ys[m].max() - ys[m].min())
    n, x0, y0, w, h = best
    ok = 4 <= n <= 160 and w <= 14 and h <= 20
    print('%5.2f  %s x=%.3f y=%.3f n=%d' % (i / fps, 'C' if ok else '?', x0 / W, y0 / H, n))
