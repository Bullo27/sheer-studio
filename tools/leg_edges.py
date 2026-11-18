# Measure leg silhouettes per image row (normalized coords) in a game-view frame.
# Legs = warm/dark pixels; background = blue gradient; fog floor = bright.
import sys, json
import numpy as np
from PIL import Image

def runs(mask_row, minlen):
    out = []; start = None
    for i, v in enumerate(np.append(mask_row, False)):
        if v and start is None: start = i
        if not v and start is not None:
            if i - start >= minlen: out.append((start, i - 1))
            start = None
    return out

def edges(path, rows):
    im = np.asarray(Image.open(path).convert('RGB')).astype(np.float32) / 255.0
    H, W, _ = im.shape
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    leg = ((b - r) < 0.07) & (lum < 0.62) & ((g - r) < 0.1)
    res = {}
    for y in rows:
        yy = int(y * (H - 1))
        m = leg[max(0, yy - 2):yy + 3].mean(0) > 0.5
        res[y] = [(round(a / W, 4), round(c / W, 4)) for a, c in runs(m, int(0.03 * W))]
    return res

if __name__ == '__main__':
    path = sys.argv[1]
    rows = [float(x) for x in sys.argv[2].split(',')]
    for y, rr in edges(path, rows).items():
        print('%.2f' % y, rr)
