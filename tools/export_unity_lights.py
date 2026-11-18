#!/usr/bin/env python3
# SHEER — converts the Blender lights of unity_export/sheer_scene.json into a Unity-ready list
# (unity/Assets/Sheer/Data/scene_lights.json): Unity axes (x, y, z) = Blender (x, z, y), emit direction = Blender
# local -Z, rectangle up = Blender local +Y, photometric power (683 lm per Blender W, so with HDRP exposure
# EV100 = log2(683 / 1.2) - blender_exposure the pre-tonemap pixel values equal Cycles'), Blender light linking ->
# HDRP rendering layers, and Blender's 'spread' approximated with barn doors.
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LM_PER_W = 683.0
# rendering layers: 0 = everything, 1 = character (body, tights, skirt), 2 = legs (body, tights), 3 = floor
LAYER_BITS = {'all': 1 << 0, 'character': 1 << 1, 'legs': 1 << 2, 'floor': 1 << 3}


def euler_xyz(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx                                  # Blender 'XYZ' euler


def b2u(v):
    return [float(v[0]), float(v[2]), float(v[1])]


def layers_for(receivers):
    r = set(receivers)
    if not r:
        return LAYER_BITS['all']
    if r == {'floor'}:
        return LAYER_BITS['floor']
    if r == {'body', 'tights'}:
        return LAYER_BITS['legs']
    if r <= {'body', 'tights', 'skirt'}:
        return LAYER_BITS['character']
    raise ValueError('unmapped receivers %s' % receivers)


def main():
    scene = json.load(open(os.path.join(ROOT, 'unity_export', 'sheer_scene.json')))
    out = []
    for name, L in scene['lights'].items():
        if L['type'] != 'AREA':
            raise ValueError('only area lights are exported (%s)' % name)
        R = euler_xyz(*L['rotation_euler'])
        fwd = b2u(-R[:, 2]); up = b2u(R[:, 1])
        w, h = L['size'], L.get('size_y', L['size'])
        spread = L.get('spread_deg', 180.0)
        # spread < 90 deg: perpendicular barn doors long enough that the rectangle centre emits within spread/2
        door = 0.0 if spread >= 90.0 else 0.5 * min(w, h) / math.tan(math.radians(spread * 0.5))
        out.append({'name': name, 'position': b2u(L['location']), 'forward': fwd, 'up': up,
                    'lumen': L['energy_w'] * LM_PER_W, 'color': L['color'][:3], 'width': w, 'height': h,
                    'spreadDeg': spread, 'barnDoorLength': door, 'layerMask': layers_for(L['receivers']),
                    'enabled': L['energy_w'] > 0.0})
    dst = os.path.join(ROOT, 'unity', 'Assets', 'Sheer', 'Data')
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(dst, 'scene_lights.json'), 'w') as fh:
        json.dump({'lights': out, 'blenderExposure': 0.3, 'lumenPerWatt': LM_PER_W}, fh, indent=1)
    for o in out:
        print('%-8s lm %7.0f  size %.2fx%.2f  spread %5.1f  door %.2f m  layers %d  fwd %s' % (
            o['name'], o['lumen'], o['width'], o['height'], o['spreadDeg'], o['barnDoorLength'], o['layerMask'],
            [round(x, 2) for x in o['forward']]))


if __name__ == '__main__':
    main()
