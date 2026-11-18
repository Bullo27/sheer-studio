# Compare sRGB colours at matching normalized image points (patch mean) between images.
import sys, numpy as np
from PIL import Image
PTS = {
 'v1': [('thigh_c', .45, .40), ('knee_c', .42, .70), ('thigh_L', .27, .45), ('thigh_R', .60, .45),
        ('shin_c', .45, .95), ('bg_mid', .85, .55), ('bg_top', .85, .10), ('bg_low', .80, .92), ('skirt', .45, .10)],
 'v2': [('calf_c', .36, .30), ('shin_c', .32, .50), ('ankle', .32, .66), ('foot', .30, .92), ('calf_L', .20, .30),
        ('calf_R', .50, .30), ('bg_mid', .62, .40), ('bg_top', .62, .08), ('fog', .62, .92), ('fog_L', .08, .88), ('horizon', .62, .72)],
}
def sample(path, pts):
    im = np.asarray(Image.open(path).convert('RGB')).astype(np.float32)
    H, W, _ = im.shape
    out = []
    for n, x, y in pts:
        cx, cy = int(x * W), int(y * H); r = max(3, W // 120)
        out.append(im[cy - r:cy + r + 1, cx - r:cx + r + 1].reshape(-1, 3).mean(0))
    return out
view = sys.argv[1]; imgs = sys.argv[2:]
res = [sample(p, PTS[view]) for p in imgs]
print('%-9s' % 'point' + ''.join('%-22s' % p.split('/')[-1][:20] for p in imgs))
for i, (n, x, y) in enumerate(PTS[view]):
    print('%-9s' % n + ''.join('%-22s' % ('(%3d,%3d,%3d)' % tuple(r[i])) for r in res))
