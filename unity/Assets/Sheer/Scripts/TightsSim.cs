// SHEER — real-time stocking simulation.
// Every frame (Burst jobs): pose (idle balance sway + knees pressed together after a tear) on body and stocking;
// areal stretch of the pose per vertex -> UV3.x; normals. The pulled fabric itself is simulated on the GPU
// (TightsCloth: per-leg pre-stretched knit lattice, the hand holding a pinched patch) and reaches the picture
// through textures: the stocking's vertex shader adds its displacement, the fragment shaders read its stretch and
// lift. Pulls: grab = stocking point under the cursor; the pinched patch follows the drag as far as the knit gives
// (HandMap); tension = the hand's drag against that reach; pre-run dashes above 0.58, tear at 1; on release the
// fabric's own tension pulls it back onto the leg. The tear state is rasterised on the GPU per leg.
using System.Collections.Generic;
using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;
using UnityEngine;

namespace Sheer
{
    /// The body's pose (same math as SheerCloth.hlsl, SheerPosePoint): per leg and per height bin (Bins over 0..1 m of
    /// rest height) every horizontal cross-section is moved rigidly - shifted (dx, dz) and turned by phi about the
    /// vertical through the leg's axis (centre cx, cz) - so skin and stocking at the same height move together and can
    /// never cross. The big toe turns up about its joint first. What straddles the midline blends the two legs' poses.
    public static class PoseMath
    {
        public const int Bins = 512;
        static float Smooth(float e0, float e1, float x) { float t = math.saturate((x - e0) / (e1 - e0)); return t * t * (3 - 2 * t); }

        /// The big toe lifted by alpha (rad) about its joint (geo: x = |x| of the cleft to the second toe, y / z = joint).
        public static float3 ToeRaise(float3 p, float alpha, float s, float4 geo)
        {
            if (alpha <= 0f) return p;
            float w = Smooth(geo.z + 0.006f, geo.z - 0.014f, p.z) * (1f - Smooth(geo.x - 0.006f, geo.x + 0.003f, s * p.x)) * Smooth(0.056f, 0.042f, p.y);
            if (w <= 0f) return p;
            math.sincos(alpha * w, out float sb, out float cb);
            float dy = p.y - geo.y, dz = p.z - geo.z;
            return new float3(p.x, geo.y + dy * cb - dz * sb, geo.z + dy * sb + dz * cb);
        }

        public static void Sample(NativeArray<float4> A, NativeArray<float2> C, int leg, float y, out float4 a, out float2 c)
        {
            float f = math.clamp(y * Bins - 0.5f, 0f, Bins - 1.001f); int b = (int)f; float t = f - b; int o = leg * Bins + b;
            a = math.lerp(A[o], A[o + 1], t); c = math.lerp(C[o], C[o + 1], t);
        }

        public static float3 Leg(float3 p, int leg, NativeArray<float4> A, NativeArray<float2> C)
        {
            Sample(A, C, leg, p.y, out var a, out var c);
            math.sincos(a.z, out float sn, out float cs);
            float2 r = p.xz - c;
            return new float3(c.x + r.x * cs + r.y * sn + a.x, p.y, c.y - r.x * sn + r.y * cs + a.y);
        }

        public static float3 Pose(float3 p, NativeArray<float4> A, NativeArray<float2> C, float4 toe, float4 geo) => Pose(p, p.x, A, C, toe, geo);
        /// sx: the rest x that says whose leg p is (pulled fabric moves with the leg it is worn on, wherever it is drawn)
        public static float3 Pose(float3 p, float sx, NativeArray<float4> A, NativeArray<float2> C, float4 toe, float4 geo)
        {
            float wl = Smooth(-0.004f, 0.004f, sx);
            float3 ql = wl > 0f ? Leg(ToeRaise(p, toe.x, 1f, geo), 0, A, C) : p;
            float3 qr = wl < 1f ? Leg(ToeRaise(p, toe.y, -1f, geo), 1, A, C) : p;
            return math.lerp(qr, ql, wl);
        }
    }

    [BurstCompile]
    struct PoseJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> rest, restN;
        [ReadOnly] public NativeArray<float3> clothDisp;  // empty for the body
        [ReadOnly] public NativeArray<float4> poseA; [ReadOnly] public NativeArray<float2> poseC;
        public float4 toe, toeGeo;
        [WriteOnly] public NativeArray<float3> pos;

        public void Execute(int i)
        {
            float3 p = rest[i], n = restN[i];
            float3 disp = clothDisp.Length > 0 ? clothDisp[i] : float3.zero;
            float h = math.dot(disp, n);
            disp -= math.min(h, 0f) * n;                  // the fabric never goes into the leg
            pos[i] = PoseMath.Pose(p + disp, poseA, poseC, toe, toeGeo);
        }
    }

    /// Per stocking vertex of one leg: distance along a ray and off it, at the posed position (the replay's grab search).
    [BurstCompile]
    struct RayScoreJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> rest;
        [ReadOnly] public NativeArray<float> side;
        [ReadOnly] public NativeArray<float4> poseA; [ReadOnly] public NativeArray<float2> poseC;
        public float4 toe, toeGeo;
        public float wantSide; public float3 O, D;
        [WriteOnly] public NativeArray<float> along, perp;

        public void Execute(int i)
        {
            if (side[i] * wantSide <= 0f) { along[i] = float.NaN; perp[i] = float.MaxValue; return; }
            float3 p = PoseMath.Pose(rest[i], poseA, poseC, toe, toeGeo);
            float3 rel = p - O; float al = math.dot(rel, D);
            along[i] = al; perp[i] = math.length(rel - al * D);
        }
    }

    /// The feet's contact shadow (TightsSim.UpdateContact): the stocking below the ankles, posed, in world space ...
    [BurstCompile]
    struct ContactPoseJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> rest; [ReadOnly] public NativeArray<int> idx;
        [ReadOnly] public NativeArray<float4> poseA; [ReadOnly] public NativeArray<float2> poseC;
        public float4 toe, toeGeo; public float4x4 M;
        [WriteOnly] public NativeArray<float3> pos;
        public void Execute(int k) { pos[k] = math.transform(M, PoseMath.Pose(rest[idx[k]], poseA, poseC, toe, toeGeo)); }
    }

    /// ... its height over the floor per cell of a grid round each foot ...
    [BurstCompile]
    struct ContactSplatJob : IJob
    {
        [ReadOnly] public NativeArray<float3> pos; [ReadOnly] public NativeArray<float> side;
        public NativeArray<float> H, B; public NativeArray<float4> box;   // highest / lowest point over each cell; per foot: the grid's corner (x, z)
        public int GX, GZ; public float cell, floorY;
        public void Execute()
        {
            for (int i = 0; i < H.Length; i++) { H[i] = 0f; B[i] = 1f; }
            for (int f = 0; f < 2; f++)
            {
                float2 lo = new float2(1e9f, 1e9f), hi = new float2(-1e9f, -1e9f);
                for (int k = 0; k < pos.Length; k++) if ((side[k] > 0f) == (f == 0)) { lo = math.min(lo, pos[k].xz); hi = math.max(hi, pos[k].xz); }
                float2 c = 0.5f * (lo + hi);
                box[f] = new float4(c.x - 0.5f * GX * cell, c.y - 0.5f * GZ * cell, 0f, 0f);
            }
            for (int k = 0; k < pos.Length; k++)
            {
                int f = side[k] > 0f ? 0 : 1; float4 b = box[f];
                int i = (int)math.floor((pos[k].x - b.x) / cell), j = (int)math.floor((pos[k].z - b.y) / cell);
                if (i < 0 || j < 0 || i >= GX || j >= GZ) continue;
                int o = f * GX * GZ + j * GX + i; float y = math.max(pos[k].y - floorY, 0f);
                H[o] = math.max(H[o], y); B[o] = math.min(B[o], y);
            }
        }
    }

    /// ... the signed distance (m) of each cell to the foot's outline, + outside (bilinear in the shader: a smooth outline) ...
    [BurstCompile]
    struct ContactSDJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float> H, B;
        [WriteOnly] public NativeArray<half2> SD;            // signed distance; the sky hidden under the foot (x: outside)
        public int GX, GZ, reach; public float cell;
        public void Execute(int o)
        {
            int n = GX * GZ, f = o / n, r = o - f * n, j = r / GX, i = r - j * GX;
            bool inside = H[o] > 0.003f; float best = (reach + 0.5f) * (reach + 0.5f);
            for (int dj = -reach; dj <= reach; dj++)
            {
                int jj = j + dj; if (jj < 0 || jj >= GZ) continue;
                for (int di = -reach; di <= reach; di++)
                {
                    int ii = i + di; if (ii < 0 || ii >= GX) continue;
                    if ((H[f * n + jj * GX + ii] > 0.003f) != inside) best = math.min(best, di * di + dj * dj);
                }
            }
            float d = (math.sqrt(best) - 0.5f) * cell;
            // under it, the sky comes in only from the open edge d away, under the foot's underside B high: the cosine-weighted
            // half-hemisphere up to atan(B / d) - a toe tip's 5 mm gap is near black a centimetre in, the floor under the side
            // of the ball (1 - 2 cm up) half lit
            float bb = B[o] < 1f ? B[o] : 0f, t = bb / math.max(d + 0.5f * cell, 1e-4f);
            float under = inside ? 1f - 0.5f * t * t / (1f + t * t) : 0f;
            SD[o] = new half2((half)(inside ? -d : d), (half)under);
        }
    }

    /// ... and per cell of a grid twice as coarse the part of the sky the foot hides from the floor there (cosine-weighted:
    /// sin^2 of the horizon's height, averaged over the directions; the horizon from the next cell on - under the foot too,
    /// so that it runs on smoothly across the outline)
    [BurstCompile]
    struct ContactAOJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float> H;          // the fine grid (GX x GZ per foot)
        [WriteOnly] public NativeArray<half> AO;         // the coarse one (GX / 2 x GZ / 2)
        public int GX, GZ, steps, dirs; public float cell;   // (cell: the coarse grid's)
        float H2(int f, int i, int j)
        {
            int n = GX * GZ, b = f * n + 2 * j * GX + 2 * i;
            return math.max(math.max(H[b], H[b + 1]), math.max(H[b + GX], H[b + GX + 1]));
        }
        public void Execute(int o)
        {
            int AX = GX / 2, AZ = GZ / 2, n = AX * AZ, f = o / n, r = o - f * n, j = r / AX, i = r - j * AX;
            float ao = 0f;
            for (int a = 0; a < dirs; a++)
            {
                math.sincos(2f * math.PI * (a + 0.5f) / dirs, out float sn, out float cs);
                float mt = 0f;
                for (int s = 1; s <= steps; s++)
                {
                    int ii = i + (int)math.round(cs * s), jj = j + (int)math.round(sn * s);
                    if (ii < 0 || jj < 0 || ii >= AX || jj >= AZ) break;
                    mt = math.max(mt, H2(f, ii, jj) / (s * cell));
                }
                ao += mt * mt / (1f + mt * mt);
            }
            AO[o] = (half)(ao / dirs);
        }
    }

    public class Pull
    {
        public int side; public float u, z, dTear, tension, maxT, amp, tRel, R = 0.028f, r0 = 0.0045f, seed, preT0 = -1f;
        public Vector3 g, ng, P, Pv, target;           // local (mesh) space; target = where the hand wants the patch, from g0
        public Vector3 g0;                              // pinched patch centre at the grab (posed, mesh space)
        // Recoil: just let go - the fingers open over a few hundredths of a second and the patch runs back with the fabric
        // (measured on the original at 60 fps: a tent collapses to 56 %, 16 %, 4 % in three frames, not in one)
        public enum State { Held, Recoil, Spring, Idle }
        public State state = State.Held;
        public Vector3 Prel;                            // the patch's offset when it was let go
        public Vector3 As; public bool hasAs;           // the patch target, smoothed over ~12 ms
        public Vector3 fieldA; public bool hasField;    // where the hand last held the patch ON the skin: the fabric round it has come along that far
        public float onLegS = -1f;                      // 'the cursor is over the leg', smoothed over ~40 ms
        public Run preRun;
        public bool scripted;                           // replay: tear/release decided by the script
        public bool burst;
        public bool foot;                               // grabbed on the foot: the hand moves the fabric directly (TightsSim.IsFoot)
        public HandMap hand;                            // hand -> pinched patch (rest space)
        public Vector3 eye; public bool hasEye;         // where the hand is seen from (mesh space): the patch slides on the leg under the cursor
        public float energyCap = float.MaxValue;        // replay: the recorded strength of this pull (m of drag) for the tear it leaves
        public float fatigue;                           // strain held over time (s x tension above 0.4): the knit creeps and gives way
        public float energyOverride = -1f;              // replay: the tear's energy (0.2 .. 1) as read off the original, -1 = from the drag
        public float lift;                              // replay: the hand also pulls toward the viewer by this fraction of the patch's travel
        // replay: the patch is pulled AWAY from the leg - along the leg's outward direction at the grab - by this fraction of
        // the hand's travel (the original's VIEW 02 shin pull at 33 s: while the cursor runs down and right across the shin
        // the pinched patch goes out to the left, one smooth sail from the knee; dragged over the skin after the cursor,
        // ours folded into flat flaps with straight edges - review round 7 blocker)
        public float outward;
        public float pinch;                             // replay: how far the fingers hold the fabric off the skin (m), 0 = cloth.pinchLift
        public float gather;                            // replay: how tight the fingers bunch the pinched patch (0 = cloth.gather)
        public float pinchR;                            // replay: radius of the fabric the fingers hold (m, 0 = cloth.pinchR)
        public string dbg = "";                         // -sheerLogPulls: the hand mapping of the last substep
        public Vector3 c;                               // grab point on the cloth lattice (rest space)
        public int gi, gj;                              // its node (around, along)
    }

    [DefaultExecutionOrder(100)]
    public class TightsSim : MonoBehaviour
    {
        public SheerMeshSource tights;
        public Renderer sheenRenderer;                       // additive fibre-sheen pass (same mesh, same damage maps)
        public SheerMeshSource body;
        public ComputeShader damageRaster;
        public ComputeShader clothCompute;
        [Header("Fabric")] public float denier = 20f, fabricStrength = 1f, runTendency = 1f, holeSize = 1f;
        // (no knee reflex after a tear any more - user, 2026-11-16: 'the character does an unnatural motion that deforms her
        //  legs every time a hole gets formed'; the body's own motion is SheerBodyMotion)
        [Header("Pose")]
        public SheerBodyMotion motion = new SheerBodyMotion();
        [Tooltip("Big toe: |x| of the cleft to the second toe, height and depth of its joint (rest, m).")]
        public Vector4 toeGeo = new Vector4(0.0955f, 0.020f, -0.074f, 0f);
        [Header("Cloth")] public ClothParams cloth = new ClothParams();
        public TightsCloth Cl;
        public ClothLattice lattice;
        [Tooltip("The hand tears the fabric when it has dragged this many times further than the pinched patch can follow " +
                 "(measured in the original: no tear at 1.98x, tear at 2.2x).")]
        public float tearAtReach = 2.1f;
        float subAcc;
        public float depthBias = 0.0018f;                    // m: the stocking wins the depth test against skin up to this far in front of it
        public float fatigueTear = 1.25f;                    // s held at which the knit under the fingers gives way (StepPull: creep)
        public float recoilTau = 0.008f;                     // (0.018: t90 4 frames vs the original's 2, round 10)                     // s: how fast a released patch runs back (see Pull.State.Recoil)
        public float leanOverride = float.NaN;               // rad; NaN = the body's own (SheerBodyMotion)
        [Tooltip("The replay advances the simulation itself.")]
        public bool externallyDriven;
        public bool logPulls;                           // debug: print hand / tip / tension every 0.1 s
        // The stocking lies ON the skin: the mesh is the skin's own shape plus the fabric's 0.2 mm (tools/reshape_legs.py,
        // tools/sim/wrap.py). (Until 2026-11-17 the shell stood off 1 - 3 mm - 'a dark band of nylon outside the skin' read off
        // the original's outlines, which is nylon seen edge-on, not a gap: at a hole on the outline the fabric floated.)
        [Tooltip("Extra stand-off of the stocking shell from the skin (m): everywhere / added around knee and ankle. Experiments only.")]
        public float shellGap = 0f, shellGapBend = 0f;

        public SheerDeformable T, B;
        NativeArray<float> side, noSide;
        NativeArray<float3> noDisp;
        Vector2[] tuv;                                  // (u, rest height) per stocking vertex
        public readonly List<Pull> pulls = new List<Pull>();
        public readonly Dictionary<int, SheerDamage> damage = new Dictionary<int, SheerDamage>();
        readonly Dictionary<int, DamageRenderer> damageTex = new Dictionary<int, DamageRenderer>();
        public float sway;
        public float simTime;
        readonly System.Random rng = new System.Random(5);
        float[] circL, circR; const int CircBins = PoseMath.Bins;
        float[] gapL, gapR;                                  // per height bin: distance of each leg's inner surface from the midline
        NativeArray<float4> poseA; NativeArray<float2> poseC; // the pose per leg and height bin (PoseMath): (dx, dz, phi), centre
        float4 toeNow; float kneeRoom = 1f; float poseT = float.NaN;
        Texture2D poseTex; float[] poseBuf;                  // the same for the vertex shaders (SheerCloth.hlsl): 4 rows
        Texture2D poseTexPrev; Vector4 toePrev; int poseFrame = -1;   // what the previous frame was drawn with (motion vectors)
        Texture2D axisTex;                                   // row centres of the cloth lattice (lattice coordinates in the shaders)
        Texture2D zTexL, zTexR;                              // per node: where it is in the damage maps along its wale
        MaterialPropertyBlock mpb;

        void Awake()
        {
            // (the release fade of the drawn displacement starts at 'none': unset shader globals read 0 = no cloth at all)
            Shader.SetGlobalFloat("_SheerDispFadeL", 1f); Shader.SetGlobalFloat("_SheerDispFadeR", 1f);
            Shader.SetGlobalFloat("_SheerDispFadePrevL", 1f); Shader.SetGlobalFloat("_SheerDispFadePrevR", 1f);
            T = new SheerDeformable(tights, true);
            B = body ? new SheerDeformable(body, false) : null;
            var d = T.data; int n = d.vertexCount;
            side = new NativeArray<float>(n, Allocator.Persistent);
            noSide = new NativeArray<float>(0, Allocator.Persistent);
            tuv = new Vector2[n];
            var uv0 = d.f["uv0"]; int d0 = d.dims["uv0"];
            var uv2 = d.f["uv2"]; int d2 = d.dims["uv2"];
            for (int i = 0; i < n; i++) { side[i] = Mathf.Sign(uv2[d2 * i]); tuv[i] = new Vector2(uv0[d0 * i], uv0[d0 * i + 1]); }
            noDisp = new NativeArray<float3>(0, Allocator.Persistent);
            BuildCircumference();
            BuildGaps();
            T.Finish(default); B?.Finish(default);          // rest pose, normals and unit stretch: uploaded once
            float t0 = Time.realtimeSinceStartup;
            // ONE lattice per leg, toes to under the skirt (ClothLattice): the foot's fabric is the leg's - a pull on the shin
            // draws the instep, a ladder runs on down the ankle onto the foot (user, 2026-11-16)
            lattice = ClothLattice.Load(System.IO.Path.Combine(Application.streamingAssetsPath, "sock_lattice.bin"));
            // (no ankle band any more: the lattice ran out at the ankle, its held rows gave toward the hand and lifted off on
            //  its side to let ankle sails run on over the foot - now the fabric over heel and instep is simply there)
            cloth.ankleGive = 0f; cloth.ankleFree = 0f; cloth.ankleRows = 0;
            Cl = new TightsCloth(clothCompute, lattice, cloth) { floor = new Vector4(0f, 1f, 0f, 0.0012f) };
            footCloth = FootHand(cloth);
            Shader.SetGlobalVector("_SheerClothGrid", new Vector4(lattice.s0, 1f / lattice.dy, 1f / lattice.NU, 1f / lattice.NV));
            // (experiments: -sheerNoClothDisp draws the stocking without the simulated cloth - shape, stretch, lift)
            if (System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerNoClothDisp") >= 0)
                Shader.SetGlobalVector("_SheerClothGrid", new Vector4(lattice.s0, 1f / lattice.dy, 1f / lattice.NU, 0f));
            Shader.SetGlobalVector("_SheerSock", new Vector4(lattice.yc, lattice.zc, lattice.rho, lattice.sc));
            Shader.SetGlobalFloat("_SheerDamageZ0", SheerDamage.ZMin);
            axisTex = lattice.AxisTexture();
            Shader.SetGlobalTexture("_SheerClothAxis", axisTex);
            zTexL = lattice.ZTexture(0); zTexR = lattice.ZTexture(1);
            Shader.SetGlobalTexture("_SheerClothZL", zTexL); Shader.SetGlobalTexture("_SheerClothZR", zTexR);
            Shader.SetGlobalFloat("_SheerShellGap", shellGap); Shader.SetGlobalFloat("_SheerShellGapBend", shellGapBend);
            Shader.SetGlobalFloat("_SheerSoftLod", 2f);
            Debug.Log($"[TightsSim] cloth: 2 legs x {lattice.NU} x {lattice.NV} nodes (toes to thigh) on the GPU, set up in {(Time.realtimeSinceStartup - t0) * 1000f:0} ms");
            InitPose();
            BuildContact();
            BuildLowCirc();
            damage[1] = new SheerDamage(z => CircZ(1, z), 6, MinCirc(circL), u => ToeZ(0, u)) { runTendency = runTendency, holeSize = holeSize };
            damage[-1] = new SheerDamage(z => CircZ(-1, z), 4, MinCirc(circR), u => ToeZ(1, u)) { runTendency = runTendency, holeSize = holeSize };
            foreach (var kv in damage)
            {
                int s = kv.Key;
                damageTex[s] = new DamageRenderer(damageRaster, z => CircZ(s, z), kv.Value.Wide, "damage_" + (s > 0 ? "L" : "R"));
                damageTex[s].Render(kv.Value);
            }
            UploadCircTable();
            // submesh k <-> leg: majority side of its vertices
            mpb = new MaterialPropertyBlock();
            var r = tights.GetComponent<Renderer>();
            for (int k = 0; k < d.submeshes.Count; k++)
            {
                float acc = 0; var idx = d.submeshes[k];
                for (int j = 0; j < idx.Length; j += 3) acc += side[idx[j]];
                int sd = acc >= 0 ? 1 : -1;
                foreach (var rr in new[] { r, sheenRenderer })
                {
                    if (!rr) continue;
                    rr.GetPropertyBlock(mpb, k);
                    mpb.SetTexture("_DamageTex", damageTex[sd].Texture);
                    mpb.SetTexture("_DamageTexB", damageTex[sd].TextureB); mpb.SetTexture("_DamageTexC", damageTex[sd].TextureC);
                    mpb.SetTexture("_ClothDisp", Cl.Disp(sd)); mpb.SetTexture("_ClothNrm", Cl.Nrm(sd)); mpb.SetTexture("_ClothTens", Cl.Tens(sd));
                    mpb.SetTexture("_ClothDispPrev", Cl.DispPrev(sd));
                    rr.SetPropertyBlock(mpb, k);
                }
            }
            // the pulled fabric leaves the rest bounds (the vertex shader displaces it by up to ~10 cm)
            foreach (var rr in new[] { r, sheenRenderer })
                if (rr) { var bb = rr.localBounds; bb.Expand(0.3f); rr.localBounds = bb; }
            // the skin knows where the nylon is intact (under-nylon light, see SheerSkin_float) and where it has lifted off
            if (body)
            {
                var br = body.GetComponent<Renderer>();
                br.GetPropertyBlock(mpb);
                mpb.SetTexture("_DamageTexL", damageTex[1].Texture);
                mpb.SetTexture("_DamageTexR", damageTex[-1].Texture);
                mpb.SetTexture("_ClothDispL", Cl.Disp(1));
                mpb.SetTexture("_ClothDispR", Cl.Disp(-1));
                br.SetPropertyBlock(mpb);
            }
        }

        // leg circumference per height (ellipse fit of each leg's rest cross-section); drives tear sizes
        void BuildCircumference()
        {
            circL = new float[CircBins]; circR = new float[CircBins];
            var lo = new float[2, CircBins, 2]; var hi = new float[2, CircBins, 2];
            for (int s = 0; s < 2; s++) for (int b = 0; b < CircBins; b++) { lo[s, b, 0] = lo[s, b, 1] = 1e9f; hi[s, b, 0] = hi[s, b, 1] = -1e9f; }
            for (int i = 0; i < T.n; i++)
            {
                float3 p = T.rest[i];
                int b = Mathf.Clamp((int)(p.y * CircBins), 0, CircBins - 1), s = side[i] > 0 ? 0 : 1;
                lo[s, b, 0] = Mathf.Min(lo[s, b, 0], p.x); hi[s, b, 0] = Mathf.Max(hi[s, b, 0], p.x);
                lo[s, b, 1] = Mathf.Min(lo[s, b, 1], p.z); hi[s, b, 1] = Mathf.Max(hi[s, b, 1], p.z);
            }
            // 2 mm bins vs ~5 mm vertex rings: a bin often holds only part of a ring -> a tiny ellipse -> holes smeared sideways
            // (horizontal spikes / stair-stepped hole edges in the damage map). Extents over a +-7 bin (14 mm) window, then smooth.
            const int W = 7;
            for (int s = 0; s < 2; s++)
            {
                var arr = s == 0 ? circL : circR; float last = 0.2f;
                for (int b = 0; b < CircBins; b++)
                {
                    float x0 = 1e9f, x1 = -1e9f, z0 = 1e9f, z1 = -1e9f;
                    for (int k = Mathf.Max(0, b - W); k <= Mathf.Min(CircBins - 1, b + W); k++)
                    {
                        x0 = Mathf.Min(x0, lo[s, k, 0]); x1 = Mathf.Max(x1, hi[s, k, 0]);
                        z0 = Mathf.Min(z0, lo[s, k, 1]); z1 = Mathf.Max(z1, hi[s, k, 1]);
                    }
                    float a = (x1 - x0) * 0.5f, c = (z1 - z0) * 0.5f;
                    if (a > 0 && c > 0 && a < 1 && c < 1) last = Mathf.PI * (3 * (a + c) - Mathf.Sqrt((3 * a + c) * (a + 3 * c)));
                    arr[b] = last;
                }
                var tmp = (float[])arr.Clone();                      // light smoothing (5-bin box)
                for (int b = 0; b < CircBins; b++)
                {
                    float acc = 0; int n = 0;
                    for (int k = Mathf.Max(0, b - 2); k <= Mathf.Min(CircBins - 1, b + 2); k++) { acc += tmp[k]; n++; }
                    arr[b] = acc / n;
                }
            }
        }
        // inner surface of each leg per height (stocking = outermost shell): what the knees can close before the legs touch
        void BuildGaps()
        {
            gapL = new float[CircBins]; gapR = new float[CircBins];
            for (int b = 0; b < CircBins; b++) gapL[b] = gapR[b] = 1e9f;
            for (int i = 0; i < T.n; i++)
            {
                float3 p = T.rest[i];
                int b = Mathf.Clamp((int)(p.y * CircBins), 0, CircBins - 1);
                if (side[i] > 0) gapL[b] = Mathf.Min(gapL[b], Mathf.Abs(p.x)); else gapR[b] = Mathf.Min(gapR[b], Mathf.Abs(p.x));
            }
            foreach (var g in new[] { gapL, gapR })
            {
                float last = 0f;
                for (int b = CircBins - 1; b >= 0; b--) { if (g[b] > 1e8f) g[b] = last; else last = g[b]; }   // empty bins: from above
                var tmp = (float[])g.Clone();                             // local minimum over +-8 mm, then a light blur
                for (int b = 0; b < CircBins; b++) { float m = 1e9f; for (int k = Mathf.Max(0, b - 4); k <= Mathf.Min(CircBins - 1, b + 4); k++) m = Mathf.Min(m, tmp[k]); g[b] = m; }
                tmp = (float[])g.Clone();
                for (int b = 0; b < CircBins; b++) { float acc = 0; int n = 0; for (int k = Mathf.Max(0, b - 6); k <= Mathf.Min(CircBins - 1, b + 6); k++) { acc += tmp[k]; n++; } g[b] = acc / n; }
            }
        }

        // ------------------------------------------------------------------ the pose (SheerBodyMotion -> rigid leg segments)
        // Joint heights of the rest mesh (m): the shin turns about the ankle (the foot stays planted), the thigh about the hip.
        const float AnkleY = 0.085f, KneeY = 0.472f, HipY = 0.865f;
        static float S01(float e0, float e1, float x) { float q = Mathf.Clamp01((x - e0) / (e1 - e0)); return q * q * (3 - 2 * q); }
        /// How far a cross-section follows the knee's move: 0 at ankle and hip joint, 1 at the knee - two straight bones
        /// meeting at a rounded joint (the old smoothstep profile bent thigh and shin into S-curves).
        static float KneeProfile(float y)
        {
            float a = (y - AnkleY) / (KneeY - AnkleY), b = (HipY - y) / (HipY - KneeY);
            const float k = 0.22f;
            float h = Mathf.Clamp01(0.5f + 0.5f * (b - a) / k);
            return Mathf.Clamp01((Mathf.Lerp(b, a, h) - k * h * (1f - h)) / (1f - 0.25f * k));
        }
        /// How much of the leg's inward turn a cross-section takes: none at the planted foot, all of it from the knee up,
        /// none again where the thigh joins the pelvis.
        /// (fading out below the buttocks, 0.70 - 0.80 m: turned with the thigh up to 0.84 m a turned-in leg swung its buttock out
        ///  through the skirt, 2026-11-17)
        static float TwistProfile(float y) => S01(AnkleY + 0.01f, KneeY - 0.03f, y) * (1f - S01(0.70f, 0.80f, y));
        /// The foot's own turn (toes in): the foot, part of the ankle.
        static float FootProfile(float y) => 1f - S01(0.065f, 0.13f, y);

        void InitPose()
        {
            poseA = new NativeArray<float4>(2 * CircBins, Allocator.Persistent);
            poseC = new NativeArray<float2>(2 * CircBins, Allocator.Persistent);
            // the cross-sections turn about the leg's axis (the cloth lattice's, from the stocking); the foot about the ankle
            for (int leg = 0; leg < 2; leg++)
                for (int b = 0; b < CircBins; b++)
                {
                    float y = Mathf.Clamp((b + 0.5f) / CircBins, Mathf.Max(0.10f, lattice.yc), lattice.y1 - 0.001f);   // (the leg's rows)
                    float f = Mathf.Clamp((y - lattice.y0) / lattice.dy, 0f, lattice.NV - 1.001f); int j = (int)f; float a = f - j;
                    poseC[leg * CircBins + b] = new float2(Mathf.Lerp(lattice.ax[leg][j], lattice.ax[leg][j + 1], a), Mathf.Lerp(lattice.az[leg][j], lattice.az[leg][j + 1], a));
                }
            // how far the two knees may turn in together before they touch (2 mm of the stockings left between them)
            kneeRoom = 1f;
            for (int b = 0; b < CircBins; b++)
            {
                float y = (b + 0.5f) / CircBins, pk = KneeProfile(y);
                if (pk < 0.25f) continue;
                kneeRoom = Mathf.Min(kneeRoom, Mathf.Max(gapL[b] + gapR[b] - 0.002f, 0f) / pk);
            }
            // (free play: a different life every launch; the replay restarts it with the fixed seed - ResetMotion)
            motion.Reset(System.Environment.TickCount & 0x7fffffff);
            // (tests: -sheerStill holds the body still - legs straight - so that a test's clicks land where they were aimed)
            if (System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerStill") >= 0) motion.motionScale = 0f;
            Debug.Log($"[pose] knees may turn in {kneeRoom * 1000f:0.0} mm together before they touch");
            BuildPose();
        }

        /// This frame's pose tables from the body's motion; the knees touch but never pass through each other (both turns
        /// scaled back together, each keeping its share).
        void BuildPose()
        {
            if (!poseA.IsCreated) return;
            LegPose L = motion.L, R = motion.R;
            // (a knee further forward than the other gains a little room: two round knees ~9 cm across, dz apart in depth,
            //  pass each other by 2r - sqrt(4r^2 - dz^2) - 2.7 mm for the relaxed knee's 22 mm)
            float dzk = Mathf.Min(Mathf.Abs(L.kneeFwd - R.kneeFwd), 0.06f), room = kneeRoom + (0.09f - Mathf.Sqrt(0.0081f - dzk * dzk));
            float kin = L.kneeIn + R.kneeIn, ks = kin > room && kin > 1e-6f ? room / kin : 1f;
            for (int leg = 0; leg < 2; leg++)
            {
                float s = leg == 0 ? 1f : -1f; LegPose P = leg == 0 ? L : R;
                for (int b = 0; b < CircBins; b++)
                {
                    float y = (b + 0.5f) / CircBins, pk = KneeProfile(y);
                    float dx = -s * P.kneeIn * ks * pk + sway * LeanProfile(y);
                    float dz = -P.kneeFwd * pk;
                    float phi = s * (P.twist * TwistProfile(y) + P.footYaw * FootProfile(y));
                    poseA[leg * CircBins + b] = new float4(dx, dz, phi, 0f);
                }
            }
            toeNow = new float4(L.toe, R.toe, 0f, 0f);
            // per height: each leg's rest frame -> the other leg's, as both are posed now (the cloth keeps lifted fabric off the
            // other leg: SheerCloth.compute). Leg pose: xz -> M(phi)(xz - c) + c + t, M(a) M(b) = M(a + b); so the map is
            // M(phiL - phiO) xz + tau, tau = -M(d) cL + M(-phiO)(cL + tL - cO - tO) + cO
            for (int leg = 0; leg < 2; leg++)
                for (int b = 0; b < TightsCloth.RelBins; b++)
                {
                    float y = (b + 0.5f) / TightsCloth.RelBins;
                    PoseMath.Sample(poseA, poseC, leg, y, out var aL, out var cL);
                    PoseMath.Sample(poseA, poseC, 1 - leg, y, out var aO, out var cO);
                    float d = aL.z - aO.z; math.sincos(d, out float sd, out float cd); math.sincos(-aO.z, out float so, out float co);
                    float2 v = cL + aL.xy - cO - aO.xy;
                    float2 tau = -new float2(cL.x * cd + cL.y * sd, -cL.x * sd + cL.y * cd) + new float2(v.x * co + v.y * so, -v.x * so + v.y * co) + cO;
                    relTab[leg * TightsCloth.RelBins + b] = new Vector4(cd, sd, tau.x, tau.y);
                }
            Cl?.SetRelative(relTab);
        }
        readonly Vector4[] relTab = new Vector4[2 * TightsCloth.RelBins];

        /// Keeps a rest-space point of the given side's fabric `margin` off the OTHER leg (as SheerCloth.compute's OffOtherLeg).
        public Vector3 CollideOther(int sd, Vector3 p, float margin)
        {
            int L = ClothLattice.Leg(sd), O = 1 - L;
            float f = Mathf.Clamp(p.y * TightsCloth.RelBins - 0.5f, 0f, TightsCloth.RelBins - 1.001f); int b = (int)f;
            Vector4 r = Vector4.Lerp(relTab[L * TightsCloth.RelBins + b], relTab[L * TightsCloth.RelBins + b + 1], f - b);
            var q = new Vector3(r.x * p.x + r.y * p.z + r.z, p.y, -r.y * p.x + r.x * p.z + r.w);
            float R = lattice.Radius(O, q, out float dx, out float dz, out Vector3 eB) + margin;
            float rho = Mathf.Sqrt(dx * dx + dz * dz);
            if (rho >= R || rho < 1e-6f) return p;
            q += (new Vector3(dx, 0f, 0f) + eB * dz) * ((R - rho) / rho);
            float qx = q.x - r.z, qz = q.z - r.w;
            return new Vector3(r.x * qx - r.y * qz, q.y, r.y * qx + r.x * qz);
        }

        /// The pose tables (PoseMath) - the skirt drapes over the posed thighs (SkirtCloth).
        public NativeArray<float4> PoseTableA => poseA;
        public NativeArray<float2> PoseTableC => poseC;

        /// Rest-space point -> where the pose puts it (mesh space).
        public Vector3 PosePoint(Vector3 p) => poseA.IsCreated ? (Vector3)PoseMath.Pose(p, poseA, poseC, toeNow, toeGeo) : p;
        /// ... of fabric worn on the given side's leg (posed with that leg wherever it has been drawn)
        public Vector3 PosePoint(Vector3 p, int side) => poseA.IsCreated ? (Vector3)PoseMath.Pose(p, side > 0 ? 0.05f : -0.05f, poseA, poseC, toeNow, toeGeo) : p;
        /// A direction drawn in the posed leg (the hand's drag) -> the rest frame of the cross-section at atRest.
        public Vector3 UnposeVector(Vector3 v, Vector3 atRest)
        {
            if (!poseA.IsCreated) return v;
            PoseMath.Sample(poseA, poseC, atRest.x >= 0f ? 0 : 1, atRest.y, out var a, out _);
            math.sincos(a.z, out float sn, out float cs);
            return new Vector3(v.x * cs - v.z * sn, v.y, v.x * sn + v.z * cs);
        }
        /// A posed point -> the rest frame of the cross-section at height hSlice of the given leg (the eye seen from the
        /// pulled patch).
        public Vector3 UnposePointAt(Vector3 q, float hSlice, int sd)
        {
            if (!poseA.IsCreated) return q;
            PoseMath.Sample(poseA, poseC, sd > 0 ? 0 : 1, hSlice, out var a, out var c);
            math.sincos(a.z, out float sn, out float cs);
            float rx = q.x - c.x - a.x, rz = q.z - c.y - a.y;
            return new Vector3(c.x + rx * cs - rz * sn, q.y, c.y + rx * sn + rz * cs);
        }

        /// Metres of sideways shift per radian of lean at a height (SheerLeanProfile in SheerCloth.hlsl): the body pivots at
        /// the ankles, the shift levels off above the knee.
        public static float LeanProfile(float y)
        {
            float t = Mathf.Clamp01((y - 0.45f) / 0.17f);
            return 0.36f * (float)System.Math.Tanh(Mathf.Max(y - 0.07f, 0f) / 0.36f) * (1f - 0.12f * t * t * (3f - 2f * t));
        }

        /// The pose for the vertex shaders (SheerCloth.hlsl): a 512 x 4 table - rows 0 / 1: (dx, dz, phi) of the +x / -x leg,
        /// rows 2 / 3: the turning centres - and the big toes. Fabric that the hand has slid along the leg is posed at the
        /// height where it is now.
        void PushPose()
        {
            if (!poseA.IsCreated) return;
            void Fill()
            {
                for (int leg = 0; leg < 2; leg++)
                    for (int b = 0; b < CircBins; b++)
                    {
                        float4 a = poseA[leg * CircBins + b]; float2 c = poseC[leg * CircBins + b];
                        int o = 4 * (leg * CircBins + b), oc = 4 * ((2 + leg) * CircBins + b);
                        poseBuf[o] = a.x; poseBuf[o + 1] = a.y; poseBuf[o + 2] = a.z; poseBuf[o + 3] = 0f;
                        poseBuf[oc] = c.x; poseBuf[oc + 1] = c.y; poseBuf[oc + 2] = 0f; poseBuf[oc + 3] = 0f;
                    }
            }
            if (!poseTex)
            {
                poseTex = new Texture2D(CircBins, 4, TextureFormat.RGBAFloat, false, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "pose" };
                poseTexPrev = new Texture2D(CircBins, 4, TextureFormat.RGBAFloat, false, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "pose_prev" };
                poseBuf = new float[4 * 4 * CircBins];
                Fill(); toePrev = (Vector4)toeNow;
            }
            // the first push of a frame: what the shaders had until now becomes the 'previous' pose (motion vectors); a
            // second push in the same frame (replay capture: after its own step) only refreshes the current one
            if (poseFrame != Time.frameCount)
            {
                poseFrame = Time.frameCount;
                poseTexPrev.SetPixelData(poseBuf, 0); poseTexPrev.Apply(false);
                Shader.SetGlobalTexture("_SheerPoseTexPrev", poseTexPrev);
                Shader.SetGlobalVector("_SheerPoseParamsPrev", new Vector4(CircBins, 0, 0, 0));
                Shader.SetGlobalVector("_SheerToePrev", toePrev);
            }
            Fill();
            poseTex.SetPixelData(poseBuf, 0); poseTex.Apply(false);
            toePrev = (Vector4)toeNow;
            Shader.SetGlobalTexture("_SheerPoseTex", poseTex);
            Shader.SetGlobalVector("_SheerPoseParams", new Vector4(CircBins, 0, 0, 0));
            Shader.SetGlobalVector("_SheerToe", (Vector4)toeNow);
            Shader.SetGlobalVector("_SheerToeGeo", toeGeo);
        }

        static float Circ(float[] arr, float z) { float f = Mathf.Clamp(z * CircBins, 0, CircBins - 1.001f); int i = (int)f; return Mathf.Lerp(arr[i], arr[i + 1], f - i); }
        static float MinCirc(float[] arr) { float m = 1e9f; for (int b = (int)(0.1f * CircBins); b < (int)(0.35f * CircBins); b++) m = Mathf.Min(m, arr[b]); return m; }

        // ------------------------------------------------------------------ the hand
        /// Hand offset (world space) for a cursor drag D (world, in the plane facing the camera at the pinch depth). Measured
        /// in the original from two views: the pinched patch moves in that plane (lift = 0); how far it follows is the
        /// fabric's business (HandMap). `lift` adds a pull toward the viewer for experiments.
        public Vector3 HandOffset(Pull p, Vector3 D, Vector3 toCam, float lift) => D + toCam.normalized * (lift * D.magnitude);

        // ------------------------------------------------------------------ grabbing (local mesh space)
        public int VertexSide(int v) => side[v] > 0 ? 1 : -1;

        /// The stocking vertex of the given leg closest to a ray (mesh space), preferring the near side; miss = its distance
        /// from the ray (m). (A plain loop over the 284k vertices cost ~75 ms: a visible hitch at every press of the replay.)
        public int NearestToRay(Vector3 O, Vector3 D, int wantSide, out float miss)
        {
            var along = new NativeArray<float>(T.n, Allocator.TempJob, NativeArrayOptions.UninitializedMemory);
            var perp = new NativeArray<float>(T.n, Allocator.TempJob, NativeArrayOptions.UninitializedMemory);
            new RayScoreJob { rest = PickRest, side = side, poseA = poseA, poseC = poseC, toe = toeNow, toeGeo = toeGeo, wantSide = wantSide,
                              O = O, D = math.normalize((float3)D), along = along, perp = perp }.Schedule(T.n, 4096).Complete();
            float minAlong = float.MaxValue;
            for (int v = 0; v < T.n; v++) { float a = along[v]; if (a < minAlong) minAlong = a; }      // (NaN never compares less)
            int best = -1; float bs = float.MaxValue;
            for (int v = 0; v < T.n; v++)
            {
                float a = along[v]; if (float.IsNaN(a)) continue;
                float sc = perp[v] + 0.02f * Mathf.Max(a - minAlong, 0f);
                if (sc < bs) { bs = sc; best = v; }
            }
            miss = best >= 0 ? perp[best] : float.MaxValue;
            along.Dispose(); perp.Dispose();
            return best;
        }
        public Vector2 VertexUZ(int v) => tuv[v];
        /// the rasterised tear state of a leg (R hole SDF, G ladder SDF) - the Studio's pro tab shows it
        public Texture DamageTexture(int side) => damageTex.TryGetValue(side, out var d) ? d.Texture : null;

        /// The Studio's events: a hand took hold of the fabric; let go of it (burst = it tore).
        public static event System.Action<Pull> Grabbed;
        public static event System.Action<Pull, bool> Released;
        /// The top of the stocking (rest height; >= 0.99: pantyhose to the waist). Above it the leg is bare: nothing to grab,
        /// the lattice held there (a thigh-high's welt grips the leg), ladders stop below the welt.
        public float bandTop { get; private set; } = 1f;
        /// Height of that top's welt (m). The welt does not tear: it is a doubled, elastic band, far stronger than the sheer
        /// leg - a pull on it only stretches it, a fingernail does not catch, and a tear from below stops along its lower
        /// edge (SheerTights.hlsl clips holes and ladders there).
        public float bandWelt { get; private set; }
        bool OnWelt(Vector3 rest) => bandTop < 0.99f && rest.y > bandTop - bandWelt - 0.002f;
        public void SetBand(float top, float welt)
        {
            bandTop = top; bandWelt = top < 0.99f ? Mathf.Max(welt, 0.01f) : 0f;
            if (Cl != null) Cl.SetTopPin(top < 0.99f ? top - welt * 0.5f : 2f);
            foreach (var d in damage.Values) d.topZ = top < 0.99f ? Mathf.Min(0.665f, top - welt - 0.004f) : 0.665f;
        }

        /// A fingernail SNAG (Shift + click): one loop caught and broken - a pinhole, and often a ladder running from it both
        /// ways (SheerDamage.Snag; as short as the yarn's ladder tendency allows: a fishnet hardly runs). No pull. False on
        /// bare skin above a thigh-high's top.
        public bool SnagAt(int vertex)
        {
            int sd = VertexSide(vertex); Vector3 rest = T.rest[vertex];
            if (bandTop < 0.99f && rest.y > bandTop - 0.004f) return false;
            if (OnWelt(rest)) return false;                       // (nothing to catch in the band)
            int leg = ClothLattice.Leg(sd);
            Vector2 uz = rest.y >= lattice.yc ? tuv[vertex] : lattice.DamageUZ(leg, rest);
            var dmg = damage[sd];
            dmg.Snag(uz.x, uz.y); dmg.dirty = true;
            Snagged?.Invoke(sd, uz.y);
            return true;
        }
        public static event System.Action<int, float> Snagged;

        public Pull Grab(int vertex, bool scripted = false)
        {
            int sd = VertexSide(vertex); Vector3 rest = T.rest[vertex];
            if (bandTop < 0.99f && rest.y > bandTop - 0.004f) return null;
            int leg = ClothLattice.Leg(sd);
            // where it tears: on the leg the maps' own coordinates (the mesh's), below the bend's top along the wales
            Vector2 uz = rest.y >= lattice.yc ? tuv[vertex] : lattice.DamageUZ(leg, rest);
            float u = uz.x, z = uz.y;
            // on the foot the hand moves the fabric directly (the camera looks along the foot: see Advance); the foot's
            // fabric is shorter and follows the hand less far
            bool foot = IsFoot(rest, T.restN[vertex]);
            var cp = foot ? footCloth : cloth;
            var dmg = damage[sd];
            // the fabric's reach (how far the patch follows) x tearAtReach = the drag that tears it; heavier yarn holds longer
            float denierK = (0.75f + Mathf.Clamp01((denier - 8f) / 70f) * 0.9f) / 0.904f;      // 1 at 20 denier
            float dTear = cp.tearReach * denierK * fabricStrength * (0.93f + 0.14f * (float)rng.NextDouble());
            float near = dmg.HoleSdAt(u, z);
            if (near < 0.012f) dTear *= 0.75f + 0.25f * Mathf.Max(near, 0f) / 0.012f;   // damaged fabric gives a little sooner (x0.45 tore a pinch beside a hole before any tent formed - the original holds one there, 7.7 s; review 2026-11-17)
            if (OnWelt(rest)) dTear *= 20f;                                              // (the welt holds: it only stretches)
            var p = new Pull { side = sd, u = u, z = z, dTear = dTear, g = rest, ng = T.restN[vertex], seed = (float)rng.NextDouble(), scripted = scripted, amp = 1f, foot = foot };
            foreach (var q in pulls)                                                                    // one hand per leg
            {
                if (q.side != sd) continue;
                if (q.state == Pull.State.Held) Release(q, false);
                if (q.state == Pull.State.Recoil) { Cl.EndGrab(sd); q.state = Pull.State.Spring; }
            }
            // (not inside the held toe tip / top bands)
            lattice.NodeAt(leg, rest, cloth.pinRows + cloth.pinHold + 2, out p.gj, out p.gi, cloth.pinRows + 2);
            p.c = Cl.BeginGrab(sd, p.gj, p.gi, DamageTexture(sd));      // (the fingers hold only fabric joined to the grab: not behind a hole)
            p.hand = new HandMap { axis = lattice.AxisDir(leg, p.gj), rMax = cp.rMax };
            // (the patch the fingers draw out spreads about 1.25 x as far as it is pulled, + 2.8 cm (p.R in StepPull): it must
            //  not reach past the last free row under the pinned band at the top, or it creases against the anchored edge -
            //  a hard corner and a flat, lit face (reviews 12-16 at 3.4 and 19 s). So the hand's reach shrinks toward that
            //  band, for EVERY grab. This general rule replaces the replay's hand-set per-press caps near the hem)
            float dTop = (lattice.NV - 1 - cloth.pinRows - cloth.pinHold - p.gj) * lattice.dy;
            p.hand.reachScale = Mathf.Clamp((dTop - 0.038f) / 1.25f / cp.rMax, 0.3f, 1f);
            // (No shorter reach beside a hole any more: the original draws full sails next to its holes - 5.4 - 5.7, 6.9, 7.9 -
            //  8.1 s - with the holes stretched into them; cut to 0.4 x there, ours made a nub or nothing while the cursor went
            //  13 cm out, independent review 6. Damaged fabric still tears a little sooner, dTear above.)
            p.g0 = PosePoint(p.c);
            pulls.Add(p);
            Grabbed?.Invoke(p);
            return p;
        }

        // ------------------------------------------------------------------ body shape (the Studio's leg types)
        /// leg cross-sections scaled by height - x about the inner surface, z about the axis - so the thighs grow away from
        /// each other; skin and stocking in the vertex shaders (SheerShapePoint), the cloth lattice, picking and tear sizes alike
        public static readonly string[] ShapeNames = { "Default|ふつう", "Slender|ほっそり", "Athletic|アスリート", "Curvy|むっちり", "Petite|小柄" };
        static readonly float[] ShapeY = { 0.09f, 0.14f, 0.22f, 0.30f, 0.40f, 0.47f, 0.55f, 0.63f, 0.70f, 0.80f };
        static readonly float[][] ShapeK =
        {
            new[] { 1f, 1f, 1f, 1f, 1f, 1f, 1f, 1f, 1f, 1f },
            new[] { 1f, 0.95f, 0.93f, 0.92f, 0.93f, 0.95f, 0.92f, 0.90f, 0.90f, 1f },
            new[] { 1f, 0.97f, 1.03f, 1.06f, 1.02f, 0.96f, 0.97f, 0.98f, 0.98f, 1f },
            new[] { 1f, 1.0f, 1.02f, 1.04f, 1.03f, 1.03f, 1.07f, 1.10f, 1.12f, 1f },
            new[] { 1f, 0.93f, 0.91f, 0.90f, 0.92f, 0.93f, 0.90f, 0.88f, 0.88f, 1f },
        };
        public int shapeType { get; private set; }
        Texture2D shapeTex; NativeArray<float3> shapedRest; float[] circL0, circR0;
        NativeArray<float3> PickRest => shapeType != 0 && shapedRest.IsCreated ? shapedRest : T.rest;
        static float ShapeScale(int type, float y)
        {
            var k = ShapeK[Mathf.Clamp(type, 0, ShapeK.Length - 1)];
            if (y <= ShapeY[0]) return k[0];
            for (int i = 1; i < ShapeY.Length; i++)
                if (y <= ShapeY[i]) { float a = (y - ShapeY[i - 1]) / (ShapeY[i] - ShapeY[i - 1]); a = a * a * (3f - 2f * a); return Mathf.Lerp(k[i - 1], k[i], a); }
            return k[k.Length - 1];
        }
        /// (scale, inner surface x, axis z) of a leg at a rest height
        Vector3 ShapeAt(int leg, float y)
        {
            float s = ShapeScale(shapeType, y);
            int b = Mathf.Clamp((int)(y * CircBins), 0, CircBins - 1);
            float xin = leg == 0 ? gapL[b] : -gapR[b];
            Vector2 la = lattice.LegAxis0(leg, y);
            return new Vector3(s, xin, la.y);
        }
        public void SetShape(int type)
        {
            type = Mathf.Clamp(type, 0, ShapeK.Length - 1);
            if (type == shapeType && (shapeTex || type == 0)) return;      // (the default body at start: nothing to do)
            foreach (var p in pulls) if (p.state == Pull.State.Held) Release(p, false);
            shapeType = type;
            // the shaders' table: 512 heights x 2 legs, (scale, inner x, axis z)
            if (!shapeTex) shapeTex = new Texture2D(CircBins, 2, TextureFormat.RGBAFloat, false, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "body_shape" };
            var px = new float[4 * CircBins * 2];
            for (int leg = 0; leg < 2; leg++)
                for (int b = 0; b < CircBins; b++)
                {
                    var sh = ShapeAt(leg, (b + 0.5f) / CircBins); int o = 4 * (leg * CircBins + b);
                    px[o] = sh.x; px[o + 1] = sh.y; px[o + 2] = sh.z; px[o + 3] = 1f;
                }
            shapeTex.SetPixelData(px, 0); shapeTex.Apply(false);
            Shader.SetGlobalTexture("_SheerShapeTex", shapeTex);
            Shader.SetGlobalVector("_SheerShape", new Vector4(type == 0 ? 0f : 1f, 0f, 0f, 0f));
            // the cloth follows the body
            lattice.ApplyShape((leg, y) => ShapeAt(leg, y));
            Cl?.ReloadRest();
            // picking: the shaped rest positions
            if (type != 0)
            {
                if (!shapedRest.IsCreated) shapedRest = new NativeArray<float3>(T.n, Allocator.Persistent);
                for (int v = 0; v < T.n; v++)
                {
                    float3 p = T.rest[v]; var sh = ShapeAt(side[v] > 0 ? 0 : 1, p.y);
                    shapedRest[v] = new float3(sh.y + sh.x * (p.x - sh.y), p.y, sh.z + sh.x * (p.z - sh.z));
                }
            }
            // tear sizes: the circumference by height
            circL0 ??= (float[])circL.Clone(); circR0 ??= (float[])circR.Clone();
            for (int b = 0; b < CircBins; b++) { float y = (b + 0.5f) / CircBins; circL[b] = circL0[b] * ShapeAt(0, y).x; circR[b] = circR0[b] * ShapeAt(1, y).x; }
            foreach (var kv in damageTex) { int s = kv.Key; kv.Value.UpdateTables(z => CircZ(s, z), damage[s].Wide); damage[s].dirty = true; }
            UploadCircTable();
            FindAnyObjectByType<SkirtCloth>()?.RefreshHull();
        }

        // ------------------------------------------------------------------ the feet (the hand's mapping there)
        public ClothParams footCloth;
        /// The hand works the fabric of the FOOT below this rest height (m), and on the instep's slope up to the bend's top
        /// (fabric facing up): there it drags it over the surface facing the eye (Advance) - Snap models a vertical leg seen
        /// from the side, and on the sloping instep it threw the patch back into the ankle - and reaches less far. The sides
        /// and back of the ankle keep the leg's mapping.
        public const float FootCut = 0.072f;
        public bool IsFoot(Vector3 rest, Vector3 normal) => rest.y < FootCut || (rest.y < lattice.yc && normal.y > 0.45f);
        float RecoilTau(ClothParams cp) => cp.recoilTau > 0f ? cp.recoilTau : recoilTau;
        /// (experiments: -sheerCloth changed the leg's hand; the foot's follows)
        public void RefreshFootHand() { footCloth = FootHand(cloth); }
        public TightsCloth ClothOf(Pull p) => Cl;
        public ClothLattice LatticeOf(Pull p) => lattice;
        /// the rest-space point (mesh) of where a pull holds the fabric
        public Vector3 PullRest(Pull p) => p.c;
        public Vector3 PullRest(Pull p, Vector3 local) => local;

        static ClothParams FootHand(ClothParams c)
        {
            var f = JsonUtility.FromJson<ClothParams>(JsonUtility.ToJson(c));
            // (the foot's fabric is shorter: it follows the hand less far, and the fingers hold a smaller fold)
            f.rMax = 0.060f; f.rMaxOnLeg = 0.050f; f.tearReach = 0.060f; f.pinchLift = Mathf.Min(c.pinchLift, 0.008f);
            // (... and gather it tighter: the leg's 7 mm patch at 0.6 - a rigid plate - lifted off the top of the toes as a
            //  flat lid on straight walls, a box instead of a tent (free-play sweep 2026-11-17); 4 mm at 0.3 draws a cone)
            f.pinchR = 0.004f; f.gather = 0.30f; f.pinchElong = 1f; f.gatherAlong = 0f;   // (a round grip: 'along the wale' is not rest-space up on the foot)
            return f;
        }

        /// Below the bend's top the damage maps run along the wales (Z: ClothLattice): the circumference there is the
        /// lattice rows' (sizes of holes in metres), averaged over the nodes at each Z; above it, the leg's by height.
        float[] lowCircL, lowCircR; const int LowBins = 160;     // Z from SheerDamage.ZMin to the bend's top
        void BuildLowCirc()
        {
            var L = lattice; float zTop = L.yc + 0.01f;
            for (int leg = 0; leg < 2; leg++)
            {
                var acc = new float[LowBins]; var cnt = new float[LowBins];
                for (int j = 0; j < L.NV; j++)
                {
                    float per = 0f;
                    for (int i = 0; i < L.NU; i++) per += (L.Node(leg, j, (i + 1) % L.NU) - L.Node(leg, j, i)).magnitude;
                    for (int i = 0; i < L.NU; i++)
                    {
                        float zz = L.Z[leg][j * L.NU + i];
                        int bb = Mathf.FloorToInt((zz - SheerDamage.ZMin) / (zTop - SheerDamage.ZMin) * LowBins);
                        if (bb < 0 || bb >= LowBins) continue;
                        acc[bb] += per; cnt[bb] += 1f;
                    }
                }
                var arr = new float[LowBins]; float last = -1f;
                for (int bb = 0; bb < LowBins; bb++) if (cnt[bb] > 0f) { last = acc[bb] / cnt[bb]; break; }
                for (int bb = 0; bb < LowBins; bb++) { if (cnt[bb] > 0f) last = acc[bb] / cnt[bb]; arr[bb] = last; }
                var tmp = (float[])arr.Clone();
                for (int bb = 0; bb < LowBins; bb++) { float s = 0f; int n = 0; for (int k = Mathf.Max(0, bb - 3); k <= Mathf.Min(LowBins - 1, bb + 3); k++) { s += tmp[k]; n++; } arr[bb] = s / n; }
                if (leg == 0) lowCircL = arr; else lowCircR = arr;
            }
        }
        /// the shaders' copy of CircZ (SheerLook.hlsl SheerCirc: a knitted pattern's size in metres round the leg): 512 texels
        /// over 1 m of damage z from SheerDamage.ZMin, row 0 the left leg (side +1), row 1 the right
        Texture2D circTex;
        void UploadCircTable()
        {
            const int W = 512;
            if (!circTex) circTex = new Texture2D(W, 2, TextureFormat.RFloat, false, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "leg_circumference" };
            var px = new float[W * 2];
            for (int i = 0; i < W; i++) { float z = SheerDamage.ZMin + (i + 0.5f) / W; px[i] = CircZ(1, z); px[W + i] = CircZ(-1, z); }
            circTex.SetPixelData(px, 0); circTex.Apply(false);
            Shader.SetGlobalTexture("_SheerCircTex", circTex); Shader.SetGlobalFloat("_SheerCircZ0", SheerDamage.ZMin);
        }

        /// circumference (m) at damage-map z of the given side: the leg's by height, along the wales below the bend's top
        public float CircZ(int side, float z)
        {
            float hi = Circ(side > 0 ? circL : circR, z);
            if (z >= lattice.yc + 0.01f || lowCircL == null) return hi;
            var arr = side > 0 ? lowCircL : lowCircR; float zTop = lattice.yc + 0.01f;
            float f = Mathf.Clamp((z - SheerDamage.ZMin) / (zTop - SheerDamage.ZMin) * LowBins - 0.5f, 0f, LowBins - 1.001f); int i0 = (int)f;
            float lo = Mathf.Lerp(arr[i0], arr[i0 + 1], f - i0);
            return Mathf.Lerp(lo, hi, Mathf.Clamp01((z - (lattice.yc - 0.01f)) / 0.02f));
        }
        /// where the reinforced toe starts on the wale at u (damage z): ladders stop there (5 cm from the toe tip)
        public float ToeZ(int leg, float u)
        {
            var L = lattice; int j = Mathf.Clamp(Mathf.RoundToInt((0.050f - L.s0) / L.dy), 0, L.NV - 1);
            // (the wale whose damage u - theta / 2 pi + its offset - is u: the offset is small, one step finds it)
            float th = u - L.du[leg][Mathf.Clamp((int)(u * L.NU), 0, L.NU - 1)];
            th -= Mathf.Floor(th);
            float g = th * L.NU; int i0 = ((int)g) % L.NU, i1 = (i0 + 1) % L.NU;
            return Mathf.Lerp(L.Z[leg][j * L.NU + i0], L.Z[leg][j * L.NU + i1], g - (int)g);
        }

        /// Ray (world space) against the deformed stocking; returns the nearest vertex of the hit triangle or -1.
        public int Pick(Ray worldRay, out Vector3 hitWorld, out float hitDistance)
        {
            var tr = tights.transform;
            float3 o = tr.InverseTransformPoint(worldRay.origin), d = math.normalize((float3)tr.InverseTransformDirection(worldRay.direction));
            // (the mesh on the CPU is only posed when somebody clicks)
            BuildPose();
            new PoseJob { rest = PickRest, restN = T.restN, clothDisp = noDisp, poseA = poseA, poseC = poseC, toe = toeNow, toeGeo = toeGeo,
                          pos = T.pos }.Schedule(T.n, 2048).Complete();
            int t = T.Raycast(o, d, out float th, out float3 bary);
            hitWorld = Vector3.zero; hitDistance = float.MaxValue;
            if (t < 0) return -1;
            hitWorld = tr.TransformPoint(o + d * th);
            hitDistance = Vector3.Distance(worldRay.origin, hitWorld);
            int a = T.tris[3 * t], b = T.tris[3 * t + 1], c = T.tris[3 * t + 2];
            return bary.x >= bary.y && bary.x >= bary.z ? a : bary.y >= bary.z ? b : c;
        }

        public void Release(Pull p, bool burst)
        {
            if (p.state != Pull.State.Held) return;
            // (let go once its column of slits has shown 0.3 s, the laddering knit gives way in the snap-back - StepPull)
            if (!burst && p.preRun != null && p.preRun.pre && !p.scripted && simTime - p.preT0 >= 0.30f) burst = true;
            Released?.Invoke(p, burst);
            var dmg = damage[p.side];
            p.burst = burst;
            // released elastic energy ~ how far the FABRIC had been drawn out (the patch from its grab; a full pull is ~10 cm).
            // (It was the hand's drag: the opening knee pinch - the hand 11 cm down, the fabric 4 cm - ran a ladder from the knee
            //  to the upper thigh where the original's stays local, independent review 2026-11-17)
            // (under a thigh-high's welt the tear opens in the sheer knit below the band, not half inside it)
            // (a run is driven by the tension the stocking is WORN under, not by how far this pull drew the fabric: scaled by that
            //  alone, the creep tears - which give way before the patch has gone far - left short stubs, 'damage never builds up
            //  into long laddered runs', review 11. The draw still lengthens it)
            if (burst) dmg.Burst(p.u, bandTop < 0.99f ? Mathf.Min(p.z, dmg.topZ - 0.006f) : p.z, Mathf.Clamp(p.tension, 1f, 1.6f), p.preRun, Mathf.Max(0.4f, p.energyOverride > 0f ? p.energyOverride : Mathf.Min(p.P.magnitude, p.energyCap) / 0.10f));   // (0.7: the first press already ripped a 5-hole chain knee to shin, review 12)
            else
            {
                if (p.maxT > 0.35f) dmg.AddMark(p.u, p.z, Mathf.Min(p.R * 0.5f, 0.045f), Mathf.Min(0.75f, (p.maxT - 0.3f) * 0.9f));
                // (the row of slits was only the knit opening under the hand's tension: let go without a tear, it closes -
                //  left at its age it stayed as a straight bar on the leg for the rest of the session)
                // (gone at once: kept as a fading run it was drawn as a pale, ruled strip for a moment after every press that did
                //  not tear, review 11)
                if (p.preRun != null) { dmg.runs.Remove(p.preRun); dmg.dirty = true; p.preRun = null; }
            }
            p.state = Pull.State.Recoil; p.tRel = simTime; p.Prel = p.P;
        }

        /// Repair with a flourish: let go of the fabric, then every tear shrinks away over `seconds` (SheerDamage.Mend)
        public void MendDamage(float seconds = 0.9f)
        {
            foreach (var p in pulls) { if (p.state == Pull.State.Held || p.state == Pull.State.Recoil) ClothOf(p).EndGrab(p.side); p.state = Pull.State.Idle; }
            pulls.Clear();
            foreach (var d in damage.Values) d.BeginMend();
            mendT = 0f; mendDur = Mathf.Max(seconds, 0.05f);
        }
        float mendT = -1f, mendDur = 0.9f;
        public bool Mending => mendT >= 0f;
        void StepMend()
        {
            if (mendT < 0f) return;
            mendT += Time.unscaledDeltaTime;                      // (it mends while paused too)
            float x = Mathf.Clamp01(mendT / mendDur), k = 1f - x * x * (3f - 2f * x);
            foreach (var d in damage.Values) d.ApplyMend(k);
            if (x >= 1f) { foreach (var d in damage.Values) d.EndMend(); mendT = -1f; }
        }

        public void ResetDamage()
        {
            foreach (var d in damage.Values) { d.holes.Clear(); d.runs.Clear(); d.marks.Clear(); d.dirty = true; }
            foreach (var p in pulls) { if (p.state == Pull.State.Held || p.state == Pull.State.Recoil) ClothOf(p).EndGrab(p.side); p.state = Pull.State.Idle; }
            pulls.Clear();
        }

        // ------------------------------------------------------------------ simulation
        void StepPull(Pull p, float dt)
        {
            if (p.state == Pull.State.Held)
            {
                p.R = Mathf.Min(0.028f + p.P.magnitude * 1.25f, 0.18f); p.amp = 1f;
                p.tension = p.target.magnitude / (tearAtReach * p.dTear); p.maxT = Mathf.Max(p.maxT, p.tension);
                if (logPulls && Mathf.Repeat(simTime, 0.1f) < dt)
                    Debug.Log($"[pull] t={simTime:0.00} side {p.side} node ({p.gj},{p.gi}) hand {p.target.magnitude * 1000:0} mm patch {p.P.magnitude * 1000:0} mm ({p.P.x * 1000:0},{p.P.y * 1000:0},{p.P.z * 1000:0}) tension {p.tension:0.00} | {p.dbg}");
                if (!p.scripted)
                {
                    var dmg = damage[p.side];
                    // the knit fails under SUSTAINED strain, not only at a breaking point: loops held stretched creep and give
                    // way. One global material constant (fatigueTear), calibrated once against the original's session - its
                    // pulls held above tension 0.4 for an integral >= ~0.19 tore, those <= 0.16 did not - and applied to every
                    // pull alike (CLAUDE.md: no per-pull values). The row of slits before a tear grows with the strain held
                    // (CREEP: a held pinch strains the loops under the fingers whatever the drag - the knit gives way after about
                    //  a second held, sooner the harder it is drawn. Refitted 2026-11-18 on the original's 17 presses with the
                    //  session's own cursor (input only, the pre-video path no longer hand-made): its 6 tearing pulls are exactly
                    //  the ones held >= 0.96 s - press 8 barely moves the cursor (tension 0.12) and tears, press 7 reaches 0.94
                    //  and does not; the old rule (strain above tension 0.4 only) tore 2 of the 6. Rate 1 + 2 x tension, tear at
                    //  fatigueTear 0.35 once the slit column has shown 0.7 s: all 6 tear, 0.06 - 0.4 s before the original's
                    //  (press 0's 0.3 vs 0.73 s rests on its guessed press time), none of the 11 others)
                    // (2026-11-18, review 11: pure hold time. Weighted by tension, every press reached the slit column's onset in
                    //  0.2 s - slits on every press, fading as pale strips after the short ones; the original shows them only before
                    //  its tears. A hard yank still tears sooner: tension >= 1, below. Refit on the 17 presses: slits from 0.46 s of
                    //  holding, the tear 0.4 s later - all 6 of the original's tearing pulls, none of the 11 others)
                    p.fatigue += dt;
                    float fat = p.fatigue / fatigueTear;
                    // (THE RUN COMES FIRST: in the original every tear is preceded by a column of crisp bright slits walking down
                    //  the leg for 0.5 - 0.7 s - 3.3 - 3.9 s, 15.3 - 15.9 s, 19.3 - 20.0 s. Ours started at tension 0.58, needed
                    //  ~0.3 s to show, and a fast pull tore first: the hole popped open with no run, independent review 2026-11-17.
                    //  Now from 0.42, visible at once, growing from the start; and the fabric gives way only once its run has
                    //  shown for 0.35 s)
                    // (review 5: from tension 0.62 / fatigue 0.35 the slits came almost at the grab - a held pull that sat at 0.63 -
                    //  0.73 showed them for its whole half second; the original's fabric visibly stretches first and its column
                    //  of slits forms as the knit nears failure, 0.3 - 0.7 s before the tear. The 0.35 s it must show before any
                    //  tear is unchanged, so a fast yank still runs first)
                    // (HOLD OR LET GO, refit 2026-11-18 after review 12 - the original's tears land within 0.15 s of the hand letting
                    //  go, after a column of slits shown 0.3 - 0.9 s: the slits come from 0.65 s held (fatigueTear 1.25: fat 0.52);
                    //  held on, the knit gives way at 1.25 s once they have shown 0.8 s; let go after they have shown 0.3 s, it gives
                    //  way in the snap-back (Release). All 6 of the original's tears, 0 - 0.14 s from its times (5 exact), none of
                    //  the other 11; 0.16 s of slits in all on presses that do not tear)
                    if ((p.tension > 0.80f || fat > 0.52f) && p.preRun == null) { p.preRun = dmg.PreRun(p.u, p.z, 0.09f, 0.16f); p.preT0 = simTime; }
                    // ... and a hole beside the fingers is worked bigger: its edge loops unravel under the held pull (the original:
                    // 'pulling near a hole makes it bigger'; ours kept every hole as it was made, review 11)
                    dmg.GrowNear(p.u, p.z, (0.12f + 0.3f * Mathf.Clamp01(p.tension)) * dt);
                    if (p.preRun != null && p.preRun.pre)
                    {
                        float gx = Mathf.Max(Mathf.Max(p.tension - 0.62f, 0f), 0.25f * fat);
                        p.preRun.dn.speed = Mathf.Max(p.preRun.dn.speed, 0.16f + gx * 0.30f); p.preRun.up.speed = Mathf.Max(p.preRun.up.speed, 0.01f + gx * 0.03f);
                        // (its age stays below the ladder's: at 0.22 + 0.3 x strain it passed 0.3 under a hard pull and the row of
                        //  slits half-opened into a ladder band with square ends - a pale 'sticker' beside the hole, review 2)
                        p.preRun.ageT = 0.22f + gx * 0.04f;
                    }
                    // (0.5 s: the original's column of slits stands 0.26 - 0.7 s before every tear in its session - 0.47 - 0.73,
                    //  3.3 - 4.0, 15.3 - 15.9, 19.3 - 20.0 s; ours showed for ~0.15 s, review 5)
                    float shownT = p.preRun == null ? 0f : simTime - p.preT0;
                    if ((p.tension >= 1f && shownT >= 0.4f) || (fat >= 1f && shownT >= 0.8f)) Release(p, true);
                }
            }
            else if (p.state == Pull.State.Spring)
            {
                if (simTime - p.tRel > 0.9f) { p.state = Pull.State.Idle; p.amp = 0f; }   // the cloth pulls itself back
            }
        }

        /// Advances fabric + tears by dt (sub-stepped at 240 Hz like the offline version).
        // profiling counters (SheerUI -sheerPerfLog prints them)
        public static double profSimMs, profDmgMs, profApplyMs, profRasterMs; public static int profSubsteps, profClothSubsteps;
        static readonly bool noClothDiag = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerNoCloth") >= 0;   // profiling only
        static readonly System.Diagnostics.Stopwatch profSw = new System.Diagnostics.Stopwatch();

        public void Advance(float dt, System.Action<float> perSubstep = null)
        {
            // replay / tear logic at 240 Hz; the cloth itself runs ONCE per call as one job that sub-steps internally
            // (a scheduled job + main-thread sync per 240 Hz step cost more than the solve and spiralled to 1 fps)
            int sub = Mathf.Max(1, Mathf.CeilToInt(dt * 240f - 1e-4f)); float h = dt / sub;
            // debug (-sheerLogPulls): every second, the ladders of each leg
            if (logPulls && Mathf.Repeat(simTime, 1f) < dt)
                foreach (var kv in damage)
                    foreach (var r in kv.Value.runs)
                        Debug.Log($"[run] t={simTime:0.00} side {kv.Key} u={r.u:0.0000} z0={r.z0:0.0000} lo={r.lo:0.0000} hi={r.hi:0.0000} hw={r.hw * 1000:0.0}/{r.hwT * 1000:0.0} mm age={r.age:0.00}/{r.ageT:0.00} pre={r.pre} done={r.done} fan={r.up.fan:0.000}/{r.dn.fan:0.000}");
            for (int s = 0; s < sub; s++)
            {
                perSubstep?.Invoke(h);
                foreach (var p in pulls) StepPull(p, h);
                profSw.Restart();
                // the cloth: a fixed number of substeps per second, each with its own position of the hand
                subAcc += h * cloth.subRate; int ns = (int)subAcc; subAcc -= ns;
                if (!noClothDiag)
                    for (int sd = 1; sd >= -1; sd -= 2)
                    {
                        Pull held = null;
                        foreach (var p in pulls) if (p.side == sd && p.state == Pull.State.Held) held = p;
                        Pull rec = null;
                        if (held == null) foreach (var p in pulls) if (p.side == sd && p.state == Pull.State.Recoil) rec = p;
                        Pull act = held ?? rec;
                        // (no hand on this leg: a released stocking relaxes back onto it, then sleeps)
                        if (Cl.Awake(sd) && act == null) for (int k = 0; k < ns; k++) Cl.StepFree(sd);
                        if (held != null)
                        {
                            int leg = ClothLattice.Leg(sd);
                            bool ft = held.foot; var lat = lattice; var cl = Cl; var cp = ft ? footCloth : cloth;
                            for (int k = 0; k < ns; k++)
                            {
                                // is the cursor itself over the leg (the patch is dragged over the skin) or past its outline?
                                // (the eye and the drag in the rest frame of the cross-section under the patch: the pose turns
                                //  the leg's cross-sections, not only shifts them)
                                Vector3 cRest = held.c + held.P;
                                float onLeg = 0f, qDbg = -1f; Vector3 eyeR = UnposePointAt(held.eye, cRest.y, sd);
                                Vector3 tgt = UnposeVector(held.target, held.c);
                                if (held.outward > 0f)
                                {   // away from the leg: out along its radius at the grab, and a little of the hand's drop
                                    lat.Radius(leg, held.c, out float ox, out float oz, out Vector3 eOut);
                                    Vector3 nOut = (new Vector3(ox, 0f, 0f) + eOut * oz).normalized;
                                    tgt = nOut * (held.outward * tgt.magnitude) + Vector3.up * (0.3f * tgt.y);
                                }
                                // (not on the foot: seen from in front, down its length, the closest approach of the cursor's ray to
                                //  the foot's axis is undefined - the patch slid 22 cm along it. There the patch follows the drag)
                                else if (held.hasEye && !ft) { lat.Snap(leg, eyeR, held.c + tgt, out float qc); qDbg = qc; onLeg = 1f - Mathf.SmoothStep(0f, 1f, (qc - 1.02f) / 0.28f); }   // (a cursor AT the outline still drags the patch over the skin: the original's thigh pull at 3 - 4 s)
                                // On the foot - seen from in front, down its length - the hand drags the fabric over the surface
                                // facing the eye: the drag goes where the cursor's ray meets the plane tangent to the foot at the
                                // grab (down the instep toward the toes, up it toward the shin; past the outline the fabric leaves
                                // the foot along that plane). (In the screen plane at the grab's depth, a drag past the toes went
                                // straight down under the foot and blew the fabric round its side into a sail.) Where the foot is
                                // seen edge-on (its sides) the plane runs off to infinity: there the drag stays in the screen plane.
                                else if (held.hasEye)
                                {
                                    Vector3 nG = held.ng.normalized, dir = (held.c + tgt - eyeR).normalized;
                                    float dn = Vector3.Dot(dir, nG);
                                    onLeg = Mathf.SmoothStep(0f, 1f, (-dn - 0.25f) / 0.20f);
                                    if (onLeg > 0f) tgt = Vector3.Lerp(tgt, eyeR + dir * (Vector3.Dot(held.c - eyeR, nG) / dn) - held.c, onLeg);
                                }
                                // (a fast cursor crosses the outline within a frame: the mapping switched at once and the tent's tip
                                //  retracted for a frame, review round 7 - over ~40 ms instead)
                                if (held.onLegS < 0f) held.onLegS = onLeg;
                                held.onLegS += (onLeg - held.onLegS) * (1f - Mathf.Exp(-1f / (cp.subRate * 0.04f)));
                                onLeg = held.onLegS;
                                Vector3 Sv = held.hand.Update(tgt, 1f / cp.subRate, cp, onLeg);
                                Vector3 W = held.c + Sv;
                                // (over the first 2 cm the patch simply leaves the grab point in the screen plane: the snapped path
                                //  does not pass through the grab point itself, and the fabric must not jump at the touch)
                                if (held.hasEye && held.outward <= 0f && !ft) W = Vector3.Lerp(W, lat.Snap(leg, eyeR, W), Mathf.SmoothStep(0f, 1f, Sv.magnitude / 0.02f));
                                // (the opening knee pinch: the hand pulls down AND toward the viewer - a fold hangs in front of the shin)
                                if (held.hasEye && held.lift > 0f) W += (eyeR - W).normalized * (held.lift * Sv.magnitude);
                                if (!ft)
                                {
                                    // (a pinch stays under the skirt: no higher than 1.5 cm below the skirt's own hem on that side
                                    //  of the body (SkirtCloth.HemAt), or than its grab if that was taken closer to the hem.
                                    //  Drawn up past the hem the tent's apex went through the pleats - a cyan shard in front of the
                                    //  cloth, review rounds 12 / 14 - and once the skirt was cloth, the hand reaching in after it
                                    //  lifted the hem with nothing visible doing it (2026-11-17, original session at 3 s: our skirt
                                    //  hangs 4.5 cm lower than the original's, longer by request). Was a fixed 0.695 m - HemDrop,
                                    //  which is 3 cm above the hem at the front.)
                                    W.y = Mathf.Min(W.y, Mathf.Max(SkirtCloth.HemAt(W) - 0.015f, held.c.y));
                                    W = lat.ClampToPins(leg, held.gj, held.gi, held.c, lat.ClampHeight(W, cp), cp, cl.Give(sd), cl.Free(sd));
                                }
                                else
                                {
                                    // (the foot: along it between heel and a little beyond the toe tip, never into the floor, no
                                    //  higher than the top of the ankle. No reach limit toward the lattice's held toe rows: they are
                                    //  where the lattice ends, not a seam that holds - limited by them a pinch on the toes hardly moved)
                                    W.z = Mathf.Clamp(W.z, -0.17f, 0.12f);
                                    W.y = Mathf.Clamp(W.y, 0.004f, 0.16f);
                                }
                                // the fingers hold a fold of fabric off the skin (the original's on-leg pinches are dark gathered blobs)
                                // (and rises off it as it is dragged further: ClothParams.liftK - sliding flat on the skin it made no tent, review 2026-11-17)
                                // (by the drag ALONG the leg only: pulled along it the fabric, held above and below, bunches and stands up
                                //  - the original's knee pocket, its calf at 33 s -; dragged round the leg the tube slides with it and shows
                                //  nothing until the hand passes the outline - the original's thigh at 5.0 - 5.25 s, where ours pinched up)
                                float sAlong = Mathf.Abs(Vector3.Dot(Sv, held.hand.axis));
                                float lift = (held.pinch > 0f ? held.pinch : cp.pinchLift) + Mathf.Min(cp.liftMax, cp.liftK * Mathf.Max(0f, sAlong - 0.012f));
                                float liftE = Mathf.Lerp(0.001f, lift, Mathf.SmoothStep(0f, 1f, Sv.magnitude / 0.012f));
                                Vector3 A;
                                if (!ft)
                                {
                                    // (the fold stands off the skin along the skin's own normal under the fingers: lifted
                                    //  radially from the leg's axis - ~35 deg off the true normal below the kneecap - the
                                    //  opening knee pinch swung ~2 cm round to the leg's front outline, a flap off its side
                                    //  where the original draws a deep pocket in the kneecap, independent review 4)
                                    Vector3 A0 = lat.Collide(leg, W, 0.001f);
                                    float h0 = lat.Lift(leg, A0);
                                    A = h0 < liftE ? lat.Collide(leg, A0 + lat.SurfaceNormal(leg, A0) * (liftE - Mathf.Max(h0, 0f)), 0.001f) : A0;
                                }
                                else A = lat.Collide(leg, W, liftE);
                                A.y = Mathf.Max(A.y, 0.003f);
                                // (drawn toward the other leg, the fingers stop at it: they cannot pull the fabric into it)
                                A = CollideOther(sd, A, 0.004f);
                                // (smoothed over ~12 ms: where the cursor crosses the outline the on-leg / off-leg mapping switched
                                //  within a frame and the tent's tip retracted into a dome for one frame, review round 7)
                                if (!held.hasAs) { held.As = A; held.hasAs = true; }
                                held.As += (A - held.As) * (1f - Mathf.Exp(-1f / (cp.subRate * 0.005f)));   // (5 ms: the tip trailed the cursor, rounds 9 / 10)
                                A = held.As;
                                // (gathered fabric is pressed onto the skin only while the fingers themselves are on the leg: drawn
                                //  off it, the tent stands by its threads - pressed, it collapsed to a needle)
                                float onSkin = 1f - Mathf.SmoothStep(0f, 1f, (lat.Lift(leg, A) - 0.006f) / 0.006f);
                                // (... and the fabric round the pinch goes along with it as far as the hand has dragged it OVER the
                                //  skin: the point where it left the skin stays the field's end while a tent is drawn off there)
                                if (!held.hasField) { held.fieldA = held.c; held.hasField = true; }
                                // (off the skin the field follows the skin point nearest the hand: the fabric slides round the leg to
                                //  where the hand leaves it, and the sail grows from there - the original's from the outline at 5.4 s.
                                //  Frozen where the patch had left the skin, ours grew from the front of the thigh and crossed it,
                                //  2026-11-17. The field's own limits - dragRound, 1 - 2 rad round the leg - still hold the far side)
                                Vector3 fTarget = Vector3.Lerp(lat.SurfacePoint(leg, A), A, onSkin);
                                held.fieldA += (fTarget - held.fieldA) * (1f - Mathf.Exp(-1f / (cp.subRate * 0.02f)));
                                // (fingers pressing the fabric against the leg cannot bunch it into a point: on the skin the fold is held
                                //  broad and soft, gathered only once it stands off it - a sail's sharp tip. Gathered to a point on the
                                //  leg, the opening knee pinch was a small black 'navel' with radial creases, review 11; the original's
                                //  is a soft hollow / tent)
                                float gOn = ft ? 0f : onSkin;
                                cl.Step(sd, A, held.gather > 0f ? held.gather : Mathf.Lerp(cp.gather, 0.45f, gOn), held.pinchR > 0f ? held.pinchR : cp.pinchR, 0f, -1f, onSkin,
                                        lat.DragField(leg, held.c, held.fieldA, cp), ft ? -1f : Mathf.Lerp(cp.gatherAlong, 0.5f, gOn));
                                held.P = A - held.c;
                                held.dbg = $"{(ft ? "FOOT " : "")}q {qDbg:0.00} c ({held.c.x * 1000:0},{held.c.y * 1000:0},{held.c.z * 1000:0}) onLeg {onLeg:0.00} S ({Sv.x * 1000:0},{Sv.y * 1000:0},{Sv.z * 1000:0}) eye ({eyeR.x:0.00},{eyeR.y:0.00},{eyeR.z:0.00}) W-c ({(W.x - held.c.x) * 1000:0},{(W.y - held.c.y) * 1000:0},{(W.z - held.c.z) * 1000:0})";
                            }
                        }
                        else if (rec != null)
                        {
                            int leg = ClothLattice.Leg(sd);
                            var lat = lattice; var cl = Cl; var cp = rec.foot ? footCloth : cloth;
                            for (int k = 0; k < ns; k++)
                            {
                                // LETTING GO: the whole pulled shape - the sail, the tent, the fabric slid round the leg - goes home
                                // together in its own shape, every node the same share of its way per substep, on the profile of a
                                // released elastic: from rest, fastest at tau, settled after a few tau - (1 + t/tau) e^(-t/tau).
                                // The original's sails shrink that way: ~half gone 20 ms after the hand lets go, gone by ~50 ms
                                // (5.88 s). (Run dynamically - springs, the bunched patch opening in the air, a leash - the sail's
                                // sheet snapped onto the patch within 8 ms and the bunched patch stood off the leg as a crumpled
                                // star of spikes for ~45 ms at every release, review 14 at 13.27 / 27.97 / 30.33 s.)
                                // (torn, nothing holds the fabric out: it is back within a frame - drawn half-way back, the fresh holes
                                //  showed as white rectangles in stretched knit with a dark smudge at the pinch for a frame, review 12)
                                float tauR = rec.burst ? 0.004f : RecoilTau(cp);
                                float tr0 = Mathf.Max(simTime - rec.tRel + k / cp.subRate, 0f), tr = tr0 + 1f / cp.subRate;
                                float s0 = (1f + tr0 / tauR) * Mathf.Exp(-tr0 / tauR), s1 = (1f + tr / tauR) * Mathf.Exp(-tr / tauR);
                                cl.StepRecoil(sd, s1 / Mathf.Max(s0, 1e-6f));
                                rec.P = rec.Prel * s1;
                            }
                            if (simTime - rec.tRel + ns / cp.subRate >= cp.recoilLen * (rec.burst ? 0.004f : RecoilTau(cp))) { cl.EndGrab(sd); rec.state = Pull.State.Spring; }
                        }
                    }
                profSimMs += profSw.Elapsed.TotalMilliseconds;
                profSw.Restart();
                foreach (var d in damage.Values) d.Update(h);
                profDmgMs += profSw.Elapsed.TotalMilliseconds;
                simTime += h;
                profSubsteps++;
            }
            UpdatePose(simTime);
            profSw.Restart();
            int flushed = Cl.Flush(); profClothSubsteps += flushed; SheerFun.LastSubsteps = flushed;
            profSimMs += profSw.Elapsed.TotalMilliseconds;
            pulls.RemoveAll(p => p.state == Pull.State.Idle);
        }

        void Update()
        {
            StepMend();
            if (!externallyDriven) Advance(Mathf.Min(Time.deltaTime, 1f / 20f));
            Apply();
        }

        /// The body at sim time t: SheerBodyMotion advanced to t (stance, knees, toes, weight); the lean (rad; 'sway' x
        /// LeanProfile(height) = sideways shift) is the replay's - measured on the original's outlines - when it drives.
        void UpdatePose(float t)
        {
            float dt = float.IsNaN(poseT) ? 0f : t - poseT;
            if (dt < 0f || dt > 1f) dt = 0f;                              // (a replay restart jumps the clock)
            poseT = t;
            if (dt > 0f) motion.Advance(dt);
            sway = !float.IsNaN(leanOverride) ? leanOverride : motion.lean;
            BuildPose();
        }

        /// The replay restarts the body's motion with a fixed seed (the same session renders the same every time).
        public void ResetMotion() { motion.Reset(); poseT = float.NaN; BuildPose(); }

        /// Pose + cloth -> meshes; tear maps -> GPU.
        Light keyLight;
        readonly Vector3[] pinchUZ = new Vector3[2]; readonly float[] pinchW = new float[2], heldW = new float[2];
        readonly Vector4[] pinchDir = new Vector4[2];   // the pull in the fabric's own coordinates: round (m), along (m), on the leg (0..1)
        readonly float[] relFadeT = { -2f, -2f }, dispFade = { 1f, 1f };      // release fade of the drawn displacement (-1: held, -2: none)
        // ---- the feet's CONTACT SHADOW on the floor (SheerSurfaces.hlsl, SheerContactVis): per foot, the posed foot's height
        //      over the floor on a 2 mm grid; from it the foot's outline (a signed distance, so the shader draws it smooth) and,
        //      on a 4 mm grid, how much of the sky each point of the floor round it sees (horizon-based: 12 directions out to
        //      6 cm) - small textures the floor's shader darkens by, every frame
        const int CGX = 128, CGZ = 192, AGX = CGX / 2, AGZ = CGZ / 2; const float CCell = 0.002f;
        NativeArray<int> contactVtx; NativeArray<float> contactSide; NativeArray<float3> contactPos;
        NativeArray<float> contactH, contactB; NativeArray<half> contactAO; NativeArray<half2> contactSD; NativeArray<float4> contactBoxN;
        Texture2D contactAOL, contactAOR, contactSDL, contactSDR;
        readonly Vector4[] contactBox = new Vector4[2];
        [Tooltip("Strength of the feet's contact shadow on the floor (0: the shader's default).")]
        public float contactK = 0f;

        void BuildContact()
        {
            var rest = T.rest; var idx = new List<int>();
            for (int i = 0; i < rest.Length; i++) if (rest[i].y < 0.09f) idx.Add(i);       // (below the ankle)
            contactVtx = new NativeArray<int>(idx.ToArray(), Allocator.Persistent);
            contactSide = new NativeArray<float>(idx.Count, Allocator.Persistent);
            for (int k = 0; k < idx.Count; k++) contactSide[k] = rest[idx[k]].x > 0f ? 1f : -1f;
            contactPos = new NativeArray<float3>(idx.Count, Allocator.Persistent);
            contactH = new NativeArray<float>(2 * CGX * CGZ, Allocator.Persistent);
            contactB = new NativeArray<float>(2 * CGX * CGZ, Allocator.Persistent);
            contactSD = new NativeArray<half2>(2 * CGX * CGZ, Allocator.Persistent);
            contactAO = new NativeArray<half>(2 * AGX * AGZ, Allocator.Persistent);
            contactBoxN = new NativeArray<float4>(2, Allocator.Persistent);
            Texture2D Tex(int w, int h, string n, TextureFormat tf) => new Texture2D(w, h, tf, false, true) { name = n, filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp };
            contactAOL = Tex(AGX, AGZ, "contact_ao_L", TextureFormat.RHalf); contactAOR = Tex(AGX, AGZ, "contact_ao_R", TextureFormat.RHalf);
            contactSDL = Tex(CGX, CGZ, "contact_sd_L", TextureFormat.RGHalf); contactSDR = Tex(CGX, CGZ, "contact_sd_R", TextureFormat.RGHalf);
            Shader.SetGlobalTexture("_SheerContactL", contactAOL); Shader.SetGlobalTexture("_SheerContactR", contactAOR);
            Shader.SetGlobalTexture("_SheerContactSDL", contactSDL); Shader.SetGlobalTexture("_SheerContactSDR", contactSDR);
            Debug.Log($"[TightsSim] contact shadow: {idx.Count} points below the ankles, 2 x {CGX} x {CGZ} cells of {CCell * 1000f:0} mm");
        }

        void UpdateContact()
        {
            if (!contactVtx.IsCreated || !poseA.IsCreated) return;
            var hp = new ContactPoseJob { rest = PickRest, idx = contactVtx, poseA = poseA, poseC = poseC, toe = toeNow, toeGeo = toeGeo,
                                          M = tights.transform.localToWorldMatrix, pos = contactPos }.Schedule(contactVtx.Length, 2048);
            var hs = new ContactSplatJob { pos = contactPos, side = contactSide, H = contactH, B = contactB, box = contactBoxN, GX = CGX, GZ = CGZ, cell = CCell, floorY = 0f }.Schedule(hp);
            var hd = new ContactSDJob { H = contactH, B = contactB, SD = contactSD, GX = CGX, GZ = CGZ, cell = CCell, reach = 8 }.Schedule(2 * CGX * CGZ, 512, hs);
            new ContactAOJob { H = contactH, AO = contactAO, GX = CGX, GZ = CGZ, cell = 2f * CCell, steps = 15, dirs = 12 }.Schedule(2 * AGX * AGZ, 256, hd).Complete();
            contactAOL.SetPixelData(contactAO.GetSubArray(0, AGX * AGZ), 0, 0); contactAOL.Apply(false, false);
            contactAOR.SetPixelData(contactAO.GetSubArray(AGX * AGZ, AGX * AGZ), 0, 0); contactAOR.Apply(false, false);
            contactSDL.SetPixelData(contactSD.GetSubArray(0, CGX * CGZ), 0, 0); contactSDL.Apply(false, false);
            contactSDR.SetPixelData(contactSD.GetSubArray(CGX * CGZ, CGX * CGZ), 0, 0); contactSDR.Apply(false, false);
            for (int f = 0; f < 2; f++) { var b = contactBoxN[f]; contactBox[f] = new Vector4(b.x, b.y, 1f / (CGX * CCell), 1f / (CGZ * CCell)); }
            Shader.SetGlobalVectorArray("_SheerContactBox", contactBox);
            Shader.SetGlobalVector("_SheerContactInfo", new Vector4(1f, 0f, contactK, 0f));
        }

        public void Apply()
        {
            UpdatePose(simTime);
            UpdateContact();
            // The meshes stay at rest: the pose (rigid cross-sections per height and side) and the pulled fabric are applied in
            // the vertex shaders (SheerCloth.hlsl) from the tables pushed here. (Posing 526k vertices in Burst jobs and
            // uploading both meshes cost ~9 ms of every frame.)
            profSw.Restart();
            PushPose();
            // the glints flash in the key light (SheerTights.hlsl)
            if (!keyLight) foreach (var l in FindObjectsByType<Light>(FindObjectsSortMode.None)) if (l.name == "key") keyLight = l;
            if (keyLight) { var kp = keyLight.transform.position; Shader.SetGlobalVector("_SheerKeyPos", new Vector4(kp.x, kp.y, kp.z, 1f)); }
            Shader.SetGlobalFloat("_SheerDepthBias", depthBias);
            // the pinch of each leg (traction lines fan out from it, SheerTights.hlsl): strength eases in with the pull and
            // out with the recoil
            for (int sd = 1; sd >= -1; sd -= 2)
            {
                Pull hp = null;
                foreach (var p in pulls) if (p.side == sd && (p.state == Pull.State.Held || p.state == Pull.State.Recoil)) hp = p;
                int li = sd > 0 ? 0 : 1;
                if (hp != null)
                {
                    pinchUZ[li] = new Vector3(hp.u, hp.z, damage[sd].Circ(hp.z)); pinchW[li] = Mathf.Clamp01(hp.P.magnitude / 0.012f);
                    // (which way the fingers pull, in the fabric's coordinates: the drawn fan of wrinkles lies behind the pinch,
                    //  from where the fabric is held toward the fingers - SheerTights.hlsl)
                    if (!hp.foot)
                    {
                        int lg = ClothLattice.Leg(sd);
                        Vector2 uz0 = lattice.DamageUZ(lg, hp.c), uz1 = lattice.DamageUZ(lg, hp.c + hp.P);
                        float du = Mathf.Repeat(uz1.x - uz0.x + 0.5f, 1f) - 0.5f;
                        float onSk = 1f - Mathf.SmoothStep(0f, 1f, (lattice.Lift(lg, hp.c + hp.P) - 0.01f) / 0.03f);
                        pinchDir[li] = new Vector4(du * pinchUZ[li].z, uz1.y - uz0.y, onSk, 0f);
                    }
                    else pinchDir[li] = Vector4.zero;
                }
                else pinchW[li] = Mathf.MoveTowards(pinchW[li], 0f, Time.deltaTime / 0.12f);
                Shader.SetGlobalVector(sd > 0 ? "_SheerPinchL" : "_SheerPinchR", new Vector4(pinchUZ[li].x, pinchUZ[li].y, pinchUZ[li].z, pinchW[li]));
                if (hp == null) pinchDir[li] *= Mathf.Clamp01(pinchW[li]);
                Shader.SetGlobalVector(sd > 0 ? "_SheerPinchDirL" : "_SheerPinchDirR", pinchDir[li]);
                // let go, the drawn fabric snaps onto the leg: its displacement fades out within ~2 frames while the cloth itself,
                // pulled back hard, relaxes underneath, and comes back in over 0.4 s (review round 10: sails took 4 frames to
                // go and bulged into a dome on the way; the original's are 90 % gone in 2)
                bool heldNow = false; foreach (var p in pulls) if (p.side == sd && p.state == Pull.State.Held) heldNow = true;
                if (heldNow) relFadeT[li] = -1f;
                else if (relFadeT[li] == -1f) foreach (var p in pulls) if (p.side == sd && p.state != Pull.State.Held && p.state != Pull.State.Idle) relFadeT[li] = Mathf.Max(relFadeT[li], p.tRel);
                float tf = relFadeT[li] >= 0f ? simTime - relFadeT[li] : -1f;
                // (OFF since review round 11: scaled straight back toward rest, fabric that had wrapped round the leg cut
                //  through the skin for a frame or two - black slashes, skin flashes, one-frame holes at almost every release;
                //  the physical release - fingers opening, hard pull-back, collision - does it now)
                float fade = 1f;
                if (tf > 0.6f) relFadeT[li] = -2f;
                Shader.SetGlobalFloat(sd > 0 ? "_SheerDispFadePrevL" : "_SheerDispFadePrevR", dispFade[li]);
                dispFade[li] = fade;
                Shader.SetGlobalFloat(sd > 0 ? "_SheerDispFadeL" : "_SheerDispFadeR", fade);
                // gathered-fabric darkening (SheerTights.hlsl) only while the hand holds the fabric: eased out after a release,
                // cut at once when it tore - the recoiling fabric is squeezed for a frame or two, which drew a dark ring round
                // the new hole
                bool holding = false, torn = false;
                foreach (var p in pulls) if (p.side == sd) { if (p.state == Pull.State.Held) holding = true; else if (p.state == Pull.State.Recoil && p.burst) torn = true; }
                // (out in 0.03 s after a release: over 0.1 s the recoiling fabric's squeeze drew a dark blotch, review round 7)
                heldW[li] = holding ? Mathf.MoveTowards(heldW[li], 1f, Time.deltaTime / 0.04f) : torn ? 0f : Mathf.MoveTowards(heldW[li], 0f, Time.deltaTime / 0.03f);
                Shader.SetGlobalFloat(sd > 0 ? "_SheerHeldL" : "_SheerHeldR", heldW[li]);
            }
            if (Cl != null && Cl.lastFlushFrame != Time.frameCount) Cl.SyncPrev();   // a frame without a cloth step: nothing moved
            profApplyMs += profSw.Elapsed.TotalMilliseconds;
            profSw.Restart();
            foreach (var kv in damage) if (kv.Value.dirty) damageTex[kv.Key].Render(kv.Value);
            profRasterMs += profSw.Elapsed.TotalMilliseconds;
        }

        static float Smoother(float x) { x = Mathf.Clamp01(x); return x * x * x * (x * (x * 6 - 15) + 10); }

        /// The pinched patch of the pull that is held now (mesh space, posed), if any: the hand under the hem lifts the skirt.
        /// Where the hand of the held pull is (posed mesh space): the patch's grab point + the hand's drag, unclamped.
        public bool HeldHand(out Vector3 at, out Vector3 grab)
        {
            foreach (var p in pulls)
                if (p.state == Pull.State.Held) { grab = PosePoint(PullRest(p), p.side); at = grab + p.target; return true; }   // (target: the hand's drag, mesh space)
            at = default; grab = default; return false;
        }

        public bool HeldPatch(out Vector3 at)
        {
            foreach (var p in pulls)
                if (p.state == Pull.State.Held) { at = PosePoint(PullRest(p, p.c + p.P), p.side); return true; }
            at = default; return false;
        }

        /// Pose displacement at a rest-space point (for the skirt, the hand).
        public Vector3 PoseOffset(Vector3 p) => PosePoint(p) - p;

        void OnDestroy()
        {
            T?.Dispose(); B?.Dispose();
            if (side.IsCreated) side.Dispose(); if (noSide.IsCreated) noSide.Dispose();
            if (noDisp.IsCreated) noDisp.Dispose();
            if (poseA.IsCreated) poseA.Dispose(); if (poseC.IsCreated) poseC.Dispose();
            Cl?.Dispose();
            if (contactVtx.IsCreated) { contactVtx.Dispose(); contactSide.Dispose(); contactPos.Dispose(); contactH.Dispose(); contactAO.Dispose(); contactSD.Dispose(); contactB.Dispose(); contactBoxN.Dispose(); }
            if (zTexL) Destroy(zTexL);
            if (shapedRest.IsCreated) shapedRest.Dispose();
            if (shapeTex) Destroy(shapeTex);
            if (circTex) Destroy(circTex);
            if (zTexR) Destroy(zTexR);
            Shader.SetGlobalVector("_SheerClothGrid", Vector4.zero);
            Shader.SetGlobalVector("_SheerSock", Vector4.zero);
            Shader.SetGlobalFloat("_SheerShellGap", 0f); Shader.SetGlobalFloat("_SheerShellGapBend", 0f); Shader.SetGlobalFloat("_SheerSoftLod", 0f);
            Shader.SetGlobalVector("_SheerPoseParams", Vector4.zero);
            Shader.SetGlobalVector("_SheerPoseParamsPrev", Vector4.zero);
            Shader.SetGlobalVector("_SheerKeyPos", Vector4.zero); Shader.SetGlobalFloat("_SheerDepthBias", 0f);
            Shader.SetGlobalVector("_SheerPinchL", Vector4.zero); Shader.SetGlobalVector("_SheerPinchR", Vector4.zero);
            Shader.SetGlobalVector("_SheerPinchDirL", Vector4.zero); Shader.SetGlobalVector("_SheerPinchDirR", Vector4.zero);
            if (poseTex) Destroy(poseTex);
            if (poseTexPrev) Destroy(poseTexPrev);
            if (axisTex) Destroy(axisTex);
            foreach (var d in damageTex.Values) d.Dispose();
        }
    }
}
