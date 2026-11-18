# Sanity checks for the .smesh exports: header/channels, winding vs normals (Unity convention:
# cross(b-a, c-a) of an index triple must point along the stored outward normal), tangent frame.
import sys, struct, numpy as np

def load(path):
    b = open(path, 'rb').read(); o = 4
    assert b[:4] == b'SMSH'
    ver, nv, ns = struct.unpack_from('<III', b, o); o += 12
    subs = []
    for _ in range(ns):
        (c,) = struct.unpack_from('<I', b, o); o += 4
        subs.append(np.frombuffer(b, np.uint32, c, o).reshape(-1, 3)); o += 4 * c
    (nc,) = struct.unpack_from('<I', b, o); o += 4
    ch = {}
    for _ in range(nc):
        name = b[o:o + 16].rstrip(b'\0').decode(); o += 16
        typ, dim, _ = struct.unpack_from('<BBH', b, o); o += 4
        a = np.frombuffer(b, np.uint32 if typ else np.float32, nv * dim, o).reshape(nv, dim); o += 4 * nv * dim
        ch[name] = a
    assert o == len(b), (o, len(b))
    return nv, subs, ch

for path in sys.argv[1:]:
    nv, subs, ch = load(path)
    P, N, T = ch['position'], ch['normal'], ch['tangent']
    tri = np.concatenate(subs)
    a, b_, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    fn = np.cross(b_ - a, c - a)
    agree = np.einsum('ij,ij->i', fn, N[tri[:, 0]] + N[tri[:, 1]] + N[tri[:, 2]]) > 0
    tdot = np.abs(np.einsum('ij,ij->i', T[:, :3], N))
    print('%s: %d verts, subs %s, channels %s' % (path.split('/')[-1], nv, [len(s) for s in subs],
          {k: v.shape[1] for k, v in ch.items()}))
    print('   winding agrees with normals: %.2f%%   |N|~1: %.4f   max |T.N| %.3g   bbox min %s max %s' % (
          100 * agree.mean(), np.abs(np.linalg.norm(N, axis=1) - 1).max(), tdot.max(),
          P.min(0).round(3).tolist(), P.max(0).round(3).tolist()))
