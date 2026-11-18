// SHEER — reading the cloth simulation (TightsCloth.cs / SheerCloth.compute) in the surface shaders.
// Per leg: _ClothDisp (xyz displacement of the worn stocking in mesh space, w = lift above the leg, m),
// _ClothNrm (change of the surface normal), _ClothTens (largest / smallest in-plane stretch, direction of the
// largest as (cos 2a, sin 2a), a measured from 'around the leg'). The lattice is addressed by the rest position of a
// point: its height and its angle about the lattice's own leg axis (_SheerClothAxis), exactly as the simulation does.
#ifndef SHEER_CLOTH_INCLUDED
#define SHEER_CLOTH_INCLUDED
#include "Assets/Sheer/Shaders/SheerLook.hlsl"

// set by TightsSim: row parameter S of row 0, rows per metre, 1 / columns, 1 / rows (all zero while no simulation runs)
float4 _SheerClothGrid;
float _SheerDispFadeL, _SheerDispFadeR, _SheerDispFadePrevL, _SheerDispFadePrevR;   // release fade of the drawn displacement (TightsSim)
// set by TightsSim: extra stand-off of the stocking shell from the skin (m): everywhere / more at knee and ankle
float _SheerShellGap, _SheerShellGapBend;
// set by TightsSim: how far the stocking is drawn toward the eye (m, depth only)
float _SheerDepthBias;
// set by TightsSim: mip level at which fabric lying ON the leg reads the simulation's tension and normal maps (2 = averaged
// over ~4 lattice cells, 6 - 9 mm). Gathered nylon on a leg is a pile of wrinkles a millimetre high: what one sees is a soft
// dark blotch ahead of the fingers and a paler fan behind them (the original's knee pinch, 0 - 0.6 s). The lattice's cells
// are 1.4 x 2.2 mm: read cell by cell, a row of jammed cells drew a razor-sharp dark line and the stretched fan a flat sheet
// with ruled edges - 'a folded sheet of paper' (free-play sweep 2026-11-17). Fabric lifted off the leg keeps every crease.
float _SheerSoftLod;

// The body's pose (TightsSim.PushPose, same math as PoseMath in TightsSim.cs): per leg and per height (512 bins over
// 0 .. 1 m of rest height) every horizontal cross-section moves rigidly - shifted by (dx, dz) and turned by phi about the
// vertical through the leg's axis - so skin and stocking at one height move together and can never cross. Joints: the
// shin turns about the ankle (feet planted), the thigh about the hip, the foot about the ankle (toes in); the knees turn
// in, come forward, the body leans; the big toes lift about their joints first. What straddles the midline blends the
// two legs' poses. Table rows: 0 / 1 = (dx, dz, phi) of the +x / -x leg, 2 / 3 = the turning centres (x, z).
// _SheerPoseParams.x = bins (0: no pose). The ...Prev set is what the previous frame was drawn with (motion vectors).
TEXTURE2D(_SheerPoseTex);
TEXTURE2D(_SheerPoseTexPrev);
float4 _SheerPoseParams, _SheerPoseParamsPrev;
float4 _SheerToe, _SheerToePrev;          // big toes lifted (rad): x = +x leg, y = -x leg
float4 _SheerToeGeo;                      // x: |x| of the cleft to the second toe, y / z: height / depth of the toe's joint (m)

float SheerSmooth(float e0, float e1, float x) { float t = saturate((x - e0) / (e1 - e0)); return t * t * (3.0 - 2.0 * t); }

// the big toe lifted by alpha (rad) about its joint (rest space); w = how much of it this point takes
float3 SheerToeRaise(float3 p, float alpha, float s, out float b)
{
    b = 0.0;
    if (alpha <= 0.0) return p;
    float w = SheerSmooth(_SheerToeGeo.z + 0.006, _SheerToeGeo.z - 0.014, p.z)
            * (1.0 - SheerSmooth(_SheerToeGeo.x - 0.006, _SheerToeGeo.x + 0.003, s * p.x)) * SheerSmooth(0.056, 0.042, p.y);
    b = alpha * w;
    float sb, cb; sincos(b, sb, cb);
    float dy = p.y - _SheerToeGeo.y, dz = p.z - _SheerToeGeo.z;
    return float3(p.x, _SheerToeGeo.y + dy * cb - dz * sb, _SheerToeGeo.z + dy * sb + dz * cb);
}

// one leg's cross-section transform at the height of p
float3 SheerPoseLegOf(TEXTURE2D_PARAM(tex, smp), float3 p, float leg, out float phi)
{
    float u = saturate(p.y);
    float4 a = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(u, leg * 0.25 + 0.125), 0);
    float2 c = SAMPLE_TEXTURE2D_LOD(tex, smp, float2(u, leg * 0.25 + 0.625), 0).xy;
    phi = a.z;
    float sn, cs; sincos(a.z, sn, cs);
    float2 r = p.xz - c;
    return float3(c.x + r.x * cs + r.y * sn + a.x, p.y, c.y - r.x * sn + r.y * cs + a.y);
}

// posed position of a rest-space point; with n: the normal carried along (exact for the rigid cross-sections: turned
// with them, then tilted by how the posed section shifts with height). sx: the rest x that says whose leg the point is
// (the point's own for skin; for pulled fabric where it is WORN - a tent drawn from one leg across the midline still
// moves with that leg: posed with the other leg's twist and knee its tip broke off and jumped, into the other leg)
float3 SheerPosePointOf(TEXTURE2D_PARAM(tex, smp), float4 toe, float3 p, float sx, inout float3 n, out float phiOut, bool wantN)
{
    float wl = SheerSmooth(-0.004, 0.004, sx);
    float3 q = 0.0, nq = 0.0; float wsum = 0.0; phiOut = 0.0;
    [unroll] for (int k = 0; k < 2; k++)
    {
        float w = k == 0 ? wl : 1.0 - wl;
        if (w <= 0.0) continue;
        float s = k == 0 ? 1.0 : -1.0, b, phi, phiA, phiB;
        float3 pr = SheerToeRaise(p, k == 0 ? toe.x : toe.y, s, b);
        float3 ql = SheerPoseLegOf(TEXTURE2D_ARGS(tex, smp), pr, k, phi);
        q += w * ql; phiOut += w * phi;
        if (wantN)
        {
            // the toe's turn about x, then the section's turn about y, then the shear of the section's drift with height
            float3 nn = n;
            if (b > 0.0) { float sb, cb; sincos(b, sb, cb); nn = float3(nn.x, nn.y * cb + nn.z * sb, -nn.y * sb + nn.z * cb); }
            float sn, cs; sincos(phi, sn, cs);
            nn = float3(nn.x * cs + nn.z * sn, nn.y, -nn.x * sn + nn.z * cs);
            const float e = 0.004;
            float3 qa = SheerPoseLegOf(TEXTURE2D_ARGS(tex, smp), pr + float3(0, e, 0), k, phiA);
            float3 qb = SheerPoseLegOf(TEXTURE2D_ARGS(tex, smp), pr - float3(0, e, 0), k, phiB);
            float2 t = (qa.xz - qb.xz) / (2.0 * e);
            nn.y -= dot(t, nn.xz);
            nq += w * nn;
        }
        wsum += w;
    }
    if (wantN) n = nq;
    phiOut /= max(wsum, 1e-6);
    return q / max(wsum, 1e-6);
}

// posed position, normal and tangent (the tangent turns with its cross-section); sx: see SheerPosePointOf
float3 SheerPosePoint(float3 p, float sx, inout float3 n, inout float3 tg)
{
    if (_SheerPoseParams.x <= 0.0) return p;
    float phi;
    float3 q = SheerPosePointOf(TEXTURE2D_ARGS(_SheerPoseTex, s_linear_clamp_sampler), _SheerToe, p, sx, n, phi, true);
    float sn, cs; sincos(phi, sn, cs);
    tg = float3(tg.x * cs + tg.z * sn, tg.y, -tg.x * sn + tg.z * cs);
    return q;
}

// the same one frame ago (the current one while no previous pose has been pushed)
float3 SheerPosePointPrev(float3 p, float sx)
{
    if (_SheerPoseParams.x <= 0.0) return p;
    float3 n = 0.0; float phi;
    if (_SheerPoseParamsPrev.x <= 0.0) return SheerPosePointOf(TEXTURE2D_ARGS(_SheerPoseTex, s_linear_clamp_sampler), _SheerToe, p, sx, n, phi, false);
    return SheerPosePointOf(TEXTURE2D_ARGS(_SheerPoseTexPrev, s_linear_clamp_sampler), _SheerToePrev, p, sx, n, phi, false);
}

// ONE lattice per leg, toes to under the skirt (ClothLattice in TightsCloth.cs): rows are cross-sections of the stocking by
// planes - horizontal on the leg (rest height >= _SheerSock.x), half-planes through the bend's axis (a line along x at
// height _SheerSock.x, depth _SheerSock.y, in front of the ankle) round ankle and heel, vertical (z = const) along the
// foot - so each column is one wale from the toe seam up the leg. Row parameter S: 0 at the toe tip, + along the foot,
// _SheerSock.z x the bend's angle, + height up the leg; _SheerSock.w = S at the bend's top. In a row's plane a point has
// x and B (z on the leg; zc + its distance from the bend's axis round the bend; zc + yc - y on the foot).
float4 _SheerSock;
// row centres of the lattice: NV x 2 texels (row 0: left / +x leg, row 1: right leg), RG = centre (x, B) per row
TEXTURE2D(_SheerClothAxis);
// per node (Z, u offset of its wale): where it is in the damage maps along its wale below the bend's top (TightsSim)
TEXTURE2D(_SheerClothZL); TEXTURE2D(_SheerClothZR);
float _SheerDamageZ0;                     // z of the damage maps' first row (SheerDamage.ZMin; they cover 1 m from there)

// row parameter S of a rest point and its in-plane coordinate B
float SheerSockS(float3 p, out float B)
{
    float yc = _SheerSock.x, zc = _SheerSock.y;
    if (p.y >= yc) { B = p.z; return _SheerSock.w + (p.y - yc); }
    if (p.z > zc) { float h = yc - p.y, d = p.z - zc; B = zc + sqrt(h * h + d * d); return _SheerSock.w - _SheerSock.z * atan2(h, d); }
    B = zc + (yc - p.y); return _SheerSock.w - _SheerSock.z * 1.5707963 - (zc - p.z);
}

// lattice texture coordinates of a rest-space point of the leg on the given side (+1 / -1)
float2 SheerClothUV(float3 rest, float side)
{
    float B; float S = SheerSockS(rest, B);
    float v = ((S - _SheerClothGrid.x) * _SheerClothGrid.y + 0.5) * _SheerClothGrid.w;
    float2 ax = SAMPLE_TEXTURE2D_LOD(_SheerClothAxis, s_linear_clamp_sampler, float2(v, side > 0.0 ? 0.25 : 0.75), 0).xy;
    float th = atan2(rest.x - ax.x, B - ax.y) * (1.0 / 6.28318530718);
    return float2(th - floor(th) + 0.5 * _SheerClothGrid.z, v);
}

// Damage-map coordinates (u around, z along) of a stocking / skin point: on the leg the mesh's own (legUV: the stocking's
// uv0.xy, the skin's uv2.xy - angle about the leg, rest height); below the bend's top along the wales (TightsSim /
// ClothLattice.DamageUZ), so a ladder from the shin runs on over the ankle onto the foot.
float2 SheerDamageUV(float3 rest, float side, float2 legUV)
{
    if (_SheerSock.x <= 0.0 || rest.y >= _SheerSock.x) return legUV;
    float2 uv = SheerClothUV(rest, side);
    uv.y = clamp(uv.y, 0.5 * _SheerClothGrid.w, 1.0 - 0.5 * _SheerClothGrid.w);      // (the sampler repeats: not past the toe tip)
    float2 zd = side > 0.0 ? SAMPLE_TEXTURE2D_LOD(_SheerClothZL, s_linear_repeat_sampler, uv, 0).xy
                           : SAMPLE_TEXTURE2D_LOD(_SheerClothZR, s_linear_repeat_sampler, uv, 0).xy;
    float u = uv.x - 0.5 * _SheerClothGrid.z + zd.y;
    return float2(u - floor(u), zd.x);
}
// the damage maps' texture coordinates of damage coordinates (u, z) (v kept off the edges: the samplers repeat)
float2 SheerDamageTexUV(float2 uz) { return float2(uz.x, clamp(uz.y - _SheerDamageZ0, 0.00025, 0.99975)); }

// Vertex stage of the skin graph: the pose. Velocity = how far the vertex has moved since the previous frame (object
// space; HDRP's 'custom velocity'): without it the temporal anti-aliasing reprojects the swaying leg as if it stood
// still and smears every fine detail (pores, knit, glints) whenever the body moves.
void SheerPoseVertex_float(float3 PositionOS, float3 NormalOS, float3 TangentOS, out float3 PositionOut, out float3 NormalOut,
                           out float3 TangentOut, out float3 Velocity)
{
    float3 n = NormalOS, t0 = TangentOS;
    PositionOS = SheerShapePoint(PositionOS, PositionOS.x);         // (the chosen body shape)
    PositionOS += NormalOS * SheerBandOffset(PositionOS.y);          // (a thigh-high's welt presses into the thigh)
    PositionOut = SheerPosePoint(PositionOS, PositionOS.x, n, t0);
    float ln = length(n);
    NormalOut = ln > 1e-5 ? n / ln : NormalOS;
    // (the tangent turns with the section too, re-orthogonalised against the posed normal)
    float3 tg = t0 - NormalOut * dot(t0, NormalOut); float lt = length(tg);
    TangentOut = lt > 1e-4 ? tg / lt : TangentOS;
    Velocity = PositionOut - SheerPosePointPrev(PositionOS, PositionOS.x);
}

// The knee pit: the knit bunches in soft horizontal folds behind the knee (the original's orbit views show ~5 - 8 of
// them notching the outline; a normal-only crease never reached the outline - review round 7). Height profile 0..1
// (flat-bottomed valleys, rounded crests), w = where (back of the knee, in patches). rest = rest position, u = around (0 = back).
float SheerKneeCrease(float3 rest, float u, out float w)
{
    float back = saturate((cos(u * 6.2831853) + 0.2) / 0.8); back = back * back * (3.0 - 2.0 * back);
    float a = saturate((rest.y - 0.425) / 0.03), b = saturate((0.525 - rest.y) / 0.03);
    a = a * a * (3.0 - 2.0 * a); b = b * b * (3.0 - 2.0 * b);
    float pw = 0.5 + 0.5 * sin(rest.x * 173.0 + rest.z * 141.0 + 1.7 * sin(rest.y * 260.0));
    // (patchy, each crease its own depth, the spacing wandering more: round 14 counted ~12 thick evenly spaced ridges
    //  scalloping the outline like a ribbed hose; the original's are fine, irregular, the outline smooth)
    w = back * a * b * (0.25 + 0.75 * pw);      // (round 15: 'perfectly smooth' - between round 14's ribs and nothing)
    float ph = rest.y * (6.2831853 / 0.0036) + 3.0 * sin(rest.x * 97.0 - rest.z * 83.0) + 2.2 * sin(rest.y * 410.0 + rest.x * 60.0);   // (finer: round 10 'corrugated hose')
    float wv = 0.5 + 0.5 * sin(ph);
    float amp = 0.3 + 0.7 * frac(sin(floor(ph / 6.2831853) * 12.9898 + 4.1) * 43758.5453);
    return (1.0 - (1.0 - wv) * (1.0 - wv) * (1.0 - wv)) * amp;
}

// Vertex stage of the stocking graphs: the pulled fabric, then the pose where the fabric is now. DispPrev = the
// displacement texture of the previous frame (for Velocity, see above).
void SheerClothVertex_float(float3 PositionOS, float3 NormalOS, float3 TangentOS, float4 UV0, float4 UV1, float4 UV2,
                            UnityTexture2D Disp, UnityTexture2D Nrm, UnityTexture2D DispPrev, out float3 PositionOut,
                            out float3 NormalOut, out float3 TangentOut, out float3 Velocity)
{
    float3 d = 0.0, dp = 0.0, n = NormalOS;
    PositionOS = SheerShapePoint(PositionOS, UV2.x);                // (the chosen body shape: the cloth's rest shape follows it)
    // The shell stands off the skin a little more where the leg bends (knee, ankle): a taut tube bridges what curves
    // away under it. Measured on the original's outlines: ~1 mm on thigh and shin, 2-2.5 mm around the knee.
    float hz = PositionOS.y;
    float kb = saturate(1.0 - abs(hz - 0.47) / 0.085), ab = saturate(1.0 - abs(hz - 0.115) / 0.05);
    float gap = _SheerShellGap + _SheerShellGapBend * max(kb * kb * (3.0 - 2.0 * kb), 0.7 * ab * ab * (3.0 - 2.0 * ab));
    PositionOS += NormalOS * (gap + SheerBandOffset(UV1.y));
    float kneeW; float kneeC = SheerKneeCrease(UV1.xyz, UV0.x, kneeW);
    PositionOS += NormalOS * (0.00032 * kneeW * kneeC);       // (0.45 mm notched the outline: round 14; 0.22 smooth: round 15)
    if (_SheerClothGrid.w > 0.0)
    {
        float2 uv = SheerClothUV(UV1.xyz, UV2.x);
        d = SAMPLE_TEXTURE2D_LOD(Disp.tex, Disp.samplerstate, uv, 0).xyz;
        dp = SAMPLE_TEXTURE2D_LOD(DispPrev.tex, Disp.samplerstate, uv, 0).xyz;
        float rf = UV2.x > 0.0 ? _SheerDispFadeL : _SheerDispFadeR, rfp = UV2.x > 0.0 ? _SheerDispFadePrevL : _SheerDispFadePrevR;
        d *= rf; dp *= rfp;
        // (on the leg the lattice's fine folds shade softer than they stand: gathered nylon lies in soft folds, layer on
        //  layer - read averaged over a centimetre (_SheerSoftLod); fabric lifted off the leg - a tent, a sail - keeps its creases)
        float liftN = SAMPLE_TEXTURE2D_LOD(Disp.tex, Disp.samplerstate, uv, 0).w;
        float crisp = saturate((liftN - 0.002) / 0.01);
        float3 dn = SAMPLE_TEXTURE2D_LOD(Nrm.tex, Nrm.samplerstate, uv, _SheerSoftLod * (1.0 - crisp)).xyz;
        float soft = lerp(0.55, 1.0, crisp);
        n += dn * soft;
    }
    // posed where the fabric is NOW: fabric that has slid along a bent leg must follow the leg there, or it sinks into the
    // skin on one side
    float3 tg0 = TangentOS;
    PositionOut = SheerPosePoint(PositionOS + d, PositionOS.x, n, tg0);
    float ln = length(n);
    NormalOut = ln > 1e-4 ? n / ln : NormalOS;
    float3 t = tg0 - NormalOut * dot(tg0, NormalOut);
    float lt = length(t);
    TangentOut = lt > 1e-4 ? t / lt : TangentOS;
    Velocity = PositionOut - SheerPosePointPrev(PositionOS + dp, PositionOS.x);
    // Toward the eye along the line of sight: the picture does not change, the depth does. Where the simulated fabric
    // dips a millimetre under the skin's surface (drawn taut across the knee) the skin poked through as a pale patch.
    if (_SheerDepthBias > 0.0)
    {
        float3 eyeOS = TransformWorldToObject(float3(0.0, 0.0, 0.0));    // (HDRP's world space is camera-relative: the eye is its origin)
        float3 toEye = eyeOS - PositionOut; float le = length(toEye);
        PositionOut += toEye * (min(_SheerDepthBias, 0.25 * le) / max(le, 1e-5));
    }
}

// The skirt keeps the high lights off the top of the thighs: in the original the stocking is ~20 % darker for the
// first ~10 cm below the hem (colour profiles across the thigh at 0.5 s: 93 at the hem's height vs 127 further down).
// Baked as a soft occlusion by rest height (a real shadow of the hem only reaches ~1 cm with our low key light).
float _SheerHemDrop;      // how much longer the skirt is than the asset (m, SkirtCloth.lengthen): what is measured from its hem follows

float SheerSkirtShade(float height)
{
    height += _SheerHemDrop;
    // (fit: x1.0 at 13 cm below the hem, x0.83 at 8 cm, x0.71 at 3 cm)
    // (+ the contact shadow right under the hem; review round 3: the original's thigh 15 px below the hem is at
    //  64 - 67 % of its level 240 px lower, ours was at 86 - 95 %)
    float t = saturate((height - 0.565) / 0.125), c = saturate((height - 0.635) / 0.05);
    return 1.0 - 0.34 * pow(t, 0.8) - 0.21 * c * c * (3.0 - 2.0 * c);
}

// (largest stretch, smallest stretch, cos 2a, sin 2a); (1, 1, 0, 0) = at rest
float4 SheerClothTension(float3 rest, float side, Texture2D tens, SamplerState ss)
{
    if (_SheerClothGrid.w <= 0.0) return float4(1.0, 1.0, 0.0, 0.0);
    float rf = side > 0.0 ? _SheerDispFadeL : _SheerDispFadeR;          // (with the drawn displacement's release fade)
    return lerp(float4(1.0, 1.0, 0.0, 0.0), tens.SampleLevel(ss, SheerClothUV(rest, side), 0), rf);
}
// ... as the fabric shows it: lying on the leg softened (see _SheerSoftLod), lifted off it (lift, m) cell by cell
float4 SheerClothTensionSeen(float3 rest, float side, Texture2D tens, SamplerState ss, float lift)
{
    if (_SheerClothGrid.w <= 0.0) return float4(1.0, 1.0, 0.0, 0.0);
    float rf = side > 0.0 ? _SheerDispFadeL : _SheerDispFadeR;
    float crisp = saturate((lift - 0.002) / 0.012);
    float2 uv = SheerClothUV(rest, side);
    float lod = _SheerSoftLod * (1.0 - crisp);
    float4 t = tens.SampleLevel(ss, uv, lod);
    // (where the knit is pushed together, a centimetre of fabric covers a third of that in the picture: read wider there,
    //  or the edge of the gathered pile stayed razor-sharp)
    float sqz = saturate((0.75 - t.y) / 0.35) * (1.0 - crisp);
    if (sqz > 0.0 && _SheerSoftLod > 0.0) t = tens.SampleLevel(ss, uv, lod + 1.5 * sqz);
    return lerp(float4(1.0, 1.0, 0.0, 0.0), t, rf);
}

// lift of the fabric above the leg (m)
float SheerClothLift(float3 rest, float side, Texture2D disp, SamplerState ss)
{
    if (_SheerClothGrid.w <= 0.0) return 0.0;
    return disp.SampleLevel(ss, SheerClothUV(rest, side), 0).w * (side > 0.0 ? _SheerDispFadeL : _SheerDispFadeR);
}
// how far the fabric over this point has moved from where it is worn (m)
float SheerClothMoved(float3 rest, float side, Texture2D disp, SamplerState ss)
{
    if (_SheerClothGrid.w <= 0.0) return 0.0;
    return length(disp.SampleLevel(ss, SheerClothUV(rest, side), 0).xyz) * (side > 0.0 ? _SheerDispFadeL : _SheerDispFadeR);
}
#endif
