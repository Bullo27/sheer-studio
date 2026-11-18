#!/usr/bin/env python3
"""Overview sheets of the Studio from a self-test run (player: -sheerStudioTest DIR).

usage: studio_sheets.py DIR OUTDIR [TAG]
Writes OUTDIR/studio_<TAG>_{tabs,presets,scene,extras}.jpg (TAG defaults to today's date).
"""
import datetime
import glob
import os
import sys

from PIL import Image, ImageDraw


def sheet(paths, out, cols, cell_w, crop=None, labels=None):
    ims = []
    for p in paths:
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        if crop:
            im = im.crop(crop(im))
        im = im.resize((cell_w, int(im.height * cell_w / im.width)))
        ims.append((os.path.basename(p), im))
    if not ims:
        return
    ch = max(im.height for _, im in ims)
    rows = (len(ims) + cols - 1) // cols
    s = Image.new("RGB", (cols * cell_w, rows * ch), (24, 22, 26))
    d = ImageDraw.Draw(s)
    for i, (name, im) in enumerate(ims):
        x, y = (i % cols) * cell_w, (i // cols) * ch
        s.paste(im, (x, y))
        lab = labels[i] if labels and i < len(labels) else os.path.splitext(name)[0]
        d.text((x + 6, y + 4), lab, fill=(255, 235, 120))
    s.save(out, quality=88)
    print("wrote", out, s.size)


def main():
    src, out = sys.argv[1], sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else datetime.date.today().isoformat()
    os.makedirs(out, exist_ok=True)
    g = lambda pat: sorted(glob.glob(os.path.join(src, pat)))
    panel = lambda im: (im.width - 440, 0, im.width, im.height)
    sheet(g("tab_*.png"), f"{out}/studio_{tag}_tabs.jpg", 6, 300, crop=panel)
    sheet(g("preset_*.png"), f"{out}/studio_{tag}_presets.jpg", 4, 420, crop=lambda im: (0, 0, im.width - 470, im.height))
    sheet(g("back_*.png") + g("floor_*.png"), f"{out}/studio_{tag}_scene.jpg", 4, 400)
    sheet(g("shape_*.png") + g("plush_*.png") + g("filter_*.png") + g("frame_*.png") + g("ribbon_v0_0.png")
          + g("classic.png") + g("classic_tip.png") + g("classic_hier.png") + g("mend_*.png") + g("polish_*.png") + g("sandal_*.png"),
          f"{out}/studio_{tag}_extras.jpg", 5, 380)


if __name__ == "__main__":
    main()
