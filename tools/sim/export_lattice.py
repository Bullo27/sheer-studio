# (SUPERSEDED 2026-11-16: Unity reads sock_lattice.bin - one lattice per leg from the toes, tools/sim/export_sock_lattice.py.
#  This leg-only lattice is still what the Python prototype - geom.build_leg, leash.py - simulates.)
# Exports the cloth lattice of both legs for the Unity compute cloth (unity/Assets/StreamingAssets/cloth_lattice.bin).
#   'SLAT', u32 version, u32 NU, u32 NV, f32 y0, f32 y1, then per leg (side +1, then -1):
#   f32 ax[NV], az[NV], R[NV*NU] (row major: j along, i around), X[NV*NU*3]
#   python3 tools/sim/export_lattice.py [NU NV]
import os, sys, struct, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom

def main():
    NU = int(sys.argv[1]) if len(sys.argv) > 1 else 256
    NV = int(sys.argv[2]) if len(sys.argv) > 2 else 320
    # from the ankle to under the skirt. (Tried from the instep, y0 = 0.05, for the original's ankle / foot sails: the
    # foot is not a tube about an axis - cross-sections 30 x 85 mm - and the radial leg field blows the fabric up there.)
    y0, y1 = 0.086, 0.776
    out = os.path.join(geom.SA, 'cloth_lattice.bin')
    with open(out, 'wb') as fh:
        fh.write(b'SLAT'); fh.write(struct.pack('<IIIff', 1, NU, NV, y0, y1))
        for side in (1, -1):
            g = geom.build_leg(side, NU=NU, NV=NV, y0=y0, y1=y1)
            for k in ('ax', 'az', 'R', 'X'):
                fh.write(np.ascontiguousarray(g[k], dtype='<f4').tobytes())
    print('wrote %s (%.1f MB): %d x %d per leg' % (out, os.path.getsize(out) / 1e6, NU, NV))

if __name__ == '__main__':
    main()
