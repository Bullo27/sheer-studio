# SHEER — bakes Blender's display transform (AgX + 'AgX - Punchy', the look the Cycles version was calibrated
# with) into a 3D LUT for HDRP's External tonemapping mode. HDRP encodes the linear Rec.709 colour with ARRI
# LogC (EI 1000, non-precise variant), samples an N^3 LUT (x = R, y = G, z = B) and expects LINEAR output (the
# sRGB encoding happens later). Exposure is 0 here: HDRP's fixed exposure already includes Blender's +0.3.
# Usage: blender -b --factory-startup -P blender/make_agx_lut.py -- OUT.raw [N=32]
#        OUT.raw = float32 RGB, x fastest (N*N*N*3 values)
import bpy, sys, os
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
out = argv[0]; N = int(argv[1]) if len(argv) > 1 else 32

# HDRP LogC (Color.hlsl, LogC = {cut 0.011361, a 5.555556, b 0.047996, c 0.244161, d 0.386036, e 5.301883, f 0.092819})
A, B, C, D = 5.555556, 0.047996, 0.244161, 0.386036
g = np.arange(N, dtype=np.float64) / (N - 1)
lin1 = (np.power(10.0, (g - D) / C) - B) / A                 # inverse of c*log10(a*x+b)+d
lin1 = np.maximum(lin1, 0.0)
r, gg, b = np.meshgrid(lin1, lin1, lin1, indexing='ij')     # [r][g][b]
# image layout: width = N*N (x = r + N*g), height = N (y = b)
rgb = np.zeros((N, N * N, 3))
for bi in range(N):
    for gi in range(N):
        rgb[bi, gi * N:(gi + 1) * N, 0] = lin1
        rgb[bi, gi * N:(gi + 1) * N, 1] = lin1[gi]
        rgb[bi, gi * N:(gi + 1) * N, 2] = lin1[bi]

img = bpy.data.images.new('lut_in', width=N * N, height=N, float_buffer=True, alpha=True)
img.colorspace_settings.name = 'Linear Rec.709'
px = np.ones((N, N * N, 4), np.float32); px[..., :3] = rgb
img.pixels.foreach_set(px.ravel())

scene = bpy.context.scene
vs = scene.view_settings
scene.display_settings.display_device = 'sRGB'
vs.view_transform = 'AgX'
looks = [l.name for l in bpy.types.ColorManagedViewSettings.bl_rna.properties['look'].enum_items] if False else None
try:
    vs.look = 'AgX - Punchy'
except TypeError:
    vs.look = 'Punchy'
vs.exposure = 0.0; vs.gamma = 1.0
vs.use_curve_mapping = False
st = scene.render.image_settings
st.file_format = 'PNG'; st.color_depth = '16'; st.color_mode = 'RGB'
tmp = out + '.png'
img.save_render(tmp, scene=scene)
res = bpy.data.images.load(tmp)
res.colorspace_settings.name = 'Non-Color'                    # read the stored display values verbatim
d = np.empty(N * N * N * 4, np.float32); res.pixels.foreach_get(d)
d = d.reshape(N, N * N, 4)[..., :3].astype(np.float64)
# sRGB display encoding -> linear (HDRP encodes to sRGB itself after the LUT)
lin = np.where(d <= 0.04045, d / 12.92, np.power((d + 0.055) / 1.055, 2.4))
lut = np.zeros((N, N, N, 3), np.float32)                     # [b][g][r] -> x = r fastest
for bi in range(N):
    for gi in range(N):
        lut[bi, gi, :, :] = lin[bi, gi * N:(gi + 1) * N, :]
lut.astype(np.float32).tofile(out)
os.remove(tmp)
print('[agx-lut] look %r, N=%d, wrote %s; mid grey 0.18 ->' % (vs.look, N, out),
      lut[int(round((C * np.log10(A * 0.18 + B) + D) * (N - 1)))].mean() if False else '')
k = int(round((C * np.log10(A * 0.18 + B) + D) * (N - 1)))
print('[agx-lut] LogC(0.18) index %d -> out %s (display %s)' % (k, lut[k, k, k].round(4), d[k, k * N + k].round(4)))
