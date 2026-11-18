# SHEER — photoreal sheer-tights tension & tearing (Blender / Cycles version)

(This was the project README before the Unity real-time version became the main deliverable; preserved here.)

<!-- DEMO VIDEO: media/sheer_demo.mp4 (drag the MP4 into this README on GitHub to embed it) -->
https://github.com/OWNER/REPO/raw/main/media/sheer_demo.mp4

A path-traced recreation of the **pantyhose tension / tear demo** shown by Sakura Rabbit (樱花兔) in
Unity 6. Black 20-denier tights grabbed and pulled by the player: the knit goes sheer as it stretches,
tents into a membrane, tears into holes and ladders (runs) that zip along the leg, with secondary
holes along the ladder. Same two camera presets (**VIEW 01** thigh/knee, **VIEW 02** calf/foot), same
inspector (`TensionData: Pantyhose`) with the same parameters and values as in the original video.

Rendered with **Blender 4.5 LTS + Cycles** (OptiX). Every step is scripted (bpy + numpy) and
reproducible headless.

## What is replicated

| Original (Unity) | Here |
|---|---|
| Grab-and-drag pulls on the tights | the original video's cursor path is **replayed**: each press ray-casts the cursor into the matched camera, the tent tip follows the drag |
| Stretch → sheer, tension → tear | per-vertex stretch drives the shader; scripted tears create holes + ladders (numpy damage engine, rasterised to UV-space SDF textures every frame) |
| Holes, "bowling-pin" holes, ladders with rungs, secondary holes | `sheer_damage.py` (holes snap to existing ladders, lobes, run holes) + tights shader (rolled rims, fringe, ladder threads) |
| Model reacting (knees pressed together after tears) | pose layer driven by the knee gap measured on the original footage, feet planted |
| Skirt moving in the air of a fan | real cloth simulation (pressed knife pleats) draped on a collision proxy, wind + gusts |
| VIEW 01 / VIEW 02 + camera moves | cameras fitted to the original's leg silhouettes; zooms and the smooth VIEW 01→02 move at the same times |
| Inspector sliders (张力与褶皱 / 珠光与闪点 / 雾面与透肤 …) | `sheer_params.py` (names, ranges, **the video's values**) + Blender add-on panel `sheer_addon.py` (live) |
| Stocking toe, reinforced foot | morphological *closing* of the forefoot → one continuous toe box (`sheer_toebox.py`); foot "frost" layer |

The skirt is a plain charcoal pleated mini skirt (no school-uniform striping) and the model is an adult
body (CC0 Blender Studio base mesh).

## Player controls (the original's inspector)

`blender/sheer_addon.py` adds **View3D › Sidebar › Pantyhose** with every field of the original
inspector, at the values shown in the video:

- Normal Strength 1 · Weave Tiling 12 · Weave Normal Strength 0.845 · Weave Contrast 0.025
- **张力与褶皱 Tension & Wrinkles** — Tension Mode Stretch · Wrinkle Strength 9 · Tension Normal Boost 1.5
- **珠光与闪点 Pearl & Glints** — Strength 0.387 · Grain Scale 572 · Randomness 0.435 · Specular Strength 0.64 ·
  Edge Strength 0.128 · Edge Start 0 · Edge Width Power 0.54 · Pull Edge Width 0.0122 · Glint Strength 0.85 · Glint Density 0.117
- **雾面与透肤 Frost & Skin show-through** — Body Coverage 0.829 · Foot Coverage 0.889 · Clear At Stretch 1 ·
  Matte Smoothness 0.837 · Boundary Strength 1 · Boundary Width (px) 5.9

Moving a slider rebuilds the material; *Reset to the video's values* restores the demo look.

## Build & render

Requirements: Blender 4.5 LTS, an NVIDIA GPU (OptiX), Python 3 with numpy/Pillow (tools), ffmpeg,
and the CC0 *Human Base Meshes* bundle from Blender Studio.

```bash
# 1) scene (body prep, toe box, tights, materials, cloth-draped skirt, floor cloth, lights, cameras)
blender -b -P blender/sheer_build.py -- human_base_meshes_bundle.blend scene.blend
# 2) replay the original session (36 s, 30 fps) — resumable
blender -b scene.blend -P blender/sheer_replay.py -- --out frames --pct 100 --spp 128
# 3) UI overlay (VIEW 01/02 buttons, cursor) + encode
python3 tools/composite.py frames media/sheer_demo.mp4
```

Stills: `blender -b scene.blend -P blender/render_still.py -- out.png VIEW01 100 128`.

## Repository map

- `blender/sheer_build.py` — builds the scene; `sheer_body.py` (base mesh prep, proportions, stance, feet),
  `sheer_toebox.py` (stocking toe box), `sheer_tights.py` (tights mesh, UV, attributes), `sheer_materials.py`
  (skin, tights, wool skirt, floor cloth), `sheer_skirt.py` (pleated cloth skirt), `sheer_scene.py`
  (lights, backdrop, floor, cameras), `sheer_params.py` / `sheer_addon.py` (inspector).
- `blender/sheer_damage.py` — holes / ladders / marks engine; `sheer_anim.py` — tent deformer & pull physics;
  `sheer_story.py` + `sheer_replay.py` — the original's session replayed (cursor, presses, flinches, camera, wind).
- `blender/data/original_track.json` — cursor path and knee gap measured on the original video (30 fps).
- `tools/` — measurement & compositing (`track_all.py`, `leg_edges.py`, `sample_colors.py`, `composite.py`).
- `web/` — an earlier real-time WebGL prototype (not the showcase).

## Credits

Original demo and shader design: Sakura Rabbit (樱花兔), Unity 6. This repository is an independent
recreation. Body: Blender Studio *Human Base Meshes* (CC0). Rendering: Blender / Cycles.
