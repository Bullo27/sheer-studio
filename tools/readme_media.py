#!/usr/bin/env python3
"""SHEER - the README's media from the player's own output (nothing from the original video).

usage: readme_media.py SHOWCASE_DIR CAPTURES_DIR [OUT_DIR=docs/img]
  SHOWCASE_DIR: the player's -sheerShowcase DIR output (panel.png, classic.png, look_0..5.png)
  CAPTURES_DIR: batch replay captures, one folder per clip (u_0001.jpg|png ...): hero/ and clip_*/ (sorted), each
                clip optionally with a label.txt
Writes: hero.gif (the README's first image), showreel.mp4, panel.jpg, classic.jpg, looks.jpg and
        social_preview.png (1280 x 640: GitHub's link card, uploaded in the repo settings).
"""
import glob
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_B = os.path.join(HERE, '..', 'unity', 'Assets', 'Sheer', 'Resources', 'Fonts', 'MPLUSRounded1c-Bold.ttf')
FONT_M = os.path.join(HERE, '..', 'unity', 'Assets', 'Sheer', 'Resources', 'Fonts', 'MPLUSRounded1c-Medium.ttf')


def frames(d):
    f = sorted(glob.glob(os.path.join(d, 'u_*.jpg'))) or sorted(glob.glob(os.path.join(d, 'u_*.png')))
    return f


def jpg(src, dst, crop=None, width=None, q=88):
    im = Image.open(src).convert('RGB')
    if crop:
        im = im.crop(crop(im))
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, quality=q, optimize=True, progressive=True)
    print('wrote', dst, im.size, os.path.getsize(dst) // 1024, 'KB')


def hero_gif(d, out, start=0, n=None, fps=15, width=380):
    f = frames(d)[start:(start + n) if n else None]
    tmp = os.path.join(os.path.dirname(out), '_hero_list.txt')
    with open(tmp, 'w') as fh:
        for p in f:
            fh.write(f"file '{os.path.abspath(p)}'\nduration {1 / 30:.6f}\n")
    vf = f'fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', tmp, '-vf', vf, '-loop', '0', out], check=True)
    os.remove(tmp)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')


def showreel(clips, out, width=720):
    """clips: list of (frame dir, label); every clip scaled to one size, a label in the corner, a short fade"""
    parts = []
    for i, (d, label) in enumerate(clips):
        f = frames(d)
        if not f:
            continue
        lst = out + f'.{i}.txt'
        with open(lst, 'w') as fh:
            for p in f:
                fh.write(f"file '{os.path.abspath(p)}'\nduration {1 / 30:.6f}\n")
        part = out + f'.{i}.mp4'
        n = len(f)
        txt = label.replace(':', '\\:').replace("'", "’")
        vf = (f"scale={width}:-2:flags=lanczos,fade=in:0:6,fade=out:{max(n - 6, 0)}:6,"
              f"drawtext=fontfile='{FONT_B}':text='{txt}':x=24:y=h-th-28:fontsize=30:fontcolor=white:"
              f"box=1:boxcolor=0xE84888@0.75:boxborderw=12")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-vf', vf, '-r', '30',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '22', '-preset', 'slow', part], check=True)
        os.remove(lst)
        parts.append(part)
    lst = out + '.parts.txt'
    with open(lst, 'w') as fh:
        for p in parts:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', '-movflags', '+faststart', out], check=True)
    for p in parts + [lst]:
        os.remove(p)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')


def rounded(im, r):
    m = Image.new('L', im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    out = Image.new('RGBA', im.size)
    out.paste(im, (0, 0), m)
    return out


def social(left_img, right_img, out):
    W, H = 1280, 640
    bg = Image.new('RGB', (W, H))
    top, bot = (255, 226, 238), (226, 214, 255)
    d = ImageDraw.Draw(bg)
    for y in range(H):
        k = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(top[c] + (bot[c] - top[c]) * k) for c in range(3)))
    # the simulator, a portrait card on the left
    a = Image.open(left_img).convert('RGB')
    ar = 400 / 560
    if a.width / a.height < ar:      # portrait frame: full width, a band of the right height around the knees
        cw, ch = a.width, round(a.width / ar); y0 = max(0, min(a.height - ch, round(a.height * 0.18))); a = a.crop((0, y0, cw, y0 + ch))
    else:                            # landscape screenshot: the game view's left part
        cw = min(a.width, round(a.height * ar)); ch = round(cw / ar); x0 = max(0, (a.width - cw) // 2 - round(a.width * 0.12)); a = a.crop((x0, 0, x0 + cw, ch))
    a = a.resize((400, 560), Image.LANCZOS)
    sh = Image.new('RGBA', (440, 600), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((20, 26, 420, 586), 30, fill=(120, 40, 90, 90))
    bg.paste(sh.filter(ImageFilter.GaussianBlur(12)), (20, 14), sh.filter(ImageFilter.GaussianBlur(12)))
    card = rounded(a, 28); bg.paste(card, (40, 40), card)
    # the title
    fb = ImageFont.truetype(FONT_B, 92); fm = ImageFont.truetype(FONT_M, 34); fs = ImageFont.truetype(FONT_M, 25)
    x = 490
    d.text((x, 70), 'SHEER', font=fb, fill=(232, 72, 136))
    d.text((x, 185), 'a real-time sheer-tights simulator', font=fm, fill=(90, 60, 100))
    lines = ['grab it anywhere - it stretches, sails and tears',
             'GPU knit cloth · holes & ladders along the wales',
             "the original demo's panel, field for field",
             'a cloth skirt, colours, skin tones, backdrops, music']
    for i, s in enumerate(lines):
        y = 250 + 50 * i
        d.ellipse((x, y + 10, x + 14, y + 24), fill=(255, 122, 172))
        d.text((x + 28, y), s, font=fs, fill=(70, 50, 80))
    # the original's panel (the right part of a classic-inspector screenshot), small, bottom right
    if right_img and os.path.exists(right_img):
        b = Image.open(right_img).convert('RGB')
        b = b.crop((round(b.width * 0.72), round(b.height * 0.06), b.width, round(b.height * 0.29)))
        b = b.resize((250, round(b.height * 250 / b.width)), Image.LANCZOS)
        rb = rounded(b, 14); bg.paste(rb, (W - 250 - 44, H - rb.height - 40), rb)
    d.text((x, H - 76), 'Unity 6 · HDRP · Windows & Linux', font=fs, fill=(140, 110, 150))
    bg.save(out, optimize=True)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')


def main():
    sc, caps = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, '..', 'docs', 'img')
    os.makedirs(out, exist_ok=True)
    s = lambda n: os.path.join(sc, n)
    jpg(s('panel.png'), os.path.join(out, 'panel.jpg'), width=1280)
    jpg(s('classic.png'), os.path.join(out, 'classic.jpg'), width=1280)
    # the looks: a strip of legs (panel closed, VIEW 01), each cropped to the legs
    looks = [s(f'look_{i}.png') for i in range(6)]
    looks = [p for p in looks if os.path.exists(p)]
    if looks:
        cells = []
        for p in looks:
            im = Image.open(p).convert('RGB')
            w, h = im.size; cw = round(h * 0.55); x0 = max(0, round(w * 0.5 - cw * 0.5) - round(w * 0.04))
            cells.append(im.crop((x0, 0, x0 + cw, h)).resize((300, round(300 * h / cw)), Image.LANCZOS))
        st = Image.new('RGB', (300 * len(cells) + 8 * (len(cells) - 1), cells[0].height), (255, 255, 255))
        for i, c in enumerate(cells):
            st.paste(c, (i * 308, 0))
        st.save(os.path.join(out, 'looks.jpg'), quality=86, optimize=True, progressive=True)
        print('wrote looks.jpg', st.size)
    hero = os.path.join(caps, 'hero')
    if os.path.isdir(hero):
        hero_gif(hero, os.path.join(out, 'hero.gif'))
    clips = []
    for d in sorted(glob.glob(os.path.join(caps, 'clip_*'))):
        lab = open(os.path.join(d, 'label.txt')).read().strip() if os.path.exists(os.path.join(d, 'label.txt')) else ''
        clips.append((d, lab))
    if clips:
        showreel(clips, os.path.join(out, 'showreel.mp4'))
    hf = frames(hero) if os.path.isdir(hero) else []
    left = hf[min(len(hf) - 1, int(len(hf) * 0.55))] if hf else s('classic.png')
    social(left, s('classic.png'), os.path.join(out, 'social_preview.png'))


if __name__ == '__main__':
    main()
