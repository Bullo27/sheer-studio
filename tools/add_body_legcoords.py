#!/usr/bin/env python3
# SHEER — gives the body mesh the stocking's damage-map coordinates, so the skin shader knows where it is covered
# by nylon (and where a hole or ladder exposes it): uv2 = (u around the leg 0..1 (0 = back), rest height m,
# leg side +1/-1, under-stocking weight). Same leg axis construction as the stocking's 'tuv' (sheer_tights /
# cloth_proto.axis_tables), computed from the exported stocking mesh. Rewrites body.smesh in place (backup .bak).
# Usage: python3 tools/add_body_legcoords.py unity_export/StreamingAssets [unity/Assets/StreamingAssets]
import os, struct, shutil, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloth_proto as C

TOP = 0.985          # waistband height (Blender z): above it there is no stocking


def write_smesh(path, nv, subs, ch, types):
    out = bytearray(b'SMSH') + struct.pack('<III', 1, nv, len(subs))
    for s in subs:
        a = np.ascontiguousarray(s, np.uint32).ravel()
        out += struct.pack('<I', a.size) + a.tobytes()
    out += struct.pack('<I', len(ch))
    for name, arr in ch.items():
        typ = types[name]; arr = np.ascontiguousarray(arr, np.uint32 if typ else np.float32)
        out += name.encode().ljust(16, b'\0')[:16] + struct.pack('<BBH', typ, arr.shape[1], 0) + arr.tobytes()
    open(path, 'wb').write(bytes(out))


def main():
    dirs = sys.argv[1:] or ['unity_export/StreamingAssets']
    src = dirs[0]
    nvt, _, tch = C.load_smesh(os.path.join(src, 'tights.smesh'))
    PT = tch['position'][:, [0, 2, 1]].astype(np.float64)                 # Blender axes
    tables = {s: C.axis_tables(PT, s) for s in (1, -1)}
    nv, subs, ch = C.load_smesh(os.path.join(src, 'body.smesh'))
    if 'uv2' in ch:
        print('body.smesh already has uv2; recomputing')
    P = ch['position'][:, [0, 2, 1]].astype(np.float64)
    side = np.where(P[:, 0] >= 0, 1.0, -1.0)
    u = np.zeros(nv); cover = np.zeros(nv)
    for s in (1, -1):
        zc, cx, cy = tables[s]
        m = side == s
        ax = np.interp(P[m, 2], zc, cx); ay = np.interp(P[m, 2], zc, cy)
        u[m] = (np.arctan2(P[m, 0] - ax, P[m, 1] - ay) / (2 * np.pi)) % 1.0
    cover = (P[:, 2] < TOP).astype(np.float64)
    uv2 = np.stack([u, P[:, 2], side, cover], 1).astype(np.float32)
    ch = dict(ch); ch['uv2'] = uv2
    types = {k: (1 if v.dtype == np.uint32 else 0) for k, v in ch.items()}
    for d in dirs:
        path = os.path.join(d, 'body.smesh')
        if not os.path.exists(path + '.bak'):
            shutil.copyfile(path, path + '.bak')
        write_smesh(path, nv, subs, ch, types)
        nv2, _, ch2 = C.load_smesh(path)
        assert nv2 == nv and np.allclose(ch2['uv2'], uv2)
        print('wrote %s: %d verts, channels %s' % (path, nv, {k: v.shape[1] for k, v in ch2.items()}))


if __name__ == '__main__':
    main()
