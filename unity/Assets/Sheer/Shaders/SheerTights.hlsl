// SHEER — sheer nylon pantyhose surface (port of make_tights in blender/sheer_materials.py, calibrated
// against the original). Used from the HDRP StackLit Shader Graph "SheerTights" through a Custom Function
// node (SheerTights_float). Material properties (the TensionData inspector) are read directly from the
// graph's blackboard (same names as TensionData.Push()).
//
// Mesh data (see SheerMesh.cs / blender/export_unity.py):
//   uv0 = (u around the leg 0..1 (0 = back), v = rest height m, static stretch 'prestretch', toe-cap fade)
//   uv1 = (rest position xyz in Unity axes (m), toe seam signed distance m)
//   uv2 = (leg side +1/-1, toe pocket weight)
//   uv3 = (areal stretch of the pose from TightsSim, 0, 0, 0)
// Cloth simulation (SheerCloth.hlsl): _ClothTens = principal stretches of the pulled fabric, per pixel.
// Damage maps (DamageRaster.compute): A = R hole SDF, G ladder SDF (packed sd/(2*RANGE)+0.5), B ladder age, A 1-bagging;
// B = RG displacement of the yarn by the holes (u, m), B lateral coordinate across the ladder, A wale density - 1;
// C = R / G distance to the ladder's top / bottom end (in frayed lengths), B distance along the wale to the hole that
// cuts it (m, 0.08 = none), A course density - 1.
#ifndef SHEER_TIGHTS_INCLUDED
#define SHEER_TIGHTS_INCLUDED

#define SH_DMG_RANGE 0.012

// set by TightsSim: world position of the key light (w = 1 when set); the glints flash in it
float4 _SheerKeyPos;
// set by TightsSim: the pinch on the left / right leg while the hand holds it: (u, rest height, circumference there, strength)
float4 _SheerPinchL, _SheerPinchR;
float4 _SheerPinchDirL, _SheerPinchDirR;   // the pull of each leg's pinch in the fabric's coordinates: round (m), along (m), on the leg (0..1)
// set by TightsSim: 1 while the hand holds this leg's fabric (eased out after a release, 0 at once after a tear)
#ifndef SHEER_HELD_DECLARED
#define SHEER_HELD_DECLARED
float _SheerHeldL, _SheerHeldR;                // 1 while the hand holds that leg's fabric (TightsSim)
#endif
// rendered pixels per pixel of the final picture (supersampling; 0 = unset = 1)
#ifndef SHEER_PIXSCALE_DECL
#define SHEER_PIXSCALE_DECL
float _SheerPixelScale;
#endif
// experiments (-sheerGlobal / look variants; 0 = off): knit coverage grain, knit normal, gauze threads off; flaps forced
float _SheerDbgK, _SheerDbgN, _SheerDbgG, _SheerDbgF, _SheerDbgH, _SheerDbgL, _SheerDbgS;
// (experiments, -sheerGlobal: knit grain - per-loop variation kept down to this many px (0: 2.5), fine grain contrast x;
//  glints - size x, how many x)
float _SheerKresPx, _SheerGrainK, _SheerGlintSz, _SheerGlintN, _SheerSheenSm, _SheerSailHaze, _SheerRugPile;

#include "Assets/Sheer/Shaders/SheerNoise.hlsl"
#include "Assets/Sheer/Shaders/SheerCloth.hlsl"
#include "Assets/Sheer/Shaders/SheerLook.hlsl"

// ------------------------------------------------------------------------------------------ threads
// A family of parallel threads: phase = 1 per thread, duty = share of the pitch the yarn covers. Returns the yarn's
// presence with mean ~1. No two threads are alike (irregular = 1: each has its own thickness, weight and place in its
// slot, so a bundle never reads as a ruled hatch). fw = fwidth(phase) in pixels of the FINAL picture (supersampling
// divided out; taken outside any branch): finer than ~4 of them the threads melt into the knit's haze - what is left
// is a soft streakiness along them (user, 2026-11-15: the original's gauze round a hole is a smooth, fine-grained haze
// in which no single thread can be followed; ours, drawn down to ~2.3 px, read as a coarse net / screen door).
float sh_threads(float phase, float fw, float duty, float seed, float irregular, float along, float fade0, float jit)
{
    float k = floor(phase), f = phase - k;
    float h1 = sh_hash11(k * 1.731 + seed), h2 = sh_hash11(k * 3.117 + seed + 5.3), h3 = sh_hash11(k * 7.713 + seed + 9.1);
    // (here and there two or three threads lie together as a bundle - wider and darker - for a centimetre or two;
    //  `along` = a coordinate along the thread, ~1 per 2 cm)
    float ai = floor(along), af = along - ai;
    float hv = lerp(sh_hash21(float2(k * 5.371 + seed, ai)), sh_hash21(float2(k * 5.371 + seed, ai + 1.0)), af * af * (3.0 - 2.0 * af));
    float heavy = sh_smooth(0.74, 0.86, hv);
    // (... and stretches where a thread is faint or gone: lines that break off and come back, not a ruled net)
    float faint = sh_smooth(0.32, 0.12, hv) * irregular;
    float w = duty * lerp(1.0, 0.65 + 0.7 * h1, irregular) * (1.0 + 0.6 * heavy);
    float d = abs(f - 0.5 - (h2 - 0.5) * jit);
    float l = saturate((0.5 * w - d) / fw + 0.5);
    float pat = l * lerp(1.0, 0.55 + 0.9 * h3, irregular) * (1.0 + 0.6 * heavy) * (1.0 - 0.75 * faint) / (duty * 1.1 * (1.0 - 0.09 * irregular));
    float streak = 1.0 + 0.3 * irregular * (sh_noise(float3(phase * 0.31, along * 0.6, seed), 1.0, 1, 0.5) - 0.5) * saturate((0.55 - fw * 0.31) / 0.25);
    return lerp(pat, streak, saturate((fw - fade0) / 0.2));
}

// Threads at any crowding. Plain gauze melts into haze (above); a BUNCHED family (bunch = 1: lying several deep against
// a hole's edge, in a strap between two holes) shows its grain instead - every 2nd / 4th / 8th ... thread, at least
// ~4 picture pixels apart, blended from one level to the next: a ribbon of yarn along the edge, not a flat tone.
float sh_threadsLod(float phase, float fw, float duty, float seed, float irregular, float along, float bunch, float fade0)
{
    float fine = sh_threads(phase, fw, duty, seed, irregular, along, fade0, 0.28 * irregular);
    [branch] if (bunch < 0.01) return fine;
    float lod = max(log2(max(fw / 0.24, 1e-6)), 0.0);
    float l0 = floor(lod), lf = lod - l0;
    float n0 = exp2(l0), n1 = n0 * 2.0;
    // (a drawn line is a bundle of two or three threads, not a band n threads wide: thin, however far apart)
    // (... and anywhere in its slot: a bundle every n threads at random, not a ruled set of ripples)
    float p0 = sh_threads(phase / n0, fw / n0, max(duty * 2.0 / n0, 0.14), seed, irregular, along, 0.22, 0.7);
    float p1 = sh_threads(phase / n1, fw / n1, max(duty * 2.0 / n1, 0.14), seed + 3.7, irregular, along, 0.22, 0.7);
    return lerp(fine, lerp(p0, p1, lf * lf * (3.0 - 2.0 * lf)), bunch);
}

// The same as a line mask: 0 between threads .. ~1.4 on a heavy one (each thread has its own thickness, weight and place
// in its slot); gone where the threads are finer than ~1.5 pixels.
float sh_threadLine(float phase, float fw, float duty, float seed)
{
    float k = floor(phase), f = phase - k;
    float h1 = sh_hash11(k * 1.731 + seed), h2 = sh_hash11(k * 3.117 + seed + 5.3), h3 = sh_hash11(k * 7.713 + seed + 9.1);
    float w = duty * (0.55 + 0.9 * h1);
    float d = abs(f - 0.5 - (h2 - 0.5) * 0.3);
    float l = saturate((0.5 * w - d) / fw + 0.5);
    return l * (0.45 + 1.0 * h3) * saturate(1.6 - fw * 1.6);
}

// Lowest packed hole distance r metres from uv along the leg and round it (U taken on a 36 cm leg): how deep a hole is.
float sh_probe4(Texture2D t, SamplerState s, float2 uv, float r)
{
    float2 du = float2(r / 0.36, 0.0), dv = float2(0.0, r);
    return min(min(t.SampleLevel(s, uv + du, 0).r, t.SampleLevel(s, uv - du, 0).r), min(t.SampleLevel(s, uv + dv, 0).r, t.SampleLevel(s, uv - dv, 0).r));
}

// Has this wale run (dropped its loops) here? A ladder is a band of run wales. Every wale ends the band at its own
// width (ragged sides) and stops on its own at the ladder's ends: per ladder a top / bottom end is anything between a
// flame of many fine streaks and two or three long 'comet tails' (both measured on the original at 11 s). A few wales
// inside the band hold for a few centimetres (dark streaks of gathered yarn).
float SheerWaleOpen(float col, float lat, float tTop, float tBot, float2 style, float zm)
{
    float grp = floor(col / 3.0);
    // (the wales' own random numbers do not depend on the ladder: where one ladder takes over from another - a tear on
    //  an existing run - the streaks continue; only the ends' style is the ladder's own)
    const float ws = 0.37;
    // (each wale mostly its own: with 0.7 of it shared by groups of three, the ends of the now edge-to-edge open bands
    //  stopped in blocks - square steps, a '+' where a band met its tails, independent review 4)
    float h1 = 0.75 * sh_hash21(float2(col, ws * 91.7 + 1.3)) + 0.25 * sh_hash21(float2(grp, ws * 23.1 + 4.4));
    float h3 = 0.75 * sh_hash21(float2(col + 0.5, ws * 53.9 + 7.7)) + 0.25 * sh_hash21(float2(grp + 0.5, ws * 61.3 + 2.9));
    float h2 = sh_hash21(float2(col * 1.37 + 5.1, ws * 37.3));
    h1 = saturate(h1 * 1.15 - 0.075); h3 = saturate(h3 * 1.15 - 0.075);     // (the sum of two is bell-shaped: spread it)
    // sides: every wale joins / leaves the band somewhere along the leg (long streaks, no straight edge)
    float zs = zm / 0.045 + h2 * 9.0, zsi = floor(zs), zsf = zs - zsi;
    float sideN = lerp(sh_hash21(float2(col + 0.25, zsi + ws * 29.0)), sh_hash21(float2(col + 0.25, zsi + 1.0 + ws * 29.0)), zsf * zsf * (3.0 - 2.0 * zsf));
    // (soft: toward the band's sides the wales have dropped fewer loops, and only some of them)
    float al = abs(lat);
    // (open right across the band - the original's ladders are pale from edge to edge, about as wide as the holes they
    //  join; fully open only within 0.45 of the half-width, ours read a third of that, independent review 4 - ragged only
    //  along the edge)
    // (review 5: open to 0.8 the bands came out as wide as the holes or wider - the original's are ~70 % of the hole they
    //  leave: open to 0.6, ragged from 0.55)
    // (review 9: the original's bands have straight edges - fabric to gauze within 2 - 4 mm, a darker wale along each
    //  side; ours faded out over 1.5 - 2.5 cm, 'soft-edged glowing smears'. Open to 0.68, the edge in the next 0.14, ragged
    //  only there: the band stays ~75 % of the half-width, as before)
    float side = sh_smooth(0.82, 0.68, al) * lerp(1.0, saturate(sideN * 1.5 + 0.05), sh_smooth(0.66, 0.84, al));
    // ends: the band TAPERS - the wales in its middle run furthest, those at its sides stop first - and every wale
    // stops at its own course. Per ladder end the taper is anything between a broad flame of many streaks and a point
    // drawn out into two or three long tails (measured on the original at 11 s: both, never a straight cut).
    float sT = style.x, sB = style.y;                                  // (the style of a ladder's ends: by place on the leg)
    float midT = saturate(1.0 - pow(al, lerp(1.6, 0.7, sT))), midB = saturate(1.0 - pow(al, lerp(1.3, 0.55, sB)));
    float reachT = midT * lerp(0.35 + 0.65 * h1, pow(h1, 3.0), sT * 0.4);
    float reachB = midB * lerp(0.35 + 0.65 * h3, pow(h3, 3.0), sB * 0.8);
    float eT = sh_smooth(0.0, 0.3, tTop - 1.0 + reachT + saturate((tTop - 1.0) * 2.5));
    float eB = sh_smooth(0.0, 0.3, tBot - 1.0 + reachB + saturate((tBot - 1.0) * 2.5));
    // a wale that is only starting to run (toward the tip of a frayed end) has dropped few loops: a paler streak, not
    // an open band
    float fray = saturate(min(tTop, tBot));
    float amt = lerp(0.82, 1.0, fray * fray);
    float zc = zm / 0.03 + h2 * 7.0, zi = floor(zc), zf = zc - zi;
    float hold = lerp(sh_hash21(float2(col, zi + ws * 17.0)), sh_hash21(float2(col, zi + 1.0 + ws * 17.0)), zf * zf * (3.0 - 2.0 * zf));
    // (streaks: wale groups that dropped fewer loops, and wales that hold for a few centimetres)
    float tone = lerp(0.84, 1.0, sh_hash21(float2(grp + 0.37, ws * 71.9 + 3.3)));       // (0.70: a band of pale and dark stripes)
    return side * min(eT, eB) * amt * tone * (1.0 - 0.45 * sh_smooth(0.80, 0.92, hold));
}

// ------------------------------------------------------------------------------------------ material
struct SheerSurface
{
    float3 baseColor;
    float3 specularColor;     // F0
    float  smoothness;        // perceptual
    float  anisotropy;        // + along the tangent (around the leg)
    float3 normalWS;
    float3 tangentWS;
    float  alpha;
    float  glint;             // glint mask (for debugging)
    float3 sheen;             // fibre sheen reflectance (additive Fabric pass, SheerTightsSheen_float)
    float  covRest;           // the worn knit's coverage here before a pull stretches it (for the layer behind a sail)
};

// Parameters are the blackboard properties of the graph (declared in the UnityPerMaterial CBUFFER by Shader Graph):
// _NormalStrength _WeaveTiling _WeaveNormalStrength _WeaveContrast _TensionMode _WrinkleStrength _TensionNormalBoost
// _PearlStrength _PearlGrainScale _PearlRandomness _PearlSpecularStrength _PearlEdgeStrength _PearlEdgeStart
// _PearlEdgeWidthPower _PearlPullEdgeWidth _PearlGlintStrength _PearlGlintDensity _FrostBodyCoverage
// _FrostFootCoverage _FrostClearAtStretch _FrostMatteSmoothness _FrostBoundaryStrength _FrostBoundaryWidthM
// _KnitMean  (mean coverage of the weave map, from SheerWeave.cs), _YarnColor (yarn albedo, float4),
// _NylonShadow (share of the light the yarn takes on its way in, per unit coverage), _AngleFalloff (how fast the
// knit closes up towards grazing views), _FrostColor (albedo of the hazy worn knit; _YarnColor = taut / haze-free),
// _LiftShadow (share of that shadow kept by nylon lifted off the skin)

SheerSurface SheerEvaluate(float4 uv0, float4 uv1, float4 uv2, float4 uv3, float3 posWS, float3 N, float3 T, float3 B,
                           float3 V, float viewDist, Texture2D dmgTex, Texture2D dmgB, Texture2D dmgC, Texture2D weaveTex,
                           SamplerState ssLinearRepeat, SamplerState ssWeave, float4 tens, float lift)
{
    // (round 10: the original's foot is LIGHTER than its shin and cool - instep (129, 111, 115) vs ours (111, 88, 84),
    //  an olive 'clay sock': a cooler yarn, sheerer over the foot, a neutral toe)
    // (round 11: the instep still warmer than the toe - (119,97,96) vs the original's even (129,111,115) down the foot)
    const float3 FOOT_YARN = float3(0.118, 0.112, 0.150);     // (cooler: the original's foot is violet-grey, R-B 12 vs our 26 - round 13)
    const float RUNG = 0.0011, THREADS = 1.0;
    float U = uv0.x, Vz = uv0.y, pre = uv0.z, cavAO = uv0.w;        // (uv0.w: the worn stocking's cavities, baked - tools/reshape_legs.py)
    float3 rest = uv1.xyz; float tseam = uv1.w;
    // U, Vz: where this point is in the damage maps (around, along). Vh: its rest HEIGHT, for the body's regions (foot,
    // shin, knee, thigh, under the skirt). On the leg they are the same; below the ankle's top the tears, threads and
    // ladders run along the wales - down the ankle, round the heel, along the foot (the stocking's one lattice, TightsSim)
    float Vh = rest.y;
    { float2 dz2 = SheerDamageUV(rest, uv2.x, float2(U, Vz)); U = dz2.x; Vz = dz2.y; }
    float sPose = uv3.x > 1e-4 ? uv3.x : 1.0;                        // no live stretch stream (edit mode / static) = at rest
    // the pulled fabric (cloth simulation): the knit closes up where it is squeezed across its threads (smallest stretch)
    // and opens only a little where it is drawn out (largest stretch): the original's in-plane drags leave a dark blotch
    // of gathered knit around the hand although the fabric there is longer one way than it is shorter the other
    // (fabric lifted off the leg - a tent, a sail - simply thins with its area: the original's sails are sheer veils with
    //  the knit drawn large; the squeeze-weighted measure is for fabric lying on the skin)
    // (once the hand has let go, fabric springing back is millimetres off the skin for a frame or two: sheer over it, as
    //  on it - drawn as a sail's dark veil, with its shade on the skin, it flashed a sooty blob where a sail tore away,
    //  review 9 at 9.93 / 10.93 s. Held, the fabric lifts into tents and sails from the first millimetres as before)
    float heldNow = uv2.x > 0.0 ? _SheerHeldL : _SheerHeldR;
    // (review 13: from 2 mm the pinch's 4 mm lift turned a 1.4 x 5 cm patch into a dark sail veil - a grey-green 'bruise' at
    //  every press on the calf, a sooty dent at the knee; the original's pinch is a tent of ordinary lit nylon, its sails
    //  centimetres off. From 5 mm; let go, from 8 mm as before)
    float lifted = sh_smooth(0.005, 0.018, lift) * lerp(sh_smooth(0.008, 0.022, lift), 1.0, heldNow);
    // (0.6: a little of the drawing-out shows on the leg too - the original's knee pinch has a faintly paler, warmer fan
    //  behind the fingers; at 0.3 ours only ever darkened)
    float sCloth = max(lerp(pow(max(tens.x, 0.05), 0.6) * tens.y, tens.x * tens.y, lifted), 0.05);
    float stretch = sPose * sCloth;

    // ---- damage fields
    float2 duv = SheerDamageTexUV(float2(U, Vz));
    float4 dm = dmgTex.SampleLevel(ssLinearRepeat, duv, 0);
    float4 dB = dmgB.SampleLevel(ssLinearRepeat, duv, 0);
    float4 dC = dmgC.SampleLevel(ssLinearRepeat, duv, 0);
    float holeSD = (dm.r - 0.5) * 2 * SH_DMG_RANGE;
    float runSD = (dm.g - 0.5) * 2 * SH_DMG_RANGE;
    float age = dm.b;
    float bag = 1.0 - dm.a;
    // The WELT of a thigh-high / over-knee / knee-high does not tear. It is a doubled, elastic band, far stronger than the
    // sheer leg: a tear that reaches it stops along its lower edge - the sheer knit comes away from the band - and no
    // ladder, fringe or pushed-aside yarn shows in it. (A tear just under the band used to eat a round hole on through ribs
    // and lace, a sliver of scallops left hanging: user, 2026-11-17.) TightsSim: a pull ON the welt does not tear at all.
    float weltK = 0.0;
    if (SheerHasBand())
    {
        float wsd = Vh - (_SheerBand.x - max(_SheerBand.y, 0.01));     // > 0 in the welt (rest height above its lower edge)
        holeSD = max(holeSD, wsd + 0.0015); runSD = max(runSD, wsd + 0.0015);
        weltK = sh_smooth(-0.0015, 0.0005, wsd);
    }
    // 'material' coordinates: where this yarn sat before the holes opened (the yarn a hole displaced is gathered around
    // it); knit, wales and rungs are drawn there, so they flow around the holes and bunch into rims, hoods and straps
    float Um = U - dB.x, Zm = Vz - dB.y;
    // (thread densities: bunched yarn piles up rather than closing ranks, so the effect is compressed)
    // (thread densities: where a hole has pushed the yarn against its edge the threads lie several deep - a ribbon)
    float dWale = lerp(clamp(1.0 + dB.w * 0.8, 0.3, 4.5), 1.0, weltK), dCourse = lerp(clamp(1.0 + dC.w * 0.8, 0.3, 4.5), 1.0, weltK);
    float nz = sh_noise(rest, 650, 3, 0.6), nzc = sh_noise(rest, 140, 2, 0.5);
    // (rougher than they were: review round 8 measured perimeter / smoothed perimeter 1.04 - 1.08 vs the original's
    //  1.13 - 1.21 - torn knit is jagged at the scale of a few loops)
    // (round 9: the fine part wiggled the 1-px rim at the pixel scale into stipple - 13 - 17 specks / 100 px of edge vs
    //  the original's 4 - 8; the roughness is in the coarse part)
    holeSD += (nz - 0.5) * 0.00018 + (nzc - 0.5) * 0.0010;
    // nicks (the edge bitten back) and tufts of loose yarn reaching into the hole, here and there along the outline
    // (everything that only matters at a tear is skipped away from tears: the leg is mostly intact, and the frame is
    //  bound by what the stocking's pixels cost)
    [branch] if (abs(holeSD) < 0.006)
    {
        float fr1 = sh_noise(rest + 1.9, 420, 2, 0.5), fr2 = sh_noise(rest + 7.3, 300, 2, 0.5);
        holeSD += max(fr1 - 0.70, 0.0) * 0.0012 - max(fr2 - 0.71, 0.0) * 0.0010;
        // (and the whole outline a little ragged - torn loop by torn loop, never a smooth blob with a ruled rim: the
        //  holes looked cut out, independent review 2026-11-17)
        // (only a slow wobble: with a fine one too the rims read as thin jagged lines, review 2)
        holeSD += (sh_noise(rest + 2.2, 180, 2, 0.5) - 0.5) * 0.0010;
        // (+ a slow, larger one, +-1 mm over ~2 cm: 'smooth, punched-looking ovals and peanuts', review 5 - the original's
        //  outlines are torn, irregular at the centimetre scale; still no fine jaggies)
        holeSD += (sh_noise(rest + 4.4, 55, 2, 0.5) - 0.5) * 0.0020;
    }
    runSD += (nz - 0.5) * 0.0008;
    // the hole's edge: one pixel wide however far the fabric is stretched
    float hfw = max(fwidth(holeSD), 1e-6);
    float inHole = saturate(0.5 - holeSD / hfw);
    // how far the edge here faces up / down the leg (1 above and below a hole, 0 at its sides): the rolled edge is
    // heavier where the courses pile up against it (hood and lip)
    float2 dUs = float2(ddx(U), ddy(U)), dZs = float2(ddx(Vz), ddy(Vz)), dSs = float2(ddx(holeSD), ddy(holeSD));
    float jdz = dZs.x * dUs.y - dZs.y * dUs.x;
    float tbs = abs(jdz) > 1e-12 ? (dSs.x * dUs.y - dSs.y * dUs.x) / jdz : 0.0;
    float tb = saturate(abs(tbs));
    float edgeTop = saturate(tbs * 1.6), edgeBot = saturate(-tbs * 1.6);

    // ---- wales (columns of loops along the leg) and courses (rows around it)
    const float NW = 576.0, PC = 0.00086;                           // (= the weave map's cells: 12 tiles x 48 wales, 26 courses per 22.4 mm)
    // (threads are smooth lines: straight, or gently curved where a hole pushed them aside. Their phase only wanders
    //  slowly - a third of a pitch over centimetres; finer noise on it drew zigzags like an ECG trace)
    float2 wander = (float2(sh_noise(rest + 3.1, 30.0, 0, 0.5), sh_noise(rest + 8.7, 30.0, 0, 0.5)) - 0.5) * 0.7;
    float wph = Um * NW + wander.x;
    float wcol = floor(wph), wfr = wph - wcol;
    float cph = Zm / PC + wander.y;
    float ck = floor(cph);
    float runOpen = sh_smooth(0.3, 0.8, age);
    // (blended over the neighbouring wales: a streak is a soft band, not a ruled stripe)
    float open = 0.0;
    float fwW = max(fwidth(wph), 1e-5), fwC = max(fwidth(cph), 1e-5);
    [branch] if (abs(dB.z) < 1.3 && runOpen > 0.0)
    {
        float2 endStyle = saturate((float2(sh_noise(float3(U * 5.0, Vz * 2.5, 1.7), 1.0, 0, 0.5), sh_noise(float3(U * 5.0, Vz * 2.5, 8.3), 1.0, 0, 0.5)) - 0.5) * 2.4 + 0.5);
        // (narrower on the lower leg: the original's calf runs are faint thin strips between the holes; ours glowed as a band
        //  2 cm wide, review 7 - the lateral coordinate scaled up there, so the band opens only near its middle)
        float latK = lerp(1.0, 1.45, 1.0 - sh_smooth(0.30, 0.50, Vh));
        float oM = SheerWaleOpen(wcol - 1.0, dB.z * latK, dC.x, dC.y, endStyle, Zm), o0 = SheerWaleOpen(wcol, dB.z * latK, dC.x, dC.y, endStyle, Zm),
              oP = SheerWaleOpen(wcol + 1.0, dB.z * latK, dC.x, dC.y, endStyle, Zm);
        open = (lerp(0.5 * (oM + o0), 0.5 * (o0 + oP), wfr) * 0.6 + lerp(o0, oP, wfr) * 0.2 + lerp(oM, o0, wfr) * 0.2) * runOpen;
    }
    open *= (1.0 - _SheerDbgL) * (1.0 - weltK);
    float ladO = open;                                                 // (the ladders' share, before the halo / fringe)
    float inRun = sh_smooth(0.002, -0.002, runSD);
    // a halo of loosened knit round every hole (the original: each hole sits in a pale gauze a few millimetres wide,
    // also where it is wider than its ladder)
    // (narrow and streaky - wale by wale - not an even glow round the hole)
    // The loosened knit lies ABOVE and BELOW a hole: every wale the hole has cut has started to run, each to its own
    // length - a fringe of pale streaks as wide as the hole, a 'flame' of a few centimetres (dC.z = distance along the
    // wale to the hole that cuts it, DamageRaster) - not at its sides, where the knit is whole right up to the ribbon
    // of threads the hole has pushed against its edge. (An even pale ring all round read as a glow.)
    float wsm = wfr * wfr * (3.0 - 2.0 * wfr);
    float hs1 = lerp(sh_hash21(float2(wcol, 7.7)), sh_hash21(float2(wcol + 1.0, 7.7)), wsm);
    // Every wale its own streak: its own length - most stop after 0.5 - 2 cm, about one in eight runs on for 3 - 7 cm
    // (user, 2026-11-15: in the original a few of the threads drawn out of a hole's edge are long, ours were all short
    // and alike) - its own tone, fading toward its tip, one wale wide (box-filtered over the pixel, not smeared).
    float pxF = max(_SheerPixelScale, 1.0);
    float fringe = 0.0;
    [branch] if (dC.z < 0.075)
    {
        float fhw = clamp(fwW * pxF, 0.3, 1.8) * 0.5;
        [unroll] for (int fk = -1; fk <= 1; fk++)
        {
            float col = wcol + fk;
            float ov = max(min(wph + fhw, col + 1.0) - max(wph - fhw, col), 0.0) / (2.0 * fhw);
            float hA = sh_hash21(float2(col, 7.7)), hB = sh_hash21(float2(col * 1.37 + 2.1, 4.9)), hG = sh_hash21(float2(floor(col / 4.0), 3.3));
            float fL = 0.004 + 0.008 * hA + 0.008 * hG + 0.062 * pow(hB, 7.0);
            fringe += ov * sh_smooth(fL, fL * 0.3, dC.z) * lerp(0.45, 1.0, sh_hash21(float2(col, 5.1))) * lerp(1.0, 0.5, saturate(dC.z / fL));
        }
        // (and the band as a whole: above and below a hole the knit has loosened as far as most of its wales have run -
        //  a pale flame as wide as the hole, 1 - 3 cm long, each group of ~6 wales its own length - the streaks run on)
        float gq = wph / 6.0, gi = floor(gq), gf = gq - gi;
        float fLb = 0.015 + 0.025 * lerp(sh_hash21(float2(gi, 8.1)), sh_hash21(float2(gi + 1.0, 8.1)), gf * gf * (3.0 - 2.0 * gf));
        fringe = max(fringe, 0.5 * sh_smooth(fLb, 0.25 * fLb, dC.z) * lerp(1.0, 0.5, saturate(dC.z / fLb)));
        fringe *= 1.0 - inHole;
    }
    fringe *= 1.0 - weltK;
    float nearHole = max(sh_smooth(0.0020, 0.0005, holeSD) * (1.0 - inHole), fringe);   // (2.6 mm: an even pale band round every hole, review 12)
    float nearCore = sh_smooth(0.0065, 0.001, holeSD) * (1.0 - inHole);
    float haloW = lerp(0.2, 1.0, hs1) * lerp(0.5, 1.0, nz);    // (an even pale ring round every hole read as a sticker's halo, review 12)
    open = max(open, nearHole * haloW);

    // ---- coverage ('Frost'): body/foot coverage, opened by stretch
    float bw = _FrostBoundaryWidthM;
    float footMask = sh_smooth(0.0775 + bw / 2, 0.0775 - bw / 2, Vh);
    // reinforced foot: denser than the leg (Frost Foot Coverage 0.889 > body 0.829); the Cycles port had a 0.84 factor that
    // made the HDRP foot lighter than the leg, while the original's foot is the darkest part of the stocking
    // (x0.845 on the leg: fit of the colour profile across thigh / knee / shin at 0.5 s - with the inspector's 0.829 as
    //  it is the leg came out grey and flat, the original's is warm: more skin through the knit)
    float cov0 = lerp(_FrostBodyCoverage * 0.845, _FrostFootCoverage * 0.66, footMask);
    // a PALE yarn (the Studio's colours): the calibrated coverage is what BLACK nylon does to the skin - its own area plus
    // the light it stops on the way in and out, 1 - (1 - c)^2; a pale yarn scatters that light on instead of stopping it, so
    // it hides only its area, c = 1 - sqrt(1 - coverage). (paleK from the yarn's luminance, as its shadow: 0 for the
    // original's black - unchanged - to 1 for white; pink 15 D: 62 % -> 47 %, the skin shows through as on real legs)
    float paleK = _SheerTint.a > 0.5 ? saturate((1.0 - _SheerTint2.x) / 0.65) : 0.0;
    cov0 = lerp(cov0, 1.0 - sqrt(saturate(1.0 - cov0)), paleK);
    // stretched knit: the same yarn over more area (coverage ~ 1/area); compressed knit buckles out of plane
    // instead of densifying, so it only darkens a little
    float area = max(stretch, 0.4);
    float areaK = area >= 1.0 ? pow(area, _FrostClearAtStretch) : pow(area, 0.3 * _FrostClearAtStretch);
    // (ON the leg a pull's drawing-out thins the knit gradually - to 0.88 of its coverage only where it is drawn out to
    //  twice its area. Thinned as 1 / area it was at that floor from +14 % on: every fan behind a pinch one flat pale
    //  patch, ruled off where its threads reach their lock - a salmon polygon on the instep, orbit sweep 2026-11-17.
    //  Fabric lifted off the leg thins with its area as before.)
    [flatten] if (sCloth > 1.0)
    {
        float aP = max(sPose, 0.4);
        float kP = aP >= 1.0 ? pow(aP, _FrostClearAtStretch) : pow(aP, 0.3 * _FrostClearAtStretch);
        areaK = lerp(kP / lerp(1.0, 0.88, sh_smooth(1.0, 2.0, sCloth)), areaK, lifted);
    }
    float cov = cov0 / (pow(max(pre, 0.4), _PreExp * _FrostClearAtStretch) * areaK);   // _PreExp: calibrated vs the original
    float covWorn = cov0 / pow(max(pre, 0.4), _PreExp * _FrostClearAtStretch);         // (before the pull's stretch)
    // stretch clears the knit's matte haze ('frost'), not the dark yarn itself: coverage never thins below 60 % of its rest
    // value (the original's sails stay dark navy membranes); the haze clearing darkens the yarn instead (frostClear below)
    // (reviewers: the original's pinched nylon darkens; fabric that the hand only draws out on the leg gets a little sheerer)
    // (review round 5: the original's ankle / shin sails are see-through sheets - ours read darker)
    // (0.45: the thigh sails read as a uniform see-through film where the original's are dark, nearly opaque at grazing
    //  angles - review 2, 2026-11-17)
    // (review 4: at 0.65 x when lifted, the 5.6 s thigh sail was a glassy film with the leg's cyan rim line straight through
    //  it - the original's is a dark, nearly opaque sheet; its ankle veils are lighter but no glass. Lifted fabric keeps
    //  its worn coverage)
    // (0.80: at 1.0 review 8 saw the sails 'dark and much less see-through' - the original's 5.5 s sail measures close to the
    //  backdrop behind it; 0.65 had been glassy, review 4)
    // (0.92: measured, the original's 5.6 s sail lets ~0.2 - 0.3 of the backdrop through in a dark neutral - (52,53,57) on
    //  (53,72,87); ours at 0.80 let ~0.6 through, a blue-tinted film, review 10)
    cov = max(cov, cov0 * lerp(0.88, 0.92, lifted));
    cov = min(cov, 0.965);                                          // bunched knit stays a fabric of loops, not a solid band
    // fabric gathered between the fingers lies in folds, layer on layer: a dark, soft blob (the original's pinches)
    // (gathered = smaller in AREA: the cone of fabric drawn out toward the hand is squeezed across but longer - sheer)
    // (gathered = pushed together across its threads without being drawn out much: the dark blotch round the pinch while
    //  the hand drags it over the leg; the cone of fabric drawn out toward the hand is squeezed across but longer - sheer)
    // (... and the neck of a pinch - squeezed to a third across, however far it is drawn out - is folds on folds: the
    //  dark tongue of the original's opening knee pinch)
    // (by AREA only: fabric pushed together ahead of the fingers. Until 2026-11-17 squeezed-across-its-threads counted too,
    //  however far the fabric was drawn out the other way - that painted the whole fan BEHIND a pinch as one flat dark
    //  sheet, and fabric that is merely sheared, as beside a pinch dragged over the leg, as a bruise-like ring. Sheared or
    //  drawn-out fabric keeps its yarn per area: it wrinkles, it does not darken. The original's knee pinch: a soft dark
    //  wedge ahead of the fingers, a slightly paler, finely wrinkled fan behind them)
    float gather = sh_smooth(0.75, 0.40, tens.x * tens.y);
    // (only while the hand holds it: fabric recoiling from a tear is squeezed for a frame or two - a dark ring)
    gather *= uv2.x > 0.0 ? _SheerHeldL : _SheerHeldR;
    {
        float4 pinG = uv2.x > 0.0 ? _SheerPinchL : _SheerPinchR;
        float gdu = U - pinG.x; gdu -= floor(gdu + 0.5);
        float gr = length(float2(gdu * max(pinG.z, 0.1), Vz - pinG.y));
        // (the dark gather is the fabric bunched round the pinch; squeezed fabric further away - the lower edge of an
        //  ankle sail - read as a dark rope)
        gather *= lerp(0.5, 1.0, sh_smooth(0.07, 0.035, gr));
    }
    cov = lerp(cov, max(cov, 0.88), gather);          // (0.95: the pinch a sooty dent with dark radial streaks, review 13)
    // 'Frost': the worn knit's matte haze (relaxed, fuzzy loops). It clears where the threads are pulled taut - by the
    // pose - and on fabric lifted off the skin: the
    // original's tents are dark, satin membranes next to the hazy stocking on the leg.
    float poseK = pow(max(sPose, 0.4), _FrostClearAtStretch);
    // ... and where the hand has pushed the knit together: gathered fabric is yarn on yarn, dark (the original's blotch of
    // bunched nylon ahead of a pinch dragged over the leg)
    float squeeze = sh_smooth(0.80, 0.45, tens.y) * (uv2.x > 0.0 ? _SheerHeldL : _SheerHeldR);
    // (on the foot only a little by its tension / squeeze: an ankle pull's strain over the instep cleared its paler haze into a
    //  dark V across the top of the foot, review 5 - the original's instep keeps its tone; lifted fabric clears as anywhere)
    float fcK = 1.0 - 0.75 * footMask;
    // (a sail keeps part of its haze: MEASURED, review 14 - the original's sails are a neutral grey about as light as the
    //  backdrop, L 55 - 75 at 5.6 / 27.5 / 27.7 s; ours, cleared to the bare black yarn, 40 - 45 - their own light a third of
    //  the original's. _SheerSailHaze: the share of the haze a sail keeps, 0.6 by default)
    float sailHaze = _SheerSailHaze > 0.0 ? _SheerSailHaze : 0.3;     // (0.6: lighter and bluer than the original's, (65,70,78) vs (52,53,57))
    float frostClear = saturate(max(max((poseK - 1.0) * 1.5 * fcK, lifted * (1.0 - sailHaze)), squeeze * 0.5 * fcK)) * _FrostClearAtStretch;

    // ---- knit micro coverage (weave map: RGB tangent normal, A yarn coverage)
    float2 mp = float2(Um * _WeaveTiling, Zm * _WeaveTiling * 3.72);
    float3 wq = sh_noise3(float3(mp, 0), 1.6, 3, 0.6);
    float2 kuv = mp + float2((wq.x - 0.5) * 0.07, (wq.y - 0.5) * 0.09);
    // (filtered for the FINAL picture's pixels: at 2 x 2 supersampling the loops - 2.3 x 3.1 px of the 1080 px frame at
    //  the knee - were resolved in the render and box-filtered into a regular checker, a screen door round the holes)
    // (and averaged with the sample half a wale over: the loops' wale-to-wale repeat - 2.2 - 2.5 px, at the pixel limit -
    //  cancels and only the courses' rows remain, which is what the original shows; drawn, the wale repeat aliased into
    //  'fingerprint' fringes on stretched fabric and a hatch on the sails, review round 6)
    //  - only where the fabric is drawn out, squeezed or lifted (where the moire was); at rest the loops stay)
    // (the shins keep more of the loops' detail: the original shows them there at 2.5 - 3 px, band-pass 2.1 - 4.2 vs ours
    //  0.6 - 1.3; round the knee holes the full filtering stays - the screen door the user pointed out)
    float kBias = -0.6 + log2(pxF) * lerp(1.0, 0.35, sh_smooth(0.42, 0.32, Vh));
    float4 knit1 = weaveTex.SampleBias(ssWeave, kuv, kBias);
    // (not where the knit is drawn out big enough to draw its loops - 1.4 - 2.2 x its area: there the wale repeat is
    //  well above the pixel and the original's sails show their mesh; averaged, ours were smooth tinted film, review 3)
    float kAvg = saturate(max(max(lifted, (tens.x - 1.0) * 4.0), (1.0 - tens.y) * 4.0)) * (1.0 - sh_smooth(1.4, 2.2, sCloth));
    float4 knit = kAvg > 0.01 ? lerp(knit1, 0.5 * (knit1 + weaveTex.SampleBias(ssWeave, kuv + float2(0.5 / 48.0, 0.0), kBias)), kAvg) : knit1;
    // no two loops, and no two courses, are alike (yarn count and loop length vary: fine rows of dots and a faint
    // 'barre' of lighter and darker courses - what the original's fabric shows at 100 %)
    float2 kcell = kuv * float2(48.0, 26.0);
    float2 kci = floor(kcell);
    float yv = sh_hash21(kci), ycr = sh_hash11(kci.y * 1.37 + 0.71);
    // (point-sampled per cell: only while a cell is larger than ~2 pixels)
    float shinW = sh_smooth(0.42, 0.32, Vh);
    float kresPx = _SheerKresPx > 0.0 ? _SheerKresPx : 1.8;     // (2.5: the knit faded to a smooth film at VIEW 01's 2.5 px loops - 'airbrushed', review 10)
    float kres = saturate(lerp(3.0, 4.0, shinW) * 2.5 / kresPx - 6.0 * 2.5 / kresPx * pxF * max(fwidth(kcell.x), fwidth(kcell.y)));    // (loops under ~2.5 px - 2 on the shins: no per-loop dots)
    float near0 = sh_smooth(3.5, 2.2, viewDist);
    // (every loop opens a little more or less: dots of different brightness in rows - whole cells lighter or darker
    //  read as a mosaic)
    // (wider spread: with the loops no longer averaged away at rest the VIEW 02 shin read as a regular screen of dots,
    //  2 x the original's fine-grain contrast, review round 8 prep)
    float kvar = (knit.a - _KnitMean) * lerp(1.0, lerp(0.15, 1.85, yv) * lerp(0.85, 1.15, ycr), kres)
               * (1.0 - 0.75 * lifted);     // (drawn out and seen obliquely in a sail the knit beat into moire lines, review 10 at 13 / 27.4 s)
    // The knit shows most where the key light glances off the yarn (the 'sheen zone' on the front of the upper thigh)
    // and hardly elsewhere - measured on the original at 0.5 s: fine-detail contrast 5.0 there, 1.5 six centimetres lower.
    float3 Lk = _SheerKeyPos.w > 0.5 ? normalize(_SheerKeyPos.xyz - (posWS + _WorldSpaceCameraPos)) : V;
    // (by rest height: the front of the upper thigh; a little on calf and shin, which VIEW 02 sees from closer)
    // (+ the shins: measured fine-knit band-pass on the original's shins 2.1 - 3.6 in both views, ours 0.5 - 1.5)
    float hzone = 0.30 + 0.75 * sh_smooth(0.535, 0.60, Vh) + 0.75 * sh_smooth(0.42, 0.32, Vh);   // (round 10: the knee band read as smooth skin, the thigh as a 2 px mesh - more even)   // (+ a little everywhere: lower thigh 0.9 vs 1.5)
    // (where the key light glances off the yarn - the original's grain all but vanishes away from that, e.g. in the orbit
    //  views: thigh 0.5 vs our 5.0 high-pass at 13 s - and weaker on fabric drawn out, where it beat into moire; round 9)
    float kGl = sh_smooth(0.45, 0.90, dot(N, normalize(Lk + V)));
    float kmul = (0.45 + 13.0 * hzone) * lerp(0.25, 1.0, kGl) * lerp(1.0, 0.3, sh_smooth(1.03, 1.25, tens.x));      // (round 12: zig-zag moire on the stretched tent stripe)        // (round 7: the knit's micro-texture is what the original shows at 100 %; fainter glints)                                  // (x1.33 with the loops filtered for the final picture)
    // where single threads show instead of the knit's loops: in a ladder, and where the yarn is bunched around a hole
    float vis = max(open, saturate((max(dWale, dCourse) - 1.15) / 0.5));
    // (within a centimetre of a hole the knit is drawn out and loosened: its loops no longer show as a regular texture
    //  - the original beside the knee hole at 9.5 s is a smooth haze, hp 1.3; ours kept the sheen zone's grain, 2.2)
    float knitHaze = sh_smooth(0.012, 0.003, holeSD);
    // (on the foot the knit's cells are drawn out along it - height hardly changes there - and showed as a coarse net)
    cov = saturate(cov + kvar * _WeaveContrast * kmul * lerp(1.0, 0.8, shinW) * near0 * (1.0 - vis) * (1.0 - 0.8 * knitHaze) * (1.0 - 0.3 * footMask) * (1.0 - 0.2 * lifted) * (1.0 - _SheerDbgK)
          * (1.0 - 0.85 * footMask * sh_smooth(-0.085, -0.100, rest.z))     // (the toe TIP: no course rings round it, review 9 - over the whole cap it left a smooth pale patch, review 10)
          // (toward the outline the loops are foreshortened below a pixel and beat into moire under the rim light, review
          //  round 8 at 19.3 s)
          * lerp(0.3, 1.0, sh_smooth(0.10, 0.35, abs(dot(N, V))))
          // (loops under ~2 picture pixels: their grain changed with every frame's sub-pixel jitter - a faint boil on the
          //  still VIEW 02 legs, temporal spread 2.3 vs the original's 0.6, review round 11)
          * sh_smooth(0.62, 0.38, pxF * max(fwidth(kcell.x), fwidth(kcell.y))));
    cov *= 1.0 - bag * 0.15;
    // (patchy at the scale of a few loops: yarn tension and loop size vary - the original's grain is irregular, 35 % of its
    //  fine energy at 4 - 20 px periods vs our 4.5 %, ours a regular screen; round 12)
    // (+ a finer grain, ~2 mm, faded where it would be under ~4 px: review 5 still read the close-up as a regular screen door
    //  where the original's knit is an irregular grain)
    float fgPx = 0.0019 / max(length(fwidth(rest)) * pxF, 1e-7);
    float grK = _SheerGrainK > 0.0 ? _SheerGrainK : 1.4;
    cov = saturate(cov + ((sh_noise(rest + 6.1, 230.0, 2, 0.55) - 0.5) * 0.08 + (sh_noise(rest + 9.3, 520.0, 1, 0.5) - 0.5) * 0.06 * grK * saturate((fgPx - 4.0 / grK) / 3.0))
                         * near0 * (1.0 - vis) * (1.0 - footMask * 0.5));
    // Two thread families, each covering `a` of the surface (together: cov): the wales (columns of loops along the leg)
    // and the courses (rows round it). Where the knit has let go - in a ladder and for some millimetres round every hole -
    // the loops are drawn out into single threads and the SAME dense grid shows, wale by wale and course by course
    // (0.87 mm apart, ~3 px of the 1080 px frame): very thin dark lines on a paler ground, smooth - straight, or gently
    // curved where a hole has pushed the yarn aside (material coordinates, DamageRaster): the courses arch over a hole and
    // sag under it, the wales bend round its sides, both crowd toward its edge and into the strap between two holes.
    // (User feedback 2026-11-15: every second course drawn as a wavy rung read as threads that had vanished, and as an
    //  ECG trace; the original's grid stays dense, its lines straight or slightly curved.)
    float a2 = 1.0 - sqrt(max(1.0 - cov, 0.0));
    float Lw = 1.0, Lc = 1.0;
    [branch] if (vis > 0.002 && _SheerDbgG < 0.5)
    {
        // (two threads per wale - the two legs of each drawn-out loop - and every course: the original's gauze is a
        //  DENSE grid of very thin lines, 1.5 - 3 px apart at its native size, on a mid-tone ground - at this size mostly
        //  a haze; only threads drawn apart beyond ~4 px, and the grain of bunched ones, show as lines)
        float bW = sh_smooth(1.22, 1.75, dWale), bC = sh_smooth(1.22, 1.75, dCourse);
        // (the rungs are not ruled: each wanders a little on its own - spacing +-20 %, a few degrees - smooth, no zigzag)
        float cphW = cph + (sh_noise(float3(Um * 60.0, Zm * 400.0, 5.3), 1.0, 1, 0.5) - 0.5) * 0.5;
        // (in a ladder some wales show as threads too - the original's runs carry vertical threads; ours were bare
        //  horizontal stripes, review round 7)
        // (but faint inside a run: there the wales have let go and the rungs carry it - at 0.7 the ladders were a regular
        //  graph-paper grid, independent review 2026-11-17)
        // (0.5: the original's ladder is a fine grid of wales AND courses, ours rungs alone - review 4; 0.7 had read as
        //  graph paper, the threads' own wander keeps it irregular)
        // (review 9 at 3 x: the original's band is a gauze of fine VERTICAL threads - the run wales, light and dark - with
        //  faint rungs across; ours a pink grid of dark rungs. The wales carry it now)
        // (fully irregular inside a ladder - each run wale its own weight, breaking off and coming back: a regular set read as
        //  graph paper, review 12; the original's are separate threads with irregular cross-strands)
        Lw = sh_threadsLod(wph * 2.0, fwW * 2.0 * pxF, 0.40, 3.1, lerp(0.75, 1.0, ladO), Zm * 45.0, max(bW, 0.85 * ladO), 0.22);
        // (in a ladder the rungs - the courses' floats - stay lines down to ~2.5 px: broken, uneven, each one bright or
        //  dark for a few millimetres; the original's run below a hole is a busy grain of short rungs, not a haze)
        Lc = sh_threadsLod(cphW, fwC * pxF, 0.36, 11.7, 0.9, Um * 28.0, bC, 0.16);
        // (in a ladder the rungs stand apart - the run lets the fabric lengthen: 4 - 8 px in the original, ours were a
        //  haze at the knit's pitch - review round 5: rung strength 0.86 vs 3.63 - broken into ~1 cm stretches)
        // (MEASURED, review 14 at 21.2 s inside the band: the original's horizontal structure |dI/dy| 5.2 against its
        //  vertical 2.8 - dense soft rungs ~3.5 px apart, the wales showing mainly along the band's sides; ours 2.0 against
        //  5.4, sparse rungs on dense dark verticals - 'graph paper'. The rungs carry the band now: drawn down to ~2.5 px
        //  (faded from 0.3 they thinned to every third), evenly spaced but for a gentle wander)
        [branch] if (ladO > 0.01)
            Lc = lerp(Lc, sh_threads(cphW / 1.5, fwC * pxF / 1.5, 0.34, 21.3, 1.0, Um * 45.0, 0.50, 0.4), 0.85 * ladO);   // (0.3: review 10 missed the original's crisp rungs; 0.6 had been a barcode, review 5)   // (spacing jittered: no barcode; 0.6 - review 5: still a barcode of dark rungs, the original's threads are fine and low in contrast)
    }
    // (a ladder is not evenly open along the leg: stretches where more loops held)
    float openV = open;
    [branch] if (open > 0.002) openV = open * lerp(0.78, 1.0, sh_noise(float3(Um * 40.0, Zm * 28.0, 3.7), 1.0, 1, 0.5));
    // the gauze is a little opener than the knit it came from, not empty: both families stay (the wales that ran are
    // thinner than the floats of the courses; the wales that hold are the dark streaks at a ladder's sides)
    // (right round a hole the knit is at its loosest: paler still, its threads showing all the more)
    // (a little opener in a ladder: the original's band is 168 on average, ours 153 - review 4)
    // (review 5: at 0.19 / 0.23 the bands read saturated salmon - the skin through too little gauze; the original's are
    //  paler and greyer: the gauze denser again)
    // (... and denser on the lower leg: the calf's open gauze glowed salmon over the brighter skin of VIEW 02, review 7)
    float shinL = 1.0 - sh_smooth(0.30, 0.50, Vh);
    float liftKg = sh_smooth(0.004, 0.0015, lift);                       // (on the leg: over the backdrop pale threads read as smears)
    // (review 9, measured at 12 s: the original's band (178,147,141) is its skin (211,186,182) behind ~0.57 of light, its
    //  threads adding a little warm light; ours (158,113,106) let through ~0.32 and its threads lit it red - a dark salmon
    //  band. Opener, the threads less red, below)
    float aw = lerp(a2, lerp(lerp(0.19, 0.25, shinL), 0.10, nearCore), openV), ac = lerp(a2, lerp(lerp(0.22, 0.29, shinL), 0.14, nearCore), openV);
    // (the threads are FINE and soft: in plain gauze a grid one can just make out; where a family is bunched - the wales
    //  beside a hole, the courses above and below it and in a strap - its grain shows: a ribbon of threads along the edge)
    // (bunched threads softer: at full strength the wales crowding a hole's side drew a second outline ~12 px out, and the
    //  courses arching over small holes dark pen-stroke brows, review round 10)
    // (in a ladder the run wales show along its SIDES - a darker bundle each side - and only faintly across it, review 14)
    float ladEdge = sh_smooth(0.40, 0.72, abs(dB.z) * lerp(1.0, 1.45, 1.0 - sh_smooth(0.30, 0.50, Vh)));
    float wTw = vis * lerp(lerp(0.16, 0.30, sh_smooth(1.05, 1.7, dWale)), lerp(0.12, 0.36, ladEdge), ladO), wTc = vis * lerp(lerp(0.2, 0.30, sh_smooth(1.05, 1.7, dCourse)), 0.42, ladO);
    // (yarn bunched against an edge shows as its threads - lines on the loosened gauze - not as a darker band: the
    //  original's fabric right round a hole is PALER than the knit further out, ours was darker; only a third of the
    //  extra density goes into the coverage. Spread yarn, above / below a hole, thins in full)
    float dEw = dWale > 1.0 ? 1.0 + 0.3 * (dWale - 1.0) : dWale, dEc = dCourse > 1.0 ? 1.0 + 0.3 * (dCourse - 1.0) : dCourse;
    float cw = saturate(aw * dEw * lerp(1.0, Lw, wTw));
    float cc = saturate(ac * dEc * lerp(1.0, Lc, wTc));
    cov = 1.0 - (1.0 - cw) * (1.0 - cc);
    // a ladder that is only starting (the fabric is still held taut by the hand): a row of short open slits, one every
    // few courses (the original: bright horizontal dashes creeping down the thigh while the pull is held)
    // (level bars one rung apart, like the original's: counted along the height the fabric is at NOW - along the
    //  fabric's own courses the pinch bent them into chevrons)
    // (1.7 mm apart at the knee, ~7 mm on the thigh, where the knit is drawn out most: measured at 0.5 s and 3.4 - 3.8 s)
    // (near the pinch the bars follow the fabric - the original's top slits curve into chevrons where it gathers -,
    //  further down they are level; every bar its own length and weight, soft ends: review round 7 counted 11
    //  identical crisp rectangles on a ruler-straight line)
    float4 pinS = uv2.x > 0.0 ? _SheerPinchL : _SheerPinchR;
    float sdu = U - pinS.x; sdu -= floor(sdu + 0.5);
    // (only partly: there the fabric is drawn out several times over and bars counted along it fully swelled into blobs)
    float sNear = 0.35 * sh_smooth(0.06, 0.02, length(float2(sdu * max(pinS.z, 0.1), Vz - pinS.y))) * saturate(pinS.w * 2.0);
    float sPitch = lerp(2.0 * PC, 0.0068, sh_smooth(0.47, 0.54, Vh));
    // (not bent toward the fabric's own height near the pinch any more: where the pull had drawn the fabric up that packed
    //  the bars 4 x closer - a rung grew into an X, then a fan of curved bars 8 px apart, review round 13 at 3.4 s)
    // (and the pitch follows the height in the picture too, the bars counted along it as its integral: level bars whose
    //  spacing changes smoothly. A pitch picked by the fabric's own height - fine at the knee, coarse on the thigh - drew
    //  the thigh pull's row, which ran down into the knee's pitch, as an X and a fan of arcs 8 px apart, round 13. The
    //  change sits between the knee's ladder - up to 0.505 m - and the thigh pull's row - down to 0.517 m)
    float yW = posWS.y + _WorldSpaceCameraPos.y;
    // (PK 3.4 mm: the original's knee rungs grow ~13 px apart, 0.07 - 0.68 s; at 1.7 mm ours were a 6 px barcode that had
    //  to be faded out - and then the knee showed no build-up before its tear, review round 14)
    const float PK = 0.0034, PT = 0.0068, Y0 = 0.500, Y1 = 0.520;
    const float kP = (PT - PK) / (Y1 - Y0);
    float slpI = (min(yW, Y0) - Y0) / PK + log((PK + kP * (clamp(yW, Y0, Y1) - Y0)) / PK) / kP + max(yW - Y1, 0.0) / PT;
    float slp0 = slpI + (nzc - 0.5) * 0.3 + (sNear + sPitch) * 0.0;
    float w2s = sh_hash11(floor(slp0) * 2.3 + 1.1);
    float sLen = (sh_hash11(floor(slp0) * 7.1 + 3.3) - 0.5) * 0.0024;           // +-1.2 mm on the band's half-width
    // LENS-shaped openings, not bars (review round 8: 'identical hard-edged parallelograms'; the original's are soft,
    // pointed at both ends and slightly bent): across the band t runs 0 at its edge to 1 some 4 mm in; the opening is
    // widest in the middle and closes to a point toward the edge, and its ends sag a little
    float tS = saturate(-(runSD + sLen + 0.0002) / (0.0035 + 0.0015 * w2s));
    float slp = slp0 - 0.30 * (1.0 - tS) * (1.0 - tS) * (w2s - 0.3);
    float sl = abs(frac(slp) - 0.5);
    float lens = sqrt(tS);
    // (only well inside a band: along its border the stored age is blended down from 1 to 0 by the filter and looked
    //  'young' for one texel - a full ladder's lower end drew a single straight bar, review round 5, 17 - 23 s)
    // (at the knee's fine pitch - 1.7 mm, ~5 px - a third of the pitch drew faint hairlines: a little thicker there and
    //  more open; the original's first rungs under the knee pinch are distinct bright bars, review round 8)
    float kneeS = 1.0 - sh_smooth(0.47, 0.54, Vh);
    float slit = sh_smoothAA(lerp(0.30, 0.37, kneeS) * lens, 0.04, sl * lerp(0.85, 1.25, w2s)) * sh_smooth(0.0, 0.15, tS) * (1.0 - runOpen) * sh_smooth(0.10, 0.22, age)
               * sh_smooth(0.25, 0.40, tens.y)            // (not in knit the fingers have gathered: slits bent into bright streaks in the dimple; from 0.55 it also hid them in
                                                          //  the fabric drawn down below a pinch - narrowed across as it lengthens - where the original's column runs, review 5)
               * sh_smooth(7.0, 10.0, 1.0 / max(fwidth(slp) * pxF, 1e-4));  // (closer than ~4 px they beat into a zig-zag, round 12; at the
                                                                             //  knee's ~6 px a barcode of 25 bars - the original shows a few, round 14)
    // (each opening its own strength, and uneven along its length)
    float sAlong = lerp(0.65, 1.0, sh_noise(float3(U * 90.0, floor(slp) * 1.7, 2.9), 1.0, 1, 0.5));
    cov = lerp(cov, cov * lerp(0.3, 0.15, kneeS), slit * (0.45 + 0.55 * w2s) * sAlong * (1.0 - _SheerDbgS));
    // holes: the torn edge. Along most of an outline it is a THIN, uneven line of rolled yarn (0.3 - 1.2 mm, here and
    // there missing; measured on the original, the fabric 2 px outside a hole is only 3 - 5 % darker than further out).
    // Along some stretches - about a third of it - the edge has rolled up into a LIP: a cord of yarn 1 - 2.5 mm wide,
    // two or three threads deep, with paler crests between them; and here and there a FLAP of knit still hangs into the
    // hole, a translucent crescent with its own torn edge (user, 2026-11-15: in the original some stretches of an edge
    // carry a thick 'labium' of torn fabric and others none; ours were all alike).
    float lip = 0.0, lipN = 0.5, cordL = 0.0, flapC = 0.0, lipB = 0.0;
    [branch] if (holeSD < 0.0032 && holeSD > -0.0045)
    {
        lipN = sh_noise(rest, 95, 2, 0.5);
        // (labia mostly along a hole's top edge - the edge curls up over it -, flaps along its bottom edge: the original
        //  at 17, 30, 35 s)
        // (varying faster along an outline and mostly on its top: a small hole lying inside one patch of lip got its cords
        //  all round - concentric rings, review round 6's 'stacked arcs')
        // (on more of the outline: the original's big thigh holes at 12 s carry a thick rolled lip along most of their edge)
        float lipBig = sh_smooth(0.38 - 0.22 * edgeTop, 0.56 - 0.22 * edgeTop, sh_noise(rest + 21.7, 70.0, 1, 0.5)) * lerp(0.45, 1.0, edgeTop);
        lipB = lipBig;
        // (thinner on the shin, where the tears are narrow slits)
        float shin = lerp(0.5, 1.0, sh_smooth(0.17, 0.46, Vh));
        float lipW = ((0.0007 + 0.0010 * lipN * lipN) * (1.0 + 0.4 * saturate(dCourse - 1.3)) * lerp(0.8, 1.3, tb)
                      + lipBig * (0.0010 + 0.0018 * sh_noise(rest + 2.9, 160.0, 1, 0.5)) * lerp(1.0, 1.3, edgeTop) / max(shin, 0.75)) * shin;
        float lq = saturate(holeSD / max(lipW, 1e-5));
        lip = sh_smooth(1.0, lerp(0.0, 0.7, lipBig), lq) * (1.0 - inHole) * max(sh_smooth(0.30, 0.52, lipN), lipBig);
        // the cord: 2 - 3 dark threads following the edge, paler between - only where they are > ~2.5 px apart
        float nCord = lerp(1.0, 2.2, lipBig);
        float cpx = lipW / nCord / max(hfw * pxF, 1e-7);
        cordL = lipBig * pow(0.5 + 0.5 * cos(SH_TAU * lq * nCord), 2.0) * sh_smooth(2.0, 3.5, cpx) * (1.0 - inHole);
        // the flap: as wide as the hole allows - a fifth to a quarter of its depth (probes 4 and 10 mm in, along the leg
        // and round it: a small hole or a slit is not closed by a membrane)
        float fl = max(sh_smooth(0.56 - 0.07 * edgeBot, 0.64 - 0.07 * edgeBot, sh_noise(rest + 33.1, 26.0, 1, 0.5)), _SheerDbgF) * shin;
        [branch] if (fl > 0.01 && holeSD < 0.0)
        {
            float depth = holeSD - (min(sh_probe4(dmgTex, ssLinearRepeat, duv, 0.004), sh_probe4(dmgTex, ssLinearRepeat, duv, 0.010)) - 0.5) * 2 * SH_DMG_RANGE;
            float flapW = fl * min(0.0012 + 0.0028 * sh_noise(rest + 5.9, 60.0, 1, 0.5), 0.3 * depth);
            float fq = -holeSD / max(flapW, 1e-5);
            float fin = saturate((flapW + holeSD) / hfw + 0.5);                 // inside the flap's free edge
            float fedge = saturate(1.0 - abs(flapW + holeSD) / (1.2 * hfw));    // its torn edge: a fine dark line
            flapC = max(fin * lerp(0.62, 0.30, saturate(fq)), fedge * 0.75) * sh_smooth(0.0, 0.0005, flapW);
        }
    }
    // (a labium is translucent - a few threads rolled together, the skin shows between them - mid-tone, not black)
    // (lighter: 0.60 / 0.48 drew a dark rim 2 - 4 px wide round every hole - 'a thin dark-red outline, drawn on', review 5;
    //  the original's is one dark thread line with a paler rim of loosened yarn beyond it)
    cov = lerp(cov, max(cov, lerp(0.52, 0.44, lipB)), lip * lerp(lip, 1.0, lipB) * _FrostBoundaryStrength);
    // (softer: dark at 0.8 - 0.9 the cords drew a second outline beside the rim and, over small holes, detached 'eyebrow'
    //  arcs - review round 11)
    cov = lerp(cov, max(cov, lerp(0.62, 0.70, edgeTop)), cordL * 0.5 * lip * _FrostBoundaryStrength);
    float rimW = 0.00008 + 0.00010 * nzc;
    // (broken and lighter: present all round every hole at 0.85 it outlined each one like a sticker, review 12 - the original's
    //  rims are thin, frayed, here and there)
    float rim = saturate((rimW * lerp(0.8, 1.7, tb) - holeSD) / hfw + 0.5) * (1.0 - inHole) * sh_smooth(0.40, 0.66, lipN);
    cov = lerp(cov, max(cov, 0.74), rim * _FrostBoundaryStrength);
    // loose thread ends: here and there along the edge a few fine threads curl a millimetre or two into the hole
    float threadA = 0.0;
    [branch] if (holeSD < 0.0003 && holeSD > -0.0030)
    {
        float wn = sh_noise(rest + 3.3, 480, 1, 0.5), wg = sh_noise(rest + 9.1, 120, 1, 0.5);
        float wfw = max(fwidth(wn), 1e-5), ww = 0.016;
        float wln = saturate((ww - abs(wn - 0.5)) / wfw + 0.5) * saturate(2.0 * ww / wfw);
        threadA = wln * sh_smooth(0.72, 0.80, wg) * sh_smooth(-0.0030, -0.0008, holeSD) * inHole;
    }
    // the TOE SEAM, low across the front of the toes (uv1.w = signed distance to it): a dense, darker line of sewn
    // thread on a soft ridge, the knit gathered a little on either side. (Faded into the reinforced toe since round 12 it
    // had disappeared - user, 2026-11-16: 'the original has it, and it's realistic'; round 7's dense 0.9 mm ridge had
    // read as a pale wire, so the ridge is low and the line dark)
    float seamLine = sh_smoothAA(0.0011, 0.0005, abs(tseam)) * (1.0 - _SheerToeStyle.x);
    float seamRidge = 1.0 - sh_smooth(0.0, 0.0019, abs(tseam));
    float seamSide = saturate(sh_smooth(0.0032, 0.0013, abs(tseam)) - seamLine) * (1.0 - _SheerToeStyle.x);
    float toePocket = sh_smooth(0.0005, -0.0015, -tseam);
    cov = lerp(cov, max(cov, 0.985), seamLine);
    cov = lerp(cov, max(cov, 0.93), seamSide * 0.5);
    // (toePocket is 1 over the whole leg as well: +0.06 coverage there, which the look calibration includes)
    cov = lerp(cov, min(cov + 0.06, 0.99), toePocket);
    // reinforced TOE: the cap beyond the toe seam (toePocket is 1 everywhere else - it had made the whole foot a dense,
    // opaque clay-grey sock; the original's instep is sheer with the knit showing and only the toe cap darker, review
    // round 6)
    // (+ the toes themselves, tips to bases: sheer there, the skin's deep gaps between the toes showed through and the foot
    //  read bare - review round 7 'toes separated'; the original's reinforced toe covers them all, darker)
    float toesR = sh_smooth(-0.058, -0.095, rest.z) * sh_smooth(0.056, 0.024, rest.y);      // (a soft change, not a band; wider - 'the seam where it starts is abrupt', review 8)
    float toeBox = max(1.0 - toePocket, toesR) * footMask * (1.0 - _SheerToeStyle.x);   // (none on sandal-toe hosiery)
    // (round 9: opaque at 0.97 the toe cap read as grey clay, a material break; the original's reinforced toe is only
    //  a little denser, the skin's warmth and the toes' sheen still come through)
    // (0.83: measured at 26.5 s the original's toes are L 104 - 130 (~117, as its forefoot), pink-violet (127,107,113); ours
    //  at 0.86 with the darker yarn below were ~97 and grey - 'opaque grey-mauve rubber', review 9)
    cov = lerp(cov, max(cov, 0.83), toeBox);       // (round 12: 'no denser, darker toe area'; 0.88 read opaque, round 13; 0.86 - review 6: 'no reinforced toe')
    // (thinning it over the toes' tops - tried after review 7 - made the cap read LIGHTER than the forefoot, an inverted
    //  reinforced toe, review 8: removed)
    // (the toe darkens toward the floor - where the fabric wraps under it, seen edge-on and in the contact shadow; ours was
    //  one flat mid-grey down to the outline, round 14)
    // (the lowest centimetre only, and less: the toes' contact with the floor is shaded by it now - SheerTights' contactOcc)
    float toeLow = toeBox * sh_smooth(0.016, 0.004, rest.y);
    cov = lerp(cov, max(cov, 0.90), toeLow);
    // the player's PATTERN and the TOP of a thigh-high (SheerLook.hlsl): knitted in, so it rides with the fabric and its
    // tears (it is drawn in the same coordinates); a fishnet replaces the knit (keeping _SheerPat.z of it)
    SheerPatOut pat = SheerPattern(U, Vz, Vh, uv2.x);
    // (a reinforced toe is knitted plain: dots, hearts, stripes stop at it - fishnets stay netted)
    if (pat.replace < 0.5) { float plainToe = 1.0 - toeBox; pat.covW *= lerp(plainToe, 1.0, pat.welt); pat.mix *= plainToe; }
    // a torn FISHNET opens along its cords: a segment (knot to knot) is gone when its middle lies inside the tear, so the
    // opening is whole diamonds run together, bounded by intact cords, with short broken ends left at the knots; the sheer
    // layer under the net (if any) is cut like the knit, and the knit's loose threads and flaps belong to that layer only
    float cordKeep = 1.0, under = pat.replace > 0.5 ? _SheerPat.z : 1.0;
    [branch] if (pat.replace > 0.5 && holeSD < 0.0105)
    {
        float segSD = (dmgTex.SampleLevel(ssLinearRepeat, SheerDamageTexUV(pat.seg.xy), 0).r - 0.5) * 2 * SH_DMG_RANGE;
        float broken = sh_smooth(-0.0003, -0.0013, segSD);
        float stubL = 0.07 + 0.2 * sh_hash21(pat.seg.xy * float2(517.0, 9631.0));
        float past = saturate((pat.seg.z - stubL) / max(fwidth(pat.seg.z), 1e-4) + 0.5);
        cordKeep = 1.0 - broken * past;
    }
    if (pat.replace > 0.5) cov = max(cov * _SheerPat.z * (1.0 - inHole), pat.cov * cordKeep);
    else { cov = lerp(cov, max(cov, pat.cov), pat.covW); cov = lerp(cov, 0.0, inHole); }
    cov = max(cov, max(threadA * 0.85, flapC) * under);
    // (in a cleft the knit lies doubled - over the side of one toe and the next - and is seen edge-on: denser. The worn
    //  stocking's cavity (baked) only while it lies on the leg: lifted, it leaves its hollow)
    // (only the deep ones: the shallow dips over the tops of the toes as dark streaks back over the forefoot - 'veins')
    // (... and little where the fabric faces up: a dip open to the light above - dark marks on top of the forefoot)
    // (half on the foot: the toes read as separate beads with deep gaps, review 5 - the original's knit bridges them, soft dips)
    float cavW = 0.75 * sh_smooth(0.12, 0.55, 1.0 - saturate(cavAO)) * (1.0 - sh_smooth(0.002, 0.008, lift)) * (1.0 - 0.7 * sh_smooth(0.55, 0.9, N.y)) * (1.0 - 0.5 * footMask)
               * (1.0 - 0.55 * toeBox);      // (the reinforced toe runs over the clefts: dark between every toe they read as 'sausages', review 11)
    cov = lerp(cov, max(cov, 0.92), saturate(cavW * 1.6));

    // ---- opacity vs viewing angle (denier effect)
    float ndv = max(abs(dot(N, V)), 0.02);
    float expo = 1.0 / pow(ndv, _AngleFalloff * (1.0 + 0.6 * footMask));   // (the foot darkens toward its outline: 0.70 vs the original's 0.43, round 12)
    float alpha = 1.0 - pow(max(1.0 - cov, 0.0), expo);
    alpha = max(alpha, threadA * 0.85 * under);

    // ---- normals: knit + ankle wrinkles + hole rims + toe seam
    float near = sh_smooth(3.5, 2.2, viewDist);
    float tboost = 1.0 + sh_smooth(1.0, 1.6, stretch * pre) * (_TensionNormalBoost - 1.0);
    // (the loops' relief shows where the key light glances off them - the sheen zone, as the coverage grain above -
    //  and hardly elsewhere: at the knee the loops are 2.3 x 3.1 px of the 1080 px frame and their shading was a regular
    //  checker round every hole, the original is a smooth haze there; in the gauze the threads take over)
    float kStrength = near * tboost * 1.3 * _WeaveNormalStrength * _NormalStrength * (1.0 - _SheerDbgN) * (1.0 - 0.7 * lifted)
                    * lerp(0.1, 1.0, saturate(hzone)) * (1.0 - 0.8 * max(vis, knitHaze))
    // (... and not on the foot - the original's is a smooth haze, ours a moire of curved lines, review round 5 - nor
    //  toward the outlines, where the loops' relief caught the rim light as contour-line moire)
                    * (1.0 - 0.5 * footMask) * sh_smooth(0.12, 0.40, abs(dot(N, V))) * (1.0 - 0.5 * lifted)   // (0.85: 'no visible knit' on the foot, review 13)
                    // (hardly any in the reinforced toe: the lattice's rows close into circles round the toe tip there, and the
                    //  courses drew a fingerprint whorl on the big toe, review 9)
                    * (1.0 - 0.9 * toeBox * sh_smooth(-0.085, -0.100, rest.z));
    float3 kn = knit.rgb * 2.0 - 1.0;
    float3 Nk = normalize(kn.x * T + kn.y * B + kn.z * N);
    float3 Nn = normalize(lerp(N, Nk, kStrength));
    // ankle creases: fine, close, soft horizontal folds in a short band just above the instep, mostly at the front. The
    // original (26 - 32 s, native size): ~1.5 - 2.4 mm apart, wavy, each its own depth, in a band ~3 cm tall; ours were
    // 3.6 mm apart over ~5 cm, deep and regular (user, 2026-11-16: 'too far apart ... and run for too long, height-wise').
    // Band-limited by the pixel footprint (a sub-4-px period only aliases into sparkles under the rim lights)
    const float WK = SH_TAU / 0.0021;
    float wqn = sh_noise(rest, 40.0, 1, 0.5), wqf = sh_noise(rest + 1.9, 130.0, 1, 0.5);
    // (spacing that changes from place to place - 1.7 - 2.6 mm - and creases that run only part of the way round: evenly
    //  spaced full rings read as contour lines, independent reviews 2 / 3; the original's are irregular, broken, branching)
    // (spacing varies again, 1.6 - 2.9 mm, and each crease wanders a little: evenly spaced along the courses they read as
    //  'a ribbed sock cuff', review 10 - the original's bunching is irregular)
    float wkl = WK * (0.72 + 0.56 * sh_noise(float3(U * 9.0, 0.0, rest.x * 7.0) + 9.1, 1.0, 1, 0.5));
    // (less wavy: deeper, they read as contour lines when they wandered this much - the original's are near level)
    // (along the knit's COURSES - its height along the wale, Vh, from the band's middle: as rest.y x a varying frequency they
    //  were literally contour lines of the instep's slope, U-shaped and tilted 35 deg where the frequency changed - 'many thin
    //  wavy concentric contour-line wrinkles, a fingerprint', review 9; the original's run level round the ankle's front)
    float aph = (Vh - 0.074) * wkl + 1.6 * (wqn * 2.0 - 1.0) + 0.6 * (wqf * 2.0 - 1.0) + 0.4 * sin(rest.x * 211.0 + rest.z * 157.0);
    float wv = 0.5 + 0.5 * sin(aph - 1.5707963);
    float wamp = 0.35 + 0.65 * frac(sin(floor(aph / SH_TAU) * 12.9898 + 4.1) * 43758.5453);    // (changes where wv = 0)
    float wseg = sh_smooth(0.22, 0.48, sh_noise(float3(U * 30.0, floor(aph / SH_TAU) * 3.7, 1.3), 1.0, 1, 0.5));
    float wave = (1.0 - pow(1.0 - wv, 3.0)) * wamp * wseg;
    float fpw = max(length(fwidth(rest)), 1e-6);
    float wband = saturate((0.0021 / fpw - 2.0) / 2.0);
    float front = sh_smooth(0.3, -0.7, cos(U * SH_TAU));                 // (U = 0.5 on the shin and on the instep: the front)
    // (short creases in patches at the front of the ankle - evenly spaced wavy lines across the shin read as a pattern)
    float wpatch = sh_smooth(0.25, 0.50, sh_noise(rest + 4.7, 38.0, 1, 0.5));
    // (creases are slack fabric: where a pull draws it taut, or lifts it off the leg, they are pulled flat - drawn in the
    //  fabric's own coordinates they rode out onto every ankle sail as ruled contour lines, free-play sweep 2026-11-17)
    // (where a sail leaves the leg - lifted only millimetres - its fabric is gathered: the creases stay; the original's
    //  ankle sail at 30.2 s has a fan of fine wrinkles at its base, ours none, review 3)
    float slackW = (1.0 - sh_smooth(0.010, 0.025, lift)) * sh_smooth(1.22, 1.05, tens.x);
    // (a narrower band, ~2.5 cm just above the ankle's bend: the original's few lines sit there, ours ran over 4.5 cm)
    float ankleW = sh_smooth(0.058, 0.066, Vh) * sh_smooth(0.090, 0.080, Vh) * (0.15 + 0.85 * front) * (0.35 + 0.65 * wpatch) * (1.0 - footMask * 0.5) * slackW;
    // (deeper and darker: review 8 - the original's ankle front shows distinct dark horizontal wrinkles through VIEW 02, ours
    //  faint hairlines once the creases were broken up)
    // INSPECTOR, Tension Mode (0 Both, 1 Stretch, 2 Compression): which strain draws creases - the fan of lines along a pull
    // (stretch) and the buckled folds where the knit is pushed together, the ankle's bend among them (compression). Wrinkle
    // Strength scales all of them (9 = as calibrated).
    float tmStretch = _TensionMode > 1.5 ? 0.0 : 1.0, tmComp = _TensionMode > 0.5 && _TensionMode < 1.5 ? 0.0 : 1.0;
    float wrK = max(_WrinkleStrength, 0.0) / 9.0;
    Nn = sh_bump(Nn, posWS, wave, 0.00040, ankleW * wband * wrK * tmComp);
    alpha = lerp(alpha, min(alpha + 0.13, 1.0), ankleW * wband * (wamp - wave) * (1.0 - inHole) * tmComp * saturate(wrK));
    // the knee pit: the knit bunches in soft horizontal folds where the knee bends (the original's orbit views show
    // ~10 behind the knee, ours none - review round 7). Same crease profile, at the back of the knee
    // (the stocking's surface itself stands out in these folds, SheerClothVertex: same profile, so light and outline agree)
    float kneeW; float kneeC = SheerKneeCrease(rest, U, kneeW);
    float kband = saturate((0.0036 / fpw - 2.0) / 2.0);
    Nn = sh_bump(Nn, posWS, kneeC, 0.0003, kneeW * kband * 0.7 * slackW);
    // rucks: pushed together beyond its natural (unworn) size the knit buckles into fine folds that run along the
    // largest stretch. The knit is pre-stretched ~2x around and ~1.3x along the leg, so it takes more squeezing around.
    float ruckAt = 0.625 + 0.125 * tens.z;
    float ruck = sh_smooth(ruckAt + 0.08, ruckAt - 0.25, tens.y);
    // (irregular: the folds wander, merge and die out - their phase is warped at the scale of the folds themselves and
    //  whole patches stay smooth; a constant pitch drew an engraved hatch round every pinch, review round 3)
    // (softer and fewer than they were: review round 5 counted 30 - 40 sharp strokes fanning from the knee pinch where
    //  the original shows a soft dimple with a few ripples, and a crisp crumple under the hem at 3.8 s)
    // (each fold a short streak of its own - noise drawn out five times along the fold: a sine with a warped phase drew
    //  evenly spaced contour lines, 'wood grain', wherever a wide zone was gently pushed together)
    float su = U * SH_TAU * 0.055;                                      // arc length around a mean leg (m)
    float wH = max(tens.z, 0.0), wV = max(-tens.z, 0.0), wD1 = max(tens.w, 0.0), wD2 = max(-tens.w, 0.0);
    float hr = 0.5;
    [branch] if (ruck > 0.002)
    {
        const float RKN = 300.0;                                        // folds ~3 mm apart, ~15 mm long
        float da = (su - Vz) * 0.7071, db = (su + Vz) * 0.7071;
        float hH = sh_noise(float3(su * 0.2, Vz, 1.7), RKN, 1, 0.5), hV = sh_noise(float3(su, Vz * 0.2, 5.1), RKN, 1, 0.5);
        float hD1 = sh_noise(float3(da, db * 0.2, 9.3), RKN, 1, 0.5), hD2 = sh_noise(float3(da * 0.2, db, 3.9), RKN, 1, 0.5);
        hr = (hH * wH + hV * wV + hD1 * wD1 + hD2 * wD2) / max(wH + wV + wD1 + wD2, 1e-3);
        hr = 1.0 - abs(2.0 * hr - 1.0);                                 // crests
        hr = hr * hr * (3.0 - 2.0 * hr);
    }
    float rpatch = sh_smooth(0.38, 0.62, sh_noise(rest + 6.1, 90.0, 1, 0.5));
    float rband = saturate((0.0058 / fpw - 2.0) / 2.0);
    // (and faint inside the dark pile of gathered fabric: its regular waves read as wood grain there)
    float ruckW = ruck * rpatch * rband * (1.0 - 0.85 * sh_smooth(0.012, 0.03, lift)) * (1.0 - 0.6 * gather);   // (a sail is taut: no buckling folds - but its base is gathered, review 3)
    ruckW *= tmComp;
    Nn = sh_bump(Nn, posWS, hr, 0.00018, ruckW * wrK);
    Nn = sh_bump(Nn, posWS, lip * lip, 0.00022, lip * 0.5);           // the lip is a little roll standing off the leg
    // ---- traction lines. Fabric held taut between the hand and wherever it is anchored wrinkles ALONG the pull: fine
    // sharp crests that fan out from the pinch over many centimetres, branching as they spread so that they stay 1.5 - 3
    // mm apart (the original's knee pinch at 0.5 s: a fan of thin bright lines from the pinch to the leg's outline). The
    // lattice cannot buckle that finely, so they are drawn: where the simulated fabric is drawn out one way (tens.x)
    // without being drawn out the other, along the lines through the pinch (_SheerPinchL / R: grab point in rest
    // coordinates, circumference there, strength).
    float4 pin = uv2.x > 0.0 ? _SheerPinchL : _SheerPinchR;
    float tdu = U - pin.x; tdu -= floor(tdu + 0.5);
    float2 trv = float2(tdu * max(pin.z, 0.1), Vz - pin.y);
    float trr = max(length(trv), 0.002);
    // (the lines wander: their direction drifts with the distance from the pinch - no ruled sunburst)
    // (review round 8: in the close-up they read as dead-straight 1-px scratches - wider, softer crests that wander more)
    float tth = atan2(trv.y, trv.x) + (sh_noise(rest + 12.9, 16.0, 1, 0.5) - 0.5) * 0.9 * sh_smooth(0.01, 0.08, trr);
    float tlg = log2(max(SH_TAU * trr / 0.0034, 16.0)), tl0 = floor(tlg), tlf = tlg - tl0;
    float tnA = exp2(tl0), tpA = tth / SH_TAU * tnA, tpB = tpA * 2.0;
    // every line has its own strength and its own length; most are faint, a few stand out
    float thA = sh_hash11(floor(tpA) + 17.0 * tl0), thB = sh_hash11(floor(tpB) + 17.0 * (tl0 + 1.0));
    float tgA = sh_hash11(floor(tpA) * 1.37 + 5.0 * tl0 + 0.7), tgB = sh_hash11(floor(tpB) * 1.37 + 5.0 * (tl0 + 1.0) + 0.7);
    // (review round 5: 30 - 40 hairlines reaching half way up the thigh, dashed where aliased - the original's are a few
    //  soft creases near the pinch: fewer (a fifth of the slots), wider crests, 2 - 8 cm long)
    // (about half of the slots: the original's knee pinch shows fifteen to twenty fine lines fanning out behind the fingers,
    //  1.5 - 2 mm apart - at a fifth of the slots ours had three or four)
    // (longer, 3 - 11 cm: review 6 - the original's knee pinch fans dozens of fine wrinkles over the whole kneecap, ours a short
    //  knife-edge crease)
    // (review 9: 'long razor-thin scratch lines fanning across the leg, no relief' - the original's fan at the knee pinch lies
    //  within 3 - 5 cm of its pocket, soft crests read by light and shade: 2.5 - 6 cm, broader crests, no dark ink below)
    float trA = pow(0.5 + 0.5 * cos(SH_TAU * tpA), 0.9) * sh_smooth(0.42, 0.85, thA) * sh_smooth(0.025 + 0.035 * tgA, 0.008 + 0.017 * tgA, trr);
    float trB = pow(0.5 + 0.5 * cos(SH_TAU * tpB), 0.9) * sh_smooth(0.42, 0.85, thB) * sh_smooth(0.025 + 0.035 * tgB, 0.008 + 0.017 * tgB, trr);
    float tridge = lerp(trA, trB, tlf * tlf * (3.0 - 2.0 * tlf));
    // (is the fabric drawn out along this line? tens.zw = (cos 2a, sin 2a) of the largest stretch, a from 'around the leg')
    float talign = 0.5 + 0.5 * (tens.z * cos(2.0 * tth) + tens.w * sin(2.0 * tth));
    // (only where a crest is wider than ~3 picture pixels: finer ones only aliased into dashes)
    // (6 - 11 px: at 10 - 18 the original's 15 - 20 lines behind the knee pinch - 5 - 7 px apart at its size - never showed in
    //  ours at the normal distance; the pinch read as a smooth pink fold, independent reviews 2 / 3)
    float tband = sh_smooth(6.0, 11.0, SH_TAU * trr / tnA / max(fpw * pxF, 1e-7));
    float tw = sh_smooth(0.03, 0.18, tens.x - 1.0) * sh_smooth(1.10, 0.97, tens.y) * sh_smooth(0.35, 0.8, talign) * pin.w
             * sh_smooth(0.004, 0.012, trr) * (1.0 - inHole) * tband
             * sh_smooth(0.15, 0.45, abs(dot(N, V)));             // (toward the outline they caught the rim light as cyan streaks)
    // ... and BY THE PULL: a pinch dragged over the leg draws the fabric behind it - between where it is held and the fingers -
    // into a fan of fine wrinkles converging on the pinch (the original's knee at 0.1 - 0.7 s: dozens over the kneecap). The
    // solver's own stretch there is small (the fabric round the pinch goes along with it), so the fan is drawn from the pull
    // itself: behind the pinch, over a few centimetres, stronger the further it is drawn (independent reviews 6 / 7)
    float4 pdir = uv2.x > 0.0 ? _SheerPinchDirL : _SheerPinchDirR;
    float plen = length(pdir.xy);
    [branch] if (plen > 0.008 && pdir.z > 0.01)
    {
        float behind = saturate(-dot(trv / trr, pdir.xy / plen));
        float fanW = pin.w * pdir.z * sh_smooth(0.008, 0.035, plen) * behind * sqrt(behind)
                   * sh_smooth(0.004, 0.012, trr) * sh_smooth(0.055, 0.02, trr) * (1.0 - inHole) * tband * sh_smooth(0.15, 0.45, abs(dot(N, V)));
        tw = max(tw, 0.85 * fanW);
    }
    // (none on a sail standing off the leg: its radial lines read as brushed metal, review 8 - the original's sails are smooth
    //  and matte; the fan of wrinkles belongs to fabric lying on the leg)
    tw *= 1.0 - 0.85 * sh_smooth(0.01, 0.04, lift);
    tw *= tmStretch * wrK;
    Nn = sh_bump(Nn, posWS, tridge, 0.00040, tw * 0.9);           // (round 10: still a dashed line across the shin at 33.6 s; x1.5 - the fan read smooth, reviews 2 / 3; broader relief, review 5; deeper - the original's knee fan is crisp creases with lit crests, review 7)
    // ... and each is a fold - fabric lying double: a fine darker line where the fan is squeezed across its pull (what the
    // squeeze adds to the fabric's density sits in these lines, not spread over the fan as a flat tone)
    // (a knit drawn out one way narrows the other way - held by the fabric round it, it gathers into these lines: by the
    //  stretch along the pull)
    // (also in a pocket lifted a few millimetres - an on-leg pinch now stands up, and its fan of fine lines is exactly what
    //  the original's knee shows; cut by 'lifted' they vanished with it, reviews 2 / 3. Gone only in a sail standing clear)
    // (x 0.5 - review 5: a starburst of thin dark scratches; the original's tension folds are broad and read by their light
    //  and shade, the relief above, more than by their density)
    alpha = lerp(alpha, max(alpha, 0.85), 0.15 * tridge * tw * sh_smooth(0.08, 0.35, tens.x - 1.0) * (1.0 - sh_smooth(0.015, 0.035, lift)));   // (0.5: thin dark scratches, review 9)
    Nn = sh_bump(Nn, posWS, seamRidge * seamRidge * (3.0 - 2.0 * seamRidge), 0.00025, 0.75 * footMask);
    Nn = sh_bump(Nn, posWS, pat.rib, 0.0003, pat.ribW * (pat.replace > 0.5 ? cordKeep : 1.0 - inHole));     // welt ribs, seam, fishnet cords

    // ---- yarn BSDF parameters (Principled -> StackLit, specular-colour parametrisation)
    float rimdark = 1.0 - max(rim * 0.2, lip * 0.08) * _FrostBoundaryStrength;
    // (the foot's paler haze clears like the leg's where the fabric is lifted or drawn taut: kept, a sail pulled off the
    //  foot or the ankle was a pale sheet - plastic, not nylon; the original's ankle sails are dark veils like any other)
    float3 yarnCol = lerp(lerp(_FrostColor.rgb, FOOT_YARN, footMask), _YarnColor.rgb * lerp(1.0, 1.6, footMask), frostClear) * rimdark;
    // (a pile of gathered fabric is yarn on yarn, each layer in the shade of the next: darker - on the foot, whose yarn is
    //  paler, gathered fabric had come out LIGHTER than the stocking round it, a whitish blob)
    // (review 5: an ankle pull's gathered fabric over the instep - 0.42 on the foot - drew dark crumpled blotches across the top
    //  of the foot; the original's instep stays smooth, fine wrinkles at the ankle only)
    yarnCol *= lerp(1.0, lerp(0.86, 0.66, footMask), gather);
    // reinforced toe: dense (coverage above) but dark like the original's (94,80,84), not milky
    // (round 13: the original's toe is only a little darker than its instep - L 116 vs 123 - and violet-grey (125,108,113);
    //  ours was a much darker taupe, 88 vs 115: an opaque clay cap)
    // (lifted or drawn taut, the toe's yarn darkens like the rest: a tent pinched off the toes was a pale tongue)
    yarnCol = lerp(yarnCol, float3(0.098, 0.079, 0.087) * lerp(1.0, 0.4, frostClear), toeBox);     // (darker - review 6 saw no reinforced toe, review 8 one lighter than the forefoot)    // (the original's toes (125,108,113): R-B +12; ours went blue-grey)
    yarnCol *= lerp(1.0, 0.8, toeLow);
    yarnCol *= lerp(1.0, 0.84, seamLine * footMask) * lerp(1.0, 0.93, seamSide * footMask);   // (0.72: with the ledge above the toes a deep groove, review 13)
    // (threads of loosened gauze - ladders, round holes - catch the skin's warm light; drawn in the yarn's cool dark they read
    //  grey-green, R/G 1.18 vs 1.27 around them; the original's are warmer than their surroundings - review round 11)
    yarnCol *= lerp(float3(1.0, 1.0, 1.0), float3(1.04, 1.0, 0.99), saturate(vis) * 0.8);     // (1.45 / 0.85: a red band, review 9; 1.12: still 1.7 x the original's saturation, review 13)
    // (the loose threads of a ladder are single filaments lit from every side - paler than the knit they came from: the
    //  original's band is a pale grey-pink gauze, (178,147,141) at 12 s; ours stayed a dark salmon at the knit's own tone)
    yarnCol *= lerp(1.0, 1.45, saturate(ladO) * liftKg);   // (1.9: bands L 0.61 vs the original's 0.54, review 13)
    // the player's colours (SheerLook.hlsl): the yarn's own (a multiplier of the calibrated black, so its haze, foot and
    // toe keep their relations), the pattern's, the welt's; seams and heels are denser and darker
    float3 tintY = _SheerTint.a > 0.5 ? _SheerTint.rgb : float3(1.0, 1.0, 1.0);
    float3 yarnBase = yarnCol;
    yarnCol *= tintY;
    float3 patC = _SheerPatCol.a > 0.5 ? _SheerPatCol.rgb : yarnCol;
    yarnCol = lerp(yarnCol, patC * lerp(0.92, 1.08, frostClear), pat.mix);
    if (_SheerBandCol.a > 0.5) yarnCol = lerp(yarnCol, _SheerBandCol.rgb * lerp(0.92, 1.08, frostClear), pat.welt);
    yarnCol *= 1.0 - 0.45 * pat.dark;
    float gloss = _SheerTint.a > 0.5 ? _SheerTint2.y : 0.0;
    float rough = 0.85 + (0.5 - 0.85) * _FrostMatteSmoothness;
    // taut, haze-free nylon on the leg: satin. (Not a sail standing off it: at 0.42 it mirrored the blue backdrop and the
    //  rim light - 'clear glossy plastic film, bright specular streaks', review 10; the original's sails are smoky and matte)
    rough = lerp(rough, 0.42, frostClear * 0.7 * (1.0 - 0.85 * lifted));
    rough = lerp(rough, 0.23, gloss);                                // (shiny nylon / lycra: a broad bright sheen - at 0.17 it read as latex)
    float f0 = 0.0439 * 2.0 * (0.074 + 0.111 * _PearlSpecularStrength) * (1.0 + 1.7 * gloss);   // IOR 1.53 x 'Specular IOR Level' (x0.74: no central ridge)
    // pearl edge: the fibres' sheen (Principled sheen in the Cycles version) -> a real Charlie sheen lobe, rendered by the
    // additive Fabric pass (it is what lights the silhouette when a light is behind the legs); the edge profile weights
    // it towards grazing views
    float est = _PearlEdgeStart;
    float edge = pow(max(((1.0 - ndv) - est) / max(1e-3, 1.0 - est), 0.0), max(_PearlEdgeWidthPower, 1e-3));
    float sheenW = (0.5 + edge * 0.5 / 0.7) * _PearlEdgeStrength * _PearlStrength / 0.387;
    float3 sheenCol = _SheenGain * sheenW * float3(0.95, 0.9, 0.92);
    // INSPECTOR, the pearl edge (Pearl Strength, Edge Strength, Edge Start, Edge Width Power) and Pearl Pull Edge Width.
    // The fibres' sheen toward the outlines is drawn in this pass as a soft pale rim in the base colour, RELATIVE to the
    // calibrated look: the separate sheen pass is off (the original's outlines are dark), so at the calibrated values the
    // picture is unchanged, and each slider moved up brightens the outlines, moved down darkens them. Pull Edge Width: the
    // same along the outline of fabric pulled off the leg (a sail's edge), in a band of view angle that widens with it.
    float edge0 = pow(max(1.0 - ndv, 0.0), 0.54);
    float pearlD = (0.5 + edge * 0.5 / 0.7) * _PearlEdgeStrength * _PearlStrength - (0.5 + edge0 * 0.5 / 0.7) * 0.128 * 0.387;
    float pew = clamp(_PearlPullEdgeWidth / 0.0122, 0.05, 4.0);
    // (the band's reach in view angle: 0.2 at the calibrated width, most of an obliquely seen sail at the widest - drawn as a
    //  rim only, the sails of the audit frames face the camera and the control showed nothing, 2026-11-18)
    float pullD = (sh_smooth(min(0.2 * pew, 0.95), 0.0, ndv) - sh_smooth(0.20, 0.0, ndv)) * lifted;
    float3 pearlRim = float3(0.95, 0.9, 0.92) * (0.11 * pearlD * edge0 + 0.08 * pullD);
    // lit threads (rungs, strands, pulled loops) catch more light
    // lit threads: the floats of an open ladder and the threads strung across a hole catch more light
    // (the rungs of a ladder are glossy floats: the original's run below a hole is a grain of short BRIGHT rungs)
    float litMix = max(saturate(Lc * 0.40) * open * 0.08, threadA * 0.15);
    float3 col = lerp(yarnCol, float3(0.07, 0.065, 0.07) * tintY, litMix) * SheerSkirtShade(Vh);
    // (... and lit: the rungs read as pale lines over the skin, warm like the key light, not as dark dashes)
    // (warm and pale: the yarn's cool dark tint read grey-teal on the warm pale band, review rounds 6 / 7)
    // (not where the fabric is lifted off the leg: the paleness is the skin seen through the gauze - over the backdrop
    //  the rungs of a ladder run onto a sail drew bright smeared streaks, review round 8)
    float liftK = sh_smooth(0.004, 0.0015, lift);
    // (a neutral pale grey: the warm pink drew the rungs as faint red lines, independent review 2026-11-17)
    // (review 4: at 4 x the brightest rungs still read as grey-green rows on the pink band; the original's ladder threads
    //  are DARKER than the gaps between them - 137/109/105 vs 185/154/150 at 12 s - and warm: a little, warm)
    col = lerp(col, float3(0.26, 0.20, 0.19) * SheerSkirtShade(Vh), saturate(Lc * 0.30 - 0.15) * ladO * vis * 0.25 * liftK);
    // a pale rim of loosened, lit yarn just outside every hole's edge line: the original's - measured at 12 s - is one dark
    // thread line ~2 px out, then a rim ~8 levels paler for 1 - 3 mm, then the fabric; ours only darkened outward (review 5:
    // 'a thin dark outline that looks drawn on')
    float paleRim = sh_smooth(0.0005, 0.0012, holeSD) * sh_smooth(0.0042, 0.0018, holeSD) * (1.0 - inHole);
    col *= 1.0 + 0.07 * paleRim;           // (0.16 + the lit lip: a smooth salmon halo round every hole, 'inflamed', review 8)
    // (the rolled lip itself is yarn bunched and lit - a mid-tone cord, paler than the knit's dark, not a drawn black line)
    col *= 1.0 + 0.12 * lip * (1.0 - 0.5 * cordL);
    float roughL = lerp(rough, 0.42, litMix);
    float f0L = lerp(f0, 0.0439 * 1.6, litMix);
    float aniso = lerp(0.4, 0.8, litMix);

    // ---- glints: single fibres flashing in the key light. A fibre is a cylinder: it mirrors a light whenever its axis
    // is square to the half vector, whichever way the fabric itself faces - so the sparkles sit on the surface at
    // random and crowd toward the outlines, where the fabric is seen edge-on (measured on the original: 85 % of them in
    // the outer fifths of the leg's width; ours had them in the middle only, as the flakes took the surface's normal).
    float vd; float3 vc, vo;
    float3 pv = float3(rest.x, rest.y * 0.7, rest.z) * (_PearlGrainScale * 2.0);
    sh_voronoiR(pv, vd, vc, vo);
    float grazing = 1.0 - ndv;
    // (review round 6: a dotted line of specks along the outline - 5 x the inside density, the original's ~1 x - and hard
    //  white peaks: fewer at grazing, a few more inside, half as bright)
    // (round 7 then counted too few near the outline - 4 - 5 vs 11 - 22 per 10 kpx: in between)
    // (round 8: 0.7 - 2.4 per 10 kpx vs the original's 1.6 - 8.7, and its reinforced toe is full of them: more inside,
    //  twice on the foot)
    // (round 11: still ~10 x fewer than the original's 15 - 24 per 10 kpx, and 4 - 5 px across vs ~1.5: 4 x more inside,
    //  and finer)
    // (the grazing crowd belongs to the leg's outline, not to the crease of a fold lifted off the leg: there it drew a
    //  dotted teal line under the rim light, review round 13 at 2.7 - 3.9 s)
    float gGraze = 1.0 - 0.9 * sh_smooth(0.0015, 0.005, lift);
    // (review 6: at 1:1 the original's leg is full of fine light specks, ours nearly smooth - 2 x on the leg; the foot had
    //  3 x the original's specks already: its extra share down from x3 to x1.5)
    float gsel = vc.x < _PearlGlintDensity * (_SheerGlintN > 0.0 ? _SheerGlintN : 1.8) * (0.18 + (0.40 * grazing * grazing * grazing + 0.05 * grazing * grazing) * gGraze) * (1.0 + 0.5 * footMask) * (1.0 - saturate(ruckW * 1.5)) * (1.0 - 0.8 * gather) ? 1.0 : 0.0;   // (round 12: 8 x fewer; cyan specks in a gathered fold; review 9: the pinch a 'glittery slot' - few in gathered fabric)
    // every glint has its own size and its own direction of elongation (a short piece of fibre)
    float3 gax = normalize(sh_hash33(vc * 91.7 + 3.1) - 0.5);
    float gpar = dot(vo, gax);
    float gd = sqrt(max(vd * vd - 0.72 * gpar * gpar, 0.0));
    // INSPECTOR, Pearl Randomness: how unlike each other the glints are - their sizes and brightness (0 = all alike,
    // 0.435 = as calibrated, 1 = extremes)
    float prk = max(_PearlRandomness, 0.0) / 0.435;
    vc.y = saturate(0.6 + (vc.y - 0.6) * prk); vc.z = saturate(0.6 + (vc.z - 0.6) * prk);
    float gsz = 0.55 + 1.05 * vc.z * vc.z;
    float r1 = 0.20 * gsz, r0 = 0.09 * gsz;
    // On screen a glint is never smaller than about one pixel, however the fabric is foreshortened (toward the
    // outlines a patch of fabric is a sliver: sized on the surface, the glints there vanished): distance to the
    // glint's centre in PIXELS, from the screen-space derivatives of the cell coordinate.
    float3 dpx = ddx(pv), dpy = ddy(pv);
    float ja = dot(dpx, dpx), jb = dot(dpx, dpy), jc = dot(dpy, dpy), jdet = max(ja * jc - jb * jb, 1e-12);
    float jx = dot(dpx, vo), jy = dot(dpy, vo);
    float dpix = length(float2(jc * jx - jb * jy, ja * jy - jb * jx)) / jdet;
    // (radii in pixels of the final picture: _SheerPixelScale = rendered pixels per picture pixel, supersampling)
    // (x0.7 in size, x1.8 in number: 'sparse, coarse glitter dots' vs the original's fine dust of specks, review 10)
    float pxs = max(_SheerPixelScale, 1.0) * lerp(0.7, 1.5, vc.z) * (_SheerGlintSz > 0.0 ? _SheerGlintSz : 0.7);
    float gspot = max(sh_smooth(r1, r0, gd), sh_smooth(1.0 * pxs, 0.35 * pxs, dpix) * lerp(0.55, 1.0, vc.y));
    float gmask = saturate(gsel * gspot * (1.0 - inHole) * saturate(_PearlGlintStrength) * (0.2 + 0.8 * vc.y) * (0.45 + 0.55 * grazing));
    // (INSPECTOR, Pearl Glint Strength: up to 1 the glints fade in, from 1 to 2 they brighten to a mirror flash)
    float glintF0 = lerp(0.5, 1.0, saturate(_PearlGlintStrength - 1.0));
    // (a glint is the key light caught by a fibre: none on fabric facing down, away from every light - under a lifted toe
    //  they sparkled like stars on black, independent review 2026-11-17 at 31.8 - 32.4 s)
    gmask *= sh_smooth(-0.45, -0.05, N.y);
    // the flake's normal: the half vector between the key light and the eye (+ a little scatter)
    float3 gn = normalize(Lk + V + (vc - 0.5) * 0.16);

    // The yarn also takes its share of the light on its way IN to whatever lies behind it (double pass). That shadow is
    // carried by the stocking's own opacity instead of being painted on the skin, so it stays with the fabric wherever
    // the hand pulls it (tents in front of the leg, holes that ride along). The yarn's own light is kept unchanged:
    // what it adds to the picture is colour x fibre coverage, so the colour is scaled by coverage / opacity.
    float aFibre = saturate(alpha);
    // Lifted off the skin, the nylon hides what is behind it (_LiftOpaque): in the original the leg does not show through
    // a tent, only its back-lit rim does.
    // (that shadow belongs to fabric lying on what it covers; a sheet standing off the leg lets the backdrop through
    //  by its own openness, _LiftShadow of the shadow is kept for whatever is close behind it)
    // (a fold a few millimetres off the leg - the neck of a pinch - still shades the skin right behind it: without its
    //  shadow it showed the skin 2.8 x brighter, a pale wedge down the middle of every pinch; the shadow goes only when
    //  the fabric stands centimetres off the leg)
    float liftFar = sh_smooth(0.012, 0.045, lift);
    // (a pale yarn scatters the light it stops on toward the skin: it shadows less than black nylon - SheerStudio)
    float shadowK = _SheerTint.a > 0.5 ? _SheerTint2.x : 1.0;
    float aOut = 1.0 - (1.0 - aFibre) * (1.0 - _NylonShadow * shadowK * saturate(cov) * lerp(1.0, _LiftShadow, liftFar));
    float kcol = aFibre / max(aOut, 1e-4);

    SheerSurface s;
    // The band of nylon seen edge-on beyond the skin's outline (a shell ~1 mm off the skin: every ray that still hits
    // the skin crosses it at |N.V| > ~0.2) is a dark line in the original, also where the rim light is: the yarn there
    // returns little light (no grazing sheen / specular, dim diffuse).
    float shellEdge = sh_smooth(0.10, 0.26, ndv);
    // (lifted at the very edge: a 1 - 2 px near-black contour, L 12 vs the original's soft band at 32, review round 11)
    s.baseColor = max(lerp(col, 0.0, gmask) * kcol * lerp(1.3, 1.0, shellEdge) + pearlRim * kcol * (1.0 - inHole), 0.0);
    // the white floor lights the fabric facing down at it (the underside of a lifted toe, the sole's edge): the sky's lower
    // half is a third of its upper and nothing stood in for the bright cloth under the feet - the underside of a lifted
    // toe read as a black void (review 2026-11-17). Near the floor only, as far as it faces down.
    // (... but not where it rests ON the floor: there the floor and the foot shade each other - the original's foot has a
    //  dark line where it meets the rug; ours had none and floated, independent reviews 4 - 6)
    // (where it rests on the cloth, the toes' undersides and the crease where they meet it see only the shaded cloth under
    //  the foot: the original's toes end in a band of ~50 where they are ~118 - in linear light 85 % gone within 5 mm of the
    //  floor; ours stayed 70 - 85, the bottom row of toes read as lumps of grey clay floating on the rug, review 9. Facing
    //  down it is darker still; the floor's bounce, above, lights only what stands clear of it.)
    float yWc = posWS.y + _WorldSpaceCameraPos.y;
    float floorProx = sh_smooth(0.011, 0.0012, yWc) * footMask;
    float contactOcc = floorProx * lerp(0.45, 0.78, saturate(0.2 - 1.5 * N.y));   // (0.62 - 0.92: near-black undersides, 'rubber', review 13)
    s.baseColor *= (1.0 + 1.6 * sh_smooth(0.0, -0.7, N.y) * sh_smooth(0.06, 0.0, rest.y) * (1.0 - floorProx)) * (1.0 - contactOcc);
    // (the fine folds of gathered fabric must not catch the back light as a hatch of teal lines)
    // (a taut crest catches the light: the traction lines are thin bright threads of sheen)
    float crest = tridge * tw;
    // (the rungs of a ladder mirrored the blue backdrop: teal lines on the warm band - less specular there)
    // (and the whole band less: a fold across a stretched ladder caught the rim light as a smeared cyan streak, round 8/9)
    // (review 4: still red / green stripes at 4 x - the rungs mirrored the blue backdrop line by line: most of it off)
    float rungSpec = 1.0 - ladO * (0.72 + 0.20 * saturate(Lc * 0.36)) * lerp(1.08, 1.0, sh_smooth(0.004, 0.0015, lift));
    // (0.4 -> 0.6 at the very edge: the original's outline keeps a thin sheen of the surroundings, ours went to ink black
    //  where no light reached it - 0-1 / 255 in the orbits, review round 9)
    // (a fold of lifted fabric seen edge-on caught the rim light as a straight 1 - 2 px teal line, review round 13 at 3.6 s)
    float foldEdge = sh_smooth(0.003, 0.010, lift) * (1.0 - sh_smooth(0.10, 0.35, ndv));
    s.specularColor = lerp(f0L.xxx * lerp(0.8, 1.0, shellEdge) * (1.0 - 0.75 * ruckW) * (1.0 + 0.6 * crest) * rungSpec * (1.0 + 0.55 * footMask) * (1.0 - 0.5 * foldEdge), glintF0.xxx, gmask) * kcol;   // (the foot has a sheen, not clay - round 10; x1.55 - 'clay', reviews 4 - 7)
    s.smoothness = 1.0 - lerp(roughL, 0.08, gmask);
    s.anisotropy = lerp(aniso, 0.0, gmask);
    s.normalWS = normalize(lerp(Nn, gn, gmask));
    s.tangentWS = T;
    s.alpha = aOut;
    s.covRest = covWorn;
    s.glint = gmask;
    s.sheen = sheenCol * (1.0 - litMix * 0.5) * kcol * shellEdge * rungSpec;
    // UNDER the skirt (rest height above its hem): seen only when the hand lifts the hem, and there in the skirt's shade -
    // lit by the rim light it was a flat, hard-edged cyan panel above the hem at 19 s (review rounds 12 / 14); the
    // original's thigh under its lifted hem is dark
    float underSkirt = sh_smooth(0.698, 0.722, Vh + _SheerHemDrop);
    s.specularColor *= 1.0 - 0.92 * underSkirt; s.sheen *= 1.0 - 0.92 * underSkirt; s.baseColor *= 1.0 - 0.6 * underSkirt;
    // ... and lit less: the clefts between the toes, the knee pit, where the thighs meet (independent review 4: the original's
    // toes stand apart by their dark clefts, ours read as flat clay - a tonal spread of 11 over the toes vs 22 - 28)
    float aoK = 1.0 - cavW;
    s.baseColor *= aoK; s.specularColor *= lerp(1.0, aoK, 0.8); s.sheen *= aoK;
    s.specularColor *= 1.0 - contactOcc; s.sheen *= 1.0 - contactOcc;      // (the contact with the floor, above)
    // THE RUG'S PILE IN FRONT OF THE FOOT: the original's toes stand IN a shaggy white rug - its tufts hide the bottom few
    // millimetres of the foot along an uneven, fuzzy line, with the pile's own shade under it. Ours stood ON a flat cloth with
    // a hard edge - 'pasted on', 'a flat white haze with a hard edge underneath' (reviews 10 - 14). The floor is a flat
    // mesh, so the tufts standing in front of the foot are drawn on the foot: up to ~6.5 mm, each clump (~2.5 mm) its own
    // height, soft-topped and broken into upright strands at the top. Only on the default rug (the Studio's other floors
    // are boards, marble, ...).
    // (OFF by default - _SheerRugPile > 0 turns it on: tried 2026-11-18, a bright spiky white trim along the toes, not the
    //  original's soft dark contact; kept for experiments)
    [branch] if (_SheerRugPile > 0.0 && footMask > 0.01 && yWc < 0.009 && _SheerFloor.x < 0.5)
    {
        float3 pa = posWS + _WorldSpaceCameraPos;
        float tuft = sh_noise(float3(pa.x * 380.0, pa.z * 380.0, 2.7), 1.0, 2, 0.5);
        float strand = sh_noise(float3(pa.x * 1400.0 + pa.z * 900.0, pa.y * 120.0, 5.9), 1.0, 1, 0.5);
        float top = 0.0065 * lerp(0.35, 1.0, tuft) * lerp(0.75, 1.0, strand);
        float pile = sh_smooth(top + 0.0012, top - 0.0008, yWc) * footMask;
        pile *= lerp(1.0, saturate(strand * 1.6 - 0.2), sh_smooth(top - 0.003, top, yWc));       // (the tips: broken fuzz)
        float3 pileCol = float3(0.80, 0.80, 0.85) * lerp(0.45, 1.0, saturate(yWc / 0.006));      // (darker deep in the pile)
        s.baseColor = lerp(s.baseColor, pileCol, pile);
        s.specularColor *= 1.0 - pile; s.sheen *= 1.0 - pile; s.glint *= 1.0 - pile;
        s.alpha = lerp(s.alpha, 1.0, pile);
        s.normalWS = normalize(lerp(s.normalWS, float3(0.0, 1.0, 0.0), 0.5 * pile));
    }
    // GLITTER (SheerStudio): the glints in every colour, and many more of them
    float glit = _SheerTint.a > 0.5 ? _SheerTint2.z : 0.0;
    [branch] if (glit > 0.0)
    {
        float3 hue = saturate(abs(frac(vc.x * 7.31 + float3(0.0, 0.333, 0.667)) * 6.0 - 3.0) - 1.0);
        float gm2 = saturate(gspot * step(vc.x, 0.08 + 0.25 * glit) * (1.0 - inHole) * (0.3 + 0.7 * vc.y)) * glit;
        s.baseColor = lerp(s.baseColor, hue * 0.9, gm2 * 0.6); s.specularColor = lerp(s.specularColor, hue * 0.8, gm2);
        s.smoothness = lerp(s.smoothness, 0.93, gm2); s.alpha = max(s.alpha, gm2 * 0.9);
    }
    // nothing ABOVE the top of a thigh-high: bare skin there
    float keep = 1.0 - pat.cut;
    s.alpha *= keep; s.baseColor *= keep; s.specularColor *= keep; s.sheen *= keep; s.glint *= keep;
    if (_DebugTension > 5.5)
    {   // look-dev: the CLOTH LATTICE - the simulation's grid (every 8th node row / column) riding on the fabric as it
        // deforms, over the stretch colours (R stretch, G squeeze); the pinned rows (toe tip, top band) in lilac
        float2 lu = SheerClothUV(rest, uv2.x);
        float2 g = float2(lu.x / max(_SheerClothGrid.z, 1e-6), lu.y / max(_SheerClothGrid.w, 1e-6)) / 8.0;
        float2 gd = abs(frac(g + 0.5) - 0.5) / max(fwidth(g), 1e-6);
        float gridL = saturate(1.0 - min(gd.x, gd.y) * 0.8);
        float3 base = 0.12 + 0.6 * float3(saturate(tens.x - 1.0), saturate(1.0 - tens.y), lifted);
        float edgeRows = step(lu.y, 0.012) + step(0.988, lu.y);
        base = lerp(base, float3(0.55, 0.42, 0.8), saturate(edgeRows) * 0.6);
        s.baseColor = lerp(base, float3(1.0, 0.92, 0.97), gridL); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    else if (_DebugTension > 4.5)
    {   // look-dev: R = inside a hole (sharp), G = hole distance 0..4 mm, B = fringe
        s.baseColor = float3(saturate(0.5 - holeSD / 0.0003), saturate(holeSD / 0.004), saturate(fringe)); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    else if (_DebugTension > 3.5)
    {   // look-dev: fibre opacity, opacity with the yarn's shadow, single-thread visibility
        s.baseColor = float3(aFibre, aOut, vis); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    else if (_DebugTension > 2.5)
    {   // look-dev: ladder fields (lateral coordinate, top end, bottom end)
        s.baseColor = float3(saturate(abs(dB.z)), saturate(dC.x * 0.5), saturate(dC.y * 0.5)); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    else if (_DebugTension > 1.5)
    {   // look-dev: red = wale has run, green / blue = coverage of the wale / course threads
        s.baseColor = float3(open, cw, cc); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    else if (_DebugTension > 0.5)
    {   // look-dev: red = largest stretch - 1, green = 1 - smallest stretch (squeeze), blue = lifted
        s.baseColor = float3(saturate(tens.x - 1.0), saturate(1.0 - tens.y), lifted); s.specularColor = 0.0; s.alpha = 1.0; s.sheen = 0.0;
    }
    return s;
}

// Contact shadow under the skirt's hem (review round 5: the original's thigh right under the hem is at 0.3 - 0.5 of its
// level further down, ours at 0.8 - 0.9 - a rest-height band never sat under a hem that sways, leans and lifts).
// Screen space: walk up the picture from this fragment over 14 mm and look in the depth buffer (opaques: skirt, skin)
// for something more than 6 mm in front of the stocking - the hem hangs in front of the thigh. Above the knee only
// (the kneecap stands in front of the shin below it). Dithered sample offsets: the supersampling smooths the steps.
float SheerHemShade(float3 posWS, float3 nWS, float jitAmt = 1.0)
{
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
    float hY = posWS.y + _WorldSpaceCameraPos.y;
    if (hY < 0.55) return 1.0;
    nWS = dot(posWS, nWS) > 0.0 ? -nWS : nWS;                  // (facing the eye; posWS is camera-relative)
    // the walk: 40 mm up the picture; every probe also strays sideways by up to ~0.7 x its height (dithered per pixel):
    // the shadow's edge below a step of the hem is a soft penumbra that widens with distance (review round 7: straight
    // up, every step of the pleated hem cast a hard vertical shadow edge 45 - 190 px down the thigh)
    float3 upW = float3(0.0, 0.040, 0.0);
    float3 sideW = normalize(cross(float3(0.0, 1.0, 0.0), posWS)) * 0.040;   // horizontal, across the view
    float2 n0 = ComputeNormalizedDeviceCoordinates(posWS, UNITY_MATRIX_VP);
    float d0 = TransformWorldToHClip(posWS).w;
    float2 px = floor(n0 * _ScreenSize.xy);
    float jit = lerp(0.5, frac(52.9829189 * frac(dot(px, float2(0.06711056, 0.00583715)))), jitAmt);
    float jit2 = lerp(0.5, frac(52.9829189 * frac(dot(px + 17.0, float2(0.00583715, 0.06711056)))), jitAmt);
    float first = 2.0;
    [unroll] for (int k = 0; k < 9; k++)
    {
        float w = (k + jit) / 9.0;
        float sx = (frac(jit2 + k * 0.618034) - 0.5) * 1.4 * w;
        float3 Q = posWS + upW * w + sideW * sx;
        float2 nk = ComputeNormalizedDeviceCoordinates(Q, UNITY_MATRIX_VP);
        if (any(nk < 0.0) || any(nk > 1.0)) continue;
        float dk = LinearEyeDepth(SampleCameraDepth(nk), _ZBufferParams);
        // (not the leg itself: a probe that strays sideways toward the middle of the leg finds the leg's own nearer
        //  surface in front - the outlines went dark above 0.55 m, a hard horizontal line across both legs. Where the
        //  leg's own surface is along the probe's ray: the leg as a round column of 65 mm radius (the thigh's), this
        //  fragment at its angle round it - only what is further in front than that counts. (Its tangent plane was too
        //  strict a bound: the hem hangs only some millimetres in front of the thigh.) Sideways only - straight up, the
        //  walk never caught the leg)
        float3 nh = normalize(float3(nWS.x, 0.0, nWS.z) + 1e-5);
        float3 vh = normalize(float3(-posWS.x, 0.0, -posWS.z) + 1e-5);
        float sinT = dot(nh, normalize(sideW)), cosT = max(dot(nh, vh), 0.0);
        const float RL = 0.065;
        float xp = RL * sinT + sx * 0.040;
        float dT = abs(xp) < RL ? d0 + RL * cosT - sqrt(RL * RL - xp * xp) : 1e4;
        if (dk < min(d0, dT) - 0.006 && dk > d0 - 0.30) first = min(first, w);
    }
    // (the original at 0.5 s: dark for ~45 - 60 px under the hem, back by ~100 px - dark to ~6 mm, full by ~30 mm)
    return first > 1.5 ? 1.0 : 1.0 - 0.9 * (1.0 - smoothstep(0.12, 0.75, first)) * smoothstep(0.55, 0.58, hY);
#else
    return 1.0;
#endif
}

// The same contact shadow, smooth - for bare skin seen through a hole under the hem. Each probe ray walks up the picture
// (16 steps over 40 mm) and the hem's edge is then found by bisection between the last miss and the first hit (6 steps:
// to a fraction of a pixel). Seven rays, leaning sideways by up to 0.6 x their height, averaged: a penumbra that widens
// away from the hem. (Fixed probes drew hard stair-stepped bands, round 12; the hit height interpolated from the depth
// margins did not help - the depth jumps at the hem, every guess landed at the same fraction: 2 mm contour bands, 10 - 17
// levels each, round 13; dithered probes drew a diagonal mesh, round 10)
bool SheerHemOcc(float3 posWS, float w, float slope, float3 sideU, float d0, float sinT, float cosT)
{
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
    float sx = slope * w * 0.040;
    float2 nk = ComputeNormalizedDeviceCoordinates(posWS + float3(0.0, 0.040 * w, 0.0) + sideU * sx, UNITY_MATRIX_VP);
    if (any(nk < 0.0) || any(nk > 1.0)) return false;
    float dk = LinearEyeDepth(SampleCameraDepth(nk), _ZBufferParams);
    // (not the leg's own nearer surface toward its middle: the leg as a column of 65 mm radius - see SheerHemShade)
    const float RL = 0.065;
    float xp = RL * sinT + sx;
    float dT = abs(xp) < RL ? d0 + RL * cosT - sqrt(RL * RL - xp * xp) : 1e4;
    return dk < min(d0, dT) - 0.006 && dk > d0 - 0.30;
#else
    return false;
#endif
}

float SheerHemShadeSmooth(float3 posWS, float3 nWS)
{
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
    float hY = posWS.y + _WorldSpaceCameraPos.y;
    if (hY < 0.55) return 1.0;
    nWS = dot(posWS, nWS) > 0.0 ? -nWS : nWS;
    float d0 = TransformWorldToHClip(posWS).w;
    float3 sideU = normalize(cross(float3(0.0, 1.0, 0.0), posWS));
    float3 nh = normalize(float3(nWS.x, 0.0, nWS.z) + 1e-5);
    float3 vh = normalize(float3(-posWS.x, 0.0, -posWS.z) + 1e-5);
    float sinT = dot(nh, sideU), cosT = max(dot(nh, vh), 0.0);
    float acc = 0.0;
    [loop] for (int r = 0; r < 7; r++)
    {
        float slope = (r - 3) * 0.2;
        float first = 2.0, wPrev = 0.0;
        [loop] for (int k = 1; k <= 16; k++)
        {
            float w = k / 16.0;
            if (SheerHemOcc(posWS, w, slope, sideU, d0, sinT, cosT))
            {
                float lo = wPrev, hi = w;
                [unroll] for (int bs = 0; bs < 6; bs++)
                {
                    float mid = 0.5 * (lo + hi);
                    if (SheerHemOcc(posWS, mid, slope, sideU, d0, sinT, cosT)) hi = mid; else lo = mid;
                }
                first = 0.5 * (lo + hi);
                break;
            }
            wPrev = w;
        }
        acc += first > 1.5 ? 1.0 : 1.0 - 0.9 * (1.0 - smoothstep(0.12, 0.75, first));
    }
    return lerp(1.0, acc / 7.0, smoothstep(0.55, 0.58, hY));
#else
    return 1.0;
#endif
}

// A fold of fabric lifted off the leg and seen edge-on IN FRONT OF THE LEG (the depth buffer - skin - lies within a few
// centimetres behind it): its sheen and specular caught the rim light as a straight 1 - 2 px teal line along the crease of
// the thigh pull's funnel, read as a see-through seam (review round 13, 2.7 - 3.9 s). A sail's outline against the
// backdrop keeps its sheen (the depth behind it is metres away).
float SheerFoldCrease(float3 posWS, float3 nWS, float lift)
{
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
    float ndv = abs(dot(nWS, normalize(-posWS)));
    float k = sh_smooth(0.0012, 0.005, lift) * (1.0 - sh_smooth(0.10, 0.40, ndv));
    if (k <= 0.0) return 0.0;
    float2 n0 = ComputeNormalizedDeviceCoordinates(posWS, UNITY_MATRIX_VP);
    float d0 = TransformWorldToHClip(posWS).w;
    float dB = LinearEyeDepth(SampleCameraDepth(n0), _ZBufferParams);
    return k * sh_smooth(0.10, 0.04, dB - d0);
#else
    return 0.0;
#endif
}

// Fabric of one leg lifted IN FRONT OF THE OTHER LEG (a sail drawn across it): the transparent depth prepass keeps only the
// nearest layer of stocking, so the other leg's stocking behind the sail was dropped and its bare skin showed through the
// sheer sail - a salmon patch (free-play orbit sweep 2026-11-17). 0..1 where the solid surface behind this fragment is the
// other leg's (across the body's midline, between the ankles and the hem / the stocking's top), 1.5 - 25 cm behind.
float SheerOtherLegBehind(float3 posWS, float side, float lift)
{
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
    float k = sh_smooth(0.002, 0.006, lift);
    if (k <= 0.0) return 0.0;
    float2 n0 = ComputeNormalizedDeviceCoordinates(posWS, UNITY_MATRIX_VP);
    float d0 = TransformWorldToHClip(posWS).w;
    float dB = LinearEyeDepth(SampleCameraDepth(n0), _ZBufferParams);
    float gap = dB - d0;
    k *= sh_smooth(0.006, 0.015, gap) * sh_smooth(0.40, 0.25, gap);
    if (k <= 0.0) return 0.0;
    float3 oB = TransformWorldToObject(posWS * (dB / max(d0, 1e-4)));      // (camera-relative: along the eye ray)
    float top = SheerHasBand() ? _SheerBand.x : 0.72;
    return k * sh_smooth(0.005, 0.02, -oB.x * side) * sh_smooth(0.10, 0.14, oB.y) * sh_smooth(top, top - 0.03, oB.y);
#else
    return 0.0;
#endif
}

// Shader Graph entry point (Custom Function node, File mode, precision float)
void SheerTights_float(float4 UV0, float4 UV1, float4 UV2, float4 UV3, float3 PositionWS, float3 NormalWS,
                       float3 TangentWS, float3 BitangentWS, float3 ViewDirWS, UnityTexture2D DamageTex,
                       UnityTexture2D DamageTexB, UnityTexture2D DamageTexC,
                       UnityTexture2D WeaveTex, UnityTexture2D TensTex, UnityTexture2D DispTex, UnitySamplerState Sampler,
                       out float3 BaseColor, out float3 SpecularColor, out float Smoothness, out float Anisotropy,
                       out float3 NormalOut, out float3 TangentOut, out float Alpha)
{
    float3 V = normalize(ViewDirWS);
    float viewDist = length(PositionWS);           // HDRP: Shader Graph 'World' positions are camera-relative
    float lift = SheerClothLift(UV1.xyz, UV2.x, DispTex.tex, DispTex.samplerstate);
    float4 tens = SheerClothTensionSeen(UV1.xyz, UV2.x, TensTex.tex, TensTex.samplerstate, lift);
    SheerSurface s = SheerEvaluate(UV0, UV1, UV2, UV3, PositionWS, normalize(NormalWS), normalize(TangentWS),
                                   normalize(BitangentWS), V, viewDist, DamageTex.tex, DamageTexB.tex, DamageTexC.tex, WeaveTex.tex,
                                   DamageTex.samplerstate, WeaveTex.samplerstate, tens, lift);
    // (the stocking takes the hem's shade and passes it on to the skin behind it through its opacity)
    // (not as a veil over the skin in a hole: its dithered probes drew a diagonal mesh on bare skin under the hem, round 10)
    float hs = SheerHemShade(PositionWS, normalize(NormalWS));
    // (over bare skin in a hole the veil comes back - without it the skin under the hem was 25 x brighter than the nylon
    //  beside it, review round 11 - but from fixed, undithered probes: dithered they drew a diagonal mesh, round 10)
    float hsV = hs;
    [branch] if (s.alpha < 0.25) hsV = lerp(SheerHemShadeSmooth(PositionWS, normalize(NormalWS)), hs, sh_smooth(0.02, 0.25, s.alpha));
    float a1 = 1.0 - (1.0 - s.alpha) * hsV, ks = hs * s.alpha / max(a1, 1e-4);
    s.specularColor *= 1.0 - 0.6 * SheerFoldCrease(PositionWS, normalize(NormalWS), lift);
    BaseColor = s.baseColor * ks; SpecularColor = s.specularColor * ks; Smoothness = s.smoothness; Anisotropy = s.anisotropy;
    NormalOut = s.normalWS; TangentOut = s.tangentWS; Alpha = a1;
    // the other leg's stocking behind a sail (see SheerOtherLegBehind): its layer composited back under this one - its worn
    // coverage seen at a typical angle, its yarn lit like this fabric; this layer's specular keeps its strength
    float ob = SheerOtherLegBehind(PositionWS, UV2.x, lift);
    [branch] if (ob > 0.0)
    {
        float a2 = (1.0 - pow(max(1.0 - saturate(s.covRest), 0.0), 1.0 / pow(0.7, _AngleFalloff))) * ob;
        float aT = 1.0 - (1.0 - a1) * (1.0 - a2), kT = 1.0 / max(aT, 1e-4);
        BaseColor = (BaseColor * a1 + s.baseColor * hs * a2 * (1.0 - a1)) * kT;
        SpecularColor *= a1 * kT;
        Alpha = aT;
    }
    if (_SheerDbgH > 0.5)
    {   // look-dev: R = world height above 0.55 m (x5), G = this fragment's eye depth / 2 m, B = depth buffer here / 2 m
        float2 n0 = ComputeNormalizedDeviceCoordinates(PositionWS, UNITY_MATRIX_VP);
        float dB = 0.0;
#if defined(SHADERPASS) && (SHADERPASS == SHADERPASS_FORWARD)
        dB = LinearEyeDepth(SampleCameraDepth(n0), _ZBufferParams) / 2.0;
#else
        dB = 1.0;
#endif
        BaseColor = float3(saturate((PositionWS.y + _WorldSpaceCameraPos.y - 0.55) * 5.0), TransformWorldToHClip(PositionWS).w / 2.0, dB) * (hs < 0.999 ? 0.3 : 1.0);
        SpecularColor = 0.0; Alpha = 1.0;
    }
}
// Additive fibre-sheen pass (HDRP Fabric cotton/wool graph "SheerTightsSheen"): black diffuse, sheen = the fibres'
// grazing lobe, weighted by the fibre coverage (alpha; nothing in the holes)
void SheerTightsSheen_float(float4 UV0, float4 UV1, float4 UV2, float4 UV3, float3 PositionWS, float3 NormalWS,
                            float3 TangentWS, float3 BitangentWS, float3 ViewDirWS, UnityTexture2D DamageTex,
                            UnityTexture2D DamageTexB, UnityTexture2D DamageTexC,
                            UnityTexture2D WeaveTex, UnityTexture2D TensTex, UnityTexture2D DispTex, UnitySamplerState Sampler,
                            out float3 BaseColor, out float3 SheenColor, out float Smoothness, out float3 NormalOut, out float Alpha)
{
    float3 V = normalize(ViewDirWS);
    float viewDist = length(PositionWS);
    float lift = SheerClothLift(UV1.xyz, UV2.x, DispTex.tex, DispTex.samplerstate);
    float4 tens = SheerClothTensionSeen(UV1.xyz, UV2.x, TensTex.tex, TensTex.samplerstate, lift);
    SheerSurface s = SheerEvaluate(UV0, UV1, UV2, UV3, PositionWS, normalize(NormalWS), normalize(TangentWS),
                                   normalize(BitangentWS), V, viewDist, DamageTex.tex, DamageTexB.tex, DamageTexC.tex, WeaveTex.tex,
                                   DamageTex.samplerstate, WeaveTex.samplerstate, tens, lift);
    BaseColor = 0.0; SheenColor = saturate(s.sheen) * SheerHemShade(PositionWS, normalize(NormalWS)) * (1.0 - 0.8 * SheerFoldCrease(PositionWS, normalize(NormalWS), lift));
    Smoothness = _SheerSheenSm > 0.0 ? _SheerSheenSm : 0.5; NormalOut = s.normalWS;
    Alpha = s.alpha * (1.0 - s.glint);
}
#endif
