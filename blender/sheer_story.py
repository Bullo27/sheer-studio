# SHEER — the original video's choreography as data (replayed by sheer_replay.py).
# The cursor path and the knee-gap signal were measured on the original at 30 fps
# (tools/track_all.py -> data/original_track.json). Presses (grab -> drag -> release/tear),
# camera moves and the model's flinches were read off the footage frame by frame.
import os, json, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DURATION = 36.2
VIEW_SWITCH = (24.25, 25.55)          # click on VIEW 02 at ~24.2 s, smooth camera move

# side: 1 = character's left leg (VIEW 01 hero), -1 = right leg (VIEW 02 hero)
# fwd: share of the pull directed toward the camera (|drag| units); burst: tears at release
PRESSES = [
    dict(t0=-0.60, t1=1.00, side=1, fwd=0.10, burst=True, pre=False, cap=0.03),   # knee pinch: small dimple pulled down -> hole + run
    dict(t0=2.45, t1=3.95, side=1, fwd=0.30, burst=True, pre=True, cap=0.04),     # thigh pulled at the camera (dark blotch), pre-run dashes, burst
    dict(t0=5.08, t1=5.75, side=1, fwd=0.30, burst=True, pre=False),      # tent dragged right from the thigh
    dict(t0=6.45, t1=7.05, side=1, fwd=0.30, burst=True, pre=False),
    dict(t0=7.45, t1=8.05, side=1, fwd=0.30, burst=True, pre=False),      # tent at the knee, right
    dict(t0=12.62, t1=13.20, side=1, fwd=0.30, burst=False, pre=False),   # tent right, released
    dict(t0=17.30, t1=18.20, side=1, fwd=0.30, burst=False, pre=False),   # small tent right
    dict(t0=18.55, t1=19.85, side=1, fwd=0.50, burst=True, pre=True),     # just under the hem -> tear at the top
    dict(t0=21.55, t1=22.55, side=1, fwd=0.35, burst=True, pre=False),    # big tent at the top right
    dict(t0=26.94, t1=27.75, side=-1, fwd=0.10, burst=True, pre=False),   # VIEW 02: calf sail dragged down-left (onset at the calf's edge, 60 fps check)
    dict(t0=29.65, t1=30.55, side=-1, fwd=0.30, burst=False, pre=False),   # ankle tent left
    dict(t0=30.65, t1=31.40, side=-1, fwd=0.30, burst=False, pre=False),
    dict(t0=31.50, t1=32.75, side=-1, fwd=0.40, burst=False, pre=False),   # big sail from the upper calf
    dict(t0=32.80, t1=34.00, side=-1, fwd=0.10, burst=True, pre=False),
    dict(t0=34.45, t1=35.00, side=-1, fwd=0.30, burst=False, pre=False),
]
# the video starts mid-pinch: cursor path before t=0 (grab on the knee, pulled down)
PRE_CURSOR = [(-0.60, 0.470, 0.785), (0.0, 0.430, 0.910)]

# camera moves (player zoom/orbit): (t_in0, t_in1, t_out0, t_out1, base view, dolly factor, orbit deg)
CAM_MOVES = [
    (7.90, 8.30, 9.20, 9.50, 'VIEW01', 0.86, 12.0),
    (11.85, 12.15, 12.60, 12.90, 'VIEW01', 0.92, 5.0),
    (31.35, 31.65, 32.25, 32.55, 'VIEW02', 0.88, -6.0),
]
WIND_GUSTS = [(18.4, 19.6, 2.6), (20.4, 21.4, 1.6)]   # (t0, t1, strength multiplier)


def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6 - 15) + 10)


class Track:
    def __init__(self, path=os.path.join(HERE, 'data', 'original_track.json')):
        d = json.load(open(path))
        self.t = np.array([r['t'] for r in d])
        cx = np.array([r['cur'][0] if r['cur'] else np.nan for r in d])
        cy = np.array([r['cur'][1] if r['cur'] else np.nan for r in d])
        self.visible = ~np.isnan(cx)
        ok = self.visible
        self.cx = np.interp(self.t, self.t[ok], cx[ok]); self.cy = np.interp(self.t, self.t[ok], cy[ok])
        # light smoothing (3-frame) of the tracked position
        k = np.array([0.25, 0.5, 0.25])
        self.cx = np.convolve(np.pad(self.cx, 1, mode='edge'), k, 'valid')
        self.cy = np.convolve(np.pad(self.cy, 1, mode='edge'), k, 'valid')
        # knee gap (VIEW 01): hero inner edge - other leg inner edge at row .65
        g = np.array([(r['gap']['0.65'][1] - r['gap']['0.65'][0]) if '0.65' in r['gap'] else np.nan for r in d])
        bad = np.zeros_like(self.visible)
        for (a, b_, c, e, view, _, _) in CAM_MOVES:
            bad |= (self.t > a - 0.1) & (self.t < e + 0.1)
        bad |= self.t > VIEW_SWITCH[0]
        g[bad] = np.nan
        okg = ~np.isnan(g)
        g = np.interp(self.t, self.t[okg], g[okg])
        kin = np.clip((0.155 - g) / (0.155 - 0.025), 0.0, 1.0)
        kk = np.exp(-0.5 * (np.arange(-9, 10) / 4.0) ** 2); kk /= kk.sum()
        self.knee_in = np.convolve(np.pad(kin, 9, mode='edge'), kk, 'valid')

    def cursor(self, t):
        if t < 0:
            (t0, x0, y0), (t1, x1, y1) = PRE_CURSOR
            a = (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, True
        x = float(np.interp(t, self.t, self.cx)); y = float(np.interp(t, self.t, self.cy))
        i = min(int(round(t * 30)), len(self.t) - 1)
        return x, y, bool(self.visible[i])

    def knee(self, t):
        if t > VIEW_SWITCH[0]:
            # VIEW 02: no visible flinch in the original (calf tops and the other leg's edge stay put after each tear);
            # the Unity replay JSON ramps the VIEW 01 value to 0 through the camera switch (24.21-26.6 s)
            return 0.0
        return float(np.interp(max(t, 0.0), self.t, self.knee_in))


def wind_gain(t):
    g = 1.0
    for a, b_, m in WIND_GUSTS:
        if a <= t <= b_:
            x = (t - a) / (b_ - a)
            g = max(g, 1.0 + (m - 1.0) * math.sin(math.pi * x))
    return g
