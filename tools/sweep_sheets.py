#!/usr/bin/env python3
"""SHEER - review sheets for a free-play sweep (tools/sweep_session.py): one row per pull, 5 crops round the grab (onset,
mid-drag, peak, 2 frames after the release, +0.5 s). usage: sweep_sheets.py CAPDIR PULLS.json OUTPREFIX [per_sheet=6]
[fps=30] [from=0]"""
import glob, json, os, sys
from PIL import Image, ImageDraw

cap, pj, outp = sys.argv[1], sys.argv[2], sys.argv[3]
per = int(sys.argv[4]) if len(sys.argv) > 4 else 6
fps = float(sys.argv[5]) if len(sys.argv) > 5 else 30.0
t_from = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
frames = sorted(glob.glob(os.path.join(cap, 'u_*.jpg'))) or sorted(glob.glob(os.path.join(cap, 'u_*.png')))
P = json.load(open(pj))
W0, H0 = Image.open(frames[0]).size
CELL = 216


def frame_at(t):
    i = int(round((t - t_from) * fps))
    return frames[max(0, min(len(frames) - 1, i))]


rows = []
for i, p in enumerate(P):
    drag = {'short': 0.45, 'medium': 0.6, 'long': 0.8, 'tear': 0.6, 'tap': 0.0}[p['kind']]
    ts = [('onset', p['t0'] + 0.12), ('drag', p['t0'] + max(drag * 0.6, 0.05)), ('peak', p['t1'] - 0.034),
          ('+2f', p['t1'] + 0.067), ('+0.5s', p['t1'] + 0.5)]
    x0, y0, x1, y1 = p['x'] * W0, p['y'] * H0, p['tx'] * W0, p['ty'] * H0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = max(abs(x1 - x0), abs(y1 - y0)) + 150
    side = max(side, 220)
    l = int(max(0, min(W0 - side, cx - side / 2))); t = int(max(0, min(H0 - side, cy - side / 2)))
    box = (l, t, int(l + min(side, W0)), int(t + min(side, H0)))
    row = Image.new('RGB', (CELL * 5 + 4 * 4 + 150, CELL), (24, 24, 28))
    d = ImageDraw.Draw(row)
    d.text((6, 6), '#%d V%s %s' % (i, p.get('view', 0), p['kind']), fill=(255, 255, 120))
    d.text((6, 22), 'leg %+d' % p['side'], fill=(220, 220, 220))
    d.text((6, 38), 't %.2f-%.2f' % (p['t0'], p['t1']), fill=(220, 220, 220))
    if p.get('note'): d.text((6, 54), p['note'][:22], fill=(255, 150, 150))
    for k, (name, tt) in enumerate(ts):
        im = Image.open(frame_at(tt)).convert('RGB').crop(box).resize((CELL, CELL), Image.LANCZOS)
        dd = ImageDraw.Draw(im)
        # the grab and the target, as small markers
        sx = CELL / (box[2] - box[0]); sy = CELL / (box[3] - box[1])
        gx, gy = (x0 - box[0]) * sx, (y0 - box[1]) * sy
        dd.ellipse((gx - 3, gy - 3, gx + 3, gy + 3), outline=(255, 255, 0))
        dd.text((4, CELL - 14), name, fill=(255, 255, 0))
        row.paste(im, (150 + k * (CELL + 4), 0))
    rows.append(row)

for s in range(0, len(rows), per):
    chunk = rows[s:s + per]
    sheet = Image.new('RGB', (chunk[0].width, len(chunk) * (CELL + 6)), (0, 0, 0))
    for j, r in enumerate(chunk): sheet.paste(r, (0, j * (CELL + 6)))
    fn = '%s_%02d.jpg' % (outp, s // per)
    sheet.save(fn, quality=88)
    print('wrote', fn)
