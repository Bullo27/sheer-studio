// SHEER — the pleated skirt: CLOTH (user, 2026-11-17: "That's not a skirt, that's a solid shaped piece of something. It
// needs to be cloth falling naturally on the body's curves.").
// A position-based cloth sheet - the skirt's smooth envelope through the middle of its pleats, NA columns round x NR rows
// from the waistband to the hem - pinned at the waistband (it goes with the pelvis), falling under gravity, swinging
// with the body, flared and barely lifted by the air from below, and resting on the body: never inside the posed
// stocking's outline (its convex hull per height, as a radius per angle about the skirt's axis, from the stocking's
// outermost points - thighs, hips and buttocks). The pleated render mesh rides on the sheet: every vertex keeps its offset
// from the sheet in the sheet's own frame (round, down, out), so the pleats go wherever the cloth goes.
// (Until then: the Blender asset's shape with each pleat column moved in or out along its radius - a rigid shell; the
// thighs and buttocks came through it when she turned her knees in.)
// Unity Cloth on the 18.6k-vertex mesh cost ~110 ms per frame: still there, opt-in (useUnityCloth / -sheerSkirtCloth).
using System.Collections.Generic;
using System.IO;
using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;
using UnityEngine;

namespace Sheer
{
    [ExecuteAlways, RequireComponent(typeof(SkinnedMeshRenderer))]
    public class SkirtCloth : MonoBehaviour
    {
        public string file = "skirt_base.smesh";
        public TightsSim sim;                           // the body: its pose and the stocking's outline
        [Header("Fan")] public float windAmplitude = 1.0f;     // m/s^2, SHEER_WIND
        public float gustGain = 1f;                     // >1 during gusts (the replay drives it)
        [Tooltip("Studio: how often the air picks up (1 = as calibrated; < 1 calmer, > 1 windier).")] public float gustiness = 1f;
        /// how much air is blowing now (0..1, x the fan's amplitude) - for the gust sound
        public float WindLevel => windLevel * windAmplitude;
        [Header("Unity Cloth (opt-in)")] [Range(0, 1)] public float bendingStiffness = 0.95f;
        [Range(0, 1)] public float stretchingStiffness = 1f;
        [Range(0, 1)] public float damping = 0.15f;
        public int solverFrequency = 120;
        public float maxHemTravel = 0.035f;
        public bool useUnityCloth = false;
        [Header("Cloth (default)")]
        [Tooltip("Air drag of the fabric (1/s): how soon a swing dies away.")] public float drag = 0.8f;   // (1.6: the hem stood still between the body's moves, the original's swings on, review 7)
        [Tooltip("Bending softness of the sheet (0 = stiff as the rest shape, larger = softer).")] public float bendSoft = 6f;
        [Tooltip("Shear softness of the sheet.")] public float shearSoft = 0.6f;
        [Tooltip("Fabric thickness: how far the resting skirt stays off the stocking (m).")] public float drapeClear = 0.0025f;
        [Tooltip("How far the skirt may gather round (x its pressed width): the pleats close up to this.")] public float gatherMin = 0.6f;
        [Tooltip("The pressed pleats' spring (1/s^2): how hard a gathered ring pushes back out toward its pressed width. 0 = it hangs limp.")]
        public float pleatSpring = 70f;   // (45: the pleats hung straight - 'little flare', review 2)
        public float hemBias = 0.012f;                  // m toward the eye at the hem (depth only)
        [Header("Air (rises from below, a little from the front)")]
        // (2026-11-17: 0.7 / 3.0 / 0.6 / 0.5 held the hem out and up all the time - the skirt looked inflated from inside.
        //  Now a breath: it stirs the pleats and the hem, gravity keeps the shape.)
        [Tooltip("Outward push of the strongest air at the hem (m/s^2).")] public float flareAcc = 0.15f;
        [Tooltip("Upward push of the strongest air at the hem (m/s^2) - its edge just barely lifts.")] public float liftAcc = 0.7f;
        [Tooltip("Pleat tremor (m/s^2).")] public float tremorAcc = 0.35f;
        // (the hem sways: a gentle sideways swing even in calm air, most at the hem - the original's hem swings on between the
        //  body's moves, ours stood still, review 7. A radial tremor could not move it at all: the hem's circumference does not
        //  stretch and the body holds it from inside. Horizontal only - it never lifts the skirt)
        [Tooltip("Sideways sway of the hem in calm air (m/s^2).")] public float swayAcc = 0.6f;
        [Tooltip("Sideways drift with the air (m/s^2).")] public float driftAcc = 0.25f;
        [Tooltip("The skirt made longer than the asset (m at the hem; the waistband stays).")] public float lengthen = 0.02f;
        [Tooltip("The pleats' shading (tools/skirt_folds.py): x ambient occlusion in the folds, y cavity, z sheen on the fold edges, w the open faces' gain. -sheerSkirtFold x,y,z,w")]
        public Vector4 foldShade = new Vector4(1.2f, 1.15f, 0.35f, 0.05f);   // (1, 1, 0.3, -0.1: half the original's tone spread, L 24 - 38 vs 19 - 43, review 10)   // (edge sheen 0.8 still drew thin bright lines along the folds, review 2)   // (edge sheen 2 drew thin bright lines along every fold - independent review)
        [Tooltip("The woven wool, close up: x tile (m), y the threads' tone contrast, z their relief (m), w on. -sheerSkirtWool x,y,z,w")]
        public Vector4 wool = new Vector4(0.032f, 0.45f, 0.00035f, 1f);   // (0.32: 'flat board-like panels', review 10 - the original's cloth shows its weave)   // (16 mm / 0.22: the weave did not read at the default views)
        [Tooltip("The wool's soft sheen x this (1 = as calibrated before the pleats were reshaped). -sheerSkirtSheen x")] public float sheen = 0.5f;   // (1.6: turned 45 deg the skirt went a warm dusty grey (48,43,44) where the original stays (29,30,36), review 10)
        static Texture2D woolTex;

        /// A worsted wool, 16 x 16 mm: a 2/2 twill of 0.5 mm threads (warp and weft by turns two over, two under - diagonal
        /// ribs 2 mm apart), every thread its own tone and thickness, the twist of its fibres, now and then a stray light fibre.
        /// R = relief (0..1), G = tone (0.5 = the cloth's mean). Mip-mapped: from a distance it averages to the cloth's colour.
        static Texture2D MakeWool()
        {
            const int N = 256, T = 32;                      // texels, threads per tile
            var rnd = new System.Random(20261117);
            float R() => (float)rnd.NextDouble();
            var warpTone = new float[T]; var weftTone = new float[T]; var warpTh = new float[T]; var weftTh = new float[T];
            for (int i = 0; i < T; i++) { warpTone[i] = 0.82f + 0.36f * R(); weftTone[i] = 0.82f + 0.36f * R(); warpTh[i] = 0.8f + 0.3f * R(); weftTh[i] = 0.8f + 0.3f * R(); }
            var px = new Color32[N * N];
            float Hash(int x, int y) { uint h = (uint)(x * 73856093) ^ (uint)(y * 19349663); h ^= h >> 13; h *= 0x5bd1e995; h ^= h >> 15; return (h & 0xffffff) / 16777215f; }
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float u = x * (float)T / N, v = y * (float)T / N; int iu = (int)u, iv = (int)v; float fu = u - iu, fv = v - iv;
                    bool warpUp = ((iu + iv) & 3) < 2;
                    // a thread's rounded section, its fibres twisted (fine diagonal grooves along it)
                    float sw = Mathf.Sin(fu * Mathf.PI), sf = Mathf.Sin(fv * Mathf.PI);
                    float twistW = 0.5f + 0.5f * Mathf.Sin((fu * 2.2f + v * 3.0f) * 2f * Mathf.PI), twistF = 0.5f + 0.5f * Mathf.Sin((fv * 2.2f + u * 3.0f) * 2f * Mathf.PI);
                    float h, tone;
                    if (warpUp) { h = 0.55f + 0.45f * Mathf.Pow(sw, 0.7f) * warpTh[iu] - 0.10f * twistW; tone = warpTone[iu] * (0.80f + 0.20f * sw) * (0.94f + 0.06f * twistW); }
                    else { h = 0.55f + 0.45f * Mathf.Pow(sf, 0.7f) * weftTh[iv] - 0.10f * twistF; tone = weftTone[iv] * (0.80f + 0.20f * sf) * (0.94f + 0.06f * twistF); }
                    // where a thread dives under the crossing one: a small dip and shadow
                    float ends = warpUp ? Mathf.Min(fv, 1f - fv) : Mathf.Min(fu, 1f - fu);
                    bool edgeOfFloat = warpUp ? (((iu + iv + 1) & 3) >= 2 || ((iu + iv - 1) & 3) >= 2) : true;
                    if (edgeOfFloat && ends < 0.18f) { float k = 1f - ends / 0.18f; h -= 0.25f * k; tone *= 1f - 0.18f * k; }
                    // fibre noise and the odd stray light fibre
                    tone *= 0.92f + 0.16f * Hash(x, y);
                    if (Hash(x * 7 + 3, y * 5 + 11) > 0.9985f) tone = 1.45f;
                    float g = Mathf.Clamp01(tone / 1.6f);
                    px[y * N + x] = new Color32((byte)(Mathf.Clamp01(h) * 255f), (byte)(g * 255f), 0, 255);
                }
            // (the tone's mean -> 0.5, so the shader's lerp(1 - y, 1 + y, g) keeps the cloth's calibrated colour)
            double sum = 0; foreach (var c in px) sum += c.g; float mean = (float)(sum / px.Length) / 255f, kk = 0.5f / Mathf.Max(mean, 1e-3f);
            for (int i = 0; i < px.Length; i++) { var c = px[i]; c.g = (byte)Mathf.Clamp(c.g * kk, 0f, 255f); px[i] = c; }
            var tex = new Texture2D(N, N, TextureFormat.RGBA32, true, true) { name = "skirt wool", wrapMode = TextureWrapMode.Repeat, filterMode = FilterMode.Trilinear, anisoLevel = 8, hideFlags = HideFlags.DontSave };
            tex.SetPixels32(px); tex.Apply(true, true);
            return tex;
        }
        // (VIEW 01 at 6 s, the skirt above both hems, L p10 / p50 / p90 and the spread of column means: the original 18 / 32 /
        //  54, 5.9; unshaded 33 / 35 / 37, 1.4; (0.85, 0.35, 1.5, 0.25) 28 / 37 / 41, 4.9; these 13.5 / 39 / 48.6 - folds as
        //  deep as the original's, the faces a little darker)
        /// how far the hem hangs below the asset's (m): the stocking's under-hem shading and the hand's limits follow it
        public static float HemDrop { get; private set; }
        float pushW; Vector3 pushAt;
        /// the skirt's hem at rest per column round (m; the lengthened asset's) - see HemAt
        static float[] hemRest; static float hemSkirtZ = SkirtZ;
        System.Random windRng = new System.Random(4242); float windLevel = 0.2f, windTarget = 0.2f, windClock = 2f;

        // ---- the render mesh (rest, live) and how each vertex rides on the sheet
        NativeArray<float3> restPos, outPos, restNrm, outNrm; NativeArray<float> hemW; Mesh liveMesh;
        NativeArray<float4> bindUV; NativeArray<float3> bindO, bindN;
        // ---- the sheet: NA x NR particles (index j * NA + i: column i round, row j down)
        // (small steps, one pass each: stiffer and cheaper than few steps with many passes - Macklin et al. 2019)
        const int NA = 72, NR = 26, Iters = 1, MaxSteps = 36; const float Hs = 1f / 360f, SkirtZ = -0.007f, PinAbove = 0.975f;
        NativeArray<float3> px, pv, ps, prest, pacc, pT, pB, rT, rB;
        NativeArray<float> pw, tethL, rowF;
        NativeArray<int2> cons; NativeArray<float> conL, conK, conF;
        readonly float[] colTop = new float[NA], colHem = new float[NA];
        bool settled; float leanPrev, simAcc;
        // the chain of jobs runs while the frame renders: scheduled in LateUpdate, completed (and the mesh uploaded) in the
        // next one - one frame behind the body (< 1 mm), off the main thread. Its own copy of the pose tables.
        JobHandle pending; bool hasPending; NativeArray<float4> poseA; NativeArray<float2> poseC;
        // ---- the body's outline: per height level the stocking's outermost points per sector round each leg (rest), and per
        // frame the hull's radius per angle about the skirt's axis
        NativeArray<float> hullR; NativeArray<float3> hullPts;
        const int HullBins = 180, HullLevels = 44, HullK = 48; const float HullY0 = 0.56f, HullDy = 0.01f;

        [System.Serializable] class Sph { public float[] center; public float radius; public int side; }
        [System.Serializable] class Leg { public int side; public Sph[] spheres; }
        [System.Serializable] class Fit { public Leg[] legs; public Sph[] hips; }

        Cloth cloth;
        readonly List<(Transform tr, Vector3 rest)> colliders = new List<(Transform, Vector3)>();
        float t;

        SheerMeshData data;

        // the mesh loads in edit mode too (look-dev captures); the cloth simulation only in play mode
        void OnEnable()
        {
            var smr = GetComponent<SkinnedMeshRenderer>();
            if (data == null || !smr.sharedMesh)
            {
                data = SheerMeshData.Load(file);
                Lengthen(data, lengthen);
                var mesh = data.BuildMesh("skirt");
                mesh.hideFlags = HideFlags.DontSave;
                smr.sharedMesh = mesh; smr.updateWhenOffscreen = true;
                var bb = mesh.bounds; bb.Expand(0.12f); smr.localBounds = bb;      // (the cloth swings out of the rest bounds)
            }
            var args = System.Environment.GetCommandLineArgs();
            int fi = System.Array.IndexOf(args, "-sheerSkirtFold");
            if (fi >= 0 && fi + 1 < args.Length)
            {
                var v = args[fi + 1].Split(',');
                for (int i = 0; i < 4 && i < v.Length; i++) if (float.TryParse(v[i], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var f)) foldShade[i] = f;
            }
            Shader.SetGlobalVector("_SheerSkirtFold", foldShade);
            int si = System.Array.IndexOf(args, "-sheerSkirtSheen");
            if (si >= 0 && si + 1 < args.Length && float.TryParse(args[si + 1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var sv)) sheen = sv;
            Shader.SetGlobalFloat("_SheerSkirtFoldSheen", sheen);
            int wi = System.Array.IndexOf(args, "-sheerSkirtWool");
            if (wi >= 0 && wi + 1 < args.Length)
            {
                var v = args[wi + 1].Split(',');
                for (int i = 0; i < 4 && i < v.Length; i++) if (float.TryParse(v[i], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var f)) wool[i] = f;
            }
            if (!woolTex) woolTex = MakeWool();
            Shader.SetGlobalTexture("_SheerSkirtWool", woolTex);
            Shader.SetGlobalVector("_SheerSkirtWoolK", wool);
            bool wantCloth = useUnityCloth || System.Array.IndexOf(args, "-sheerSkirtCloth") >= 0;
            if (Application.isPlaying && wantCloth && !cloth) SetupCloth();
            else if (Application.isPlaying && !wantCloth) SetupSheet(smr.sharedMesh);
        }

        /// A longer skirt (user, 2026-11-16): the panel below the hips stretched down along its own slope - the hem drops
        /// by L, the waistband and hips stay, the pleats keep their folds.
        static void Lengthen(SheerMeshData d, float L)
        {
            HemDrop = Mathf.Max(L, 0f);
            Shader.SetGlobalFloat("_SheerHemDrop", HemDrop);
            if (L <= 0f) return;
            var p = d.f["position"]; var nn = d.f["normal"]; int n = d.vertexCount;
            const float top = 0.94f, hem = 0.665f;
            for (int i = 0; i < n; i++)
            {
                float y = p[3 * i + 1];
                float q = Mathf.Clamp01((top - y) / (top - hem)); q = q * q * (3f - 2f * q);
                if (q <= 0f) continue;
                // (longer at the front and sides only; the back keeps its length (raised further, it bared the top of the legs
                //  and its own jagged inside edge at the side) -
                //  longer there too, the inside of its back wall hung between the thighs as a dark slab, review 3)
                float fr = 0.5f + 0.5f * Mathf.Cos(Ang(p[3 * i], p[3 * i + 2]));
                q *= fr * fr * (3f - 2f * fr);
                var nv = new Vector3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]);
                Vector3 down = Vector3.down - nv * Vector3.Dot(nv, Vector3.down);      // down the cloth's surface
                if (down.y > -0.3f) down = Vector3.down; else down /= -down.y;          // (vertical part 1)
                Vector3 dv = down * (L * q);
                p[3 * i] += dv.x; p[3 * i + 1] += dv.y; p[3 * i + 2] += dv.z;
                if (d.f.TryGetValue("uv1", out var u1) && d.dims["uv1"] >= 3) { int k = d.dims["uv1"] * i; u1[k] += dv.x; u1[k + 1] += dv.y; u1[k + 2] += dv.z; }
            }
        }

        static float Ang(float x, float z) => Mathf.Atan2(x, -(z - SkirtZ));                // 0 = front, + toward +x

        /// The skirt's hem at rest on the side of the body where p is (m). A pinch stays under it (TightsSim): drawn up past
        /// it, the tent went in under the skirt, and the hand that reached in after it lifted the hem with nothing visible
        /// doing it - the original session at 3 s (our skirt hangs 4.5 cm lower than the original's: longer by request).
        public static float HemAt(Vector3 p)
        {
            if (hemRest == null) return 0.645f;                                                // (no sheet yet: the front)
            float fi = (Ang(p.x, p.z) + Mathf.PI) / (2f * Mathf.PI) * NA - 0.5f;
            int i0 = ((Mathf.FloorToInt(fi) % NA) + NA) % NA, i1 = (i0 + 1) % NA;
            return Mathf.Lerp(hemRest[i0], hemRest[i1], fi - Mathf.Floor(fi));
        }
        static float LeanProfile(float y) { float lt = Mathf.Clamp01((y - 0.45f) / 0.17f); return 0.36f * (float)System.Math.Tanh(Mathf.Max(y - 0.07f, 0f) / 0.36f) * (1f - 0.12f * lt * lt * (3f - 2f * lt)); }

        // ------------------------------------------------------------------ the sheet and how the mesh rides on it
        void SetupSheet(Mesh mesh)
        {
            if (restPos.IsCreated) return;
            // clicks on the skirt must not grab the tights behind it: a collider at the rest shape, registered as a blocker
            var colMesh = Instantiate(mesh); colMesh.name = "skirt collider";
            var mc = gameObject.AddComponent<MeshCollider>(); mc.sharedMesh = colMesh;
            var input = FindAnyObjectByType<SheerInput>();
            if (input) { var list = new List<Collider>(input.blockers ?? new Collider[0]) { mc }; input.blockers = list.ToArray(); }
            liveMesh = mesh; liveMesh.MarkDynamic();
            var pos = data.f["position"]; var nrm = data.f["normal"]; int n = data.vertexCount;
            restPos = new NativeArray<float3>(n, Allocator.Persistent); outPos = new NativeArray<float3>(n, Allocator.Persistent);
            restNrm = new NativeArray<float3>(n, Allocator.Persistent); outNrm = new NativeArray<float3>(n, Allocator.Persistent);
            hemW = new NativeArray<float>(n, Allocator.Persistent);
            for (int i = 0; i < n; i++)
            {
                var p = new float3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]);
                restPos[i] = p; restNrm[i] = new float3(nrm[3 * i], nrm[3 * i + 1], nrm[3 * i + 2]);
                float drop = Mathf.Clamp01((0.985f - p.y) / 0.25f);
                hemW[i] = drop * drop * (3f - 2f * drop);
            }
            // the sheet is the skirt's INSIDE: the innermost folds of its pleats (the lowest radius about the skirt's axis over one
            // pleat - 22.5 deg, 16 pleats round - and +-4 mm of height, smoothed): resting on the body, every pleat lies outside it
            // (through the middle of the pleats, the inner folds sank into the thighs wherever the cloth rested on them)
            const int TB = 360, YB = 200; const float Y0 = 0.60f, DY = 0.002f;
            var sum = new float[TB * YB]; var cnt = new int[TB * YB];
            for (int k = 0; k < sum.Length; k++) sum[k] = 1e9f;
            float lowest = 1f;
            var hemCol = new float[NA]; for (int i = 0; i < NA; i++) hemCol[i] = 1f;
            for (int v = 0; v < n; v++)
            {
                var p = restPos[v]; float a = Ang(p.x, p.z), r = Mathf.Sqrt(p.x * p.x + (p.z - SkirtZ) * (p.z - SkirtZ));
                int tb = ((Mathf.FloorToInt((a + Mathf.PI) / (2f * Mathf.PI) * TB) % TB) + TB) % TB, yb = Mathf.Clamp(Mathf.FloorToInt((p.y - Y0) / DY), 0, YB - 1);
                sum[yb * TB + tb] = Mathf.Min(sum[yb * TB + tb], r); cnt[yb * TB + tb]++;
                lowest = Mathf.Min(lowest, p.y);
                // the hem of each column (+-3 deg)
                float fi = (a + Mathf.PI) / (2f * Mathf.PI) * NA - 0.5f;
                for (int i = Mathf.FloorToInt(fi - 1f); i <= Mathf.CeilToInt(fi + 1f); i++)
                {
                    int ii = ((i % NA) + NA) % NA; float ca = -Mathf.PI + (ii + 0.5f) * 2f * Mathf.PI / NA;
                    if (Mathf.Abs(Mathf.DeltaAngle(a * Mathf.Rad2Deg, ca * Mathf.Rad2Deg)) <= 3f) hemCol[ii] = Mathf.Min(hemCol[ii], p.y);
                }
            }
            var env = new float[TB * YB];
            for (int yb = 0; yb < YB; yb++)
            {
                // round each height: the filled bins, the gaps from their neighbours (circular)
                int any = -1; for (int tb = 0; tb < TB; tb++) if (cnt[yb * TB + tb] > 0) { any = tb; break; }
                if (any < 0) { for (int tb = 0; tb < TB; tb++) env[yb * TB + tb] = -1f; continue; }
                for (int tb = 0; tb < TB; tb++)
                {
                    if (cnt[yb * TB + tb] > 0) { env[yb * TB + tb] = sum[yb * TB + tb]; continue; }
                    int l = 1, r = 1; while (cnt[yb * TB + (tb - l + TB) % TB] == 0) l++; while (cnt[yb * TB + (tb + r) % TB] == 0) r++;
                    int il = yb * TB + (tb - l + TB) % TB, ir = yb * TB + (tb + r) % TB;
                    env[yb * TB + tb] = Mathf.Lerp(sum[il], sum[ir], l / (float)(l + r));
                }
            }
            for (int yb = 0; yb < YB; yb++)                                   // (heights with no fabric: the nearest that has)
                if (env[yb * TB] < 0f)
                {
                    int best = -1;
                    for (int d = 1; d < YB && best < 0; d++) { if (yb - d >= 0 && env[(yb - d) * TB] >= 0f) best = yb - d; else if (yb + d < YB && env[(yb + d) * TB] >= 0f) best = yb + d; }
                    for (int tb = 0; tb < TB; tb++) env[yb * TB + tb] = best >= 0 ? env[best * TB + tb] : 0.13f;
                }
            var tmp = new float[TB * YB];
            // (the lowest over a pleat and +-4 mm, then a light average: no steps)
            for (int yb = 0; yb < YB; yb++) for (int tb = 0; tb < TB; tb++) { float m = 1e9f; for (int d = -11; d <= 11; d++) m = Mathf.Min(m, env[yb * TB + (tb + d + TB) % TB]); tmp[yb * TB + tb] = m; }
            for (int yb = 0; yb < YB; yb++) for (int tb = 0; tb < TB; tb++) { float m = 1e9f; for (int d = -2; d <= 2; d++) { int y2 = yb + d; if (y2 < 0 || y2 >= YB) continue; m = Mathf.Min(m, tmp[y2 * TB + tb]); } env[yb * TB + tb] = m; }
            for (int yb = 0; yb < YB; yb++) for (int tb = 0; tb < TB; tb++) { float s = 0f; for (int d = -6; d <= 6; d++) s += env[yb * TB + (tb + d + TB) % TB]; tmp[yb * TB + tb] = s / 13f; }
            for (int yb = 0; yb < YB; yb++) for (int tb = 0; tb < TB; tb++) { float s = 0f; int c = 0; for (int d = -3; d <= 3; d++) { int y2 = yb + d; if (y2 < 0 || y2 >= YB) continue; s += tmp[y2 * TB + tb]; c++; } env[yb * TB + tb] = s / c; }
            float Env(float a, float y)
            {
                float ft = (a + Mathf.PI) / (2f * Mathf.PI) * TB - 0.5f, fy = Mathf.Clamp((y - Y0) / DY - 0.5f, 0f, YB - 1.001f);
                int t0 = ((Mathf.FloorToInt(ft) % TB) + TB) % TB, t1 = (t0 + 1) % TB, y0 = (int)fy; float at = ft - Mathf.Floor(ft), ay = fy - y0;
                return Mathf.Lerp(Mathf.Lerp(env[y0 * TB + t0], env[y0 * TB + t1], at), Mathf.Lerp(env[(y0 + 1) * TB + t0], env[(y0 + 1) * TB + t1], at), ay);
            }
            // the particles at rest
            int NP = NA * NR;
            px = new NativeArray<float3>(NP, Allocator.Persistent); pv = new NativeArray<float3>(NP, Allocator.Persistent);
            ps = new NativeArray<float3>(NP, Allocator.Persistent); prest = new NativeArray<float3>(NP, Allocator.Persistent);
            pacc = new NativeArray<float3>(NP, Allocator.Persistent); pT = new NativeArray<float3>(NP, Allocator.Persistent);
            pB = new NativeArray<float3>(NP, Allocator.Persistent); rT = new NativeArray<float3>(NP, Allocator.Persistent);
            rB = new NativeArray<float3>(NP, Allocator.Persistent);
            pw = new NativeArray<float>(NP, Allocator.Persistent); tethL = new NativeArray<float>(NP, Allocator.Persistent); rowF = new NativeArray<float>(NP, Allocator.Persistent);
            for (int i = 0; i < NA; i++) { colTop[i] = 0.995f; colHem[i] = Mathf.Min(hemCol[i] < 1f ? hemCol[i] : lowest, 0.70f) - 0.001f; }
            hemRest = (float[])colHem.Clone();
            for (int j = 0; j < NR; j++)
                for (int i = 0; i < NA; i++)
                {
                    float a = -Mathf.PI + (i + 0.5f) * 2f * Mathf.PI / NA, y = Mathf.Lerp(colTop[i], colHem[i], j / (NR - 1f)), r = Env(a, y);
                    int k = j * NA + i;
                    prest[k] = new float3(r * Mathf.Sin(a), y, SkirtZ - r * Mathf.Cos(a));
                    pw[k] = y >= PinAbove ? 0f : 1f; rowF[k] = j / (NR - 1f);
                }
            // distance constraints: down (rigid), round (never longer than the pressed skirt, but free to GATHER down to
            // gatherMin of it - the pleats close), the diagonals (shear: only against stretching, or a gathering ring could not
            // shorten them), two apart (bending: down both ways, round only against stretching).
            // (Until 2026-11-17 every one was two-sided: the circumference at each height could never shrink, so the skirt
            //  could not hang - it kept the flared shape it was pressed in, a lampshade; user: 'a ghost's shell, animated and
            //  inflated by some divine inner force', 'that obeys gravity'.)
            var C = new List<int2>(); var CL = new List<float>(); var CK = new List<float>(); var CF = new List<float>();
            void Add(int a, int b, float k, float floor) { if (pw[a] == 0f && pw[b] == 0f) return; C.Add(new int2(a, b)); CL.Add(math.distance(prest[a], prest[b])); CK.Add(k); CF.Add(floor); }
            float gm = Mathf.Clamp(gatherMin, 0.3f, 1f);
            for (int j = 0; j < NR; j++) for (int i = 0; i < NA; i++) Add(j * NA + i, j * NA + (i + 1) % NA, 0f, gm);
            for (int j = 0; j + 1 < NR; j++) for (int i = 0; i < NA; i++) Add(j * NA + i, (j + 1) * NA + i, 0f, 1f);
            for (int j = 0; j + 1 < NR; j++) for (int i = 0; i < NA; i++) { Add(j * NA + i, (j + 1) * NA + (i + 1) % NA, shearSoft, 0.3f); Add(j * NA + (i + 1) % NA, (j + 1) * NA + i, shearSoft, 0.3f); }
            for (int j = 0; j < NR; j++) for (int i = 0; i < NA; i++) Add(j * NA + i, j * NA + (i + 2) % NA, bendSoft, gm);
            for (int j = 0; j + 2 < NR; j++) for (int i = 0; i < NA; i++) Add(j * NA + i, (j + 2) * NA + i, bendSoft, 1f);
            cons = new NativeArray<int2>(C.ToArray(), Allocator.Persistent); conL = new NativeArray<float>(CL.ToArray(), Allocator.Persistent);
            conK = new NativeArray<float>(CK.ToArray(), Allocator.Persistent); conF = new NativeArray<float>(CF.ToArray(), Allocator.Persistent);
            // tethers: no particle farther from its column's top than the cloth between them (+2 %)
            for (int i = 0; i < NA; i++) { float acc = 0f; tethL[i] = 0f; for (int j = 1; j < NR; j++) { acc += math.distance(prest[(j - 1) * NA + i], prest[j * NA + i]); tethL[j * NA + i] = acc * 1.02f; } }
            // the rest frames, and every render vertex's place on the sheet
            new FrameJob { x = prest, T = rT, B = rB }.Schedule(NP, 256).Complete();
            bindUV = new NativeArray<float4>(n, Allocator.Persistent); bindO = new NativeArray<float3>(n, Allocator.Persistent); bindN = new NativeArray<float3>(n, Allocator.Persistent);
            for (int v = 0; v < n; v++)
            {
                var p = restPos[v]; float a = Ang(p.x, p.z);
                float fi = (a + Mathf.PI) / (2f * Mathf.PI) * NA - 0.5f; int i0 = ((Mathf.FloorToInt(fi) % NA) + NA) % NA, i1 = (i0 + 1) % NA; float ti = fi - Mathf.Floor(fi);
                float top = Mathf.Lerp(colTop[i0], colTop[i1], ti), hem = Mathf.Lerp(colHem[i0], colHem[i1], ti);
                float fj = Mathf.Clamp((top - p.y) / (top - hem) * (NR - 1), 0f, NR - 1.0001f); int j0 = Mathf.Min((int)fj, NR - 2); float tj = fj - j0;
                var g = new float4(i0, ti, j0, tj);
                Frame(prest, rT, rB, g, out var E, out var Tn, out var Bn, out var N);
                float3 o = p - E, nr = restNrm[v];
                bindUV[v] = g; bindO[v] = new float3(math.dot(o, Tn), math.dot(o, Bn), math.dot(o, N)); bindN[v] = new float3(math.dot(nr, Tn), math.dot(nr, Bn), math.dot(nr, N));
            }
            hullR = new NativeArray<float>(HullBins * HullLevels, Allocator.Persistent);
            for (int k = 0; k < NP; k++) px[k] = prest[k];
            float hmin = 1f, hmax = 0f; foreach (var hh in colHem) { hmin = Mathf.Min(hmin, hh); hmax = Mathf.Max(hmax, hh); }
            Debug.Log($"[skirt] cloth sheet {NA} x {NR} particles, {cons.Length} constraints; hem {hmin:0.000}..{hmax:0.000} m");
        }

        static void Frame(NativeArray<float3> x, NativeArray<float3> T, NativeArray<float3> B, float4 g, out float3 E, out float3 Tn, out float3 Bn, out float3 N)
        {
            int i0 = (int)g.x, j0 = (int)g.z, i1 = (i0 + 1) % NA, j1 = j0 + 1; float ti = g.y, tj = g.w;
            int a = j0 * NA + i0, b = j0 * NA + i1, c = j1 * NA + i0, d = j1 * NA + i1;
            E = math.lerp(math.lerp(x[a], x[b], ti), math.lerp(x[c], x[d], ti), tj);
            float3 t = math.lerp(math.lerp(T[a], T[b], ti), math.lerp(T[c], T[d], ti), tj), bb = math.lerp(math.lerp(B[a], B[b], ti), math.lerp(B[c], B[d], ti), tj);
            Tn = math.normalizesafe(t, new float3(1f, 0f, 0f)); N = math.normalizesafe(math.cross(Tn, bb), new float3(0f, 0f, -1f)); Bn = math.cross(N, Tn);
        }

        /// per particle: the unit directions round (T) and down (B) the sheet
        [BurstCompile]
        struct FrameJob : IJobParallelFor
        {
            [ReadOnly] public NativeArray<float3> x;
            [WriteOnly] public NativeArray<float3> T, B;
            public void Execute(int k)
            {
                int i = k % NA, j = k / NA;
                float3 t = x[j * NA + (i + 1) % NA] - x[j * NA + (i - 1 + NA) % NA];
                float3 b = x[math.min(j + 1, NR - 1) * NA + i] - x[math.max(j - 1, 0) * NA + i];
                T[k] = math.normalizesafe(t, new float3(1f, 0f, 0f)); B[k] = math.normalizesafe(b, new float3(0f, -1f, 0f));
            }
        }

        /// the render mesh on the sheet
        [BurstCompile]
        struct SkinJob : IJobParallelFor
        {
            [ReadOnly] public NativeArray<float3> x, rest, T, B, off, nrm; [ReadOnly] public NativeArray<float4> uv; [ReadOnly] public NativeArray<float> w;
            [WriteOnly] public NativeArray<float3> outP, outN;
            public float3 eye; public float bias;
            public void Execute(int v)
            {
                float4 g = uv[v];
                int i0 = (int)g.x, j0 = (int)g.z, i1 = (i0 + 1) % NA, j1 = j0 + 1; float ti = g.y, tj = g.w;
                int a = j0 * NA + i0, b = j0 * NA + i1, c = j1 * NA + i0, d = j1 * NA + i1;
                float3 E = math.lerp(math.lerp(x[a], x[b], ti), math.lerp(x[c], x[d], ti), tj);
                float3 t = math.lerp(math.lerp(T[a], T[b], ti), math.lerp(T[c], T[d], ti), tj), bb = math.lerp(math.lerp(B[a], B[b], ti), math.lerp(B[c], B[d], ti), tj);
                float3 Tn = math.normalizesafe(t, new float3(1f, 0f, 0f)), N = math.normalizesafe(math.cross(Tn, bb), new float3(0f, 0f, -1f)), Bn = math.cross(N, Tn);
                float3 o = off[v], n = nrm[v];
                // where the cloth has gathered round (s < 1) the pleats close with it: the pleat narrows round the skirt while
                // its folds keep their depth - steeper faces (the normal's round part / s), deeper shadows
                float s0 = math.distance(x[a], x[b]) / math.max(math.distance(rest[a], rest[b]), 1e-6f);
                float s1 = math.distance(x[c], x[d]) / math.max(math.distance(rest[c], rest[d]), 1e-6f);
                float s = math.clamp(math.lerp(s0, s1, tj), 0.3f, 1.2f);
                o.x *= s; n = new float3(n.x / s, n.y, n.z);
                float3 p = E + o.x * Tn + o.y * Bn + o.z * N;
                // (along the line of sight: the picture does not change, the depth does - cloth that nearly touches the thigh
                //  never z-fights or lets it poke through)
                if (bias > 0f) p += math.normalizesafe(eye - p) * (bias * w[v]);
                outP[v] = p; outN[v] = math.normalizesafe(n.x * Tn + n.y * Bn + n.z * N, n);
            }
        }

        /// the air on each particle this frame: from below and a little from the front, strongest at the hem; billows, pleat
        /// groups and single pleats on smooth noise drifting round the skirt (never periodic)
        [BurstCompile]
        struct AirJob : IJobParallelFor
        {
            [ReadOnly] public NativeArray<float> row;
            [WriteOnly] public NativeArray<float3> acc;
            public float t, air, up; public float2 flow, sway; public float flareAcc, liftAcc, tremorAcc, driftAcc;
            public void Execute(int k)
            {
                int i = k % NA; float ang = -math.PI + (i + 0.5f) * 2f * math.PI / NA;
                float hw = row[k]; hw *= hw;
                float3 radial = new float3(math.sin(ang), 0f, -math.cos(ang));
                float facing = math.saturate(0.55f + 0.45f * math.dot(radial.xz, -flow));
                float n1 = noise.snoise(new float2(ang * 1.1f + t * 0.23f, t * 0.17f));
                float n2 = noise.snoise(new float2(ang * 3.3f - t * 0.61f, t * 0.43f + 3.1f));
                float n3 = noise.snoise(new float2(ang * 9.5f + t * 2.1f, t * 1.7f + 7.7f));
                float a = air * facing;
                float flare = a * (0.55f + 0.45f * n1) + 0.30f * air * n2;
                float lift = up * a * math.saturate(0.5f + 0.5f * n1 + 0.35f * n2);
                // (the pleats' tremor goes on in calm air too: at 0.12 of it the skirt stood still between the body's moves -
                //  4 x less change frame to frame than the original's, whose hem sways all the time (independent review 6);
                //  in and out only, it never lifts the hem)
                acc[k] = radial * (flare * flareAcc + n3 * tremorAcc * (0.60f + 0.40f * air)) * hw
                       + new float3(0f, 1f, 0f) * (lift * liftAcc * hw * hw)
                       + new float3(flow.x, 0f, flow.y) * (driftAcc * air * (1f - up * 0.5f) * hw)
                       + new float3(sway.x, 0f, sway.y) * hw;
            }
        }

        /// The sheet over `steps` substeps of Hs: gravity and the air, the waistband with the pelvis (lean eased from leanA
        /// to leanB), distance constraints (Gauss-Seidel, softness per constraint), tethers, the body (never inside its
        /// outline), the tent of pulled fabric and the hand / forearm reaching under the hem (the cloth drapes over them).
        [BurstCompile]
        struct StepJob : IJob
        {
            public NativeArray<float3> x, v, xs;
            [ReadOnly] public NativeArray<float3> rest, acc;
            [ReadOnly] public NativeArray<float> w, tethL;
            [ReadOnly] public NativeArray<int2> cons; [ReadOnly] public NativeArray<float> conL, conK, conF;
            [ReadOnly] public NativeArray<float> hullR;
            public int steps; public float h, leanA, leanB, drag, clear, airOn, spring;
            public float3 push; public float pushW;

            static float LP(float y) { float lt = math.saturate((y - 0.45f) / 0.17f); return 0.36f * math.tanh(math.max(y - 0.07f, 0f) / 0.36f) * (1f - 0.12f * lt * lt * (3f - 2f * lt)); }

            float HullAt(float th, float y)
            {
                float fb = (th + math.PI) / (2f * math.PI) * HullBins - 0.5f, fl = math.clamp((y - HullY0) / HullDy, 0f, HullLevels - 1.001f);
                int b0 = (int)math.floor(fb); float ab = fb - b0; int l0 = (int)fl; float al = fl - l0;
                int b1 = ((b0 + 1) % HullBins + HullBins) % HullBins; b0 = (b0 % HullBins + HullBins) % HullBins;
                float v00 = hullR[l0 * HullBins + b0], v01 = hullR[l0 * HullBins + b1], v10 = hullR[(l0 + 1) * HullBins + b0], v11 = hullR[(l0 + 1) * HullBins + b1];
                return math.lerp(math.lerp(v00, v01, ab), math.lerp(v10, v11, ab), al);
            }

            float3 Body(float3 p, float lean)
            {
                float cx = lean * LP(p.y), dx = p.x - cx, dz = p.z - SkirtZ, r = math.sqrt(dx * dx + dz * dz);
                if (r < 1e-6f) return p;
                float hr = HullAt(math.atan2(dx, -dz), p.y);
                if (hr <= 0f || r >= hr + clear) return p;
                float k = (hr + clear) / r;
                return new float3(cx + dx * k, p.y, SkirtZ + dz * k);
            }

            public void Execute()
            {
                int n = x.Length;
                for (int s = 0; s < steps; s++)
                {
                    float lean = math.lerp(leanA, leanB, (s + 1f) / steps);
                    for (int k = 0; k < n; k++)
                    {
                        xs[k] = x[k];
                        if (w[k] == 0f) { float3 r = rest[k]; x[k] = new float3(r.x + lean * LP(r.y), r.y, r.z); continue; }
                        float3 ak = new float3(0f, -9.81f, 0f) + acc[k] * airOn;
                        // the pressed pleats: a gathered ring pushes back out toward its pressed width (gently - gravity wins)
                        if (spring > 0f)
                        {
                            float3 xk = x[k], r0v = rest[k];
                            float dx = xk.x - lean * LP(xk.y), dz = xk.z - SkirtZ, r = math.sqrt(dx * dx + dz * dz);
                            float r0 = math.sqrt(r0v.x * r0v.x + (r0v.z - SkirtZ) * (r0v.z - SkirtZ));
                            if (r < r0 && r > 1e-6f) ak += new float3(dx / r, 0f, dz / r) * (spring * (r0 - r));
                        }
                        float3 vk = (v[k] + ak * h) / (1f + drag * h);
                        v[k] = vk; x[k] += vk * h;
                    }
                    for (int it = 0; it < Iters; it++)
                    {
                        for (int c = 0; c < cons.Length; c++)
                        {
                            int2 e = cons[c]; float w1 = w[e.x], w2 = w[e.y], ws = w1 + w2;
                            float3 d = x[e.y] - x[e.x]; float len = math.length(d);
                            if (len < 1e-9f) continue;
                            // never longer than at rest; shorter only down to conF x rest (1 = rigid both ways)
                            float L = conL[c], lo = L * conF[c], tgt = len > L ? L : (len < lo ? lo : len);
                            if (tgt == len) continue;
                            float dl = (len - tgt) / (ws * (1f + conK[c]) * len);
                            x[e.x] += d * (dl * w1); x[e.y] -= d * (dl * w2);
                        }
                        for (int k = 0; k < n; k++)
                        {
                            if (w[k] == 0f) continue;
                            // tether to the column's top: never farther than the cloth between them
                            int top = k % NA; float3 d = x[k] - x[top]; float len = math.length(d), L = tethL[k];
                            if (len > L && len > 1e-9f) x[k] = x[top] + d * (L / len);
                            x[k] = Body(x[k], lean);
                        }
                    }
                    // the tent of pulled fabric just under the hem holds the cloth out a little.
                    // (No hand: the hand is never drawn, and a hem lifted by nothing visible read as someone lifting the skirt -
                    //  the user: 'it must not be a sexual thing'. A forearm collider, before it a 'lift toward the hand' rule,
                    //  were removed 2026-11-17; the pinch stays under the hem instead - TightsSim, SkirtCloth.HemAt.)
                    // (a soft, wide push - 5 cm, a share per step - so the cloth bulges round the tent; projected hard onto a
                    //  3 cm sphere, single particles of the sheet jumped out and the hem broke into faceted flaps with the
                    //  skirt's dark inside showing between them, review 2026-11-17 at 12.9 s)
                    if (pushW > 0f)
                        for (int k = 0; k < n; k++)
                        {
                            if (w[k] == 0f) continue;
                            float R = 0.03f * pushW; float3 d = x[k] - push; float len = math.length(d);
                            if (len < R)
                            {
                                // (3 cm, a small share per step: 5 cm at 0.12 still curled the hem into a ruffle at 12.9 s)
                                float3 tgt = push + math.normalizesafe(d, new float3(0f, 1f, 0f)) * R;
                                float wgt = 1f - len / R; wgt = wgt * wgt * (3f - 2f * wgt);
                                x[k] = math.lerp(x[k], tgt, 0.06f * wgt);
                            }
                        }
                    for (int k = 0; k < n; k++) if (w[k] > 0f) v[k] = (x[k] - xs[k]) / h;
                }
            }
        }

        // ------------------------------------------------------------------ the body's outline
        /// The outline wrapping both legs and the hips as they stand now - the convex hull of the posed stocking's outermost
        /// points at each height - as a radius per angle about the skirt's axis: where the skirt comes to rest, and what it
        /// may never be inside.
        [BurstCompile]
        struct HullJob : IJobParallelFor
        {
            [ReadOnly] public NativeArray<float3> pts;
            [ReadOnly] public NativeArray<float4> poseA; [ReadOnly] public NativeArray<float2> poseC;
            public float lean;
            [NativeDisableParallelForRestriction] public NativeArray<float> hullR;

            public void Execute(int lv)
            {
                float y = HullY0 + lv * HullDy;
                int n = 2 * HullK;
                var P = new NativeArray<float2>(n, Allocator.Temp);
                for (int k = 0; k < n; k++) P[k] = PoseMath.Pose(pts[lv * n + k], poseA, poseC, float4.zero, float4.zero).xz;
                for (int i = 1; i < n; i++)
                {
                    var key = P[i]; int k = i - 1;
                    while (k >= 0 && (P[k].x > key.x || (P[k].x == key.x && P[k].y > key.y))) { P[k + 1] = P[k]; k--; }
                    P[k + 1] = key;
                }
                var H = new NativeArray<float2>(2 * n + 2, Allocator.Temp); int h = 0;
                for (int i = 0; i < n; i++) { while (h >= 2 && Cross(H[h - 2], H[h - 1], P[i]) <= 0f) h--; H[h++] = P[i]; }
                for (int i = n - 2, lo = h + 1; i >= 0; i--) { while (h >= lo && Cross(H[h - 2], H[h - 1], P[i]) <= 0f) h--; H[h++] = P[i]; }
                float lt = math.saturate((y - 0.45f) / 0.17f);
                float2 c = new float2(lean * (0.36f * math.tanh(math.max(y - 0.07f, 0f) / 0.36f) * (1f - 0.12f * lt * lt * (3f - 2f * lt))), SkirtZ);
                for (int b = 0; b < HullBins; b++)
                {
                    float th = -math.PI + (b + 0.5f) * (2f * math.PI / HullBins);
                    float2 d = new float2(math.sin(th), -math.cos(th));
                    float best = 0f;
                    for (int e = 0; e + 1 < h; e++)
                    {
                        float2 A = H[e], E = H[e + 1] - H[e], w = A - c;
                        float det = -d.x * E.y + d.y * E.x;
                        if (math.abs(det) < 1e-12f) continue;
                        float t = (-w.x * E.y + w.y * E.x) / det, s = (d.x * w.y - d.y * w.x) / det;
                        if (s >= 0f && s <= 1f && t > best) best = t;
                    }
                    hullR[lv * HullBins + b] = best;
                }
                P.Dispose(); H.Dispose();
            }

            static float Cross(float2 o, float2 a, float2 b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
        }

        /// The stocking's outermost rest points per height level, leg and sector round the leg's own axis (taken once).
        void BuildHullPoints()
        {
            var L = sim.lattice; var rest = sim.T.rest;
            int n = 2 * HullK;
            var best = new float[HullLevels * n]; var pt = new Vector3[HullLevels * n];
            var ax = new float[HullLevels * 2]; var az = new float[HullLevels * 2];
            for (int lv = 0; lv < HullLevels; lv++)
                for (int leg = 0; leg < 2; leg++)
                {
                    float y = HullY0 + lv * HullDy, f = Mathf.Clamp((y - L.y0) / L.dy, 0f, L.NV - 1.001f); int j = (int)f; float a = f - j;
                    ax[lv * 2 + leg] = Mathf.Lerp(L.ax[leg][j], L.ax[leg][j + 1], a); az[lv * 2 + leg] = Mathf.Lerp(L.az[leg][j], L.az[leg][j + 1], a);
                }
            for (int i = 0; i < best.Length; i++) best[i] = -1f;
            for (int v = 0; v < rest.Length; v++)
            {
                float3 p = rest[v];
                float fl = (p.y - HullY0) / HullDy; int lv = Mathf.RoundToInt(fl);
                if (lv < 0 || lv >= HullLevels || Mathf.Abs(fl - lv) > 0.4f) continue;
                int leg = p.x >= 0f ? 0 : 1;
                float dx = p.x - ax[lv * 2 + leg], dz = p.z - az[lv * 2 + leg];
                int k = Mathf.Clamp(Mathf.FloorToInt((Mathf.Atan2(dx, dz) + Mathf.PI) / (2f * Mathf.PI) * HullK), 0, HullK - 1);
                float r = dx * dx + dz * dz; int o = lv * n + leg * HullK + k;
                if (r > best[o]) { best[o] = r; pt[o] = new Vector3(p.x, HullY0 + lv * HullDy, p.z); }
            }
            hullPts = new NativeArray<float3>(HullLevels * n, Allocator.Persistent);
            for (int lv = 0; lv < HullLevels; lv++)
                for (int leg = 0; leg < 2; leg++)
                    for (int k = 0; k < HullK; k++)
                    {
                        int o = lv * n + leg * HullK + k;
                        if (best[o] < 0f)
                            for (int d = 1; d < HullK && best[o] < 0f; d++)
                                foreach (int kk in new[] { (k + d) % HullK, (k - d + HullK) % HullK })
                                    if (best[lv * n + leg * HullK + kk] >= 0f) { best[o] = best[lv * n + leg * HullK + kk]; pt[o] = pt[lv * n + leg * HullK + kk]; break; }
                        hullPts[o] = best[o] >= 0f ? (float3)pt[o] : new float3(ax[lv * 2 + leg], HullY0 + lv * HullDy, az[lv * 2 + leg]);
                    }
        }

        /// the legs changed shape (TightsSim.SetShape): take the stocking's outline again
        public void RefreshHull() { if (hullPts.IsCreated) hullPts.Dispose(); hullPts = default; }

        void OnDisable()
        {
            if (hasPending) { pending.Complete(); hasPending = false; }
            if (poseA.IsCreated) poseA.Dispose(); if (poseC.IsCreated) poseC.Dispose();
            foreach (var a in new[] { restPos, outPos, restNrm, outNrm, px, pv, ps, prest, pacc, pT, pB, rT, rB, bindO, bindN }) if (a.IsCreated) a.Dispose();
            foreach (var a in new[] { hemW, pw, tethL, rowF, conL, conK, conF, hullR }) if (a.IsCreated) a.Dispose();
            if (bindUV.IsCreated) bindUV.Dispose(); if (cons.IsCreated) cons.Dispose(); if (hullPts.IsCreated) hullPts.Dispose();
        }

        // ------------------------------------------------------------------ every frame
        readonly System.Diagnostics.Stopwatch sw = new System.Diagnostics.Stopwatch();
        float lastJobMs, lastWaitMs;
        void Update() { if (cloth) UpdateUnityCloth(); }
        void LateUpdate()
        {
            if (cloth || !restPos.IsCreated || !liveMesh) return;
            if (hasPending)
            {
                sw.Restart(); pending.Complete(); hasPending = false; lastWaitMs = (float)sw.Elapsed.TotalMilliseconds;
                liveMesh.SetVertices(outPos); liveMesh.SetNormals(outNrm);
            }
            float dt = Mathf.Min(Time.deltaTime, 0.1f);
            t += Time.deltaTime;
            // the air: a wide range (user, 2026-11-16: 'need way more variation in breeze intensity') - spells of calm, light
            // air, a breeze, gusts, now and then a strong gust, each held a few seconds and eased into, short puffs inside the
            // windy spells, a flicker on top; never periodic. It rises from below (70 - 95 %), its horizontal part from the
            // front, wandering +-40 deg (the replay's measured gusts scale it)
            windClock -= dt;
            if (windClock <= 0f)
            {
                float r = (float)windRng.NextDouble();
                windTarget = r < 0.24f ? 0.03f : r < 0.48f ? 0.22f : r < 0.70f ? 0.45f : r < 0.90f ? 0.75f : 1f;
                windTarget = Mathf.Pow(windTarget, 1f / Mathf.Clamp(gustiness, 0.2f, 3f));
                windClock = 3f + 7f * (float)windRng.NextDouble();
            }
            float wtau = windTarget > windLevel ? 0.9f : 1.8f;
            windLevel += (windTarget - windLevel) * (1f - Mathf.Exp(-dt / wtau));
            float puff = Mathf.Max(N1(t * 0.55f, 8.1f), 0f);
            float air = Mathf.Clamp01(windLevel * (0.85f + 0.15f * N1(t * 0.9f, 7.3f)) + 0.30f * puff * puff * Mathf.Clamp01(windLevel * 2f));
            air = Mathf.Clamp01(air * windAmplitude * Mathf.Max(gustGain, 0f));
            float up = 0.82f + 0.13f * N1(t * 0.07f, 2.2f), fa = 0.70f * N1(t * 0.05f, 5.5f);
            sw.Restart();
            if (sim && sim.lattice != null && sim.PoseTableA.IsCreated)
            {
                float lean = sim.sway;
                if (!hullPts.IsCreated) BuildHullPoints();
                if (!poseA.IsCreated) { poseA = new NativeArray<float4>(sim.PoseTableA.Length, Allocator.Persistent); poseC = new NativeArray<float2>(sim.PoseTableC.Length, Allocator.Persistent); }
                poseA.CopyFrom(sim.PoseTableA); poseC.CopyFrom(sim.PoseTableC);
                var hull = new HullJob { pts = hullPts, poseA = poseA, poseC = poseC, lean = lean, hullR = hullR }.Schedule(HullLevels, 1);
                bool held = sim.HeldPatch(out var at) && at.y > 0.56f - HemDrop;
                if (held) pushAt = at;
                pushW = Mathf.MoveTowards(pushW, held ? 1f : 0f, dt / (held ? 0.10f : 0.25f));
                var swayV = new float2(N1(t * 0.43f, 3.7f), 0.6f * N1(t * 0.37f, 9.1f)) * swayAcc;
                var airJ = new AirJob { row = rowF, acc = pacc, t = t, air = air, up = up, flow = new float2(Mathf.Sin(fa), Mathf.Cos(fa)), sway = swayV,
                                        flareAcc = flareAcc, liftAcc = liftAcc, tremorAcc = tremorAcc, driftAcc = driftAcc }.Schedule(px.Length, 512, hull);
                var step = new StepJob { x = px, v = pv, xs = ps, rest = prest, acc = pacc, w = pw, tethL = tethL, cons = cons, conL = conL, conK = conK, conF = conF, hullR = hullR, spring = pleatSpring,
                                         h = Hs, drag = drag, clear = drapeClear, airOn = 1f, push = pushAt, pushW = pushW };
                if (!settled)
                {
                    // the first frame: the skirt falls into place on the body before anyone sees it (1.5 s, no air)
                    airJ.Complete();
                    for (int k = 0; k < px.Length; k++) { var r = prest[k]; px[k] = new float3(r.x + lean * LeanProfile(r.y), r.y, r.z); pv[k] = float3.zero; }
                    step.steps = 720; step.leanA = step.leanB = lean; step.airOn = 0f; step.pushW = 0f;
                    step.Schedule().Complete();
                    settled = true; leanPrev = lean; simAcc = 0f;
                    Debug.Log($"[skirt] settled on the body in {sw.Elapsed.TotalMilliseconds:0} ms");
                    step.airOn = 1f; step.pushW = pushW;
                }
                bool first = !settledShown; settledShown = true;
                simAcc += dt; int nsteps = Mathf.Min(Mathf.FloorToInt(simAcc / Hs), MaxSteps); simAcc -= nsteps * Hs; if (simAcc > Hs) simAcc = Hs;
                step.steps = nsteps; step.leanA = leanPrev; step.leanB = lean; lastSteps = nsteps;
                var stepH = step.Schedule(airJ);
                leanPrev = lean;
                var fr = new FrameJob { x = px, T = pT, B = pB }.Schedule(px.Length, 256, stepH);
                var camT = Camera.main ? Camera.main.transform : null;
                var skin = new SkinJob { x = px, rest = prest, T = pT, B = pB, off = bindO, nrm = bindN, uv = bindUV, w = hemW, outP = outPos, outN = outNrm,
                                         eye = camT ? (float3)transform.InverseTransformPoint(camT.position) : new float3(0f, 0.5f, -1.2f), bias = camT ? hemBias : 0f };
                pending = skin.Schedule(outPos.Length, 1024, fr); hasPending = true;
                JobHandle.ScheduleBatchedJobs();
                // (-sheerLogSkirt: once a second the chain is timed on its own - completed at once)
                if (logSkirt && Time.unscaledTime >= nextLog && !first)
                {
                    nextLog = Time.unscaledTime + 1f; sw.Restart(); pending.Complete(); lastJobMs = (float)sw.Elapsed.TotalMilliseconds;
                    LogDrape(lean, nsteps);
                }
                // (the first frame shows the settled skirt at once; captures - fixed frame steps, often far longer than a real
                //  frame - draw the skirt of THEIR frame: one frame behind, a 2-fps capture showed it half a second behind the body)
                if (first || Time.captureFramerate > 0) { pending.Complete(); hasPending = false; liveMesh.SetVertices(outPos); liveMesh.SetNormals(outNrm); }
                return;
            }
            else
            {
                // (no body yet: the sheet at rest)
                new FrameJob { x = prest, T = pT, B = pB }.Schedule(px.Length, 256).Complete();
                new SkinJob { x = prest, rest = prest, T = pT, B = pB, off = bindO, nrm = bindN, uv = bindUV, w = hemW, outP = outPos, outN = outNrm, bias = 0f }.Schedule(outPos.Length, 1024).Complete();
            }
            liveMesh.SetVertices(outPos);
            liveMesh.SetNormals(outNrm);
        }

        public void SetTime(float time) { t = time; }
        bool settledShown; int lastSteps;

        // -sheerLogSkirt: once a second, per height and angle about the skirt's axis: the body's outline (hull) / the cloth's
        // radius there now (mm), and the time the cloth took
        static readonly bool logSkirt = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerLogSkirt") >= 0;
        float nextLog;
        void LogDrape(float lean, int nsteps)
        {
            var sb = new System.Text.StringBuilder($"[skirt] t={t:0.0} lean {lean:0.000} substeps {nsteps}: the chain {lastJobMs:0.00} ms on its own, the main thread waited {lastWaitMs:0.00} ms (hull / cloth, mm):");
            // (where the sheet, the drawn mesh and the posed hips are, side to side, at 0.90 m: mean x of each, mm)
            {
                double sx = 0, sn = 0, mx = 0, mn = 0; float hx0 = 1e9f, hx1 = -1e9f;
                for (int k = 0; k < px.Length; k++) if (Mathf.Abs(px[k].y - 0.90f) < 0.01f) { sx += px[k].x; sn++; }
                for (int v = 0; v < outPos.Length; v++) if (Mathf.Abs(outPos[v].y - 0.90f) < 0.005f) { mx += outPos[v].x; mn++; }
                if (hullPts.IsCreated) { int lv = Mathf.RoundToInt((0.90f - HullY0) / HullDy); for (int k = 0; k < 2 * HullK; k++) { var q = PoseMath.Pose(hullPts[lv * 2 * HullK + k], poseA, poseC, float4.zero, float4.zero); hx0 = Mathf.Min(hx0, q.x); hx1 = Mathf.Max(hx1, q.x); } }
                sb.Append($"\n   at 0.90 m: sheet mean x {sx / System.Math.Max(sn, 1) * 1000:0.0}, drawn skirt mean x {mx / System.Math.Max(mn, 1) * 1000:0.0}, posed hips x {hx0 * 1000:0.0}..{hx1 * 1000:0.0} (centre {(hx0 + hx1) * 500:0.0}), lean shift {lean * LeanProfile(0.90f) * 1000:0.0}");
            }
            foreach (float y in new[] { 0.66f, 0.70f, 0.74f, 0.78f, 0.84f, 0.90f })
            {
                float cx = lean * LeanProfile(y);
                sb.Append($"\n   y {y:0.00}:");
                foreach (int deg in new[] { 0, 45, 90, 135, 180, -135, -90, -45 })
                {
                    float best = 1e9f, rr = 0f;
                    for (int k = 0; k < px.Length; k++)
                    {
                        var q = px[k]; float da = Mathf.Abs(Mathf.DeltaAngle(Ang(q.x - cx, q.z) * Mathf.Rad2Deg, deg)), dy = Mathf.Abs(q.y - y);
                        float sc = da * 0.002f + dy; if (sc < best) { best = sc; rr = Mathf.Sqrt((q.x - cx) * (q.x - cx) + (q.z - SkirtZ) * (q.z - SkirtZ)); }
                    }
                    int b = Mathf.Clamp(Mathf.FloorToInt((deg * Mathf.Deg2Rad + Mathf.PI) / (2f * Mathf.PI) * HullBins), 0, HullBins - 1);
                    int lv = Mathf.Clamp(Mathf.RoundToInt((y - HullY0) / HullDy), 0, HullLevels - 1);
                    sb.Append($"  {deg}: {hullR[lv * HullBins + b] * 1000f:0}/{rr * 1000f:0}");
                }
            }
            Debug.Log(sb.ToString());
        }

        // ------------------------------------------------------------------ Unity Cloth (opt-in: -sheerSkirtCloth)
        void SetupCloth()
        {
            cloth = gameObject.AddComponent<Cloth>();
            cloth.useGravity = false;                       // the rest shape is already the draped skirt
            cloth.stretchingStiffness = stretchingStiffness;
            cloth.bendingStiffness = bendingStiffness;
            cloth.damping = damping;
            cloth.friction = 0.6f;
            cloth.worldVelocityScale = 0f; cloth.worldAccelerationScale = 0f;
            cloth.clothSolverFrequency = solverFrequency;
            cloth.sleepThreshold = 0f;
            cloth.useTethers = true;
            var pin = new Dictionary<Vector3Int, float>();
            var pos = data.f["position"]; var uv2 = data.f.ContainsKey("uv2") ? data.f["uv2"] : null; int d2 = uv2 != null ? data.dims["uv2"] : 0;
            for (int i = 0; i < data.vertexCount; i++)
            {
                var k = Key(new Vector3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]));
                float w = uv2 != null ? uv2[d2 * i] : 0f;
                pin[k] = pin.TryGetValue(k, out var w0) ? Mathf.Max(w0, w) : w;
            }
            var cv = cloth.vertices; var coeff = new ClothSkinningCoefficient[cv.Length];
            for (int i = 0; i < cv.Length; i++)
            {
                pin.TryGetValue(Key(cv[i]), out float w);
                coeff[i].maxDistance = w > 0.5f ? 0f : Mathf.Lerp(0.002f, maxHemTravel, Mathf.Clamp01((0.985f - cv[i].y) / 0.25f));
                coeff[i].collisionSphereDistance = 0f;
            }
            cloth.coefficients = coeff;
            var fit = JsonUtility.FromJson<Fit>(File.ReadAllText(Path.Combine(Application.streamingAssetsPath, "skirt_colliders.json")));
            var pairs = new List<ClothSphereColliderPair>();
            foreach (var leg in fit.legs)
                for (int i = 0; i + 1 < leg.spheres.Length; i++)
                    pairs.Add(new ClothSphereColliderPair(Sphere(leg.spheres[i]), Sphere(leg.spheres[i + 1])));
            var hips = new List<SphereCollider>();
            foreach (var h in fit.hips) hips.Add(Sphere(h));
            for (int i = 0; i + 1 < hips.Count; i += 2) pairs.Add(new ClothSphereColliderPair(hips[i], hips[i + 1]));
            for (int i = 0; i + 2 < hips.Count; i++) pairs.Add(new ClothSphereColliderPair(hips[i], hips[i + 2]));
            foreach (var leg in fit.legs)
                pairs.Add(new ClothSphereColliderPair(Find(leg.spheres[leg.spheres.Length - 1]), hips[leg.side > 0 ? 0 : 1]));
            cloth.sphereColliders = pairs.ToArray();
        }

        static Vector3Int Key(Vector3 p) => new Vector3Int(Mathf.RoundToInt(p.x * 1e5f), Mathf.RoundToInt(p.y * 1e5f), Mathf.RoundToInt(p.z * 1e5f));

        readonly Dictionary<Sph, SphereCollider> made = new Dictionary<Sph, SphereCollider>();
        SphereCollider Find(Sph s) => made.TryGetValue(s, out var c) ? c : null;

        SphereCollider Sphere(Sph s)
        {
            var go = new GameObject("skirt collider");
            go.transform.SetParent(transform.parent, false);
            var rest = new Vector3(s.center[0], s.center[1], s.center[2]);
            go.transform.localPosition = rest;
            var c = go.AddComponent<SphereCollider>(); c.radius = s.radius; c.isTrigger = true;
            colliders.Add((go.transform, rest)); made[s] = c;
            return c;
        }

        void UpdateUnityCloth()
        {
            t += Time.deltaTime;
            if (sim) foreach (var (tr, rest) in colliders) tr.localPosition = rest + sim.PoseOffset(rest);
            float a = windAmplitude, g = gustGain, tt = t;
            float wx = a * g * (0.6f + 0.4f * Mathf.Sin(2 * Mathf.PI * 0.21f * tt + 0.3f) + 0.25f * Mathf.Sin(2 * Mathf.PI * 0.83f * tt + 1.1f))
                       + 0.25f * a * Mathf.Sin(2 * Mathf.PI * 2.7f * tt + 0.4f);
            float wy = a * g * (0.5f + 0.35f * Mathf.Sin(2 * Mathf.PI * 0.17f * tt + 2.0f)) + 0.2f * a * Mathf.Sin(2 * Mathf.PI * 2.3f * tt + 1.7f);
            cloth.externalAcceleration = new Vector3(wx, (g - 1f) * 1.6f, wy);
            cloth.randomAcceleration = new Vector3(0.35f, 0.15f, 0.35f) * a * g;
        }

        // smooth 1-D value noise in -1 .. 1 (as SheerBodyMotion's)
        static float N1(float x, float seed)
        {
            x += seed * 17.13f;
            float i = Mathf.Floor(x), f = x - i, s = f * f * f * (f * (f * 6f - 15f) + 10f);
            return Mathf.Lerp(H1(i), H1(i + 1f), s);
        }
        static float H1(float i) { float h = Mathf.Sin(i * 127.1f + 311.7f) * 43758.5453f; return 2f * (h - Mathf.Floor(h)) - 1f; }
    }
}
