// SHEER — skin, skirt and floor surfaces (ports of make_skin / make_skirt / make_floor in
// blender/sheer_materials.py). Procedural textures use the REST position (uv1.xyz, Unity axes) so they
// stay attached to the deforming skin and the moving skirt. Used from Custom Function nodes.
#ifndef SHEER_SURFACES_INCLUDED
#define SHEER_SURFACES_INCLUDED
#include "Assets/Sheer/Shaders/SheerNoise.hlsl"
#include "Assets/Sheer/Shaders/SheerLook.hlsl"
#ifndef SHEER_PIXSCALE_DECL
#define SHEER_PIXSCALE_DECL
float _SheerPixelScale;           // rendered pixels per pixel of the final picture (supersampling; 0 = unset = 1)
#endif

// ---- skirt: charcoal wool-blend suiting, coarse 2/2 twill (~1.2 mm), heather flecks, fuzzy sheen
void SheerSkirt_float(float2 UV, float3 Rest, float3 PositionWS, float3 NormalWS, out float3 BaseColor,
                      out float Smoothness, out float3 NormalOut, out float3 SheenColor)
{
    // Used by the HDRP Fabric (cotton/wool) graph: SheenColor -> 'Specular' (sheen tint), Smoothness -> sheen width.
    float3 bp = float3(Rest.x, Rest.z, Rest.y);
    const float s_th = 0.0012, CELL = 1.0 / 900.0;
    // metres per pixel of the FINAL picture: measured per rendered pixel, the 2 x 2 supersampled render resolved the
    // twill (3 - 4 px of the final frame) and the box filter turned it into crawling moire (review round 6: per-frame
    // change of the skirt 5.95 grey levels vs the original's 1.75)
    float fp = max(length(fwidth(Rest)), 1e-6) * max(_SheerPixelScale, 1.0);
    float tu = UV.x / s_th, tv = UV.y / s_th;
    float diag = 0.5 + 0.5 * sin((tu + tv) * 3.14159265);
    float warp = 0.5 + 0.5 * cos(tu * SH_TAU), weft = 0.5 + 0.5 * cos(tv * SH_TAU);
    float hw = diag * 0.55 + warp * weft * 0.45;
    hw = lerp(hw, 0.5125, saturate((fp / s_th - 0.12) / 0.14));     // twill (1.2 mm) -> its mean below ~8 px, gone at ~4
    float ht = hw * 0.75 + sh_noise(bp, 1400, 4, 0.5) * 0.4 * (1.0 - saturate((fp * 1400.0 - 0.08) / 0.12));
    float n1 = sh_noise(bp, 90, 8, 0.5);
    float fleck = sh_smooth(0.86, 0.97, sh_hash21(floor(bp.xy * 900.0) + floor(bp.z * 900.0) * 17.0));
    fleck = lerp(fleck, 0.085, saturate(fp / (0.5 * CELL)));        // light fibres (1.1 mm) average out with distance
    float heather = n1 * 0.5 + hw * 0.5;
    // cool charcoal (HDRP calibration vs the original's skirt: dark-60 % mean sRGB (24,24,27), median (30,30,33))
    // (a little bluer: the original's skirt measures (29,29,34) from the front AND turned 45 deg; ours (32,32,34) and, turned,
    //  a warm (48,43,44) - review 10's 'dusty brown-grey whenever the body turns')
    float3 base = lerp(float3(0.0098, 0.0108, 0.0160), float3(0.029, 0.032, 0.045), heather);
    BaseColor = lerp(base, float3(0.07, 0.074, 0.085), fleck * 0.2);   // (0.6 x brighter flecks read as video noise on the dark cloth)
    // ---- the player's skirt (SheerStudio): its colour, and the classics - sailor stripes at the hem (the original's),
    // a school tartan, pinstripes, gingham. The calibrated twill / heather stays: it modulates whatever colour is chosen.
    if (_SheerSkirtCol.a > 0.5 || _SheerSkirt.x > 0.5)
    {
        float3 var = BaseColor / float3(0.0215, 0.0228, 0.0285);       // the cloth's own variation round its mean
        float3 mainC = _SheerSkirtCol.a > 0.5 ? _SheerSkirtCol.rgb : float3(0.0215, 0.0228, 0.0285);
        float3 acc = _SheerSkirtAcc.a > 0.5 ? _SheerSkirtAcc.rgb : float3(0.80, 0.80, 0.82);
        float3 acc2 = _SheerSkirtAcc2.a > 0.5 ? _SheerSkirtAcc2.rgb : float3(0.02, 0.06, 0.035);
        float st = _SheerSkirt.x, ws = max(_SheerSkirt.y, 0.3);
        float3 c = mainC;
        float fpu = max(fwidth(UV.x), 1e-6), fpv = max(fwidth(UV.y), 1e-6);
        float hemH = UV.y - 0.665;                                      // m above the (unlengthened) hem
        if (st > 0.5 && st < 1.5)
        {   // sailor stripes: two white bands a little above the hem
            float b1 = saturate(min(hemH - 0.012, 0.022 * ws - hemH + 0.0) / fpv + 0.5);
            float b2 = saturate(min(hemH - (0.022 * ws + 0.007), (0.029 * ws + 0.007) - hemH) / fpv + 0.5);
            c = lerp(c, acc, saturate(max(b1, b2)));
        }
        else if (st > 1.5 && st < 2.5)
        {   // tartan: the same sett in warp and weft, woven 2/2 (where they differ the twill shows both)
            float per = 0.072 * ws;
            float tu = frac(UV.x / per), tv = frac(UV.y / per);
            #define SETT(t, fp) (lerp(mainC, acc2, saturate(min(t - 0.36, 0.66 - t) / (fp) + 0.5)))
            float aU = fpu / per, aV = fpv / per;
            float3 cu = SETT(tu, aU), cv = SETT(tv, aV);
            float lu = saturate(max(0.008 - abs(tu - 0.31), 0.008 - abs(tu - 0.71)) / aU + 0.5);
            float lv = saturate(max(0.008 - abs(tv - 0.31), 0.008 - abs(tv - 0.71)) / aV + 0.5);
            cu = lerp(cu, acc, lu); cv = lerp(cv, acc, lv);
            float tw = frac((floor(UV.x / 0.0012) + floor(UV.y / 0.0012)) * 0.25);
            float wsel = tw < 0.5 ? 1.0 : 0.0;
            float thr = saturate((fp / 0.0012 - 0.35) / 0.3);              // threads under ~3 px: their mean
            c = lerp(lerp(cv, cu, wsel), 0.5 * (cu + cv), thr);
            #undef SETT
        }
        else if (st > 2.5 && st < 3.5)
        {   // pinstripes down the pleats
            float pu = frac(UV.x / (0.009 * ws));
            float l = saturate((0.04 - abs(pu - 0.5)) / (fpu / (0.009 * ws)) + 0.5) * saturate((0.009 * ws / fpu - 2.5) / 2.0);
            c = lerp(c, acc, l * 0.85);
        }
        else if (st > 3.5 && st < 4.5)
        {   // gingham: checks where the coloured warp and weft cross are darkest
            float per = 0.012 * ws;
            float a = saturate((0.25 - abs(frac(UV.x / per) - 0.5)) / (fpu / per) + 0.5), b = saturate((0.25 - abs(frac(UV.y / per) - 0.5)) / (fpv / per) + 0.5);
            float sharp = saturate((per / max(fpu, fpv) - 3.0) / 3.0);
            a = lerp(0.5, a, sharp); b = lerp(0.5, b, sharp);
            c = lerp(acc, mainC, a * 0.5 + b * 0.5);
        }
        BaseColor = c * clamp(var, 0.55, 1.6);
    }
    // the inside of the skirt (back faces keep the outer normal, Skirt.mat): in the shade of the cloth itself - lit from
    // behind it read as flat grey cards between the legs, review round 11
    // (round 11: back faces with the outer normal turned the WHOLE skirt near-black - median L 1 vs the original's 40:
    //  its visible side is drawn as back faces. Flip mode again; the inside is not told apart here)
    float inside = 0.0;
    Smoothness = 0.5;                                               // Blender sheen roughness 0.35
    NormalOut = sh_bump(normalize(NormalWS), PositionWS, ht, 0.0008, 1.0);
    // (half: seen edge-on in the orbits the pleats' panels lit up flat light grey, 60 vs 25, review round 9)
    SheenColor = float3(0.8, 0.82, 0.86) * 0.045 * (1.0 - 0.8 * inside);   // (0.03: the folds' shading went black, round 10)                   // dark charcoal wool: faint sheen (HDRP's Charlie lobe is strong)
}

// ---- the pleats' folds (2026-11-17: the skirt had a quarter of the original's fold contrast - a flat dark felt panel).
// tools/skirt_folds.py bakes into the skirt mesh uv0.z = the sky light the pleat lets through (1 open face, 0 deep in a
// fold: a horizon in the ring's cross-section) and uv0.w = nearness to an outer fold's edge. _SheerSkirtFold (SkirtCloth):
// x = ambient occlusion from it, y = cavity (the hollows' own shade, for the direct light the overhanging pleat keeps out),
// z = sheen along the fold edges (a pressed fold catches the light), w = the open faces' gain. Unset (0) = as before.
float4 _SheerSkirtFold;
float _SheerSkirtFoldSheen;     // the wool's sheen x this (SkirtCloth.sheen)
// the cloth itself, close up: a woven wool (SkirtCloth.MakeWool - a 2/2 twill of 0.5 mm threads, each thread its own tone,
// stray light fibres), mip-mapped, along the fabric (uv0.xy = metres round the pleats and up). _SheerSkirtWoolK: x = the
// tile (m), y = the threads' tone contrast, z = their relief (m), w = on.
TEXTURE2D(_SheerSkirtWool);
float4 _SheerSkirtWoolK;
void SheerSkirt_float(float4 UV, float3 Rest, float3 PositionWS, float3 NormalWS, out float3 BaseColor,
                      out float Smoothness, out float3 NormalOut, out float3 SheenColor, out float Occlusion)
{
    SheerSkirt_float(UV.xy, Rest, PositionWS, NormalWS, BaseColor, Smoothness, NormalOut, SheenColor);
    float sky = saturate(UV.z), edge = saturate(UV.w);
    float4 k = _SheerSkirtFold;
    Occlusion = lerp(1.0, sky, saturate(k.x));
    BaseColor *= lerp(1.0, sky, saturate(k.y)) * (1.0 + k.w * sky);
    SheenColor *= (1.0 + k.z * edge) * max(_SheerSkirtFoldSheen, 0.0);
    [branch] if (_SheerSkirtWoolK.w > 0.5)
    {
        float4 wt = SAMPLE_TEXTURE2D(_SheerSkirtWool, s_trilinear_repeat_sampler, UV.xy / max(_SheerSkirtWoolK.x, 1e-4));
        BaseColor *= lerp(1.0 - _SheerSkirtWoolK.y, 1.0 + _SheerSkirtWoolK.y, wt.g);
        NormalOut = sh_bump(NormalOut, PositionWS, wt.r, _SheerSkirtWoolK.z, 1.0);
    }
}

// ---- floor: white cotton drop cloth, faint pink-violet patch on the left like the original (mode 0); the player's other
// floors (SheerStudio): oak boards, tatami, a gymnastics mat, a fluffy rug on boards, marble, a meadow, a glossy stage
float3 SheerFloorBoards(float3 bp, float fp, out float rough, out float h)
{
    // oak boards along x, 12 cm wide, staggered ends; grain along the board, a varnish
    float bw = 0.12, row = floor(bp.y / bw), off = SheerLookHash(float2(row, 3.1)) * 2.0;
    float bl = 0.9, col = floor((bp.x + off) / bl);
    float id = SheerLookHash(float2(row, col));
    float vy = frac(bp.y / bw), vx = frac((bp.x + off) / bl);
    float gap = max(SheerLookSmooth(0.012, 0.0, abs(vy - 0.5) - 0.5 + 0.012), SheerLookSmooth(0.004, 0.0, min(vx, 1.0 - vx) * bl));
    gap *= saturate((0.004 / fp - 1.0) / 2.0);
    float grain = sh_noise(float3(bp.x * 2.0 + id * 13.0, bp.y * 60.0, id), 6.0, 3, 0.55);
    float ring = 0.5 + 0.5 * sin((bp.y * 90.0 + grain * 9.0 + id * 40.0));
    float3 c = lerp(float3(0.33, 0.20, 0.10), float3(0.55, 0.36, 0.19), saturate(0.35 + 0.5 * grain + 0.25 * ring * saturate((0.01 / fp - 1.0))));
    c *= lerp(0.82, 1.12, id);
    c = lerp(c, float3(0.05, 0.03, 0.02), gap * 0.85);
    rough = lerp(0.32, 0.6, gap); h = -gap * 0.6 + grain * 0.05;
    return c;
}
// ---- the feet's CONTACT SHADOW on the floor: per foot, how much of the sky the posed foot hides from each point of the floor
// round it (TightsSim.UpdateContact: the foot's height over the floor on a 2 mm grid; horizon-based - cosine-weighted, 12
// directions out to 6 cm - on 4 mm) and, under its overhang (the toes' tips, the sides of the ball - which the low camera
// looks in under), near black. The original: ~50 in the gap under the toes, 114 - 198 at its edge, 233 - 236 two
// centimetres on. (The fixed 9 x 23 cm blob it replaces ignored the body's motion and greyed the cloth all round the feet -
// 213 vs 227 - while the gap under the toes stayed lit: 'no contact line, the foot hovers', review 9.)
float4 _SheerContactBox[2];                   // per foot: the grid's corner (x, z, world), 1 / its width, 1 / its depth
float4 _SheerContactInfo;                     // x: 1 when set, z: strength (0: the default)
float _SheerContactKG, _SheerContactPG;      // (experiments: -sheerGlobal _SheerContactKG=X,_SheerContactPG=Y)
TEXTURE2D(_SheerContactL); SAMPLER(sampler_SheerContactL);
TEXTURE2D(_SheerContactR); SAMPLER(sampler_SheerContactR);
TEXTURE2D(_SheerContactSDL); SAMPLER(sampler_SheerContactSDL);
TEXTURE2D(_SheerContactSDR); SAMPLER(sampler_SheerContactSDR);
float SheerContactVis(float3 p)
{
    if (_SheerContactInfo.x < 0.5) return 1.0;
    // (2.5 x AO^2 with the floor under the toes near black: from the low camera the gap under the toes showed as a hard dark
    //  slab reaching past them - 'feet pasted on', review 10; the original's rug swallows the contact: a dark crease, a short
    //  soft shade. Gentler, and under the foot no darker than ~0.38)
    float k = _SheerContactInfo.z > 0.0 ? _SheerContactInfo.z : _SheerContactKG > 0.0 ? _SheerContactKG : 1.8;
    float pw = _SheerContactPG > 0.0 ? _SheerContactPG : 2.0;
    float vis = 1.0;
    float2 uL = (p.xz - _SheerContactBox[0].xy) * _SheerContactBox[0].zw, uR = (p.xz - _SheerContactBox[1].xy) * _SheerContactBox[1].zw;
    if (all(uL > 0.0) && all(uL < 1.0))
    {
        float a = SAMPLE_TEXTURE2D_LOD(_SheerContactL, sampler_SheerContactL, uL, 0).r; float2 sd = SAMPLE_TEXTURE2D_LOD(_SheerContactSDL, sampler_SheerContactSDL, uL, 0).rg;
        float under = sh_smooth(0.0008, -0.0008, sd.x);
        vis *= lerp(saturate(1.0 - k * pow(a, pw)), max(saturate(1.0 - k * pow(max(a, sd.y), pw)), 0.38), under);
    }
    if (all(uR > 0.0) && all(uR < 1.0))
    {
        float a = SAMPLE_TEXTURE2D_LOD(_SheerContactR, sampler_SheerContactR, uR, 0).r; float2 sd = SAMPLE_TEXTURE2D_LOD(_SheerContactSDR, sampler_SheerContactSDR, uR, 0).rg;
        float under = sh_smooth(0.0008, -0.0008, sd.x);
        vis *= lerp(saturate(1.0 - k * pow(a, pw)), max(saturate(1.0 - k * pow(max(a, sd.y), pw)), 0.38), under);
    }
    return vis;
}

void SheerFloor_float(float3 PositionOS, float3 PositionWS, float3 NormalWS, out float3 BaseColor, out float Smoothness,
                      out float3 NormalOut)
{
    float3 bp = float3(PositionOS.x, PositionOS.z, PositionOS.y);
    float fp = max(length(fwidth(PositionWS)), 1e-6);                 // metres per pixel
    float cvis = SheerContactVis(PositionWS + _WorldSpaceCameraPos);
    float haze = sh_smooth(1.1, 2.0, length(PositionWS));
    float mode = _SheerFloor.x;
    [branch] if (mode < 0.5)
    {
        // fluffy fleece like the original's: soft lumps (3 cm) + tufts (8 mm) + fuzz (2.5 mm), each band-limited (faded out
        // below ~3 px: the old 0.35 mm weave only aliased into moire lines)
        float b1 = saturate((0.03 / fp - 3.0) / 3.0), b2 = saturate((0.008 / fp - 3.0) / 3.0), b3 = saturate((0.0025 / fp - 3.0) / 3.0);
        float l1 = sh_noise(bp, 33.0, 3, 0.5), l2 = sh_noise(bp + 7.3, 125.0, 2, 0.5), l3 = sh_noise(bp + 3.1, 400.0, 2, 0.5);
        // (out of focus beyond the feet: the original's rug goes soft toward the back - its fleece and lumps blur away and
        //  the horizon is mist; ours was a crisp snowfield of dunes, independent review 2026-11-17. The mesh's folds were
        //  flattened to a third as well)
        float defocus = sh_smooth(1.35, 2.2, length(PositionWS));   // (from 1.0 m the fleece by the feet went blank too, review 2)
        b1 *= 1.0 - 0.7 * defocus; b2 *= 1.0 - defocus; b3 *= 1.0 - defocus;
        float h = (l1 - 0.5) * b1 + (l2 - 0.5) * b2 * 0.35 + (l3 - 0.5) * b3 * 0.15;
        float n1 = sh_noise(bp, 4.0, 5, 0.5);
        float3 base = lerp(float3(0.60, 0.62, 0.72), float3(0.93, 0.93, 0.97), sh_smooth(0.3, 0.7, n1));
        // (deeper shade in the pile's dips: x1.6 left a flat pale cloth where the original's rug is a fluffy fur, review 2)
        // (wider: the original's fleece near the feet varies by ~40 levels - clumps and their shade, review 8)
        base *= lerp(float3(0.46, 0.48, 0.60), float3(1.10, 1.10, 1.12), saturate(0.5 + h * 2.6));   // shade in the pile's dips
        float dx = bp.x + 0.17, dy = (bp.y - 0.05) * 0.8;
        base = lerp(base, float3(0.70, 0.42, 0.60), sh_smooth(0.36, 0.04, sqrt(dx * dx + dy * dy)));
        // (the light falls on the cloth in front of the feet: there it is near white (the original's 236 - 239 at the bottom
        //  of VIEW 02), behind them it is grey-blue (~120); ours was one even lavender ~190 - 205, independent review 4)
        float zf = PositionOS.z;                                     // the cloth: z -1.6 (front) .. 0.95 (back)
        float pool = sh_smooth(0.20, -0.20, zf);                     // (the original's turns bright level with the toes)
        base = lerp(base, float3(0.96, 0.96, 0.97), 0.45 * pool) * lerp(0.74, 1.0, pool);
        // (a soft haze toward the far edge of the cloth: the horizon was a hard step, the original's is misty - round 11)
        base = lerp(base, float3(0.62, 0.66, 0.76), max(haze * 0.55, defocus * 0.45));
        // (... and the cloth's own far edges fade into the backdrop's blue: the haze above is by distance from the origin
        //  (>= 1.1 m), and the back edge is only 0.95 m behind the feet - the horizon stayed a hard straight line, review 4)
        // (only the last quarter metre: from 0.35 m the mist washed out the fleece behind the feet - 'a white haze with no
        //  texture', review 5; the original's rug is lumpy grey-blue right back to its misty edge)
        float mist = max(sh_smooth(0.68, 0.95, zf), sh_smooth(1.15, 1.58, abs(PositionOS.x)));
        base = lerp(base, float3(0.27, 0.39, 0.52), mist * mist * (3.0 - 2.0 * mist));
        if (_SheerFloorCol.a > 0.5) base *= _SheerFloorCol.rgb;
        // (the feet's shadow last: applied before the pool of light, the pool's lerp to white took half of it back)
        BaseColor = base * cvis;
        Smoothness = 0.05;
        NormalOut = sh_bump(normalize(NormalWS), PositionWS, h, 0.006, 0.6);   // (0.010 / 0.75 drew rows of dark dashes across the floor)
        return;
    }
    float3 c = 0.5; float rough = 0.5, h = 0.0, bumpS = 0.0;
    float3 tint = _SheerFloorCol.a > 0.5 ? _SheerFloorCol.rgb : float3(-1.0, 0.0, 0.0);
    if (mode < 1.5) { c = SheerFloorBoards(bp, fp, rough, h); bumpS = 0.4; }
    else if (mode < 2.5)
    {
        // tatami: mats of woven rush (fine lines across the mat), dark cloth borders (heri) along the long edges
        float2 m = float2(bp.x + 0.45, bp.y + 0.2);
        float mx = frac(m.x / 0.9), my = frac(m.y / 1.8);
        float heri = SheerLookSmooth(0.04, 0.025, min(mx, 1.0 - mx) * 0.9);
        float weave = 0.5 + 0.5 * sin(m.y * 6.2831853 / 0.0042);
        weave = lerp(0.5, weave, saturate((0.0042 / fp - 2.0) / 2.0));
        float age = sh_noise(bp, 3.0, 3, 0.5);
        c = lerp(float3(0.42, 0.40, 0.16), float3(0.62, 0.55, 0.28), saturate(age * 0.8 + weave * 0.35));
        c = lerp(c, float3(0.04, 0.05, 0.07), heri);
        float seam = SheerLookSmooth(0.004, 0.0, min(my, 1.0 - my) * 1.8) * saturate((0.004 / fp - 1.0));
        c *= 1.0 - 0.5 * seam;
        rough = lerp(0.62, 0.8, heri); h = weave * 0.6 * (1.0 - heri) - seam; bumpS = 0.35;
    }
    else if (mode < 3.5)
    {
        // a gymnastics mat: soft vinyl, orange-peel surface, stitched seams every metre
        float3 mc = tint.x >= 0.0 ? tint : float3(0.06, 0.16, 0.42);
        float peel = sh_noise(bp, 260.0, 2, 0.5);
        float sx = frac(bp.x + 0.5), sy = frac(bp.y + 0.3);
        float seamD = min(min(sx, 1.0 - sx), min(sy, 1.0 - sy));
        float seam = SheerLookSmooth(0.006, 0.0, seamD);
        float stitch = SheerLookSmooth(0.0012, 0.0, abs(seamD - 0.012)) * step(0.5, frac((bp.x + bp.y) / 0.008));
        c = mc * lerp(0.9, 1.05, peel); c = lerp(c, mc * 0.45, seam); c = lerp(c, float3(0.85, 0.85, 0.88), stitch * saturate((0.008 / fp - 2.0) / 2.0));
        rough = 0.42; h = peel * 0.4 - seam; bumpS = 0.3;
    }
    else if (mode < 4.5)
    {
        // a round fluffy rug (shaggy faux fur) on oak boards
        float r = length(float2(bp.x * 0.85, bp.y + 0.05));
        float rug = SheerLookSmooth(0.66, 0.62, r + (sh_noise(bp, 18.0, 2, 0.5) - 0.5) * 0.04);
        float rb; float hb; float3 boards = SheerFloorBoards(bp, fp, rb, hb);
        float3 fc = tint.x >= 0.0 ? tint : float3(0.95, 0.62, 0.74);
        float fur = sh_noise(bp, 220.0, 3, 0.6), clump = sh_noise(bp + 4.0, 40.0, 2, 0.5);
        fur = lerp(0.5, fur, saturate((0.006 / fp - 1.5) / 2.0));
        float3 rc = fc * lerp(0.62, 1.08, fur * 0.6 + clump * 0.4);
        c = lerp(boards, rc, rug); rough = lerp(rb, 0.95, rug); h = lerp(hb, fur * 1.2 + clump, rug); bumpS = lerp(0.4, 1.0, rug);
    }
    else if (mode < 5.5)
    {
        // white marble: veins from turbulence, polished
        float tur = sh_noise(bp, 3.5, 5, 0.55);
        float vein = 1.0 - abs(sin((bp.x * 2.0 + bp.y * 3.0 + tur * 9.0)));
        vein = pow(saturate(vein), 18.0) + 0.35 * pow(saturate(1.0 - abs(sin(bp.x * 7.0 - bp.y * 4.0 + tur * 14.0))), 30.0);
        c = lerp(float3(0.86, 0.85, 0.84), float3(0.38, 0.38, 0.42), saturate(vein));
        c *= lerp(0.94, 1.03, sh_noise(bp, 12.0, 2, 0.5));
        rough = 0.12; h = 0.0; bumpS = 0.0;
    }
    else if (mode < 6.5)
    {
        // a meadow: grass blades (fine streaks) with a few small flowers
        float g1 = sh_noise(float3(bp.x * 1.0, bp.y * 1.0, 0.0), 160.0, 3, 0.6), g2 = sh_noise(bp, 9.0, 3, 0.5);
        g1 = lerp(0.5, g1, saturate((0.006 / fp - 1.5) / 2.0));
        c = lerp(float3(0.05, 0.16, 0.03), float3(0.20, 0.42, 0.08), saturate(g1 * 0.7 + g2 * 0.5));
        float2 cell = floor(bp.xy / 0.07); float2 fq = frac(bp.xy / 0.07) - 0.5;
        float fh = SheerLookHash(cell);
        float flower = step(0.82, fh) * SheerLookSmooth(0.16, 0.08, length(fq - (float2(SheerLookHash(cell + 3.0), SheerLookHash(cell + 7.0)) - 0.5) * 0.5));
        c = lerp(c, fh > 0.91 ? float3(0.95, 0.75, 0.85) : float3(0.95, 0.95, 0.88), flower * saturate((0.02 / fp - 1.0)));
        rough = 0.85; h = g1; bumpS = 0.7;
    }
    else
    {
        // a glossy black stage, a soft pool of light round the feet
        float pool = SheerLookSmooth(0.75, 0.0, length(float2(bp.x * 0.8, bp.y + 0.05)));
        float3 sc = tint.x >= 0.0 ? tint : float3(0.012, 0.012, 0.016);
        c = sc * (1.0 + 2.5 * pool);
        rough = 0.08; h = 0.0; bumpS = 0.0;
    }
    c *= cvis;
    c = lerp(c, c * 0.7 + float3(0.02, 0.022, 0.03), haze * 0.5);
    BaseColor = c;
    Smoothness = 1.0 - rough;
    NormalOut = bumpS > 0.0 ? sh_bump(normalize(NormalWS), PositionWS, h, 0.003, bumpS) : normalize(NormalWS);
}

// ... with the light that falls on the cloth in front of the feet: the original's cloth there is near white (236 - 239 at
// the bottom of VIEW 02), its back grey-blue (~120) - an albedo cannot go above 1, ours stayed at ~215 (independent review 4).
// _SheerFloorGlow: its strength (0 = the default below; -sheerGlobal _SheerFloorGlow=X to try others)
float _SheerFloorGlow;
void SheerFloor_float(float3 PositionOS, float3 PositionWS, float3 NormalWS, out float3 BaseColor, out float Smoothness,
                      out float3 NormalOut, out float3 Emission)
{
    SheerFloor_float(PositionOS, PositionWS, NormalWS, BaseColor, Smoothness, NormalOut);
    float pool = sh_smooth(0.20, -0.20, PositionOS.z) * (1.0 - sh_smooth(0.9, 1.5, abs(PositionOS.x)));
    Emission = BaseColor * pool * (_SheerFloorGlow == 0.0 ? 2000.0 : max(_SheerFloorGlow, 0.0));   // (2000: 232 - 236 at the bottom of VIEW 02. Measured on pure cloth between the feet the original's near floor is as flat as ours - 236, spread 3.3 - review 8's 'spread 29' included feet and the letterbox)
}
// ------------------------------------------------------------------------------------------ backdrop
// Camera-only studio backdrop (port of setup_world in blender/sheer_scene.py): vertical blue-grey gradient in
// screen space times a soft radial falloff. Cycles' pre-tonemap value is ramp * 2^exposure(0.3); HDRP applies its
// Unlit colour is written as-is into its pre-exposed colour buffer, so the value lands unchanged before the tonemapper.
// The player's other backdrops (SheerStudio) are soft, out-of-focus pictures in the same place: sakura at dusk, city
// lights at night, a pastel dream, a shoji screen, a gym's wall bars, a starry night, a two-colour gradient.
float SheerBokeh(float2 p, float cellS, float seed, float t, float sizeK, out float3 tint)
{
    float2 cell = floor(p / cellS), f = frac(p / cellS) - 0.5;
    float h = SheerLookHash(cell + seed), h2 = SheerLookHash(cell + seed + 17.0), h3 = SheerLookHash(cell + seed + 41.0);
    float2 c = (float2(h, h2) - 0.5) * 0.36 + 0.05 * float2(sin(t * 0.3 + h * 6.0), cos(t * 0.23 + h2 * 6.0));
    float r = (0.12 + 0.13 * h3) * sizeK;                     // (inside its cell whatever the offset: no clipped squares)
    float d = length(f - c);
    tint = float3(h, h2, h3);
    float disc = SheerLookSmooth(r, r * 0.86, d) * (0.75 + 0.25 * SheerLookSmooth(r * 0.86, r, d));   // a bright rim like a lens's
    return disc * step(0.45, h3);
}
void SheerBackdrop_float(float4 ScreenPos, out float3 Color)
{
    float2 w = ScreenPos.xy;                                   // 'Default' screen position: [0,1], (0,0) bottom-left
    float mode = _SheerBack.x;
    float bright = _SheerBack.y > 0.0 ? _SheerBack.y : 1.0;
    [branch] if (mode < 0.5)
    {
        float3 c0 = float3(0.16, 0.28, 0.44), c1 = float3(0.09, 0.14, 0.19), c2 = float3(0.035, 0.06, 0.09);
        float y = saturate(w.y);
        float3 ramp = y < 0.45 ? lerp(c0, c1, y / 0.45) : lerp(c1, c2, (y - 0.45) / 0.55);
        float r = length(w - 0.5);
        float vig = lerp(1.0, 0.55, saturate((r - 0.25) / 0.6));
        Color = ramp * vig * 1.2311444 * bright;      // 2^0.3; HDRP Unlit colour goes straight into the pre-exposed buffer
        return;
    }
    float aspect = _ScreenParams.x / max(_ScreenParams.y, 1.0);
    float2 p = float2((w.x - 0.5) * aspect, w.y);
    float t = _Time.y * (_SheerBack.z > 0.0 ? _SheerBack.z : 1.0);
    float r = length(w - 0.5), vig = lerp(1.0, 0.6, saturate((r - 0.25) / 0.6));
    float3 col = 0.0, tint;
    if (mode < 1.5)
    {   // sakura at dusk: pink to lavender, blossoms out of focus drifting down
        col = lerp(float3(0.20, 0.09, 0.16), float3(0.55, 0.22, 0.30), saturate(w.y * 1.1));
        col = lerp(col, float3(0.62, 0.38, 0.30), SheerLookSmooth(0.5, 0.0, abs(w.y - 0.42)) * 0.35);
        for (int k = 0; k < 3; k++)
        {
            float2 q = p * (3.0 + k * 2.5) + float2(0.0, t * (0.05 + 0.03 * k));
            float b = SheerBokeh(q, 1.0, 11.0 + k * 7.0, t, 1.0 - 0.2 * k, tint);
            col += b * lerp(float3(0.9, 0.55, 0.68), float3(1.0, 0.86, 0.9), tint.x) * (0.35 - 0.08 * k);
        }
    }
    else if (mode < 2.5)
    {   // city lights at night: navy, bokeh discs of street lamps, windows, neon
        col = lerp(float3(0.012, 0.016, 0.04), float3(0.03, 0.03, 0.08), saturate(w.y));
        for (int k = 0; k < 3; k++)
        {
            float2 q = p * (4.0 + k * 3.0) + float2(t * 0.02 * (k + 1), 0.0);
            float b = SheerBokeh(q, 1.0, 3.0 + k * 13.0, t, 1.0 - 0.15 * k, tint);
            float3 lc = tint.x < 0.33 ? float3(1.0, 0.62, 0.22) : tint.x < 0.66 ? float3(0.25, 0.75, 1.0) : float3(1.0, 0.3, 0.55);
            col += b * lc * (0.30 - 0.06 * k) * SheerLookSmooth(0.95, 0.25, w.y) * (0.8 + 0.2 * sin(t * 2.0 + tint.y * 30.0));
        }
    }
    else if (mode < 3.5)
    {   // pastel dream: lavender, pink, mint; little hearts and stars floating up
        col = lerp(float3(0.55, 0.78, 0.72), float3(0.80, 0.52, 0.74), saturate(w.y));
        col = lerp(col, float3(0.68, 0.62, 0.95), SheerLookSmooth(0.0, 1.0, w.x) * 0.4);
        float2 q = p * 6.0 + float2(0.0, -t * 0.12);
        float2 cell = floor(q), f = frac(q) - 0.5;
        float h = SheerLookHash(cell + 5.0);
        float2 o = (float2(SheerLookHash(cell + 9.0), SheerLookHash(cell + 2.0)) - 0.5) * 0.4;
        float sz = 0.16 + 0.1 * h;
        float hs = SheerSdHeart((f - o) / sz * float2(1.0, -1.0) + float2(0.0, 0.5)) * sz;
        float star = length(f - o) - sz * (0.55 + 0.35 * cos(5.0 * atan2(f.y - o.y, f.x - o.x)));
        float sd = h < 0.5 ? hs : star * 0.6;
        float m = SheerLookSmooth(0.03, 0.0, sd) * step(0.5, SheerLookHash(cell + 1.0));
        col = lerp(col, float3(1.0, 0.97, 1.0), m * 0.55);
    }
    else if (mode < 4.5)
    {   // a shoji screen: paper glowing warm, the wooden kumiko lattice out of focus
        col = float3(0.62, 0.50, 0.33);
        float gx = abs(frac(p.x / 0.11) - 0.5), gy = abs(frac(w.y / 0.16) - 0.5);
        float lat = max(SheerLookSmooth(0.47, 0.5, gx), SheerLookSmooth(0.46, 0.5, gy));
        float frame = max(SheerLookSmooth(0.45, 0.5, abs(frac(p.x / 0.66) - 0.5)), SheerLookSmooth(0.04, 0.0, abs(w.y - 0.08)));
        col = lerp(col, float3(0.09, 0.055, 0.03), max(lat * 0.75, frame * 0.9));
        col *= 0.85 + 0.25 * SheerLookSmooth(0.0, 1.0, w.y);
    }
    else if (mode < 5.5)
    {   // a gym: pale wall, wooden wall bars
        col = lerp(float3(0.42, 0.50, 0.58), float3(0.58, 0.64, 0.70), saturate(w.y));
        float post = SheerLookSmooth(0.05, 0.035, abs(frac(p.x / 0.62) - 0.5) - 0.42);
        float rung = SheerLookSmooth(0.22, 0.12, abs(frac(w.y / 0.085) - 0.5)) * step(abs(frac(p.x / 0.62) - 0.5), 0.47);
        float3 wood = float3(0.55, 0.37, 0.18);
        col = lerp(col, wood * (0.8 + 0.2 * SheerLookSmooth(0.3, 0.0, abs(frac(w.y / 0.085) - 0.5))), max(rung * 0.9, post));
        col = lerp(col, float3(0.30, 0.31, 0.33), SheerLookSmooth(0.12, 0.05, w.y));
    }
    else if (mode < 6.5)
    {   // a starry night: deep violet, twinkling stars, a crescent moon
        col = lerp(float3(0.02, 0.012, 0.05), float3(0.05, 0.04, 0.12), saturate(w.y));
        for (int k = 0; k < 2; k++)
        {
            float2 q = p * (40.0 + 30.0 * k);
            float2 cell = floor(q), f = frac(q) - 0.5;
            float h = SheerLookHash(cell + 7.0 * k);
            float tw = 0.6 + 0.4 * sin(t * (1.5 + 3.0 * h) + h * 50.0);
            col += step(0.93, h) * SheerLookSmooth(0.12, 0.0, length(f - (SheerLookHash(cell + 3.0) - 0.5) * 0.6)) * tw * float3(0.9, 0.9, 1.0) * (0.7 - 0.3 * k);
        }
        // a shooting star now and then (one every ~5 s, each with its own path across the upper sky, ~0.7 s long)
        {
            float slot = floor(t / 5.0), tt = frac(t / 5.0) * 5.0;
            float hs = SheerLookHash(float2(slot, 3.7)), hs2 = SheerLookHash(float2(slot, 9.1));
            float2 a0 = float2((0.15 + 0.6 * hs) * aspect, 0.92 - 0.12 * hs2), dir = normalize(float2(0.85, -0.42 - 0.3 * hs2));
            float prog = saturate(tt / 0.7);
            float2 head = a0 + dir * prog * 0.45, rel = p - head;
            float along = dot(rel, -dir), across = abs(rel.x * dir.y - rel.y * dir.x);
            float trail = SheerLookSmooth(0.0, 0.01, along) * SheerLookSmooth(0.16, 0.0, along) * SheerLookSmooth(0.0035, 0.0, across);
            float fade = step(tt, 0.7) * sin(prog * 3.14159);
            col += trail * fade * float3(1.0, 0.95, 0.85) * 1.6;
        }
        float2 mp = p - float2(0.55 * aspect * 0.5, 0.78);
        float moon = SheerLookSmooth(0.075, 0.07, length(mp)) * (1.0 - SheerLookSmooth(0.07, 0.065, length(mp - float2(0.03, 0.02))));
        col += moon * float3(1.0, 0.95, 0.8) * 1.2 + SheerLookSmooth(0.3, 0.07, length(mp)) * float3(0.08, 0.08, 0.12);
    }
    else
    {   // two colours, top / bottom
        col = lerp(_SheerBackCol1.rgb, _SheerBackCol0.rgb, SheerLookSmooth(0.0, 1.0, w.y));
    }
    Color = col * vig * bright;
}

#endif
