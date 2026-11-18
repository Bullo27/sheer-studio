// SHEER — shared procedural helpers (Blender-equivalent noise, voronoi, bump) for the Sheer shaders.
#ifndef SHEER_NOISE_INCLUDED
#define SHEER_NOISE_INCLUDED
#define SH_TAU 6.28318530718

float sh_saturate(float x) { return saturate(x); }
float sh_smooth(float e0, float e1, float x)       // smoothstep that also accepts e0 > e1 (Blender Map Range)
{
    float t = saturate((x - e0) / (e1 - e0));
    return t * t * (3.0 - 2.0 * t);
}
float sh_hash11(float p) { p = frac(p * 0.1031); p *= p + 33.33; p *= p + p; return frac(p); }
float sh_hash21(float2 p) { float3 p3 = frac(p.xyx * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
float3 sh_hash33(float3 p3)
{
    p3 = frac(p3 * float3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yxz + 33.33);
    return frac((p3.xxy + p3.yxx) * p3.zyx);
}
// gradient noise, ~[-1, 1]
float sh_gnoise(float3 p)
{
    float3 i = floor(p), f = frac(p);
    float3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
    float n000 = dot(sh_hash33(i + float3(0, 0, 0)) * 2 - 1, f - float3(0, 0, 0));
    float n100 = dot(sh_hash33(i + float3(1, 0, 0)) * 2 - 1, f - float3(1, 0, 0));
    float n010 = dot(sh_hash33(i + float3(0, 1, 0)) * 2 - 1, f - float3(0, 1, 0));
    float n110 = dot(sh_hash33(i + float3(1, 1, 0)) * 2 - 1, f - float3(1, 1, 0));
    float n001 = dot(sh_hash33(i + float3(0, 0, 1)) * 2 - 1, f - float3(0, 0, 1));
    float n101 = dot(sh_hash33(i + float3(1, 0, 1)) * 2 - 1, f - float3(1, 0, 1));
    float n011 = dot(sh_hash33(i + float3(0, 1, 1)) * 2 - 1, f - float3(0, 1, 1));
    float n111 = dot(sh_hash33(i + float3(1, 1, 1)) * 2 - 1, f - float3(1, 1, 1));
    float nx00 = lerp(n000, n100, u.x), nx10 = lerp(n010, n110, u.x), nx01 = lerp(n001, n101, u.x), nx11 = lerp(n011, n111, u.x);
    return 1.6 * lerp(lerp(nx00, nx10, u.y), lerp(nx01, nx11, u.y), u.z);
}
// Blender 'Noise Texture' Fac (fBm, 0..1 centred on 0.5): scale, detail (octaves - 1), roughness
float sh_noise(float3 p, float scale, float detail, float rough)
{
    p *= scale;
    float sum = 0, amp = 1, norm = 0;
    int oct = (int)detail + 1;
    [loop] for (int i = 0; i < oct; i++) { sum += sh_gnoise(p) * amp; norm += amp; amp *= rough; p *= 2.0; }
    return saturate(0.5 + 0.5 * sum / norm);
}
float3 sh_noise3(float3 p, float scale, float detail, float rough)
{
    return float3(sh_noise(p, scale, detail, rough), sh_noise(p + float3(31.4, 17.9, 7.3), scale, detail, rough),
                  sh_noise(p + float3(-13.1, 47.7, 23.9), scale, detail, rough));
}
// Blender 'Voronoi Texture' F1 3D: distance + random cell colour
void sh_voronoi(float3 p, out float dist, out float3 col)
{
    float3 i = floor(p), f = frac(p);
    dist = 8.0; col = 0;
    [unroll] for (int z = -1; z <= 1; z++)
    [unroll] for (int y = -1; y <= 1; y++)
    [unroll] for (int x = -1; x <= 1; x++)
    {
        float3 c = float3(x, y, z);
        float3 r = c + sh_hash33(i + c) - f;
        float d = length(r);
        if (d < dist) { dist = d; col = sh_hash33(i + c + 17.31); }
    }
}
// the same, also returning the vector from the nearest feature point to p (cell units)
void sh_voronoiR(float3 p, out float dist, out float3 col, out float3 off)
{
    float3 i = floor(p), f = frac(p);
    dist = 8.0; col = 0; off = 0;
    [unroll] for (int z = -1; z <= 1; z++)
    [unroll] for (int y = -1; y <= 1; y++)
    [unroll] for (int x = -1; x <= 1; x++)
    {
        float3 c = float3(x, y, z);
        float3 r = c + sh_hash33(i + c) - f;
        float d = length(r);
        if (d < dist) { dist = d; col = sh_hash33(i + c + 17.31); off = -r; }
    }
}
// Blender 'Bump' node (Mikkelsen surface gradient from screen-space derivatives)
float3 sh_bump(float3 N, float3 posWS, float h, float dist, float strength)
{
    float3 dpdx = ddx(posWS), dpdy = ddy(posWS);
    float dhdx = ddx(h) * dist, dhdy = ddy(h) * dist;
    float3 r1 = cross(dpdy, N), r2 = cross(N, dpdx);
    float det = dot(dpdx, r1);
    float3 grad = sign(det) * (dhdx * r1 + dhdy * r2);
    float3 Nb = normalize(abs(det) * N - grad);
    return normalize(lerp(N, Nb, max(strength, 0.0)));
}
// anti-aliased smooth edge for thin procedural lines: widen by the pixel footprint of x
float sh_smoothAA(float e0, float e1, float x)
{
    float w = fwidth(x) * 0.75;
    float lo = min(e0, e1) - w, hi = max(e0, e1) + w;
    return e0 < e1 ? sh_smooth(lo, hi, x) : sh_smooth(hi, lo, x);
}

#endif
