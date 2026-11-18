# SHEER — writes the original session (cursor path, knee reflex, presses, camera moves, view switch, wind)
# as one JSON for the Unity replay driver (ReplayDriver.cs). Times in seconds, cursor in normalized
# game-view coordinates (x right, y down from the top) of the original 1890x1080 window.
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'blender'))
import sheer_story as STY

out = sys.argv[1]
tr = STY.Track()
fps = 30.0
t0 = STY.PRESSES[0]['t0'] - 0.05
n = int((STY.DURATION - t0) * fps) + 2
cols = dict(t=[], x=[], y=[], visible=[], knee=[], wind=[])
for i in range(n):
    t = t0 + i / fps
    x, y, vis = tr.cursor(t)
    cols['t'].append(round(t, 4)); cols['x'].append(round(x, 5)); cols['y'].append(round(y, 5))
    cols['visible'].append(1 if vis else 0); cols['knee'].append(round(tr.knee(t), 4)); cols['wind'].append(round(STY.wind_gain(t), 4))
# JsonUtility-friendly: no nested arrays, every press has all fields
presses = [dict(t0=p['t0'], t1=p['t1'], side=p['side'], fwd=p['fwd'], burst=p['burst'], pre=p['pre'], cap=p.get('cap', 0.11))
           for p in STY.PRESSES]
data = dict(duration=STY.DURATION, viewSwitch=list(STY.VIEW_SWITCH), presses=presses,
            camMoves=[dict(i0=a, i1=b, o0=c, o1=d, view=v, dolly=k, orbit=o) for (a, b, c, d, v, k, o) in STY.CAM_MOVES],
            windGusts=[dict(t0=a, t1=b, gain=m) for (a, b, m) in STY.WIND_GUSTS], fps=fps, window=[1890, 1080],
            clickView02=dict(leave=23.70, reach=24.15, release=24.30, back=24.55), **cols)
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(data, open(out, 'w'))
print('wrote', out, len(cols['t']), 'samples')
