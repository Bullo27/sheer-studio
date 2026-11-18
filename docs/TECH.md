# SHEER - how it works

The technical side of the simulator, for people who like the nitty-gritty. The [README](../README.md) is the
player's overview.

## The stocking

- **On the skin.** The nylon is its own mesh, laid on the body: in every cross-section of the tube it is the convex
  hull of the skin's section plus the fabric's 0.2 mm (`tools/sim/wrap.py`). A taut knit bridges only what is concave
  round the tube, beside the Achilles tendon and between the toes; at a hole on the outline its edge lies on the skin.
  Along every outline you see lit skin, then a dark line of nylon seen edge-on.
  - **The toes** (`tools/reshape_legs.py`). The base mesh's toes are thin flat digits. Their skin is moved out onto the
    surface 1.8 mm outside it, taken from a smoothed signed distance field of the toes: every toe is rounder and
    fuller, and clefts narrower than 3.6 mm close, as a stocking squeezes the toes together. Within the bottom
    centimetre they are filled out more (up to 1.8 x), so the pads meet the floor as one soft edge instead of a row of lobes.
    Where that left a few hundred tiny stocking triangles folded over (culled, they were holes the skin showed through),
    a last pass relaxes them back into the asset's own orientation. Nothing reshapes the toes again at load time. The toes are also drawn
    back a little and the forefoot is slimmed by up to 20 %. The knit's hull spans the toes, then `toe_wrap` lets it
    dip part way into the clefts and smooths it.
  - **Cavities.** The worn stocking's hollows are baked into its mesh (`uv0.w`): the clefts between the toes, the
    knee pit, where the thighs meet. Each vertex is measured against the centroid of its neighbourhood at 2 and 6 mm.
    The shader lights those hollows less and makes the knit a little denser there, where it lies doubled. Fabric
    lifted off the leg leaves its hollow.
- **Cloth**: `SheerCloth.compute` and `TightsCloth.cs`.
  - One "sock" lattice per leg, from the toes to the thigh: 256 × 400 nodes, simulated on the GPU at 3840 substeps
    per second.
  - The model is damped Verlet with knit springs that lock at their stretch limit, a pre-stretch (the knit is worn
    stretched), and a friction leash to the worn position that saturates like Coulomb friction.
  - Collisions are with its own leg and with the other leg. An order constraint keeps bunched fabric from folding
    through itself.
  - The foot's knit holds on harder than the leg's (twice the friction, fading in over 8 cm below the ankle's bend): it
    lies taut over the instep and is pressed to the floor at the sole, so a pull at the ankle does not drag the instep
    along, and the change is gradual enough that no collar folds where it begins.
  - Gathered fabric lying within millimetres of the skin is pressed onto it. Real wrinkles there are a millimetre high;
    the lattice's cells are coarser than that, so the shader draws them.
  - Let go, the pinched patch and the whole sail run back together: every node covers the same share of its way home
    per substep, one exponential with a 12 ms time constant (about 48 %, 11 % and 2 % left after one, two and three
    frames at 60 fps).
  - A leg nobody touches sleeps.
- **The hand** maps the cursor to a pinched patch the way the original does (measured from two views). The fingers take
  a broad patch and hold it as a fold: 14 mm round the leg bunched to 15 %, 3.5 x as long along it bunched to 40 %, so a
  press puckers the fabric round it and a sail ends in a short blunt edge, not a needle; on the foot a round 4 mm grip. While the
  cursor is over the leg, the patch slides over the skin: it follows the whole drag round the leg but only 40 % of it
  along the leg, where the stocking is held above and below. Pulled along the leg it also stands up off the skin into
  a pocket; dragged round the leg it does not, until the hand passes the outline. The pocket stands off the skin along
  the skin's own normal under the fingers. While over the leg, the patch sits where the cursor's ray meets the surface
  (a smooth approximation of the leg's outline, replaced by the exact hit wherever the section is not round, as below
  the kneecap). Past the outline the patch leaves the leg sideways, in the plane of the leg's axis facing the viewer,
  and follows the cursor out to 12 cm, also beside a hole (the original draws full sails next to its holes, the holes
  stretched into them). The drag that tears is still
  measured against the original's 85 mm reach. How far a tear's ladders run depends on how far the fabric itself was drawn out, not on how far the
  hand went.
  - **The fabric round a pinch goes along with it.** While the pinch is dragged over the skin, every node has come
    along at least `exp(-distance / L)` of the drag (L is 0.6 x the drag, between 3 and 3.5 cm, measured on the
    original: a pull 3.7 cm from a hole drew the hole's near edge three times as far as its far edge; round the leg only
    the side the hand is on follows). The fabric ahead of the fingers is pushed together gently and the fabric behind
    is drawn out. Without this the fan of fabric trailing the pinch slid over its neighbours like a folded sheet of
    paper. Once the patch is off the skin, the field follows the skin point nearest the hand, so the fabric slides round
    the leg to where the hand leaves it and a sail grows from the outline.
  - **The fingers hold only fabric that is there.** The lattice has no holes, so as the hand takes hold one pass marks
    every node joined to the grab through intact knit along a straight line: nothing behind a hole, and nothing along
    the wale inside a ladder beyond 4 mm (its loops are gone, so nothing joins the rungs above to those below). The
    fingers' patch takes only marked nodes; the tether and the drag field fade out, over about a centimetre, round the
    unmarked ones. A pull beside a hole now stretches the hole toward the sail, as the original's do, instead of
    carrying it off the leg whole.
  - On the foot the drag follows the plane tangent to the foot at the grab.
- **No per-frame mesh uploads.** Pose and the pulled fabric are applied in the vertex shaders from small textures
  (`SheerCloth.hlsl`); the meshes are static GPU buffers. The same shaders report each vertex's motion since the
  previous frame to HDRP (custom velocity).

## Tearing

`SheerDamage.cs`, `DamageRenderer.cs` and `DamageRaster.compute`.

- **Where damage lives.** Holes, ladders, pre-runs and stretch marks live in the stocking's own (around, along-the-wale)
  coordinates, rasterised into three damage maps per leg: hole and ladder distance fields, how far the yarn next to a
  hole was pushed aside, the ladder's lateral coordinate, the distances to its ends, and wale and course densities.
- **When it tears.** A pull tears when the drag exceeds what the fabric can follow (heavier denier holds longer, damaged
  fabric gives sooner), or when the knit under a held pinch creeps through, whatever the drag:
  - from 0.65 s of holding (or at once under a hard pull) a **column of slits** opens below the pinch and walks down
    the leg (hardly up);
  - **held on**, the knit gives way 1.25 s after the press, once the slits have shown for 0.8 s (a hard yank: 0.4 s);
  - **let go** once they have shown for 0.3 s, the laddering knit gives way in the snap-back; let go sooner, the slits
    close and nothing tears.
  One global rule, fitted on all 17 presses of the original's session: its 6 tears come within 0.15 s of the hand
  letting go, each after a column of slits shown 0.3 - 0.9 s, and one of them barely moves the cursor while a hard
  0.5 s pull does not tear. With the session's input ours tears those 6 (5 at the original's moment, one 0.1 s late)
  and none of the other 11, with slits for at most 0.15 s on any press that does not tear.
  - **A tear is complete in one frame**: its holes open within 20 - 35 ms and its ladder band reaches full width just
    as fast (the original's first tear: the pocket in one frame, the finished holes in the next), then the holes creep a
    little wider over a second.
  - **Runs are long.** A ladder runs because the stocking is worn stretched, so its reach does not shrink when the tear
    came before the fabric had been drawn far (a creep tear); it still grows with how far the fabric was drawn.
  - **Holes grow when pulled again.** A held pull within 15 mm of a hole's edge works its loops loose: the hole grows
    by 12 - 42 % per second of pulling (more the harder), up to 1.8 times the size it was made at.
- **Holes** come in shapes measured on the original (round, egg, bowling pin, half-moon behind a strap, pointed
  tooth at the end of a ladder, slits and beads at junctions), always with a strap of fabric between them.
  - A tear springs open as wide as the knit's pre-stretch lets it: big round holes on the thigh and knee, tall slits
    on the shin.
- **Ladders** run along the wales, both ways: a pale grey-pink band about 70 % as wide as the holes it joins, with
  straight edges (fabric to gauze within a few millimetres). Inside it the skin shows through a gauze of loose threads
  paler than the knit they came from: mostly dense, soft rungs about 3.5 px apart, with the run wales faint across the
  band and darker along its sides (measured inside the original's band: horizontal structure about twice the
  vertical). Only its edges are ragged, and its ends taper. On the lower leg a run is a narrower, fainter strip.
  - Each wale stops on its own, which frays the ends over 3 - 6 cm into a flame of fine streaks or a few long tails.
  - **Ladders join up.** A ladder that stops within 8 cm of another one in the same wales runs on into it: the strip
    of whole knit between them carries the tension of both. Tears made one after another along a column end up as one
    ladder. (A tear beside a ladder still opens where it is pulled; it does not jump onto the ladder.)
  - A tear sometimes leaves small satellite holes (a half-moon behind a strap, a bead) on one side or the other, not
    on every hole.
  - Ladders run down over the ankle and along the foot, and stop at the reinforced toe.
  - A fingernail **snag** (Shift + click) is a pinhole that may start a ladder.
- **Hole edges.** Round every hole the knit's threads curve away and crowd toward its edge. The edge itself is an
  uneven rolled lip of bunched, lit yarn, thicker along much of the outline, with a few loose thread ends and a paler
  rim of loosened knit just outside it. Outlines wander by about a millimetre over a couple of centimetres, so holes
  are torn shapes, not punched ovals.
- **Repair** mends: every hole and ladder shrinks away over a second.

## Rendering

- **Nylon shader** (`SheerTights.hlsl`, an HDRP StackLit graph patched by `tools/patch_shadergraph.py`).
  - **Coverage** follows the inspector's *Frost* fields. It opens with stretch and closes where the knit is
    squeezed, and the yarn's shadow on the skin is carried in the stocking's own opacity, so it rides with pulled
    fabric. Fabric pushed together into less area darkens (a pile shades itself); fabric that is only sheared or
    drawn out wrinkles but keeps its tone.
  - **Sails** keep most of their worn coverage when lifted (92 %), so they read as smoky, nearly opaque veils (the
    original's lets about a quarter of the backdrop through), matte (no satin sheen off the leg), with the knit's
    texture muted where it is drawn out and seen obliquely, and smooth: the drawn wrinkle fan belongs to fabric lying
    on the leg and fades out on fabric standing off it. The fingers gather the held fold to a point, so a sail ends in a
    sharp tip.
  - **Wrinkles the lattice cannot make** are drawn: a fan of fine creases behind a pinch dragged over the leg (driven by
    the pull's own direction and length, so it shows even where the solver's stretch is small; soft crests within a few
    centimetres of the pinch, read by their light and shade), and a band of a few near-level creases at the front of
    the ankle, just above its bend, where the fabric is slack. They run along the knit's courses (its height along the
    wale), so they stay level round the ankle instead of following the instep's slope.
  - **Letting go.** Everything the hand pulled (sail, tent, the fabric slid round the leg) goes home together in its
    own shape: each substep every node covers the same share of its way back, on the profile of a released elastic,
    `(1 + t/tau) e^(-t/tau)` with tau 12 ms (4 ms when it tore), then the springs settle it. The original's sails shrink
    that way: about half gone 20 ms after release, gone by about 50 ms. Run with springs instead, the sheet snapped onto
    the bunched patch within 8 ms and the patch stood off the leg as a crumpled star of spikes for 45 ms. Fabric
    springing back is drawn as fabric on the skin (sheer, no tent shadow on the skin) until it stands more than about a
    centimetre off; held fabric lifts into tents and sails from 5 mm.
  - **On the leg, softly.** Fabric lying on the leg reads the solver's tension and normal maps from a mip level,
    averaged over about a centimetre and wider where it is pushed together: a gathered pile shows as a soft dark
    blotch ahead of the fingers and a paler, finely wrinkled fan behind them. Fabric lifted off the leg keeps every
    crease.
  - **The knit** is a net of 0.87 mm loops (`SheerWeave.cs`). Its loop-to-loop variation is kept down to loops of
    about 1.8 px, and a fine irregular grain on top, so the fabric keeps a knit grain at the normal views instead of
    reading as a smooth film.
  - **Pearl** drives sheen and glints: single fibres flashing in the key light, small (about a pixel) and many.
  - **Pale yarns** (the panel's colours) hide only their own area of the skin. Black nylon also stops the light
    on its way in and out. The thickness (denier) sets the coverage through the video's values at 20 denier
    (Beer-Lambert in the yarn's weight).
  - **Layers.** The stocking is drawn after a transparent depth prepass, so only its nearest layer is drawn. Where
    one leg's sail crosses in front of the other leg, the shader adds that leg's stocking back as a layer under
    the sail (worn coverage, same yarn). Otherwise the sheer sail would show the other leg's bare skin.
- **Floor** (`SheerSurfaces.hlsl`, `SheerFloor`): a white fleece. Its light pool in front of the feet is extra
  emission (`_SheerFloorGlow`, default 2000), because an albedo cannot go above 1: near white at the bottom of VIEW 02,
  grey-blue behind the feet. Toward the cloth's far edges it fades into the backdrop's blue, so the horizon is a soft
  band of mist.
  - **Contact shadow of the feet** (`TightsSim.UpdateContact`, `SheerContactVis`). Every frame, the stocking below the
    ankles is posed on the CPU (Burst) and splatted to a 2 mm height grid per foot: its top and its underside over each
    cell. From that come the foot's outline as a signed distance (so the shader draws it smooth), the sky hidden from
    each point of the floor round it (horizon-based, cosine-weighted, 12 directions out to 6 cm, on a 4 mm grid), and
    under the foot's overhangs the sky that comes in from the open edge (`1 - 0.5 sin^2 atan(B / d)`). The floor darkens
    by `1 - 2.5 AO^2`, after its light pool. So the gap under the toes is near black, the cloth is shaded a centimetre
    or two round the foot, and the shadow follows the foot wherever the body moves it.
  - Where the toes rest on the floor, their undersides and the crease where they meet it are shaded too (stocking and
    skin): up to 92 % of the light gone within a centimetre of the floor, more where the surface faces down.
- **Skin** (`SheerSkin.hlsl`): body-part tones, mottling, pores and subsurface scattering, plus a contact shadow
  inside hole edges. Skin tones are aimed at measured albedos. Toenails (a paler, glossier plate with a lighter free
  edge, in a soft groove) show faintly through the reinforced toe.
- **Anti-aliasing = supersampling.**
  - The player renders up to 2 × 2 samples per pixel (`SheerSuperSample.cs`).
  - The factor adapts: it steps down (2 → 1.5 → 1) while the GPU can't hold about 60 fps, and back up when it has
    room.
  - SMAA on top, no temporal AA (it smeared moving fabric).
- **Look**: Blender's AgX "Punchy" view transform, baked into an HDRP external LUT at fixed exposure. Light
  placement and the fabric's coverage were fitted to the original video. No depth of field or motion blur by
  default (the original shows neither).
- **Skirt** (`SkirtCloth.cs`) is cloth: a position-based sheet, 72 columns round × 26 rows down, through the inner
  folds of the pleats. It is pinned at the waistband (which goes with the pelvis), falls under gravity, and is never
  inside the body: per height, the convex hull of the posed stocking (thighs, hips, buttocks) as a radius per angle,
  plus the fabric's 2.5 mm. Small steps (1/360 s), one pass each, with tethers so it never hangs longer than it is.
  It is lengthened at the front and sides only; the back keeps the mesh's length, so its back panel does not hang
  down between the thighs.
  The pleated mesh rides on the sheet, every vertex at its offset in the sheet's own frame, so the pleats go wherever
  the cloth goes. The air comes from a fan below and in front (calm spells, breezes, gusts). A tent of pulled
  fabric just under the hem holds the cloth out a little. A pinch never goes up under the skirt: it stays 1.5 cm
  below the skirt's own hem on that side of the body (`SkirtCloth.HemAt`). The hand is never drawn, so nothing
  invisible lifts the hem. It runs on worker threads one frame ahead of the body.
  - The pleats' shading is baked into the mesh by `tools/skirt_folds.py`: split normals on both folds of every knife
    pleat, and per vertex the sky light its pleat lets through (a horizon in the ring's cross-section) and its
    nearness to an outer fold. The shader turns them into ambient occlusion in the hollows, a cavity, sheen along
    the fold edges and lighter open faces (`_SheerSkirtFold`, `-sheerSkirtFold x,y,z,w`). Against the original in
    VIEW 01 this took the spread of brightness across the pleats from a quarter of the original's to about its
    level.
  - The cloth is a cool charcoal wool with a faint sheen (0.5 x its old strength): with the old sheen, seen turned
    45 degrees the skirt went a warm dusty grey, where the original's stays the same dark navy-charcoal at every angle.
    Its woven texture shows at the default views.
  - The panel's skirts are plain colours only (charcoal, black, navy, wine, camel, grey); stripes, tartans and
    other school-uniform looks are not offered.

## Body and camera

- **The feet are the model's own.** `tools/reshape_legs.py` reshapes the legs (cross-sections fitted to the original's
  outlines), but below the ankle the skin and the stocking are the source model's, untouched, blended into the reshaped
  leg between 11 and 7 cm. (Toe reshaping to answer reviews - shorter, slimmer, inflated toes, filled pads - had turned
  the toes into swollen lumps; the steps remain in the tool, off.)

- **Body motion** (`SheerBodyMotion.cs`) is a human waiting on her feet, knees turned in (the leg turned about its
  own axis, so the kneecaps face each other), toes in:
  - She stands on both legs or on one, changing every 3.5–7.5 s: on one leg the hips go ~5 cm over it and the
    other knee comes forward and in, in front of it.
  - Every 1–3 s a knee, the hips or a foot shifts; every few seconds she fidgets (a knee dips, the knees rub past each
    other, a foot turns, the hips sway) on smooth noise, never a rhythm. Big toes lift now and then.
  - Each leg's cross-sections are turned and shifted rigidly per height from a small pose texture; the two knees
    never pass through each other.
  - While the original's session is replayed (**P**) she stands as quietly as in the video: the original's own
    tracked sway (from its outlines) with its after-tear flinches filtered out, on a calm stance. At rest the original's
    leg stays within about 8 px; the free-play motion wandered 4 - 5 cm from it, so presses landed on or beside ladders
    where the original's did not. Free play moves as lively as ever.
- **Cameras**: VIEW 01 / VIEW 02 are fitted to the original's leg silhouettes (`tools/fit_camera*.py`); right-drag
  orbits about a pivot behind the legs, as the original's camera does.
- **Replay** (`ReplayDriver.cs`, `StreamingAssets/replay_session.json`): the original video's 36-second session,
  played on the simulator.
  - The file holds **input only**: the cursor path, the presses' timing, the camera moves, and the body motion
    tracked from the video.
  - Every pull is grabbed and simulated exactly as a player's would be.
  - The video starts in the middle of its first pull. Before t = 0 the cursor is the file's own path at t = 0, run
    back at the same velocity; it passes through the pocket the original shows in its first frame. (Nothing is placed
    by hand to make a tear land where the original's did.)

## The panel's internals

- **Building blocks.** `SheerStudio.cs` is the side panel and applies the look; `SheerLook.cs` holds it (JSON, saved
  between sessions, undo / redo). `SheerKit.cs` is a small uGUI kit (SDF sprites, widgets sized for reading: the UI
  scale follows the window's height, 1 at 720 px). `SheerInspectorUI.cs` is the original's inspector:
  each control edits `TensionData`, which pushes its values to the stocking's material every frame. Tension Mode picks
  the creases drawn (Both, Stretch: the lines along a pull, Compression: the buckled folds and the ankle's bend), Wrinkle
  Strength scales them all, Pearl Randomness sets how unlike each other the glints are, Pearl Pull Edge Width the lit band
  along a sail's outline, Pearl Glint Strength fades the glints in (0 - 1) then brightens them (1 - 2), Frost Boundary
  Strength the holes' lips and rims, Frost Boundary Width the soft change from the leg's knit to the foot's. Every
  control was checked by rendering the scene at its low and high values (`-sheerVariants`, one render per setting at a
  frozen moment of the replay) and measuring the change.
  `SheerBoot.cs` is the loading screen: the first scene draws a banner at once and loads the simulator behind it.
- **One stocking.** A look file can name more (the earlier "Studio" had other stocking kinds, patterns, finishes, leg
  shapes, light presets, props...); `SheerLook.Sanitize` holds all of those at the original's values, until each has
  been studied on its own.
- **Music and sounds** were synthesized for the game by `tools/audio_gen` (fixed seeds: `python3 build_all.py`
  rebuilds them).
- **Self-test.** `-sheerStudioTest DIR` takes screenshots of the panel and of every choice it offers in both views,
  and asserts undo/redo, the look's JSON, the parked fields, folding sections, the mend and the classic inspector's
  controls. A UI monkey clicks every button and moves every slider. Run it at the window sizes people use.
- **Free-play sweep.** `tools/sweep_session.py` writes an input-only session of 36 generic pulls at random spots on both
  legs in both views, with random direction, length and hold. `tools/sweep_sheets.py` turns a capture of it into review
  sheets: per pull, the onset, the drag, the peak, two frames after the release, and half a second after.
- **Solver dumps.** `-sheerDumpCloth T1,T2:PREFIX` writes both legs' node positions at those session times. Fold-overs,
  ridges and the release curve were measured from such dumps, not judged from pictures.

## Performance

- Measured on an RTX 3060 (Linux player): about 6 ms of GPU per frame at 0.4–1 MP.
- The default landscape window is about 1.5 MP; at 2 × 2 supersampling that is ~6 MP, ~20 ms.
- The adaptive supersampling keeps the frame rate up by dropping to 1.5× or 1×.
- The main thread costs about 9 ms; the skirt's cloth runs on worker threads (~0.3 ms per 1/360 s step).
- `-sheerPerfLog` prints frame rate, CPU and GPU time and per-system timings every 5 s. `-sheerVsync 0` lifts the
  display's cap. `-sheerLogSkirt` logs the skirt against the body's outline.

## Build from source

Unity **6000.6.9f1** (HDRP 17.6). Open `unity/` and the scene `Assets/Sheer/Scenes/Sheer.unity`. On Linux the editor
must run with Vulkan (`-force-vulkan`): HDRP does not support OpenGL.

```bash
U=~/Unity/Hub/Editor/6000.6.9f1/Editor/Unity
python3 tools/patch_shadergraph.py unity/Assets/Sheer/Graphs                       # shader graphs from the HLSL
$U -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.SceneBuilder.Build -quit
$U -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.BuildPlayers.Windows -quit   # or .Linux
bash tools/package_release.sh                                                     # dist/: the release archives
```

- **Graphics APIs.** The game was developed and tested on Vulkan. The Windows player therefore starts on Vulkan and
  falls back to Direct3D 12 when Vulkan can't start; `-force-d3d12` picks D3D12 directly.

- **Meshes.** The meshes in `unity/Assets/StreamingAssets/*.smesh` come from the Blender pipeline in `blender/`, an
  earlier offline Cycles version of the project (`blender/export_unity.py`). The legs were then reworked by
  `tools/reshape_legs.py` (their build, and the stocking laid on the skin by `tools/sim/wrap.py`).
- **Scenes.** `BuildPlayers` makes `Scenes/Boot.unity` (the loading screen) and builds it first, then `Sheer.unity`.
- **Cloth lattice.** It comes from `tools/sim/export_sock_lattice.py`.
