// SHEER — the player's look (SheerStudio / SheerLook.cs): stocking colour, finish, pattern and top band; skin tone; skirt
// cloth; floor and backdrop. Every value is a global set by SheerStudio; all zero (no Studio: editor tools, old captures)
// means "the calibrated original look", so nothing here changes a picture unless the player asks for it.
#ifndef SHEER_LOOK_INCLUDED
#define SHEER_LOOK_INCLUDED

// ---- stockings
float4 _SheerTint;        // rgb: yarn colour multiplier (chosen / calibrated black), a: 1 = set (0 = original look)
float4 _SheerTint2;       // x: how much the yarn shadows what lies behind it (dark yarn 1 .. white ~0.35), y: gloss 0..1, z: glitter 0..1
float4 _SheerPat;         // x: pattern (0 plain, 1 back seam + Cuban heel, 2 fishnet, 3 polka dots, 4 hearts, 5 stripes,
                          //    6 argyle), y: scale, z: sheer knit kept under a fishnet (0..1), w: 1 = back seam with any pattern
float4 _SheerPatCol;      // rgb: pattern colour (linear), a: 1 = set
float4 _SheerBand;        // x: top of the stocking (rest height m; 0 or >= 0.99 = pantyhose to the waist), y: welt height (m),
                          // z: lace (0 / 1), w: how far the welt presses into the leg (m)
float4 _SheerBandCol;     // rgb: welt / lace colour (linear), a: 1 = set (else the stocking's colour)
TEXTURE2D(_SheerCircTex); // circumference (m) of the leg at damage z (SheerDamage.ZMin + 1 m over the texture's width; row 0 left, 1 right)
float _SheerCircZ0;       // damage z of the circumference table's first texel (= SheerDamage.ZMin)

// ---- skin
float4 _SheerSkinTone;    // rgb: albedo multiplier, a: 1 = set
float4 _SheerNylonTint;   // rgb: colour of the light that crosses the yarn onto the skin (white = neutral), a: 1 = set

// ---- skirt
float4 _SheerSkirt;       // x: style (0 plain charcoal, 1 sailor stripes, 2 tartan, 3 pinstripe, 4 gingham), y: accent width scale
float4 _SheerSkirtCol;    // rgb: main colour (linear), a: 1 = set
float4 _SheerSkirtAcc;    // rgb: accent colour (stripes, lines), a: 1 = set
float4 _SheerSkirtAcc2;   // rgb: second accent (tartan), a: 1 = set

// ---- floor / backdrop
float4 _SheerFloor;       // x: floor (0 drop cloth, 1 oak boards, 2 tatami, 3 gym mat, 4 fluffy rug, 5 marble, 6 grass, 7 stage)
float4 _SheerFloorCol;    // rgb: tint for the floors that take one (mat, rug), a: 1 = set
float4 _SheerBack;        // x: backdrop (0 studio blue, 1 sakura dusk, 2 night city, 3 pastel dream, 4 shoji room, 5 gym,
                          //    6 starry night, 7 two-colour gradient), y: brightness, z: animation speed
float4 _SheerBackCol0, _SheerBackCol1;   // the two-colour gradient (linear, top / bottom)

// ---- body shape (TightsSim.SetShape): per rest height and leg, (scale, inner surface x, axis z); _SheerShape.x = 1 when set
TEXTURE2D(_SheerShapeTex);
float4 _SheerShape;
// a rest point of the body / stocking moved to the chosen leg shape: x scaled about the leg's inner surface, z about its axis
float3 SheerShapePoint(float3 p, float side)
{
    if (_SheerShape.x < 0.5) return p;
    float4 s = SAMPLE_TEXTURE2D_LOD(_SheerShapeTex, s_linear_clamp_sampler, float2(saturate(p.y), side > 0.0 ? 0.25 : 0.75), 0);
    return float3(s.g + s.r * (p.x - s.g), p.y, s.b + s.r * (p.z - s.b));
}

float SheerLookSmooth(float e0, float e1, float x) { float t = saturate((x - e0) / (e1 - e0)); return t * t * (3.0 - 2.0 * t); }

// ---- TOENAILS: ten nails found on the body mesh (the toe tips' front-most points, the nail a few mm back on the toe's
// top), each an ellipse in its own tangent plane: _SheerNails[i] = (centre, half width), _SheerNailsN[i] = (normal, half
// length). The skin shows them always (user, 2026-11-17: 'model appears to have no toenails, which is disturbing'): a
// paler, glossier plate with a lighter free edge at the tip and a soft groove round it. _SheerPolish = (colour, 1 =
// painted; parked). Seen through the stockings.
float4 _SheerNails[10];
float4 _SheerNailsN[10];
float4 _SheerPolish;
// sandal toe (x = 1): no reinforced toe - the foot is knitted as sheer as the leg to the tips (SheerTights)
float4 _SheerToeStyle;
// mask of the nail plate (0..1); tip = its free edge (0..1); rim = the groove round the plate (0..1, outside its tip)
float SheerNail(float3 rest, out float tip, out float rim)
{
    tip = 0.0; rim = 0.0;
    float px = max(length(fwidth(rest)), 1e-6);          // (metres per pixel - before any branch: derivatives need uniform flow)
    if (rest.y > 0.04 || rest.z > -0.08) return 0.0;
    float m = 0.0;
    [loop] for (int i = 0; i < 10; i++)
    {
        float3 d = rest - _SheerNails[i].xyz, n = _SheerNailsN[i].xyz;
        float h = dot(d, n);
        if (abs(h) > 0.004) continue;
        float3 f = normalize(float3(0.0, 0.0, -1.0) - n * dot(float3(0.0, 0.0, -1.0), n));     // along the toe, toward its tip
        float3 b = cross(n, f);
        float2 q = float2(dot(d, b) / _SheerNails[i].w, dot(d, f) / _SheerNailsN[i].w);
        // (a nail: rounded at the cuticle, the free edge squarer at the tip)
        float qy = q.y > 0.0 ? q.y * 0.92 : q.y;
        float e = length(float2(q.x, qy * (qy > 0.0 ? 1.0 : 1.08)));
        float aa = max(px / min(_SheerNails[i].w, _SheerNailsN[i].w), 1e-3);
        float inH = SheerLookSmooth(0.004, 0.0025, abs(h));
        float mi = saturate((1.0 - e) / aa + 0.5) * inH;
        if (mi > m) { m = mi; tip = SheerLookSmooth(0.50, 0.72, q.y); }
        // the nail folds: a band round the plate's edge, fading toward the tip (the free edge has no fold)
        rim = max(rim, inH * SheerLookSmooth(0.74, 0.98, e) * SheerLookSmooth(1.28, 1.02, e) * SheerLookSmooth(0.55, 0.15, q.y));
    }
    return m;
}
float SheerLookHash(float2 p) { p = frac(p * float2(123.34, 456.21)); p += dot(p, p + 45.32); return frac(p.x * p.y); }

bool SheerHasBand() { return _SheerBand.x > 0.0 && _SheerBand.x < 0.99; }

// leg circumference at damage z (the maps' metric, so a pattern's size matches the tears')
float SheerCirc(float z, float side)
{
    float c = SAMPLE_TEXTURE2D_LOD(_SheerCircTex, s_linear_clamp_sampler, float2(saturate(z - _SheerCircZ0), side > 0.0 ? 0.25 : 0.75), 0).r;
    return c > 0.01 ? c : 0.25;
}

// How far the welt of a thigh-high presses into the leg (negative: inward, m) and how the flesh rises just above it
// (a slight bulge where the band holds the thigh) - for skin and stocking alike, along the surface normal.
float SheerBandOffset(float y)
{
    if (!SheerHasBand()) return 0.0;
    float H = _SheerBand.x, wh = max(_SheerBand.y, 0.01), s = _SheerBand.w;
    float inBand = SheerLookSmooth(H - wh - 0.004, H - wh + 0.004, y) * SheerLookSmooth(H + 0.002, H - 0.001, y);
    float above = SheerLookSmooth(H - 0.001, H + 0.004, y) * SheerLookSmooth(H + 0.024, H + 0.006, y);
    return -s * inBand + 1.5 * s * above;
}

// 2-D heart (Inigo Quilez's exact SDF): tip at the origin, about 1 across, pointing down
float SheerSdHeart(float2 p)
{
    p.x = abs(p.x);
    if (p.y + p.x > 1.0) { float2 d = p - float2(0.25, 0.75); return sqrt(dot(d, d)) - 0.35355339; }
    float2 a = p - float2(0.0, 1.0), b = p - 0.5 * max(p.x + p.y, 0.0);
    return sqrt(min(dot(a, a), dot(b, b))) * sign(p.x - p.y);
}

struct SheerPatOut
{
    float cov;       // coverage the pattern asks for ...
    float covW;      // ... and how firmly (0: the knit's own)
    float replace;   // 1: the pattern replaces the knit (fishnet), which keeps _SheerPat.z of itself
    float mix;       // share of the pattern colour
    float dark;      // darker, denser yarn (seam, heel)
    float cut;       // 1: no stocking here (above a thigh-high's top)
    float rib;       // relief of the welt's ribs (0..1) and of the fishnet's cords
    float ribW;
    float welt;      // the welt / lace of a thigh-high (its own colour)
    float3 seg;      // fishnet: the nearest cord segment (knot to knot) - its middle (U, Vz) and how far along it this point
                     // is from the nearer knot (0 .. 0.5): a tear breaks whole segments (SheerTights)
};

// how much less the stocking covers the skin between its threads than the knit does (fishnet: 1 - the sheer layer under
// the net): the skin's nylon shade, tint and the contact shadow at the holes' edges scale with what really covers it
float4 _SheerSkinK;

// The stocking's pattern at damage coordinates (U around 0..1 with 0 at the back, Vz along the wale, Vh rest height).
SheerPatOut SheerPattern(float U, float Vz, float Vh, float side)
{
    SheerPatOut o; o.cov = 0.0; o.covW = 0.0; o.replace = 0.0; o.mix = 0.0; o.dark = 0.0; o.cut = 0.0; o.rib = 0.0; o.ribW = 0.0; o.welt = 0.0; o.seg = 0.0;
    float id = _SheerPat.x, sc = max(_SheerPat.y, 0.25);
    // A knitted-in pattern repeats a WHOLE number of times round the tube, the same number all the way up (the needles
    // don't change): it is counted on the machine's circumference Ck, and where the worn leg is wider (C, the thigh) each
    // repeat is stretched wider with the fabric - fishnet diamonds open at the thigh, dots grow oval - as on real legs.
    // Widths that don't stretch (the cords, a sewn seam) are in the worn metres of C.
    const float Ck = 0.25;
    float C = SheerCirc(Vz, side);
    float uc = U - floor(U + 0.5);                       // -0.5 .. 0.5, 0 = the back
    float su = uc * C;                                   // worn metres round the leg from the back
    float dVz = max(fwidth(Vz), 1e-6);
    float dU = max(min(fwidth(U), fwidth(uc)), 1e-7);    // (U wraps at the back, uc at the front: one is always smooth)
    if ((id > 0.5 && id < 1.5) || _SheerPat.w > 0.5)
    {
        // a fully-fashioned BACK SEAM up the back of the leg, from the point of a reinforced CUBAN HEEL (the heel's dense,
        // squared patch at the back, ending in a point)
        float d = abs(su), aa = max(fwidth(su), 1e-5);
        const float heelTop = 0.088;
        float seamL = saturate((0.00055 - d) / aa + 0.5) * SheerLookSmooth(heelTop - 0.006, heelTop - 0.002, Vz);
        float hwH = 0.024 * saturate((heelTop - Vz) / 0.030);
        float heel = saturate((hwH - d) / aa + 0.5) * step(-0.06, Vz);
        float side = saturate((0.0016 - d) / aa + 0.5) * SheerLookSmooth(heelTop - 0.006, heelTop - 0.002, Vz) - seamL;
        if (SheerHasBand()) seamL *= step(Vh, _SheerBand.x - _SheerBand.y);
        o.cov = max(o.cov, 0.975); o.covW = max(o.covW, max(seamL, heel * 0.9));
        o.dark = max(o.dark, max(seamL * 0.75, heel * 0.45));
        o.cov = max(o.cov, 0.9); o.covW = max(o.covW, side * 0.3);
        o.rib = max(o.rib, seamL); o.ribW = max(o.ribW, seamL * 0.6);
    }
    if (id > 1.5 && id < 2.5)
    {
        // FISHNET: diamonds of thick cord knotted at every crossing (no knit between: _SheerPat.z keeps some sheer layer)
        float a = 0.0125 * sc, n = max(round(Ck / a), 6.0), cx = C / n;
        float f1 = U * n + Vz / a, f2 = U * n - Vz / a;
        float k = rsqrt(1.0 / (cx * cx) + 1.0 / (a * a));
        float d1 = abs(f1 - round(f1)) * k, d2 = abs(f2 - round(f2)) * k;
        // the cord this point is on: along f1 = const between two knots, or along f2 = const
        float2 g = d1 < d2 ? float2(round(f1), floor(f2) + 0.5) : float2(floor(f1) + 0.5, round(f2));
        float tk = d1 < d2 ? frac(f2) : frac(f1);
        o.seg = float3((g.x + g.y) / (2.0 * n), 0.5 * a * (g.x - g.y), min(tk, 1.0 - tk));
        float w = 0.0007 * sqrt(sc), aa = max(max(dU * n, dVz / a) * k, 1e-5);
        float cord = saturate((w - min(d1, d2)) / aa + 0.5);
        float knot = saturate((w * 1.7 - max(d1, d2)) / aa + 0.5);
        cord = max(cord, knot);
        float px = a / dVz;                              // a diamond in pixels: below ~6 px only its mean coverage
        cord = lerp(saturate(2.2 * w / (a * 0.72)), cord, SheerLookSmooth(4.0, 9.0, px));
        o.cov = cord * 0.97; o.covW = 1.0; o.replace = 1.0;
        o.rib = cord; o.ribW = SheerLookSmooth(4.0, 9.0, px) * 0.8;
    }
    else if (id > 2.5 && id < 4.5)
    {
        // POLKA DOTS / HEARTS knitted in, in staggered rows (each row has a whole number of them round the leg)
        float p = 0.024 * sc, row = floor(Vz / p);
        float n = max(round(Ck / p), 3.0), off = (row - 2.0 * floor(row * 0.5)) * 0.5;
        float fu = frac(U * n + off) - 0.5, fz = frac(Vz / p) - 0.5;
        float2 q = float2(fu * Ck / n, fz * p);          // (the knit's metric: the dot widens with the fabric)
        float sd;
        if (id < 3.5) sd = length(q) - 0.0042 * sc;
        else { float hs = 0.0105 * sc; sd = SheerSdHeart(float2(q.x, -q.y) / hs + float2(0.0, 0.55)) * hs; }
        float aa = max(max(dU * Ck, dVz) * 1.2, 1e-5);
        float m = saturate(0.5 - sd / aa);
        float px = p / dVz;
        m = lerp(0.12, m, SheerLookSmooth(3.0, 7.0, px));
        o.cov = 0.93; o.covW = m; o.mix = m;
    }
    else if (id > 4.5 && id < 5.5)
    {
        // STRIPES round the leg (opaque knit in two colours, like striped over-knee socks)
        float per = 0.026 * sc, t = frac(Vz / per), aa = max(dVz / per, 1e-5);
        float s = saturate((abs(t - 0.5) - 0.25) / aa + 0.5);
        float px = per / dVz;
        s = lerp(0.5, s, SheerLookSmooth(3.0, 6.0, px));
        o.cov = 0.95; o.covW = 1.0; o.mix = s;
    }
    else if (id > 5.5 && id < 6.5)
    {
        // ARGYLE: diamonds in the pattern colour with a thin over-check seamL in the stocking's own, on an opaque knit
        float a = 0.034 * sc, n = max(round(Ck / (a * 0.75)), 4.0), cx = C / n;
        float x = frac(U * n) - 0.5, y = frac(Vz / a + 0.5 * (floor(U * n) - 2.0 * floor(floor(U * n) * 0.5))) - 0.5;
        float dia = abs(x) + abs(y);
        float aa = max(fwidth(Vz / a) * 1.5, 1e-4);
        float inD = saturate((0.5 - dia) / aa + 0.5);
        float f1 = U * n * 0.5 + Vz / (2.0 * a), f2 = U * n * 0.5 - Vz / (2.0 * a);
        float k = rsqrt(4.0 / (cx * cx) + 1.0 / (a * a) * 4.0);
        float l = min(abs(f1 - round(f1)), abs(f2 - round(f2))) * 2.0 * k;
        float seamL = saturate((0.0005 - l) / max(fwidth(f1) * 2.0 * k, 1e-5) + 0.5);
        float px = a / dVz;
        inD = lerp(0.5, inD, SheerLookSmooth(3.0, 7.0, px)); seamL *= SheerLookSmooth(5.0, 10.0, px);
        o.cov = 0.95; o.covW = 1.0; o.mix = inD * (1.0 - seamL); o.dark = seamL * 0.4;
    }
    // the TOP of thigh-highs / over-knees / knee-highs: a dense welt, a lace edge in scallops, nothing above
    if (SheerHasBand())
    {
        float H = _SheerBand.x, wh = max(_SheerBand.y, 0.01), lace = _SheerBand.z;
        // (scallops and eyelets: a whole number round the leg at the band - no break where the rows meet at the front)
        float Cb = SheerCirc(H, side);
        float nS = max(round(Cb / 0.0105), 8.0), fk = frac(uc * nS) - 0.5;
        float edge = H - lerp(0.0, 0.0042 * (1.0 - sqrt(saturate(1.0 - 4.0 * fk * fk))), lace);
        float aa = max(fwidth(Vh), 1e-5);
        o.cut = saturate((Vh - edge) / aa + 0.5);
        float welt = SheerLookSmooth(H - wh - 0.0015, H - wh + 0.0015, Vh);
        float lw = 0.020 * lace;                          // lace height
        float inLace = lace * SheerLookSmooth(H - lw - 0.001, H - lw + 0.001, Vh);
        // lace: a vine of small eyelets and petals in a dense net
        float row = floor((Vh - (H - lw)) / 0.0062);
        float nE = max(round(Cb / 0.0062), 8.0);
        float2 q = float2((frac(uc * nE + 0.5 * (row - 2.0 * floor(row * 0.5))) - 0.5) * (Cb / nE), (frac((Vh - (H - lw)) / 0.0062) - 0.5) * 0.0062);
        float eye = saturate((0.0016 - length(q)) / max(aa * 1.2, 1e-5) + 0.5);
        float petal = saturate((0.0026 - length(q - float2(0.0, 0.0018))) / max(aa * 1.2, 1e-5) + 0.5) - eye;
        float laceCov = lerp(0.82, 0.12, eye) + 0.12 * saturate(petal);
        float bandCov = lerp(0.965, laceCov, inLace);
        o.cov = lerp(o.cov, max(o.cov, bandCov), welt); o.covW = lerp(o.covW, 1.0, welt);
        o.replace *= 1.0 - welt;
        o.mix = lerp(o.mix, 0.0, welt); o.welt = welt;
        o.rib = lerp(o.rib, 0.5 + 0.5 * sin(Vh * (6.2831853 / 0.0022)), welt * (1.0 - inLace)); o.ribW = lerp(o.ribW, 0.7, welt);
        o.dark = lerp(o.dark, 0.0, welt);
    }
    return o;
}
#endif
