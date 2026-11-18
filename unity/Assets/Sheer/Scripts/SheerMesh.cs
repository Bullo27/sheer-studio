// SHEER — loads the exact binary meshes written by blender/export_unity.py (.smesh, StreamingAssets).
// float32 everywhere, Unity axes already applied, 32-bit indices, UV channels with up to 4 components.
// Vertices split at UV seams carry 'src' (the original vertex) so the simulation can weld them.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Unity.Collections;
using UnityEngine;
using UnityEngine.Rendering;

namespace Sheer
{
    public class SheerMeshData
    {
        public int vertexCount;
        public List<int[]> submeshes = new List<int[]>();
        public Dictionary<string, float[]> f = new Dictionary<string, float[]>();
        public Dictionary<string, int> dims = new Dictionary<string, int>();
        public Dictionary<string, uint[]> u = new Dictionary<string, uint[]>();

        public static string PathOf(string file) => Path.Combine(Application.streamingAssetsPath, file);

        public static SheerMeshData Load(string file)
        {
            var d = new SheerMeshData();
            var bytes = File.ReadAllBytes(PathOf(file));
            int o = 0;
            if (Encoding.ASCII.GetString(bytes, 0, 4) != "SMSH") throw new Exception(file + ": not a .smesh file");
            o = 4;
            uint U32() { uint v = BitConverter.ToUInt32(bytes, o); o += 4; return v; }
            U32();                                   // version
            d.vertexCount = (int)U32();
            int nsub = (int)U32();
            for (int s = 0; s < nsub; s++)
            {
                int cnt = (int)U32();
                var idx = new int[cnt];
                Buffer.BlockCopy(bytes, o, idx, 0, cnt * 4); o += cnt * 4;
                d.submeshes.Add(idx);
            }
            int nch = (int)U32();
            for (int c = 0; c < nch; c++)
            {
                string name = Encoding.ASCII.GetString(bytes, o, 16).TrimEnd('\0'); o += 16;
                byte typ = bytes[o]; byte dim = bytes[o + 1]; o += 4;
                int n = d.vertexCount * dim;
                if (typ == 0) { var a = new float[n]; Buffer.BlockCopy(bytes, o, a, 0, n * 4); d.f[name] = a; }
                else { var a = new uint[n]; Buffer.BlockCopy(bytes, o, a, 0, n * 4); d.u[name] = a; }
                d.dims[name] = dim; o += n * 4;
            }
            return d;
        }

        public Vector3[] V3(string name)
        {
            var a = f[name]; var r = new Vector3[vertexCount];
            for (int i = 0; i < vertexCount; i++) r[i] = new Vector3(a[3 * i], a[3 * i + 1], a[3 * i + 2]);
            return r;
        }
        public Vector4[] V4(string name)
        {
            var a = f[name]; int d = dims[name]; var r = new Vector4[vertexCount];
            for (int i = 0; i < vertexCount; i++)
                r[i] = new Vector4(a[d * i], d > 1 ? a[d * i + 1] : 0, d > 2 ? a[d * i + 2] : 0, d > 3 ? a[d * i + 3] : 0);
            return r;
        }

        /// The stocking over the toes: fabric bridges the gaps between them instead of following every toe (review round 6:
        /// a 'toe sock'). Concavity-filling smoothing on the welded mesh, only in the toe region, only vertices whose
        /// neighbours' mean lies OUTSIDE them move (the gaps fill, the toe tips stay), at most maxLift outward.
        public void BridgeToes(float maxLift = 0.008f, bool lift = false)
        {
            var p = f["position"]; var nn = f["normal"]; int n = vertexCount;
            var weld = Weld();
            // (the toes AND the top of the foot: review round 7 still saw separate toes and the tendons over the instep -
            //  'a bare foot in a film'; the original's foot is one smooth sock shape)
            float W(int i)
            {
                float y = p[3 * i + 1], z = p[3 * i + 2];
                return Mathf.Clamp01((-0.015f - z) / 0.02f) * Mathf.Clamp01((0.085f - y) / 0.015f);
            }
            var w = new float[n]; int cnt = 0;
            for (int i = 0; i < n; i++) if (weld[i] == i) { w[i] = W(i); if (w[i] > 0f) cnt++; }
            if (cnt == 0) return;
            var nb = new Dictionary<int, HashSet<int>>(cnt);
            foreach (var idx in submeshes)
                for (int t = 0; t + 2 < idx.Length; t += 3)
                {
                    int a = weld[idx[t]], b = weld[idx[t + 1]], c = weld[idx[t + 2]];
                    void Add(int x, int y) { if (w[x] <= 0f) return; if (!nb.TryGetValue(x, out var h)) nb[x] = h = new HashSet<int>(); h.Add(y); }
                    Add(a, b); Add(a, c); Add(b, a); Add(b, c); Add(c, a); Add(c, b);
                }
            var keys = new List<int>(nb.Keys);
            var P = new Vector3[n]; var P0 = new Vector3[n]; var N0 = new Vector3[n];
            for (int i = 0; i < n; i++) { P[i] = new Vector3(p[3 * i], p[3 * i + 1], p[3 * i + 2]); P0[i] = P[i]; N0[i] = new Vector3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]).normalized; }
            // (the mesh is far finer than the gaps - a one-ring smoothing moved nothing: every vertex instead rises along its
            //  normal to the Gaussian mean of the surface within ~6 mm, found with a spatial hash; the gaps between the toes
            //  come up toward the toes' tops, the tops stay)
            const float R = 0.008f;                 // (12 mm left each toe without its own sheen - round 9 'clay'; 6 mm a 'toe sock')
            // (per-vertex neighbour sums over 12 mm cost ~100 s at start-up: the normals are summed per 4 mm cell first, and
            //  every vertex adds up the cells around it, weighted by the distance to each cell's centroid)
            const float C = 0.004f;
            var cells = new Dictionary<Vector3Int, (Vector3 n, Vector3 p, int c)>();
            Vector3Int Cell(Vector3 v) => new Vector3Int(Mathf.FloorToInt(v.x / C), Mathf.FloorToInt(v.y / C), Mathf.FloorToInt(v.z / C));
            foreach (int r in keys)
            {
                var c = Cell(P[r]); cells.TryGetValue(c, out var e);
                cells[c] = (e.n + N0[r], e.p + P[r], e.c + 1);
            }
            var cl = new List<(Vector3 n, Vector3 p, int c)>(cells.Count);
            var cidx = new Dictionary<Vector3Int, int>(cells.Count);
            foreach (var kv in cells) { cidx[kv.Key] = cl.Count; cl.Add((kv.Value.n, kv.Value.p / kv.Value.c, kv.Value.c)); }
            int span = Mathf.CeilToInt(R / C);
            var Ns = new Vector3[keys.Count];
            for (int k = 0; k < keys.Count; k++)
            {
                int r = keys[k]; Vector3 pr = P[r]; var c0 = Cell(pr); Vector3 S = Vector3.zero;
                for (int dx = -span; dx <= span; dx++) for (int dy = -span; dy <= span; dy++) for (int dz = -span; dz <= span; dz++)
                {
                    if (!cidx.TryGetValue(new Vector3Int(c0.x + dx, c0.y + dy, c0.z + dz), out int ci)) continue;
                    var e = cl[ci];
                    float d2 = (e.p - pr).sqrMagnitude; if (d2 > R * R) continue;
                    if (Vector3.Dot(e.n, N0[r]) < 0.0f) continue;          // (not the far side of a toe)
                    S += e.n * Mathf.Exp(-d2 / (0.5f * R * R));
                }
                Ns[k] = S.sqrMagnitude > 1e-12f ? Vector3.Slerp(N0[r], S.normalized, w[r]) : N0[r];
            }
            // The toes themselves: the fabric spans the gaps between them (a sock's front, not five separate toes - review
            // round 7). Every vertex of the toes rises along its smoothed normal to the local mean of the surface within
            // ~9 mm where that mean lies OUTSIDE it (gaps and notches fill; toe tops and tips stay), at most 5 mm.
            int lifted = 0; float maxUp = 0f;
            if (lift)
            {
                const float RP = 0.018f; int spanP = Mathf.CeilToInt(RP / C);
                var up = new float[keys.Count];
                for (int k = 0; k < keys.Count; k++)
                {
                    int r = keys[k]; Vector3 pr = P[r];
                    float wt = Mathf.Clamp01((-0.070f - pr.z) / 0.012f) * Mathf.Clamp01((0.048f - pr.y) / 0.010f);
                    if (wt <= 0f) continue;
                    var c0 = Cell(pr); Vector3 Sp = Vector3.zero; float Sw = 0f;
                    for (int dx = -spanP; dx <= spanP; dx++) for (int dy = -spanP; dy <= spanP; dy++) for (int dz = -spanP; dz <= spanP; dz++)
                    {
                        if (!cidx.TryGetValue(new Vector3Int(c0.x + dx, c0.y + dy, c0.z + dz), out int ci)) continue;
                        var e = cl[ci];
                        float d2 = (e.p - pr).sqrMagnitude; if (d2 > RP * RP) continue;
                        if (Vector3.Dot(e.n, Ns[k]) < 0.0f) continue;
                        float g = e.c * Mathf.Exp(-d2 / (0.5f * RP * RP)); Sp += e.p * g; Sw += g;
                    }
                    if (Sw <= 0f) continue;
                    float d = Vector3.Dot(Sp / Sw - pr, Ns[k]);
                    if (d > 0f) up[k] = Mathf.Min(d * 1.6f, 0.006f) * wt;
                }
                for (int k = 0; k < keys.Count; k++)
                    if (up[k] > 0f) { P[keys[k]] += Ns[k] * up[k]; lifted++; maxUp = Mathf.Max(maxUp, up[k]); }
                for (int i = 0; i < n; i++)
                {
                    int r = weld[i]; Vector3 q = P[r];
                    if ((q - P0[r]).sqrMagnitude <= 0f) continue;
                    p[3 * i] = q.x; p[3 * i + 1] = q.y; p[3 * i + 2] = q.z;
                }
            }
            var newN = new Dictionary<int, Vector3>(keys.Count);
            for (int k = 0; k < keys.Count; k++) newN[keys[k]] = Ns[k];
            int changed = 0; float maxAng = 0f;
            for (int i = 0; i < n; i++)
            {
                if (!newN.TryGetValue(weld[i], out var nr)) continue;
                maxAng = Mathf.Max(maxAng, Vector3.Angle(N0[i], nr)); changed++;
                nn[3 * i] = nr.x; nn[3 * i + 1] = nr.y; nn[3 * i + 2] = nr.z;
            }
            Debug.Log($"[mesh] BridgeToes: normals smoothed over {R * 1000:0} mm on {changed} vertices, max change {maxAng:0} deg; {lifted} toe vertices lifted, max {maxUp * 1000:0.0} mm");
            return;
            { float mx = 0f, sum = 0f; int moved = 0; foreach (int r in keys) { float dd = (P[r] - P0[r]).magnitude; mx = Mathf.Max(mx, dd); if (dd > 0.0005f) { moved++; sum += dd; } }
              Debug.Log($"[mesh] BridgeToes: {keys.Count} vertices in the toe region, {moved} moved > 0.5 mm, mean {(moved > 0 ? sum / moved * 1000f : 0f):0.0} mm, max {mx * 1000f:0.0} mm"); }
            // normals of the moved part from its faces (area-weighted), then every welded copy takes its representative's
            var acc = new Dictionary<int, Vector3>(keys.Count);
            foreach (int r in keys) acc[r] = Vector3.zero;
            foreach (var idx in submeshes)
                for (int t = 0; t + 2 < idx.Length; t += 3)
                {
                    int a = weld[idx[t]], b = weld[idx[t + 1]], c = weld[idx[t + 2]];
                    if (!acc.ContainsKey(a) && !acc.ContainsKey(b) && !acc.ContainsKey(c)) continue;
                    Vector3 fn = Vector3.Cross(P[b] - P[a], P[c] - P[a]);
                    if (Vector3.Dot(fn, N0[a] + N0[b] + N0[c]) < 0f) fn = -fn;
                    if (acc.ContainsKey(a)) acc[a] += fn; if (acc.ContainsKey(b)) acc[b] += fn; if (acc.ContainsKey(c)) acc[c] += fn;
                }
            for (int i = 0; i < n; i++)
            {
                int r = weld[i]; if (!acc.TryGetValue(r, out var an)) continue;
                p[3 * i] = P[r].x; p[3 * i + 1] = P[r].y; p[3 * i + 2] = P[r].z;
                Vector3 nr = an.sqrMagnitude > 1e-20f ? an.normalized : N0[i];
                float bl = Mathf.Clamp01(w[r] * 1.5f);                  // (blend into the untouched normals at the region's edge)
                nr = Vector3.Slerp(N0[i], nr, bl);
                nn[3 * i] = nr.x; nn[3 * i + 1] = nr.y; nn[3 * i + 2] = nr.z;
            }
        }

        /// Weld map: for every vertex, the index of the first vertex with the same source vertex.
        /// A sock squeezes the toes into one rounded front (review rounds 7 / 8: ours were five separate bulbous lumps with
        /// the nylon shrink-wrapped into every gap). Every vertex of the toes moves to the Gaussian mean of the surface around
        /// it (same-facing surface only, ~R), body and stocking alike so the stocking stays clear of the skin (+ outward);
        /// the sole's contact with the floor stays put.
        // yzFacing (round 14): neighbours count by how alike their normals are in height and depth only - the two walls of
        // a groove between two toes (normals facing each other across it) are averaged together, the groove rises and the
        // lobes sink: a mitten; a toe's sole side under its top still does not count. yLow: how far down toward the floor.
        public void SmoothToes(float R, float outward, bool allowOut = true, bool yzFacing = false, float yLow = 0.006f, bool allowIn = true)
        {
            var p = f["position"]; var nn = f["normal"]; int n = vertexCount;
            var weld = Weld();
            float Wt(Vector3 v) => Mathf.Clamp01((-0.064f - v.z) / 0.016f) * Mathf.Clamp01((0.052f - v.y) / 0.012f) * Mathf.Clamp01((v.y - yLow) / 0.010f);
            var keys = new List<int>(); var P = new Vector3[n]; var N0 = new Vector3[n];
            for (int i = 0; i < n; i++) { P[i] = new Vector3(p[3 * i], p[3 * i + 1], p[3 * i + 2]); N0[i] = new Vector3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]).normalized; }
            const float C = 0.004f;
            var cells = new Dictionary<Vector3Int, (Vector3 n, Vector3 p, int c)>();
            Vector3Int Cell(Vector3 v) => new Vector3Int(Mathf.FloorToInt(v.x / C), Mathf.FloorToInt(v.y / C), Mathf.FloorToInt(v.z / C));
            for (int i = 0; i < n; i++)
            {
                if (weld[i] != i) continue;
                Vector3 v = P[i]; if (v.z > -0.03f || v.y > 0.08f) continue;        // (the forefoot and a margin around the toes)
                var c = Cell(v); cells.TryGetValue(c, out var e); cells[c] = (e.n + N0[i], e.p + v, e.c + 1);
                if (Wt(v) > 0f) keys.Add(i);
            }
            if (keys.Count == 0) return;
            var cl = new List<(Vector3 n, Vector3 p, int c)>(cells.Count); var cidx = new Dictionary<Vector3Int, int>(cells.Count);
            foreach (var kv in cells) { cidx[kv.Key] = cl.Count; cl.Add((kv.Value.n.normalized, kv.Value.p / kv.Value.c, kv.Value.c)); }
            int span = Mathf.CeilToInt(R / C);
            var newP = new Dictionary<int, Vector3>(keys.Count); float mx = 0f;
            foreach (int r in keys)
            {
                Vector3 pr = P[r]; var c0 = Cell(pr); Vector3 Sp = Vector3.zero; float Sw = 0f;
                for (int dx = -span; dx <= span; dx++) for (int dy = -span; dy <= span; dy++) for (int dz = -span; dz <= span; dz++)
                {
                    if (!cidx.TryGetValue(new Vector3Int(c0.x + dx, c0.y + dy, c0.z + dz), out int ci)) continue;
                    var e = cl[ci]; float d2 = (e.p - pr).sqrMagnitude; if (d2 > R * R) continue;
                    // (not the far side of a toe, nor the next toe's facing wall - weighted softly: a hard cut by facing made
                    //  neighbouring vertices take different sets and the surface came out faceted)
                    float fd = yzFacing ? Mathf.SmoothStep(0f, 1f, (e.n.y * N0[r].y + e.n.z * N0[r].z + 0.35f) / 0.8f)
                                        : Mathf.SmoothStep(0f, 1f, (Vector3.Dot(e.n, N0[r]) - 0.0f) / 0.7f);
                    if (fd <= 0f) continue;
                    float g = e.c * fd * Mathf.Exp(-d2 / (0.5f * R * R)); Sp += e.p * g; Sw += g;
                }
                if (Sw <= 0f) continue;
                float wt = Wt(pr);
                Vector3 dv = Sp / Sw - pr;
                // (the skin may only sink: its gaps filled up to 9 mm and came out through the stocking's shallower ones)
                if (!allowOut) { float dn = Vector3.Dot(dv, N0[r]); if (dn > 0f) dv -= N0[r] * dn; }
                // (... and the stocking may only rise: smoothed over the little toe's convex side it sank up to 5 mm while the
                //  skin under it sank less - pink flecks of skin through the nylon, review 11)
                if (!allowIn) { float dn = Vector3.Dot(dv, N0[r]); if (dn < 0f) dv -= N0[r] * dn; }
                Vector3 q = pr + dv * wt + N0[r] * (outward * wt);
                newP[r] = q; mx = Mathf.Max(mx, (q - pr).magnitude);
            }
            int moved = 0;
            for (int i = 0; i < n; i++)
            {
                if (!newP.TryGetValue(weld[i], out var q)) continue;
                p[3 * i] = q.x; p[3 * i + 1] = q.y; p[3 * i + 2] = q.z; moved++;
            }
            Debug.Log($"[mesh] SmoothToes: {moved} vertices, max move {mx * 1000:0.0} mm (R {R * 1000:0} mm, +{outward * 1000:0.0} mm out)");
        }

        // The nylon spans the gaps between the toes instead of following the skin into them (review round 13: each toe
        // wrapped on its own, the toes' front outline scalloped 6.1 px against the original's 1.7). The forefoot's FRONT
        // profile (how far forward, -z, the surface reaches in each cell of height x lateral position) and its TOP profile
        // (height in each cell of depth x lateral position) are CLOSED across the toes with a parabolic element: a valley
        // narrower than the element is bridged, sagging by 'sag' x half-span^2. Every front / top facing vertex then moves
        // out along -z / +y by its cell's fill (bilinear between cells), the walls inside a gap stay behind the bridge.
        // (A gaussian outward-only smoothing was tried first: the toe tops behind a gap pulled its mean back - 1.7 mm of
        //  fill in 8 passes - and it took ~5 min per call in Mono)
        public void FillToeGaps(float halfW, float sag, float maxOut)
        {
            var p = f["position"]; var nn = f["normal"]; int n = vertexCount;
            var weld = Weld();
            float Wt(Vector3 v) => Mathf.Clamp01((-0.058f - v.z) / 0.014f) * Mathf.Clamp01((0.058f - v.y) / 0.012f);
            const float CX = 0.001f, CR = 0.002f;
            int K = Mathf.CeilToInt(halfW / CX);
            var P = new Vector3[n]; var N = new Vector3[n];
            var fr = new Dictionary<(int, int), float>(); var tp = new Dictionary<(int, int), float>();
            for (int i = 0; i < n; i++)
            {
                P[i] = new Vector3(p[3 * i], p[3 * i + 1], p[3 * i + 2]); N[i] = new Vector3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]).normalized;
                if (weld[i] != i || P[i].z > -0.035f || P[i].y > 0.075f) continue;
                int cx = Mathf.FloorToInt(P[i].x / CX);
                if (N[i].z < -0.3f) { var k = (Mathf.FloorToInt(P[i].y / CR), cx); fr[k] = fr.TryGetValue(k, out float o) ? Mathf.Max(o, -P[i].z) : -P[i].z; }
                if (N[i].y > 0.3f) { var k = (Mathf.FloorToInt(P[i].z / CR), cx); tp[k] = tp.TryGetValue(k, out float o) ? Mathf.Max(o, P[i].y) : P[i].y; }
            }
            Dictionary<(int, int), float> Close(Dictionary<(int, int), float> prof)
            {
                var fill = new Dictionary<(int, int), float>();
                var rows = new Dictionary<int, List<int>>();
                foreach (var k in prof.Keys) { if (!rows.TryGetValue(k.Item1, out var l)) rows[k.Item1] = l = new List<int>(); l.Add(k.Item2); }
                foreach (var kv in rows)
                {
                    int r = kv.Key, c0 = int.MaxValue, c1 = int.MinValue;
                    foreach (int c in kv.Value) { c0 = Mathf.Min(c0, c); c1 = Mathf.Max(c1, c); }
                    int m = c1 - c0 + 1; var v = new float[m]; var has = new bool[m];
                    foreach (int c in kv.Value) { v[c - c0] = prof[(r, c)]; has[c - c0] = true; }
                    var dil = new float[m]; var hd = new bool[m];
                    for (int c = 0; c < m; c++)
                    {
                        float best = float.NegativeInfinity;
                        for (int d = -K; d <= K; d++) { int j = c + d; if (j < 0 || j >= m || !has[j]) continue; float x = d * CX; best = Mathf.Max(best, v[j] - sag * x * x); }
                        if (best > float.NegativeInfinity) { dil[c] = best; hd[c] = true; }
                    }
                    for (int c = 0; c < m; c++)
                    {
                        if (!has[c]) continue;
                        float best = float.PositiveInfinity;
                        for (int d = -K; d <= K; d++) { int j = c + d; if (j < 0 || j >= m || !hd[j]) continue; float x = d * CX; best = Mathf.Min(best, dil[j] + sag * x * x); }
                        float fl = best - v[c];
                        if (fl > 1e-5f) fill[(r, c + c0)] = Mathf.Min(fl, maxOut);
                    }
                }
                return fill;
            }
            var fFr = Close(fr); var fTp = Close(tp);
            float Lerp2(Dictionary<(int, int), float> fl, float a, float x)
            {
                float ra = a / CR - 0.5f, cxf = x / CX - 0.5f; int r0 = Mathf.FloorToInt(ra), cc0 = Mathf.FloorToInt(cxf);
                float tr = ra - r0, tc = cxf - cc0, s = 0f;
                for (int dr = 0; dr <= 1; dr++) for (int dc = 0; dc <= 1; dc++)
                    if (fl.TryGetValue((r0 + dr, cc0 + dc), out float o)) s += o * (dr == 1 ? tr : 1f - tr) * (dc == 1 ? tc : 1f - tc);
                return s;
            }
            var newP = new Dictionary<int, Vector3>(); float mx = 0f;
            for (int i = 0; i < n; i++)
            {
                if (weld[i] != i) continue;
                Vector3 v = P[i]; float wt = Wt(v); if (wt <= 0f || v.z > -0.035f || v.y > 0.075f) continue;
                float aF = Mathf.SmoothStep(0f, 1f, (-N[i].z - 0.3f) / 0.4f), aT = Mathf.SmoothStep(0f, 1f, (N[i].y - 0.6f) / 0.3f);
                // (only the TOP is filled: moving the front-facing floor of a gap forward pushed it past the gap's side walls
                //  - crumpled vertical ridges on the small toes - and shearing whole columns forward raised bumps on the
                //  instep; bridging the front needs a real 3D closing)
                float dz = 0f * aF * Lerp2(fFr, v.y, v.x), dy = aT > 0f ? Lerp2(fTp, v.z, v.x) * aT : 0f;
                if (dz <= 0f && dy <= 0f) continue;
                Vector3 q = v + new Vector3(0f, dy * wt, -dz * wt);
                newP[i] = q; mx = Mathf.Max(mx, (q - v).magnitude);
            }
            int moved = 0;
            for (int i = 0; i < n; i++)
            {
                if (!newP.TryGetValue(weld[i], out var q)) continue;
                p[3 * i] = q.x; p[3 * i + 1] = q.y; p[3 * i + 2] = q.z; moved++;
            }
            Debug.Log($"[mesh] FillToeGaps: {moved} vertices, max out {mx * 1000:0.0} mm (half-width {halfW * 1000:0} mm, sag {sag:0})");
        }

        // The nylon spans the gaps between the toes (review rounds 9 - 13: 'each toe wrapped on its own'): a voxel CLOSING of
        // the forefoot. The tights' forefoot is voxelised at h (inside = parity of the triangle crossings along x, row by
        // row of constant height and depth); in every row a run of outside voxels no wider than W with the foot on both
        // sides - a gap between two toes - is filled; every vertex the filling buries (the voxel just outside it is now
        // filled: the gap's walls and floor) moves to the nearest voxel still outside - the bridge over the gap - and the
        // moves are smoothed among the moved vertices. (Moving only the gap floors forward or up folded them past the walls)
        public void CloseToes(float W, float maxOut, float h = 0.00075f)
        {
            var p = f["position"]; var nn = f["normal"]; int n = vertexCount;
            var weld = Weld();
            var P = new Vector3[n]; var N0 = new Vector3[n];
            for (int i = 0; i < n; i++) { P[i] = new Vector3(p[3 * i], p[3 * i + 1], p[3 * i + 2]); N0[i] = new Vector3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]).normalized; }
            const float ZB = -0.045f, YT = 0.075f;
            Vector3 lo = new Vector3(1e9f, 1e9f, 1e9f), hi = -lo;
            for (int i = 0; i < n; i++) if (P[i].z < ZB && P[i].y < YT) { lo = Vector3.Min(lo, P[i]); hi = Vector3.Max(hi, P[i]); }
            if (lo.x > hi.x) return;
            lo -= Vector3.one * 0.004f; hi += Vector3.one * 0.004f; hi.z = Mathf.Min(hi.z, ZB);
            int nx = Mathf.CeilToInt((hi.x - lo.x) / h), ny = Mathf.CeilToInt((hi.y - lo.y) / h), nz = Mathf.CeilToInt((hi.z - lo.z) / h);
            const float JY = 0.137f, JZ = 0.291f;          // (row centres off the mesh's own symmetric spots)
            var cross = new List<float>[ny * nz];
            foreach (var tri in submeshes)
                for (int t = 0; t + 2 < tri.Length; t += 3)
                {
                    Vector3 a = P[tri[t]], b = P[tri[t + 1]], c = P[tri[t + 2]];
                    float y0 = Mathf.Min(a.y, Mathf.Min(b.y, c.y)), y1 = Mathf.Max(a.y, Mathf.Max(b.y, c.y));
                    float z0 = Mathf.Min(a.z, Mathf.Min(b.z, c.z)), z1 = Mathf.Max(a.z, Mathf.Max(b.z, c.z));
                    if (z0 > hi.z + 0.002f || y0 > hi.y || y1 < lo.y || z1 < lo.z) continue;
                    int j0 = Mathf.Max(0, Mathf.CeilToInt((y0 - lo.y) / h - 0.5f - JY)), j1 = Mathf.Min(ny - 1, Mathf.FloorToInt((y1 - lo.y) / h - 0.5f - JY));
                    int k0 = Mathf.Max(0, Mathf.CeilToInt((z0 - lo.z) / h - 0.5f - JZ)), k1 = Mathf.Min(nz - 1, Mathf.FloorToInt((z1 - lo.z) / h - 0.5f - JZ));
                    float d = (b.y - a.y) * (c.z - a.z) - (c.y - a.y) * (b.z - a.z);
                    if (Mathf.Abs(d) < 1e-14f) continue;
                    for (int j = j0; j <= j1; j++)
                        for (int k = k0; k <= k1; k++)
                        {
                            float yc = lo.y + (j + 0.5f + JY) * h, zc = lo.z + (k + 0.5f + JZ) * h;
                            float w1 = ((yc - a.y) * (c.z - a.z) - (c.y - a.y) * (zc - a.z)) / d;
                            float w2 = ((b.y - a.y) * (zc - a.z) - (yc - a.y) * (b.z - a.z)) / d;
                            if (w1 < 0f || w2 < 0f || w1 + w2 > 1f) continue;
                            int row = j * nz + k; (cross[row] ??= new List<float>()).Add(a.x + w1 * (b.x - a.x) + w2 * (c.x - a.x));
                        }
                }
            int N = nx * ny * nz; var ins = new bool[N]; var fil = new bool[N];
            int Vi(int i, int j, int k) => (j * nz + k) * nx + i;
            int rowsOdd = 0, nFill = 0, maxRun = Mathf.FloorToInt(W / h);
            for (int j = 0; j < ny; j++)
                for (int k = 0; k < nz; k++)
                {
                    var cl = cross[j * nz + k]; if (cl == null || cl.Count < 2) continue;
                    cl.Sort(); if ((cl.Count & 1) == 1) { rowsOdd++; continue; }
                    for (int q = 0; q + 1 < cl.Count; q += 2)
                    {
                        int i0 = Mathf.Max(0, Mathf.CeilToInt((cl[q] - lo.x) / h - 0.5f)), i1 = Mathf.Min(nx - 1, Mathf.FloorToInt((cl[q + 1] - lo.x) / h - 0.5f));
                        for (int i = i0; i <= i1; i++) ins[Vi(i, j, k)] = true;
                    }
                    // gaps between two stretches of foot in this row, no wider than W
                    int last = -1;
                    for (int i = 0; i < nx; i++)
                    {
                        if (!ins[Vi(i, j, k)]) continue;
                        if (last >= 0 && i - last - 1 > 0 && i - last - 1 <= maxRun)
                            for (int g = last + 1; g < i; g++) { fil[Vi(g, j, k)] = true; nFill++; }
                        last = i;
                    }
                }
            // nearest voxel still outside, for every filled voxel (a brushfire from the outside voxels that touch the fill)
            var near = new int[N]; for (int v = 0; v < N; v++) near[v] = -1;
            var qu = new Queue<int>();
            Vector3 C(int v) { int i = v % nx, r = v / nx; return lo + new Vector3(i + 0.5f, r / nz + 0.5f + JY, r % nz + 0.5f + JZ) * h; }
            int[] dI = { 1, -1, 0, 0, 0, 0 }, dJ = { 0, 0, 1, -1, 0, 0 }, dK = { 0, 0, 0, 0, 1, -1 };
            for (int v = 0; v < N; v++)
            {
                if (!fil[v]) continue;
                int i = v % nx, r = v / nx, j = r / nz, k = r % nz;
                for (int e = 0; e < 6; e++)
                {
                    int a = i + dI[e], b = j + dJ[e], c = k + dK[e];
                    if (a < 0 || b < 0 || c < 0 || a >= nx || b >= ny || c >= nz) continue;
                    int u = Vi(a, b, c);
                    if (!ins[u] && !fil[u] && near[u] < 0) { near[u] = u; qu.Enqueue(u); }
                }
            }
            while (qu.Count > 0)
            {
                int v = qu.Dequeue(); int i = v % nx, r = v / nx, j = r / nz, k = r % nz; Vector3 tv = C(near[v]);
                for (int e = 0; e < 6; e++)
                {
                    int a = i + dI[e], b = j + dJ[e], c = k + dK[e];
                    if (a < 0 || b < 0 || c < 0 || a >= nx || b >= ny || c >= nz) continue;
                    int u = Vi(a, b, c); if (!fil[u]) continue;
                    float du = (C(u) - tv).sqrMagnitude;
                    if (du > maxOut * maxOut * 1.5f) continue;
                    if (near[u] < 0 || du < (C(u) - C(near[u])).sqrMagnitude - 1e-12f) { near[u] = near[v]; qu.Enqueue(u); }
                }
            }
            // move the buried vertices
            var D = new Dictionary<int, Vector3>();
            for (int i = 0; i < n; i++)
            {
                if (weld[i] != i || P[i].z >= hi.z || P[i].y >= hi.y) continue;
                Vector3 q = P[i] + N0[i] * (0.6f * h);
                int a = Mathf.FloorToInt((q.x - lo.x) / h), b = Mathf.FloorToInt((q.y - lo.y) / h - JY), c = Mathf.FloorToInt((q.z - lo.z) / h - JZ);
                if (a < 0 || b < 0 || c < 0 || a >= nx || b >= ny || c >= nz) continue;
                int v = Vi(a, b, c); if (!fil[v] || near[v] < 0) continue;
                Vector3 dv = C(near[v]) - P[i]; if (dv.magnitude > maxOut) dv = dv.normalized * maxOut;
                D[i] = dv;
            }
            // smoothed among the moved vertices (the voxels' steps), 3 passes over 1.6 mm
            const float RS = 0.0016f; var keys = new List<int>(D.Keys);
            for (int pass = 0; pass < 3; pass++)
            {
                var cells = new Dictionary<Vector3Int, List<int>>();
                foreach (int r in keys) { var cc = Vector3Int.FloorToInt(P[r] / RS); if (!cells.TryGetValue(cc, out var l)) cells[cc] = l = new List<int>(); l.Add(r); }
                var D2 = new Dictionary<int, Vector3>(D.Count);
                foreach (int r in keys)
                {
                    var c0 = Vector3Int.FloorToInt(P[r] / RS); Vector3 sum = Vector3.zero; float sw = 0f;
                    for (int dx = -1; dx <= 1; dx++) for (int dy = -1; dy <= 1; dy++) for (int dz = -1; dz <= 1; dz++)
                        if (cells.TryGetValue(c0 + new Vector3Int(dx, dy, dz), out var l))
                            foreach (int o in l) { float d2 = (P[o] - P[r]).sqrMagnitude; if (d2 > RS * RS) continue; float w = Mathf.Exp(-d2 / (0.5f * RS * RS)); sum += D[o] * w; sw += w; }
                    D2[r] = sw > 0f ? sum / sw : D[r];
                }
                D = D2;
            }
            int moved = 0; float mx = 0f;
            for (int i = 0; i < n; i++)
            {
                if (!D.TryGetValue(weld[i], out var dv)) continue;
                Vector3 q = P[weld[i]] + dv; p[3 * i] = q.x; p[3 * i + 1] = q.y; p[3 * i + 2] = q.z; moved++; mx = Mathf.Max(mx, dv.magnitude);
            }
            Debug.Log($"[mesh] CloseToes: grid {nx}x{ny}x{nz}, {nFill} voxels filled ({rowsOdd} odd rows skipped), {D.Count} vertices moved (x{moved}), max {mx * 1000:0.0} mm");
        }

        public int[] Weld()
        {
            var w = new int[vertexCount];
            if (!u.TryGetValue("src", out var src)) { for (int i = 0; i < vertexCount; i++) w[i] = i; return w; }
            var first = new Dictionary<uint, int>(vertexCount);
            for (int i = 0; i < vertexCount; i++)
            {
                if (!first.TryGetValue(src[i], out int j)) { first[src[i]] = i; j = i; }
                w[i] = j;
            }
            return w;
        }

        /// Builds a render mesh. Stream 0 = position, normal, tangent (+ UV3 for the dynamic stretch when
        /// dynamicUV3); stream 1 = static UV0..UV2 (float32, as many components as exported).
        public Mesh BuildMesh(string name, bool dynamicUV3 = false)
        {
            var m = new Mesh { name = name, indexFormat = IndexFormat.UInt32 };
            var attrs = new List<VertexAttributeDescriptor>
            {
                new VertexAttributeDescriptor(VertexAttribute.Position, VertexAttributeFormat.Float32, 3, 0),
                new VertexAttributeDescriptor(VertexAttribute.Normal, VertexAttributeFormat.Float32, 3, 0),
                new VertexAttributeDescriptor(VertexAttribute.Tangent, VertexAttributeFormat.Float32, 4, 0),
            };
            string[] uvs = { "uv0", "uv1", "uv2" };
            for (int k = 0; k < uvs.Length; k++)
                if (f.ContainsKey(uvs[k]))
                    attrs.Add(new VertexAttributeDescriptor(VertexAttribute.TexCoord0 + k, VertexAttributeFormat.Float32, dims[uvs[k]], 1));
            if (dynamicUV3) attrs.Add(new VertexAttributeDescriptor(VertexAttribute.TexCoord3, VertexAttributeFormat.Float32, 2, 0));
            m.SetVertexBufferParams(vertexCount, attrs.ToArray());

            // stream 0
            int s0 = dynamicUV3 ? 12 : 10;
            var v0 = new float[vertexCount * s0];
            var p = f["position"]; var nn = f["normal"]; var t = f["tangent"];
            for (int i = 0; i < vertexCount; i++)
            {
                int b = i * s0;
                v0[b] = p[3 * i]; v0[b + 1] = p[3 * i + 1]; v0[b + 2] = p[3 * i + 2];
                v0[b + 3] = nn[3 * i]; v0[b + 4] = nn[3 * i + 1]; v0[b + 5] = nn[3 * i + 2];
                v0[b + 6] = t[4 * i]; v0[b + 7] = t[4 * i + 1]; v0[b + 8] = t[4 * i + 2]; v0[b + 9] = t[4 * i + 3];
                if (dynamicUV3) { v0[b + 10] = 1f; v0[b + 11] = 0f; }
            }
            m.SetVertexBufferData(v0, 0, 0, v0.Length, 0, MeshUpdateFlags.DontValidateIndices);
            // stream 1
            int s1 = 0; foreach (var k in uvs) if (f.ContainsKey(k)) s1 += dims[k];
            if (s1 > 0)
            {
                var v1 = new float[vertexCount * s1];
                for (int i = 0; i < vertexCount; i++)
                {
                    int b = i * s1;
                    foreach (var k in uvs)
                    {
                        if (!f.ContainsKey(k)) continue;
                        int d = dims[k]; var a = f[k];
                        for (int c = 0; c < d; c++) v1[b++] = a[d * i + c];
                    }
                }
                m.SetVertexBufferData(v1, 0, 0, v1.Length, 1, MeshUpdateFlags.DontValidateIndices);
            }
            int total = 0; foreach (var s in submeshes) total += s.Length;
            var all = new int[total]; int off = 0;
            m.subMeshCount = submeshes.Count;
            var descs = new SubMeshDescriptor[submeshes.Count];
            for (int s = 0; s < submeshes.Count; s++)
            {
                Array.Copy(submeshes[s], 0, all, off, submeshes[s].Length);
                descs[s] = new SubMeshDescriptor(off, submeshes[s].Length, MeshTopology.Triangles);
                off += submeshes[s].Length;
            }
            m.SetIndexBufferParams(total, IndexFormat.UInt32);
            m.SetIndexBufferData(all, 0, 0, total, MeshUpdateFlags.DontValidateIndices);
            for (int s = 0; s < submeshes.Count; s++) m.SetSubMesh(s, descs[s], MeshUpdateFlags.DontRecalculateBounds);
            m.RecalculateBounds();
            m.bounds = new Bounds(m.bounds.center, m.bounds.size + Vector3.one * 0.4f);     // room for pulls & sway
            // (Mesh.OptimizeIndexBuffers() was tried here for the GPU's vertex cache - the exported triangle order re-runs the
            //  vertex shaders ~1.2 times per triangle and the frame is bound by triangle count - but it crashes the player
            //  on meshes built through the low-level buffer API. Reordering belongs in blender/export_unity.py.)
            return m;
        }
    }
}
