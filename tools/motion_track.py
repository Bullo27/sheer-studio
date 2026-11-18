import os
import sys, glob, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from leg_edges import runs
files = sorted(glob.glob(sys.argv[1] + '/m_*.png'))
fps = float(sys.argv[2])
print(' t     | row .45: other_R  hero_L  hero_R | row .65: other_R hero_L hero_R | hem_y@x.35 hem_y@x.6')
for i, f in enumerate(files):
    im = np.asarray(Image.open(f).convert('RGB')).astype(np.float32) / 255.0
    H, W, _ = im.shape
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    leg = ((b - r) < 0.07) & (lum < 0.62) & ((g - r) < 0.1)
    out = []
    for y in (0.45, 0.65):
        yy = int(y * H)
        rr = runs(leg[yy - 2:yy + 3].mean(0) > 0.5, int(0.03 * W))
        if len(rr) >= 2 and rr[0][0] <= 2:
            out += [rr[0][1] / W, rr[1][0] / W, rr[1][1] / W]
        elif rr:
            out += [float('nan'), rr[0][0] / W, rr[0][1] / W]
        else:
            out += [float('nan')] * 3
    # skirt hem: lowest row (from top, within top 45%) where the column is still skirt-grey (low saturation, dark-mid)
    sat = im.max(-1) - im.min(-1)
    hem = []
    for x in (0.35, 0.6):
        col = (sat[:int(0.45 * H), int(x * W)] < 0.06) & (lum[:int(0.45 * H), int(x * W)] > 0.06)
        idx = np.nonzero(col)[0]
        hem.append(idx.max() / H if len(idx) else float('nan'))
    print('%5.2f  |        %.3f   %.3f   %.3f  |        %.3f  %.3f  %.3f  |  %.3f  %.3f' % (i / fps, *out, *hem))
