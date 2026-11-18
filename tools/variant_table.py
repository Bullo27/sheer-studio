#!/usr/bin/env python3
# SHEER — colour table for a variant sweep (sweep.sh): every var_NN.png against the original frame at the colorcal
# points; per variant the mean |log linear ratio| over the leg points (background excluded: it is unlit) and per point
# the luminance ratio and the chroma difference (ours - original, in sRGB r-b).
# Usage: python3 tools/variant_table.py v1|v2 ORIGINAL.png SWEEPDIR "variant;variant;..."
import os, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from colorcal import PTS, lin, patch


def profile(img, yy):
    """luma at 9 points across the hero leg (largest non-backdrop run) at height yy"""
    from fit_camera import leg_edges
    row = img[int(yy * 945)]
    bg = row[:, 2] > row[:, 0] + 12
    runs, i = [], 0
    while i < 540:
        if not bg[i]:
            j = i
            while j < 540 and not bg[j]: j += 1
            if j - i > 6 and i > 4: runs.append((i, j))
            i = j
        else: i += 1
    if not runs: return []
    a, b = max(runs, key=lambda r: r[1] - r[0])
    xs = np.linspace(a + 4, b - 4, 9).astype(int)
    r0 = int(yy * 945)
    return [int(img[r0 - 3:r0 + 4, x - 2:x + 3].mean()) for x in xs]


def teal(img):
    reg = img[100:800, :520]
    m = (reg[..., 1] > reg[..., 0] + 40) & (reg[..., 2] > reg[..., 0] + 40)
    px = reg[m]
    if len(px) < 10: return 'none'
    br = px.max(1); top = px[br >= np.percentile(br, 97)]
    return '%5d px, top3%% (%3d,%3d,%3d)' % ((m.sum(),) + tuple(top.mean(0).astype(int)))


def main():
    view, orig, d, vars_ = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(';')
    A = np.asarray(Image.open(orig).convert('RGB').resize((540, 945))).astype(np.float64)
    PY = 0.40 if view == 'v1' else 0.30
    pts = [p for p in PTS[view] if not p[0].startswith('bg')]
    ref = {n: patch(A, x, y, 5) for n, x, y in pts}
    print('original    ' + '  '.join('%-14s' % n for n, _, _ in pts))
    print('            ' + '  '.join('(%3d,%3d,%3d)' % tuple(ref[n]) for n, _, _ in pts))
    print('            profile %s   teal %s' % (profile(A, PY), teal(A)))
    for i, v in enumerate(vars_):
        f = os.path.join(d, 'var_%02d.png' % i)
        if not os.path.exists(f):
            print('%2d missing  %s' % (i, v)); continue
        B = np.asarray(Image.open(f).convert('RGB').resize((540, 945))).astype(np.float64)
        errs, cells = [], []
        for n, x, y in pts:
            pa, pb = ref[n], patch(B, x, y, 5)
            r = lin(pb) / np.maximum(lin(pa), 1e-4)
            errs.append(np.abs(np.log(np.maximum(r, 1e-3))))
            Y = (0.2126 * lin(pb)[0] + 0.7152 * lin(pb)[1] + 0.0722 * lin(pb)[2]) / max(0.2126 * lin(pa)[0] + 0.7152 * lin(pa)[1] + 0.0722 * lin(pa)[2], 1e-4)
            cells.append('Y%4.2f rb%+4d' % (Y, int((pb[0] - pb[2]) - (pa[0] - pa[2]))))
        e = np.array(errs).mean()
        print('%2d err %.3f  %s   [%s]' % (i, e, '  '.join(cells), v))
        print('            profile %s   teal %s' % (profile(B, PY), teal(B)))


if __name__ == '__main__':
    main()
