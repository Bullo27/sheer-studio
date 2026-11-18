# Reader for the project's .smesh files (see tools/check_smesh.py).
import struct, numpy as np

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
