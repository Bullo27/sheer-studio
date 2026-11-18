# Track the original video at 30 fps: cursor position (game-view normalized) and the knee gap
# (VIEW01 rows .45/.65). Output JSON for the replay storyboard.
import os
import sys, json, subprocess, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from leg_edges import runs
video, out = sys.argv[1], sys.argv[2]
W, H = 575, 1005
cmd = ['ffmpeg', '-v', 'error', '-i', video, '-vf', 'fps=30,crop=1150:2010:20:150,scale=%d:%d' % (W, H),
       '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
res = []; i = 0
while True:
    buf = p.stdout.read(W * H * 3)
    if len(buf) < W * H * 3:
        break
    im = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.int16)
    t = i / 30.0; i += 1
    wh = im.min(-1) >= 248
    wh[int(0.86 * H):, :int(0.25 * W)] = False
    ys, xs = np.nonzero(wh)
    cur = None
    if len(xs):
        best = None
        for k in range(0, len(xs), max(1, len(xs) // 200)):
            m = (np.abs(xs - xs[k]) < 8) & (np.abs(ys - ys[k]) < 12)
            if best is None or m.sum() > best[0]:
                best = (int(m.sum()), xs[m].min(), ys[m].min(), xs[m].max() - xs[m].min(), ys[m].max() - ys[m].min())
        n, x0, y0, w, h = best
        if 4 <= n <= 160 and w <= 14 and h <= 20:
            cur = [round(x0 / W, 4), round(y0 / H, 4)]
    f = im.astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    leg = ((b - r) < 0.07) & (lum < 0.62) & ((g - r) < 0.1)
    gap = {}
    for y in (0.45, 0.65):
        yy = int(y * H)
        rr = runs(leg[yy - 2:yy + 3].mean(0) > 0.5, int(0.03 * W))
        if len(rr) >= 2 and rr[0][0] <= 2:
            gap[str(y)] = [rr[0][1] / W, rr[1][0] / W]
    res.append(dict(t=round(t, 4), cur=cur, gap=gap))
json.dump(res, open(out, 'w'))
print('frames', len(res), 'cursor found', sum(1 for r in res if r['cur']), 'gap found', sum(1 for r in res if '0.65' in r['gap']))
