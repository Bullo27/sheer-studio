// SHEER — the weave map: the knit as a fine net of yarn (two diagonal loop legs per cell, a faint tie along the
// course). Tileable. (The first version, a port of knit_image in blender/sheer_materials.py, drew continuous
// horizontal 'ropes': at 1080 p they read as scan lines; the original's fabric is an even mesh.)
// RGB = tangent-space normal (OpenGL convention, +v up), A = yarn coverage. Also returns its mean coverage.
using UnityEngine;

namespace Sheer
{
    public static class SheerWeave
    {
        static float Frac(float v) => v - Mathf.Floor(v);
        /// rounded thread profile: 1 on the axis, 0 from half-width w outward
        static float Bump(float d, float w) => Mathf.Pow(Mathf.Clamp01(1f - (d / w) * (d / w)), 0.7f);

        // 48 wales x 26 courses per tile: with the stocking's tiling (12 tiles around the leg, 22.4 mm tall) one cell is
        // ~0.87 x 0.86 mm on the thigh - the same wales and courses the ladders are drawn with (SheerTights.hlsl NW / PC).
        // Measured on the original at native resolution (0.5 s, thigh): rows of fine dots 3 - 3.5 px = 0.8 - 0.9 mm apart;
        // the previous 0.65 mm cells were 2 px of the frame and filtered away to a smooth film (review round 3).
        public const int Loops = 48, Rows = 26;
        public static Texture2D Build(out float meanCoverage, int size = 1536, int loops = Loops, int rows = Rows)
        {
            var h = new float[size * size]; var cov = new float[size * size];
            double sum = 0;
            for (int y = 0; y < size; y++)
            {
                float gy = y / (size / (float)rows);
                for (int x = 0; x < size; x++)
                {
                    float gx = x / (size / (float)loops);
                    // A sheer knit seen from a metre away is a fine net: each loop's two legs cross the cell diagonally
                    // (a lattice of small diamonds), the heads of the loops tie the diamonds along the course. Measured on
                    // the original's close-ups: an even, low-contrast mesh without course lines.
                    float fx = gx - Mathf.Floor(gx), fy = gy - Mathf.Floor(gy);
                    float d1 = Mathf.Abs(Frac(fx + fy) - 0.5f), d2 = Mathf.Abs(Frac(fx - fy + 1f) - 0.5f);   // the two diagonals
                    float l1 = Bump(d1, 0.17f), l2 = Bump(d2, 0.17f);
                    float head = Bump(Mathf.Abs(fy - 0.5f), 0.11f) * 0.62f;                                   // course tie (rows of dots)
                    float yarn = Mathf.Max(Mathf.Max(l1, l2), head);
                    int i = y * size + x;
                    h[i] = Mathf.Max(l1, l2) * 0.8f + l1 * l2 * 0.2f + head * 0.3f;
                    cov[i] = Mathf.Clamp01(0.42f + 0.58f * yarn);
                    sum += cov[i];
                }
            }
            meanCoverage = (float)(sum / (size * size));
            var px = new Color[size * size];
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    int xp = (x + 1) % size, xm = (x - 1 + size) % size, yp = (y + 1) % size, ym = (y - 1 + size) % size;
                    float dx = (h[y * size + xp] - h[y * size + xm]) * 2.2f;
                    float dy = (h[yp * size + x] - h[ym * size + x]) * 2.2f;
                    var n = new Vector3(-dx, -dy, 1f).normalized;
                    px[y * size + x] = new Color(n.x * 0.5f + 0.5f, n.y * 0.5f + 0.5f, n.z * 0.5f + 0.5f, cov[y * size + x]);
                }
            var tex = new Texture2D(size, size, TextureFormat.RGBAHalf, true, true)
            { name = "SheerWeave", wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 16 };
            tex.SetPixels(px);
            tex.Apply(true, false);
            return tex;
        }
    }
}
