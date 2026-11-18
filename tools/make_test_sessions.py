#!/usr/bin/env python3
# SHEER - free-play test sessions for the replay driver (-sheerSession FILE): INPUT ONLY (cursor, presses, camera), no
# per-pull values, no lean track (the body's own motion runs, as in free play). CLAUDE.md: test free play directly.
#   idle.json  - nobody touches anything: VIEW 01 for 12 s, then VIEW 02 - the stance, the knees, the toes, the skirt
#   pulls.json - generic pulls of every kind on both legs, in both views
#   python3 tools/make_test_sessions.py [outdir]
import json, os, sys
import numpy as np

FPS = 30.0


def smooth(a):
    a = np.clip(a, 0, 1); return a * a * (3 - 2 * a)


def session(duration, switch, presses, keys):
    """keys: list of (t, x, y, visible) cursor keyframes (normalized original window, x right, y down)."""
    t = np.round(np.arange(0.0, duration + 1e-6, 1 / FPS), 4)
    kt = np.array([k[0] for k in keys]); kx = np.array([k[1] for k in keys]); ky = np.array([k[2] for k in keys])
    # eased between keys (a hand moves in strokes)
    x = np.empty_like(t); y = np.empty_like(t); vis = np.ones(len(t), int)
    for i, tt in enumerate(t):
        j = np.searchsorted(kt, tt, side='right') - 1
        if j < 0: x[i], y[i] = kx[0], ky[0]
        elif j >= len(kt) - 1: x[i], y[i] = kx[-1], ky[-1]
        else:
            f = smooth((tt - kt[j]) / max(kt[j + 1] - kt[j], 1e-6))
            x[i] = kx[j] + (kx[j + 1] - kx[j]) * f; y[i] = ky[j] + (ky[j + 1] - ky[j]) * f
        vis[i] = keys[max(j, 0)][3]
    return {
        'duration': duration, 'fps': FPS, 'viewSwitch': list(switch), 'presses': presses, 'camMoves': [], 'windGusts': [],
        'clickView02': {'leave': switch[0] - 0.5, 'reach': switch[0] - 0.08, 'release': switch[0], 'back': switch[0] + 0.3},
        't': t.tolist(), 'x': np.round(x, 5).tolist(), 'y': np.round(y, 5).tolist(), 'visible': vis.tolist(),
        'knee': [0.0] * len(t), 'wind': [1.0] * len(t)}


def press(t0, t1, side):
    return {'t0': t0, 't1': t1, 'side': side}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sim', 'ref_data', 'test_sessions')
    os.makedirs(out, exist_ok=True)
    # idle: the cursor parked at the side, out of the way
    idle = session(60.0, (34.0, 35.5), [], [(0.0, 0.93, 0.30, 1), (60.0, 0.93, 0.30, 1)])
    json.dump(idle, open(os.path.join(out, 'idle.json'), 'w'))
    # the camera held half way between VIEW 01 and VIEW 02 (both legs whole, like the original at 24.9 s): the poses
    mid = session(90.0, (-1000.0, 1000.0), [], [(0.0, 0.93, 0.30, 1), (90.0, 0.93, 0.30, 1)])
    mid['clickView02'] = {'leave': 5000.0, 'reach': 5001.0, 'release': 5002.0, 'back': 5003.0}
    json.dump(mid, open(os.path.join(out, 'midview.json'), 'w'))
    # generic pulls: (t0, t1, side, [(t, x, y)]) - the press holds from t0 to t1; the cursor keys include the approach
    P = [
        # VIEW 01 (hero leg = +1 on the right of the picture; the other leg's edge at the far left)
        (1.0, 2.2, 1, [(0.6, 0.36, 0.44), (1.0, 0.36, 0.44), (1.6, 0.66, 0.40), (2.2, 0.68, 0.40)]),      # thigh, out to the side
        (3.2, 4.4, 1, [(2.8, 0.30, 0.70), (3.2, 0.30, 0.70), (3.8, 0.12, 0.74), (4.4, 0.10, 0.76)]),      # knee, inward
        (5.4, 6.6, 1, [(5.0, 0.42, 0.56), (5.4, 0.42, 0.56), (6.1, 0.46, 0.80), (6.6, 0.47, 0.84)]),      # lower thigh, down
        (7.4, 8.8, 1, [(7.0, 0.40, 0.36), (7.4, 0.40, 0.36), (8.0, 0.72, 0.44), (8.8, 0.80, 0.46)]),      # long drag: should tear
        (9.6, 10.2, -1, [(9.3, 0.05, 0.60), (9.6, 0.05, 0.60), (10.2, 0.02, 0.50)]),                      # far leg's edge
        # VIEW 02 (from 13.5 s: the -1 leg on the left, the +1 leg at the right edge)
        (14.5, 15.7, -1, [(14.1, 0.40, 0.30), (14.5, 0.40, 0.30), (15.2, 0.12, 0.32), (15.7, 0.10, 0.33)]),   # shin, out left
        (16.6, 17.8, -1, [(16.2, 0.45, 0.50), (16.6, 0.45, 0.50), (17.2, 0.72, 0.52), (17.8, 0.74, 0.53)]),   # calf, toward the other leg
        (18.8, 20.4, -1, [(18.4, 0.38, 0.70), (18.8, 0.38, 0.70), (19.6, 0.10, 0.62), (20.4, 0.06, 0.60)]),   # ankle, long: should tear
        (21.4, 22.6, 1, [(21.0, 0.90, 0.35), (21.4, 0.90, 0.35), (22.0, 0.70, 0.40), (22.6, 0.68, 0.42)]),    # other leg, inward
    ]
    presses = [press(a, b, s) for a, b, s, _ in P]
    keys = [(0.0, 0.93, 0.30, 1)]
    for a, b, s, ks in P:
        for k in ks: keys.append((k[0], k[1], k[2], 1))
        keys.append((b + 0.4, ks[-1][1] + 0.02, ks[-1][2] - 0.02, 1))
    keys.append((24.0, 0.93, 0.30, 1))
    keys.sort(key=lambda k: k[0])
    pulls = session(24.0, (12.0, 13.5), presses, keys)
    json.dump(pulls, open(os.path.join(out, 'pulls.json'), 'w'))
    # a tear between two existing ones: two long held pulls ~6 cm apart on the thigh, then one between them
    # (capture it with -sheerStill: the body holds still, so the clicks land where they are aimed)
    B = [(1.0, 3.6, 1, [(0.6, 0.24, 0.42), (1.0, 0.24, 0.42), (1.5, 0.66, 0.40), (3.6, 0.68, 0.40)]),
         (5.0, 7.6, 1, [(4.6, 0.46, 0.44), (5.0, 0.46, 0.44), (5.5, 0.88, 0.42), (7.6, 0.90, 0.42)]),
         (9.0, 11.6, 1, [(8.6, 0.35, 0.43), (9.0, 0.35, 0.43), (9.5, 0.78, 0.41), (11.6, 0.80, 0.41)])]
    keys = [(0.0, 0.93, 0.30, 1)]
    for a, b_, s_, ks in B:
        for k in ks: keys.append((k[0], k[1], k[2], 1))
        keys.append((b_ + 0.4, 0.93, 0.30, 1))
    keys.sort(key=lambda k: k[0])
    between = session(14.0, (30.0, 31.5), [press(a, b_, s_) for a, b_, s_, _ in B], keys)
    json.dump(between, open(os.path.join(out, 'between.json'), 'w'))
    # ACROSS THE ANKLE (VIEW 02, the -1 leg on the left; capture with -sheerStill): the stocking is one tube from the toes
    # up - a pull on the lower shin draws the instep, one on the instep draws the shin, ladders run on across the ankle
    A = [(3.5, 5.0, -1, [(3.1, 0.340, 0.556), (3.5, 0.340, 0.556), (4.2, 0.19, 0.50), (5.0, 0.18, 0.495)]),    # lower shin, out and up
         (6.5, 8.0, -1, [(6.1, 0.294, 0.702), (6.5, 0.294, 0.702), (7.2, 0.30, 0.80), (8.0, 0.30, 0.81)]),      # instep at the ankle, toward the toes
         (9.5, 12.5, -1, [(9.1, 0.337, 0.599), (9.5, 0.337, 0.599), (10.3, 0.05, 0.42), (12.5, 0.03, 0.40)]),   # just above the ankle, far: tears
         (14.0, 17.0, -1, [(13.6, 0.300, 0.73), (14.0, 0.300, 0.73), (14.8, 0.31, 0.95), (17.0, 0.31, 0.97)])]  # instep, far: tears
    keys = [(0.0, 0.93, 0.30, 1)]
    for a, b_, s_, ks in A:
        for k in ks: keys.append((k[0], k[1], k[2], 1))
        keys.append((b_ + 0.4, 0.93, 0.30, 1))
    keys.sort(key=lambda k: k[0])
    ankle = session(19.0, (1.5, 3.0), [press(a, b_, s_) for a, b_, s_, _ in A], keys)
    json.dump(ankle, open(os.path.join(out, 'ankle.json'), 'w'))
    # ACROSS THE LEG (VIEW 02, calves; -sheerStill): grabbed on one side of a calf and drawn across it, or from its inner
    # side toward the other leg (user, 2026-11-16: 'the tent goes through the leg (as if the leg was not solid)')
    X = [(3.5, 6.0, -1, [(3.1, 0.215, 0.316), (3.5, 0.215, 0.316), (4.6, 0.50, 0.33), (6.0, 0.66, 0.34)]),     # -1 outer side -> across it
         (7.5, 10.0, -1, [(7.1, 0.520, 0.317), (7.5, 0.520, 0.317), (8.6, 0.80, 0.32), (10.0, 0.95, 0.33)]),   # -1 inner side -> into the other leg
         (11.5, 14.0, -1, [(11.1, 0.540, 0.250), (11.5, 0.540, 0.250), (12.6, 0.30, 0.26), (14.0, 0.14, 0.27)]),  # -1 inner side -> across it
         (15.5, 18.0, 1, [(15.1, 0.830, 0.317), (15.5, 0.830, 0.317), (16.6, 0.55, 0.32), (18.0, 0.40, 0.33)])]  # +1 inner side -> into the other leg
    keys = [(0.0, 0.93, 0.30, 1)]
    for a, b_, s_, ks in X:
        for k in ks: keys.append((k[0], k[1], k[2], 1))
        keys.append((b_ + 0.4, 0.98, 0.10, 1))
    keys.sort(key=lambda k: k[0])
    across = session(20.0, (1.5, 3.0), [press(a, b_, s_) for a, b_, s_, _ in X], keys)
    json.dump(across, open(os.path.join(out, 'across.json'), 'w'))
    print('wrote', out)


if __name__ == '__main__':
    main()
