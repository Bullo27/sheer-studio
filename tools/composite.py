# Composite the original game's UI over rendered frames: VIEW 01 / VIEW 02 buttons (active = steel blue,
# inactive = translucent dark plate), the mouse cursor replayed from the original, and encode to MP4.
# Usage: python3 composite.py FRAMES_DIR OUT.mp4 [--fps 30]
import sys, os, json, subprocess, glob, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument('frames'); ap.add_argument('out'); ap.add_argument('--fps', type=int, default=30)
ap.add_argument('--crf', type=int, default=16)
a = ap.parse_args()
log = json.load(open(os.path.join(a.frames, 'ui_log.json')))
frames = {r['f']: r for r in log['frames']}
files = sorted(glob.glob(os.path.join(a.frames, 'f_*.png')))
W, H = Image.open(files[0]).size
WE, HE = W - W % 2, H - H % 2          # H.264 needs even dimensions
FONT = None
for fp in ('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
    if os.path.exists(fp):
        FONT = ImageFont.truetype(fp, max(8, int(0.0115 * H))); break
BTN = [('VIEW 01', 0.905, 0.931), ('VIEW 02', 0.939, 0.965)]
X0, X1 = 0.049, 0.21
ACTIVE = (76, 119, 148, 255)
INACTIVE = (14, 16, 22, 165)
# the click on VIEW 02 (~24.2 s): the cursor travels to the button, presses, leaves
CLICK = (23.70, 24.15, 24.30, 24.55)   # leave the scene, reach button, release, back to scene


def cursor_at(r, t):
    x, y = r['cursor']; vis = r['visible']
    a0, a1, a2, a3 = CLICK
    bx, by = (X0 + X1) / 2 + 0.02, (BTN[1][1] + BTN[1][2]) / 2 + 0.004
    if a0 <= t <= a3:
        if t < a1:
            k = (t - a0) / (a1 - a0); k = k * k * (3 - 2 * k)
            return 0.54 + (bx - 0.54) * k, 0.83 + (by - 0.83) * k, True
        if t < a2:
            return bx, by, True
        k = (t - a2) / (a3 - a2); k = k * k * (3 - 2 * k)
        return bx + (0.334 - bx) * k, by + (0.85 - by) * k, True
    return x, y, vis


def draw_cursor(d, x, y, s):
    pts = [(0, 0), (0, 16.5), (4.2, 12.6), (7.2, 19.6), (9.6, 18.6), (6.7, 11.9), (12.2, 11.9)]
    P = [(x + px * s, y + py * s) for px, py in pts]
    d.polygon(P, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    d.line(P + [P[0]], fill=(0, 0, 0, 255), width=max(1, int(round(s))))


enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (WE, HE),
                        '-r', str(a.fps), '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', str(a.crf),
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
for fp in files:
    f = int(os.path.basename(fp)[2:6])
    r = frames.get(f)
    im = Image.open(fp).convert('RGBA')
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    t = r['t'] if r else (f - 1) / a.fps
    active = 'VIEW 01' if t < CLICK[2] else 'VIEW 02'
    for label, y0, y1 in BTN:
        box = (int(X0 * W), int(y0 * H), int(X1 * W), int(y1 * H))
        pressed = label == 'VIEW 02' and CLICK[1] <= t < CLICK[2]
        col = ACTIVE if label == active else INACTIVE
        if pressed:
            col = (60, 96, 122, 255)
        d.rectangle(box, fill=col)
        tw = d.textlength(label, font=FONT)
        d.text(((box[0] + box[2] - tw) / 2, (box[1] + box[3]) / 2 - FONT.size * 0.58), label, font=FONT, fill=(255, 255, 255, 255))
    if r:
        cx, cy, vis = cursor_at(r, t)
        if vis:
            draw_cursor(d, cx * W, cy * H, H / 1890 * 1.5)
    im = Image.alpha_composite(im, ov).convert('RGB').crop((0, 0, WE, HE))
    enc.stdin.write(im.tobytes())
enc.stdin.close(); enc.wait()
print('wrote', a.out, len(files), 'frames', W, 'x', H)
