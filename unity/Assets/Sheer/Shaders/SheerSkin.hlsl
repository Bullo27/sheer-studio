// SHEER — skin surface (port of make_skin in blender/sheer_materials.py) + the light that reaches the skin under
// the intact nylon. Separate from SheerSurfaces.hlsl because it reads the skin graph's own material properties.
#ifndef SHEER_SKIN_INCLUDED
#define SHEER_SKIN_INCLUDED
#include "Assets/Sheer/Shaders/SheerNoise.hlsl"
#include "Assets/Sheer/Shaders/SheerCloth.hlsl"

// ---- skin (HDRP Lit, Subsurface Scattering with HDRP's skin diffusion profile)
// Blender object space was (x, y, z) = Unity (x, z, y): 'front' = Blender -y = Unity -z, height = Unity y.
// Leg = the stocking's damage-map coordinates of this skin point (body uv2: u around the leg, rest height,
// side +1/-1, 1 below the waistband). HDRP's alpha blending of the transparent nylon accounts for the light that
// comes back out through the yarn, but the stocking does not shadow the skin (an opaque shadow would kill the
// show-through), so the light going in is applied here: where the stocking is intact (no hole, no open ladder) the
// skin receives light that crossed the yarn — shadowed by ~30% of its coverage and tinted by its transmission.
#define SH_DMG_RANGE_SKIN 0.012
// (a thigh-high's welt does not tear: holes and ladders end along its lower edge - as SheerTights.hlsl; restY = the skin
//  point's rest height; < -0.5 where there is no welt)
#ifndef SHEER_HELD_DECLARED
#define SHEER_HELD_DECLARED
float _SheerHeldL, _SheerHeldR;                // 1 while the hand holds that leg's fabric (TightsSim)
#endif
float SheerSkinWeltClip(float restY) { return SheerHasBand() ? restY - (_SheerBand.x - max(_SheerBand.y, 0.01)) + 0.0015 : -1.0; }

float SheerSkinOpenness(float4 Leg, UnityTexture2D DamageL, UnityTexture2D DamageR, float weltClip)
{
    float2 uv = SheerDamageTexUV(Leg.xy);
    float4 dm = Leg.z > 0 ? DamageL.tex.SampleLevel(DamageL.samplerstate, uv, 0)
                          : DamageR.tex.SampleLevel(DamageR.samplerstate, uv, 0);
    float holeSD = max((dm.r - 0.5) * 2 * SH_DMG_RANGE_SKIN, weltClip), runSD = max((dm.g - 0.5) * 2 * SH_DMG_RANGE_SKIN, weltClip);
    // open slightly beyond the yarn's hole edge (the stocking adds ragged-edge noise the skin does not know): skin that the
    // nylon does not cover must never stay shadowed (dark red SSS slivers inside the holes)
    // (4 mm margin: the cloth pose also shifts the yarn's hole a few mm against the skin's rest-space map at the knee)
    return max(sh_smooth(0.004, 0.0015, holeSD), 0.3 * sh_smooth(0.002, -0.001, runSD));
}

// how far the stocking has lifted off the skin here (m): the cloth simulation's lift map of this leg
float SheerSkinLift(float3 Rest, float4 Leg, UnityTexture2D LiftL, UnityTexture2D LiftR)
{
    return Leg.z > 0 ? SheerClothLift(Rest, 1.0, LiftL.tex, LiftL.samplerstate)
                     : SheerClothLift(Rest, -1.0, LiftR.tex, LiftR.samplerstate);
}

void SheerSkin_float(float3 Rest, float4 Leg, float3 PositionWS, float3 NormalWS, UnityTexture2D DamageL,
                     UnityTexture2D DamageR, UnityTexture2D LiftL, UnityTexture2D LiftR, out float3 BaseColor, out float Smoothness,
                     out float3 NormalOut, out float CoatMask)
{
    const float3 C = float3(0.95, 0.46, 0.44);                  // HDRP SSS: blue +15 % vs Cycles (fit to the original's holes)
    // (below the ankle's top the stocking's tears run along its wales - round the heel, along the foot: SheerCloth.hlsl)
    Leg.xy = SheerDamageUV(Rest, Leg.z, Leg.xy);
    float3 bp = float3(Rest.x, Rest.z, Rest.y);                 // back to Blender object coordinates for the noise
    float n1 = sh_noise(bp, 18, 4, 0.5), n2 = sh_noise(bp, 260, 2, 0.5);
    // Skin is not one colour. Measured on the bare skin inside the original's holes (11 / 23 / 35.5 s): thigh and shin
    // are pale and cool (206,180,176 / 198,174,171), the knee is rosy (203,157,150, red - green 46 against 25), and
    // inside one hole the tone drifts and mottles (spread 12-20 levels; ours was 6-8: flat cut-outs of one cream).
    float3 pale = C * lerp(float3(1.0, 1.0, 1.0), float3(1.0, 1.125, 1.19), _SkinPale);
    // the player's skin tone (SheerStudio: an albedo multiplier of the calibrated one)
    if (_SheerSkinTone.a > 0.5) pale *= _SheerSkinTone.rgb;
    // above the top of a thigh-high the skin is bare: no nylon over it
    if (SheerHasBand()) Leg.w *= sh_smooth(_SheerBand.x + 0.0015, _SheerBand.x - 0.0015, Rest.y);
    float3 base = lerp(pale, pale * float3(1.04, 0.9, 0.88), n1);
    base = lerp(base, pale * float3(0.96, 0.93, 0.93), saturate((n2 - 0.35) * 0.6));
    // rosy zones: the knee (kneecap side most, blotchy, reaching a little onto thigh and shin), ankle and heel
    float knee = sh_smooth(0.36, 0.455, bp.z) * sh_smooth(0.60, 0.50, bp.z);
    float front = sh_smooth(0.03, -0.05, bp.y);
    float blot = sh_noise(bp, 45, 2, 0.55);
    float rosy = knee * (0.45 + 0.55 * front) * (0.6 + 0.8 * blot);
    rosy = max(rosy, 0.6 * sh_smooth(0.16, 0.09, bp.z) * (0.6 + 0.8 * blot));
    base = lerp(base, base * float3(0.985, 0.70, 0.69), saturate(rosy * _SkinRose));
    // mottling: a faint net of redder patches (a centimetre or two across) all over the leg
    float mot = sh_smooth(0.48, 0.78, sh_noise(bp + 3.7, 62, 2, 0.5));
    base *= lerp(float3(1.0, 1.0, 1.0), float3(1.0, 0.895, 0.888), mot * _SkinMottle);
    // under the intact nylon: incoming light shadowed and tinted by the yarn
    // (where a pull has dragged the fabric - and its holes - away, the skin at the holes' worn place is covered again)
    float movedC = Leg.z > 0 ? SheerClothMoved(Rest, 1.0, LiftL.tex, LiftL.samplerstate) : SheerClothMoved(Rest, -1.0, LiftR.tex, LiftR.samplerstate);
    float weltClip = SheerSkinWeltClip(Rest.y);
    float covered = Leg.w * (1.0 - SheerSkinOpenness(Leg, DamageL, DamageR, weltClip) * sh_smooth(0.006, 0.002, movedC)) * (1.0 - _SheerSkinK.x);
    // where the nylon has lifted off into a sail, this skin is no longer under it: no yarn attenuation (else dark red
    // skin patches showed while the cloth moved away, the attenuation staying in leg space)
    // (only partly: a tent in front of the skin still filters its light - the original's pulled nylon reads darker)
    // (the skin under a lifted tent is still behind the nylon: its light is filtered as before; _SkinLiftShade > 0 adds the
    //  tent's soft shadow, < 0 would brighten it)
    float liftRaw = SheerSkinLift(Rest, Leg, LiftL, LiftR);
    // (not under fabric springing back after the hand let go - millimetres off for a frame or two; SheerTights.hlsl)
    float liftK = sh_smooth(0.002, 0.012, liftRaw) * lerp(sh_smooth(0.010, 0.025, liftRaw), 1.0, Leg.z > 0 ? _SheerHeldL : _SheerHeldR);
    // (... of the fabric WORN here - where the hand has dragged it away sideways before lifting it, the tent stands
    //  somewhere else and its shade is not on this skin: a dark oval stayed at the grab point while the tent's tip was 6 cm
    //  away, free-play sweep 2026-11-17, pull 32)
    liftK *= sh_smooth(0.030, 0.012, sqrt(max(movedC * movedC - liftRaw * liftRaw, 0.0)));
    float3 through = (1.0 - _SkinNylonShadow * _FrostBodyCoverage) * _SkinNylonTint.rgb;
    // (the light that crosses a coloured yarn takes its colour; a pale yarn stops less of it - SheerStudio)
    if (_SheerNylonTint.a > 0.5) through = lerp(through, saturate(through * _SheerNylonTint.rgb), 1.0);
    BaseColor = base * lerp(float3(1, 1, 1), through, covered) * (1.0 - _SkinLiftShade * liftK * Leg.w) * SheerSkirtShade(Rest.y);
    // the torn edge stands ~1 mm off the skin and keeps some light off the skin right under and inside it: a soft, warm
    // contact shadow along the inside of every hole (not where the fabric has been pulled away from its place)
    float2 uvh = SheerDamageTexUV(Leg.xy);
    float hsd = max(((Leg.z > 0 ? DamageL.tex.SampleLevel(DamageL.samplerstate, uvh, 0).r : DamageR.tex.SampleLevel(DamageR.samplerstate, uvh, 0).r) - 0.5) * 2 * SH_DMG_RANGE_SKIN, weltClip);
    // (wider and deeper: the skin in our holes was a flat fill - luminance spread 3 - 5 vs the original's 8 - 11, review
    //  round 9 - the edge shades the skin for some millimetres in)
    // (and not where the fabric - with its holes - has been dragged away: the shadow stayed behind as ghost rings of the
    //  holes on the bare leg while a pull moved them 15 - 20 cm, review round 10)
    float moved = Leg.z > 0 ? SheerClothMoved(Rest, 1.0, LiftL.tex, LiftL.samplerstate) : SheerClothMoved(Rest, -1.0, LiftR.tex, LiftR.samplerstate);
    float lip = sh_smooth(-0.0070, -0.0002, hsd) * sh_smooth(0.0030, 0.0004, hsd) * Leg.w * (1.0 - liftK) * sh_smooth(0.006, 0.002, moved) * (1.0 - _SheerSkinK.x);
    BaseColor *= lerp(float3(1.0, 1.0, 1.0), float3(0.80, 0.73, 0.72), lip * lip * _SkinRimShade);
    // the skin under the toes where they rest on the floor: in the same shade as the stocking over it (SheerTights.hlsl)
    float yWc = PositionWS.y + _WorldSpaceCameraPos.y;
    BaseColor *= 1.0 - sh_smooth(0.011, 0.0012, yWc) * sh_smooth(0.10, 0.06, Rest.y) * lerp(0.62, 0.92, saturate(0.2 - 1.5 * normalize(NormalWS).y));
    Smoothness = 1.0 - lerp(0.36, 0.52, n2);
    // pores / micro relief (0.7 mm): fade it out when it gets sub-pixel, else it sparkles
    float fp = max(length(fwidth(Rest)), 1e-6);
    float relief = 1.0 - saturate((fp / 0.0007 - 0.3) / 0.5);
    float vd; float3 vc; sh_voronoi(bp * 1400.0, vd, vc);
    float hgt = vd * 0.6 + sh_noise(bp, 700, 3, 0.5) * 0.4;
    NormalOut = sh_bump(normalize(NormalWS), PositionWS, hgt, 0.0004, 0.55 * relief);
    CoatMask = 0.08;
    // toenails: the plate is paler and pinker than the skin round it (the nail bed through the horn), glossy, with a lighter
    // free edge at the tip; the folds round it sit in a soft shade. (_SheerPolish: lacquer over it - parked.)
    float nailTip, nailRim; float nail = SheerNail(Rest, nailTip, nailRim);
    [branch] if (nail > 0.0 || nailRim > 0.0)
    {
        BaseColor *= 1.0 - 0.20 * nailRim * (1.0 - nail);
        float3 bed = BaseColor * float3(1.06, 0.92, 0.90) + 0.015;
        float3 plate = _SheerPolish.a > 0.5 ? _SheerPolish.rgb : lerp(bed, saturate(BaseColor * 1.22 + 0.07), nailTip);
        BaseColor = lerp(BaseColor, plate, nail);
        Smoothness = lerp(Smoothness, _SheerPolish.a > 0.5 ? 0.9 : 0.76, nail);
        NormalOut = normalize(lerp(NormalOut, normalize(NormalWS), nail));
        CoatMask = lerp(CoatMask, _SheerPolish.a > 0.5 ? 1.0 : 0.6, nail);
    }
}

#endif
