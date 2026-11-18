// SHEER — the stocking as cloth, on the GPU (SheerCloth.compute; reference implementation: tools/sim/leash.py).
// Each leg is a lattice (NU around x NV along, ~1.4 x 2.2 mm cells) of the worn stocking surface, exported from the
// render mesh by tools/sim/export_lattice.py. The knit is a pre-stretched membrane: every thread is shorter than the
// leg it is worn on, so it carries tension at rest; pulled, it has a soft elastic range and then locks. Friction on
// the skin is a saturating leash to the worn position, the leg is a radial height field about its axis, the ankle
// and top rows are pinned, the hand is a small kinematic gathered patch. 3840 substeps per second, only for a leg
// that is being pulled (an untouched leg is exactly at rest and sleeps).
// The result reaches the picture through three textures per leg: displacement + lift (vertex shader, skin),
// principal stretches (fragment shader: sheerness, rucks), normal change.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace Sheer
{
    [Serializable]
    public class ClothParams
    {
        [Header("Solver")] public float subRate = 3840f; public float damp = 0.985f, omega = 1.5f; public int maxSubsteps = 256;
        [Header("Knit")] public float kSoft = 0.30f;
        public float lockU = 0.90f, lockV = 0.90f, lockD = 1.20f;          // strain where the knit locks: around / along / diagonal
        public float shrinkU = 0.50f, shrinkV = 0.25f, shrinkD = 0.30f;     // pre-stretch: natural length = (1 - shrink) x worn length
        public float kDiag = 0.35f, kComp = 0.02f, kCs = 0.30f;
        public float jam = 0.35f, fold = 0.05f;                              // least spacing on the leg / in the air (fraction of worn)
        public float orderH0 = 0.015f, orderH1 = 0.030f;                     // ... kept only near the leg (lift, m)
        [Tooltip("Fabric lifted less than this off the skin (m: full / none) cannot be gathered below 'jam': it piles up ahead of a " +
                 "pinch dragged over the leg instead of folding under it.")]
        public float jamH0 = 0.006f, jamH1 = 0.012f;
        [Tooltip("Fabric pushed together in its plane and lifted only millimetres is pressed onto the skin by this much per " +
                 "substep (m; 0 = off), fading out between the two lifts (m): wrinkles lie on the leg, they do not stand up as a ridge.")]
        public float press = 0.0001f, pressH0 = 0.008f, pressH1 = 0.016f;
        [Tooltip("The fabric round a pinch goes along with it while the hand drags it over the skin, falling off as exp(-distance / L): " +
                 "L = this (m; 0 = off) or dragKL x the drag, whichever is longer; dragK = how firmly (0..1 per substep).")]
        // (measured in the original, 5.08 - 5.75 s: a pull 3.7 cm from its big hole drew the hole's near edge ~3 x as far as its
        //  far edge, 5 cm further away - L ~3 - 4 cm. Ours was 2 x the drag up to 10 cm, then 1.2 x up to 6 (review 13): the whole
        //  torn patch slid with the hand 'like a loose sleeve' and a hole beside the fingers left the leg whole, review 14)
        public float dragL0 = 0.03f, dragKL = 0.6f, dragK = 1f;
        [Tooltip("... no longer than this (m); and round the leg the fabric goes along by at most this x the leg's radius there " +
                 "(the hoop holds the rest: the pinch itself goes on alone).")]
        public float dragLMax = 0.035f, dragRound = 0.6f;
        // (friction x1.7, saturating 7.5 x later: with the old values an ankle pull drew the whole ring of fabric round the
        //  leg toward the hand - a detached 'cuff' with a fold all round the ankle, review round 6)
        [Header("Skin")] public float kLeash = 0.0025f; public float slip = 0.003f, h0 = 0.0005f, h1 = 0.0030f;
        public float kRel = 0.0025f, dampRel = 0.90f;                        // after release: back to the worn position, critically damped
        [Tooltip("Letting go: everything the hand pulled - sail, tent, the fabric slid round the leg - goes home together in its own " +
                 "shape, every node the same share of its way per substep on the profile of a released elastic, (1 + t/tau) " +
                 "e^(-t/tau) (tau, s; 0 = TightsSim.recoilTau), for recoilLen time constants; then the springs settle it. " +
                 "(recoilLeash / recoilDamp: the old dynamic recoil's, unused.)")]
        public float recoilTau = 0.012f, recoilLen = 7f, recoilLeash = -1f, recoilDamp = 0f;
        [Tooltip("Hold on the far side of the leg from the grab while the hand pulls (per substep).")]
        public float kFar = 0f;                    // (0.01 - 0.04 tried on the 27.5 s ankle sail: the visible fold is on the front, no gain)
        public int pinRows = 3, pinFade = 12;        // (4 rows of fade left a hard lower edge - a belt - where a sail meets the ankle)
        public int pinHold = 4;                      // rows above the held band that the hand's reach is measured from (as before the longer fade)
        [Tooltip("Rows of free fabric kept between a grab and the held ankle band (2.2 mm each).")]
        public int ankleRows = 11;
        [Tooltip("Share of the hand's sideways pull that the held ankle band follows when the fabric is grabbed just above it " +
                 "(the fabric over heel and instep feeds the sail), and how far it may go (m).")]
        public float ankleGive = 0f, ankleGiveMax = 0.02f;      // (0.4 lengthened the ankle sails by ~10 % but folded them into prongs when the hand turned)
        [Tooltip("Grabbed just above the ankle band, the band's rows on the hand's side may lift OFF the leg (not slide along or " +
                 "round it): the sail runs on down over the ankle to the instep, as the original's do (review round 7: ours stopped " +
                 "3 cm above the foot, a third of the original's area). 0 = the band stays on the skin.")]
        public float ankleFree = 0.65f;          // (1: the lifted band stood as a second ledge under the sail - a curled double edge)
        // (4 mm gathered to 0.3: a 7 mm patch at 0.6 is a rigid plate 8 mm across - tents ended in a bead or a flat chisel
        //  tip, and a pinch on the toes lifted a box: free-play sweep 2026-11-17)
        // (14 mm gathered to 0.15 since review 7: the fingers take a broad patch of fabric and bunch it - at 4 mm the press read
        //  as a needle poke, a knife-edge crease where the original's knee puckers into a V. A 7 mm x 0.4 trial had seemed to
        //  shrink the sails, but they were cut short by the near-hole reach rule then, since removed. The foot keeps its
        //  4 mm x 0.3, TightsSim.FootHand)
        [Header("Hand")] public float pinchR = 0.014f; public float gather = 0.15f, reach = 1.0f;
        [Tooltip("The tether's reach round the leg (0 = as along it).")] public float reachU = 3f;   // (3: no ankle cuff, 27.5 s)
        [Tooltip("The fingers hold a fold: the patch this much longer along the wale (1 = round), bunched to gatherAlong there (0 = gather).")]
        public float pinchElong = 3.5f, gatherAlong = 0.25f;   // (0.12: a needle tip, review 12; 0.4 a flat cut-off one, review 10)   // (0.4 -> 0.12: a 5 cm fold held 2 cm tall made a flat cut-off sail tip, review 10 - the fingers bunch it to a point)   // (since review 7: blunt sail tips; 3.5 x 0.4 after review 8: the sails broad sheets anchored along the leg, the 27.5 s ankle sail a curtain with a straight edge like the original's, the knee pinch still a modest fold; 4 x 0.6 made the knee a tall 'cut flap'. The foot keeps a round grip, TightsSim.FootHand)
        [Tooltip("Height of the pinched fold above the skin while the hand drags it over the leg (m).")]
        // (4 mm: fingertips sliding over the skin. It was 12 mm for some rounds - then the fan of fabric trailing a pinch
        //  dragged over the leg stood off the skin as a flat sheet and was shaded as a see-through sail, salmon patches
        //  round every on-leg pinch: free-play sweep 2026-11-17. The crisp folds 4 mm once gave are gone with the drag field)
        public float pinchLift = 0.004f;
        [Tooltip("How far the pinched patch follows the hand once it is off the leg (m).")]
        // (0.085 'measured in the original' left a tent's tip 3-4 cm short of the cursor (original session 5.6 s: hand 127 mm
        //  from the grab, patch 100 mm) where the original's tip sits ON the cursor - independent review 2026-11-17. The
        //  drag that TEARS stays measured against the old reach: tearReach)
        public float rMax = 0.12f;   // (0.15 pinned every tip exactly on the cursor; the original's mostly trail it, review 2)
        [Tooltip("The reach the tearing drag is measured against (m): the fabric tears at TightsSim.tearAtReach x this (x the yarn, x damage nearby).")]
        public float tearReach = 0.085f;
        [Tooltip("Off the leg, the patch only follows this fraction of the hand along the leg (measured: 0.56-0.58).")]
        public float along = 0.57f;
        [Tooltip("While the hand drags the patch over the skin: reach (m) and the fraction of the hand it follows around the leg " +
                 "(measured on the original's thigh drag: the patch ends 73 mm from the grab, 0.6 as far around as along).")]
        public float rMaxOnLeg = 0.09f;     // (0.073 measured on the thigh drag; 0.12 dragged the opening knee pinch 11 cm down the shin as a spike)
        [Tooltip("While the hand drags the patch over the skin: the share of its travel ALONG the leg the patch follows (the original's " +
                 "knee pinch: the pocket's tip 3 - 4 cm below the grab while the cursor goes 11 cm - the leg holds the fabric along its length).")]
        public float alongOnLeg = 0.4f;
        [Tooltip("A pinch dragged over the leg rises off the skin as it goes: lift (m) per m of drag beyond the first 12 mm, " +
                 "up to liftMax - the fabric gathers ahead of the fingers, then stands up into a bulge / tent (the original's " +
                 "calf at 33 s, thigh at 7.7 s). 0 = it slides on the skin.")]
        public float liftK = 0.8f, liftMax = 0.06f;   // (0.3 / 0.03: the knee pinch a small fold where the original draws a deep pocket)
        public float aroundOnLeg = 0.6f;
        public float tau = 0.008f, tauLocked = 0.2f;                        // lag of the patch behind the hand; creep once saturated
        public float sleepAfter = 0.30f;                                     // s of free motion after a release before the leg sleeps
    }

    /// The lattice on the CPU: picking, the hand's collision with the leg.
    /// ONE lattice per leg for the whole stocking, from the toes to under the skirt (tools/sim/export_sock_lattice.py; user,
    /// 2026-11-16: the leg's and the foot's fabric had been two lattices joined only at the ankle - a ladder could not run
    /// on from the shin onto the foot, a pull on one did not draw the other). As a real tube-knit stocking: its rows are
    /// cross-sections of the tube by planes - horizontal on the leg (rest height >= yc), half-planes through the bend's
    /// axis (a line along x at (yc, zc), in front of the ankle) turning from horizontal to vertical round ankle and heel,
    /// vertical (z = const) along the foot - and each column is one wale from the toe seam up the leg: on the shin's front
    /// it runs on down the ankle onto the instep, at the back down the heel and along the sole. Row parameter S (m): 0 at
    /// the toe tip, + along the foot, rho x the bend's angle, + height up the leg (row j at S = s0 + j ds; on the leg its
    /// height is y0 + j dy, dy = ds). In a row's plane a point has a = x and B (= z on the leg, zc + its distance from the
    /// bend's axis round the bend, zc + yc - y on the foot); theta = atan2(a - ax, B - az) about the row's centre (0 = back
    /// of the leg / heel / sole, pi = shin / instep).
    public class ClothLattice
    {
        public int NU, NV; public float y0, y1, dy;
        public float yc, zc, rho, sc, s0;                   // the bend's axis (height, depth), its radius in S, S at its top, S of row 0
        public readonly float[][] ax = new float[2][], az = new float[2][], R = new float[2][], X = new float[2][];   // per leg (0: side +1, 1: side -1)
        /// as exported: the stocking's coordinates are addressed with these (the shaders' UVs, NodeAt, DamageUZ) whatever the
        /// body shape; ax / az / R / X above are the PHYSICAL lattice (the solver's, the hand's) - the same unless a shape is set
        public float[][] ax0 = new float[2][], az0 = new float[2][], R0 = new float[2][], X0 = new float[2][];
        /// per node held (1) or free (the sole on the floor), and the same softened over a few nodes
        public readonly float[][] pin = new float[2][], pinSoft = new float[2][];
        /// per node: where it is in the damage maps along its wale (the rest height on the leg; below yc, yc minus the arc
        /// length down the wale); per column: the damage maps' u offset below yc (the leg's u is the mesh's own uv0.x)
        public readonly float[][] Z = new float[2][], du = new float[2][];

        public static int Leg(int side) => side > 0 ? 0 : 1;

        public static ClothLattice Load(string path)
        {
            var b = File.ReadAllBytes(path);
            if (b[0] != 'S' || b[1] != 'L' || b[2] != 'A' || b[3] != 'T') throw new Exception("not a cloth lattice: " + path);
            int version = BitConverter.ToInt32(b, 4);
            if (version != 3) throw new Exception("cloth lattice version " + version + " (the stocking's lattice is version 3: tools/sim/export_sock_lattice.py)");
            var L = new ClothLattice { NU = BitConverter.ToInt32(b, 8), NV = BitConverter.ToInt32(b, 12), y0 = BitConverter.ToSingle(b, 16), y1 = BitConverter.ToSingle(b, 20) };
            L.yc = BitConverter.ToSingle(b, 24); L.zc = BitConverter.ToSingle(b, 28); L.rho = BitConverter.ToSingle(b, 32);
            L.sc = BitConverter.ToSingle(b, 36); L.s0 = BitConverter.ToSingle(b, 40); L.dy = BitConverter.ToSingle(b, 44);
            int o = 48, n = L.NU * L.NV;
            float[] Read(int count) { var a = new float[count]; Buffer.BlockCopy(b, o, a, 0, 4 * count); o += 4 * count; return a; }
            for (int l = 0; l < 2; l++)
            {
                L.ax[l] = Read(L.NV); L.az[l] = Read(L.NV); L.R[l] = Read(n); L.X[l] = Read(3 * n);
                L.pin[l] = Read(n); L.pinSoft[l] = Read(n); L.Z[l] = Read(n); L.du[l] = Read(L.NU);
                L.ax0[l] = (float[])L.ax[l].Clone(); L.az0[l] = (float[])L.az[l].Clone(); L.R0[l] = (float[])L.R[l].Clone(); L.X0[l] = (float[])L.X[l].Clone();
            }
            if (o != b.Length) throw new Exception("cloth lattice size mismatch");
            return L;
        }

        public Vector3 Node(int leg, int j, int i) { int k = 3 * (j * NU + i); var x = X[leg]; return new Vector3(x[k], x[k + 1], x[k + 2]); }

        /// The row parameter S of a point, its in-plane coordinate B and the direction in which B grows (unit).
        public float S(Vector3 p, out float B, out Vector3 eB)
        {
            if (p.y >= yc) { B = p.z; eB = Vector3.forward; return sc + (p.y - yc); }
            if (p.z > zc)
            {
                float h = yc - p.y, d = p.z - zc, q = Mathf.Sqrt(h * h + d * d);
                B = zc + q; eB = q > 1e-9f ? new Vector3(0f, -h / q, d / q) : Vector3.forward;
                return sc - rho * Mathf.Atan2(h, d);
            }
            B = zc + (yc - p.y); eB = Vector3.down;
            return sc - rho * 0.5f * Mathf.PI - (zc - p.z);
        }
        /// Fractional row of a point (clamped to the lattice).
        public float RowF(Vector3 p) => Mathf.Clamp((S(p, out _, out _) - s0) / dy, 0f, NV - 1.001f);
        /// (S, a, B) -> mesh space
        public Vector3 ToMesh(float s, float a, float B)
        {
            if (s >= sc) return new Vector3(a, yc + (s - sc), B);
            float b = B - zc, sf = sc - rho * 0.5f * Mathf.PI;
            if (s > sf) { float g = (sc - s) / rho; return new Vector3(a, yc - b * Mathf.Sin(g), zc + b * Mathf.Cos(g)); }
            return new Vector3(a, yc - b, zc - (sf - s));
        }
        /// The centre of row j (mesh space).
        public Vector3 Centre(int leg, int j) => ToMesh(s0 + j * dy, ax[leg][j], az[leg][j]);

        /// Nearest node to a rest-space point of the stocking, kept off the pinned rows. (The angle is taken about the
        /// row's own centre, as the shaders do: SheerClothUV in SheerCloth.hlsl.)
        public void NodeAt(int leg, Vector3 rest, int margin, out int j, out int i, int marginToe = -1)
        {
            if (marginToe < 0) marginToe = margin;
            float f = Mathf.Clamp((S(rest, out float B, out _) - s0) / dy, 0f, NV - 1.001f); int j0 = (int)f; float a = f - j0;
            float dx = rest.x - Mathf.Lerp(ax0[leg][j0], ax0[leg][j0 + 1], a), dz = B - Mathf.Lerp(az0[leg][j0], az0[leg][j0 + 1], a);
            float th = Mathf.Atan2(dx, dz) / (2f * Mathf.PI); th -= Mathf.Floor(th);
            i = ((Mathf.RoundToInt(th * NU) % NU) + NU) % NU;
            j = Mathf.Clamp(Mathf.RoundToInt(f), marginToe, NV - 1 - margin);
        }

        /// Where a rest point of the stocking is in the damage maps (u around, z along its wale) - below yc (the bend and the
        /// foot); on the leg the maps use the mesh's own coordinates (uv0) and this agrees with them at yc.
        public Vector2 DamageUZ(int leg, Vector3 rest)
        {
            float f = Mathf.Clamp((S(rest, out float B, out _) - s0) / dy, 0f, NV - 1.001f); int j0 = (int)f; float a = f - j0;
            float dx = rest.x - Mathf.Lerp(ax0[leg][j0], ax0[leg][j0 + 1], a), dz = B - Mathf.Lerp(az0[leg][j0], az0[leg][j0 + 1], a);
            float th = Mathf.Atan2(dx, dz) / (2f * Mathf.PI); th -= Mathf.Floor(th);
            float g = th * NU; int i0 = ((int)g) % NU, i1 = (i0 + 1) % NU; float bq = g - (int)g;
            var z = Z[leg]; var d = du[leg];
            float zz = Mathf.Lerp(Mathf.Lerp(z[j0 * NU + i0], z[j0 * NU + i1], bq), Mathf.Lerp(z[(j0 + 1) * NU + i0], z[(j0 + 1) * NU + i1], bq), a);
            float u = th + Mathf.Lerp(d[i0], d[i1], bq);
            return new Vector2(u - Mathf.Floor(u), zz);
        }

        /// The row centres as a texture for the shaders: NV x 2 (row 0: left leg, row 1: right leg), RG = centre (a, B).
        public Texture2D AxisTexture()
        {
            var t = new Texture2D(NV, 2, TextureFormat.RGFloat, false, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "cloth_axis" };
            var d = new float[4 * NV];
            for (int l = 0; l < 2; l++) for (int j = 0; j < NV; j++) { d[2 * (l * NV + j)] = ax0[l][j]; d[2 * (l * NV + j) + 1] = az0[l][j]; }
            t.SetPixelData(d, 0); t.Apply(false, true);
            return t;
        }

        /// BODY SHAPE (TightsSim.SetShape): every leg row's cross-section scaled by s about its inner side - x about the inner
        /// surface xin, z about the axis - so the thighs grow away from each other; the physical lattice follows the body.
        /// shape(leg, y) = (s, xin, az).
        public void ApplyShape(System.Func<int, float, Vector3> shape)
        {
            int n = NU * NV;
            for (int l = 0; l < 2; l++)
            {
                for (int j = 0; j < NV; j++)
                {
                    // the row's own height (leg rows are horizontal; below the bend's top the shape is 1)
                    float y = j < 0 ? 0f : Centre0Y(l, j);
                    var sh = shape(l, y);
                    ax[l][j] = sh.y + sh.x * (ax0[l][j] - sh.y); az[l][j] = az0[l][j];
                    for (int i = 0; i < NU; i++)
                    {
                        int k = j * NU + i;
                        R[l][k] = R0[l][k] * sh.x;
                        float px = X0[l][3 * k], py = X0[l][3 * k + 1], pz = X0[l][3 * k + 2];
                        var s2 = shape(l, py);
                        X[l][3 * k] = s2.y + s2.x * (px - s2.y); X[l][3 * k + 1] = py; X[l][3 * k + 2] = s2.z + s2.x * (pz - s2.z);
                    }
                }
            }
        }
        float Centre0Y(int l, int j) { float s = s0 + j * dy; return s >= sc ? yc + (s - sc) : 0f; }

        /// Per node (Z, u offset of its wale) as a texture (NU x NV, bilinear, u repeats).
        public Texture2D ZTexture(int leg)
        {
            var t = new Texture2D(NU, NV, TextureFormat.RGFloat, false, true) { wrapModeU = TextureWrapMode.Repeat, wrapModeV = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "cloth_z_" + (leg == 0 ? "L" : "R") };
            var d = new float[2 * NU * NV];
            for (int j = 0; j < NV; j++) for (int i = 0; i < NU; i++) { int k = j * NU + i; d[2 * k] = Z[leg][k]; d[2 * k + 1] = du[leg][i]; }
            t.SetPixelData(d, 0); t.Apply(false, true);
            return t;
        }

        /// Direction of the tube (along the wales, toward the top) at row j.
        public Vector3 AxisDir(int leg, int j)
        {
            int j0 = Mathf.Max(j - 4, 0), j1 = Mathf.Min(j + 4, NV - 1);
            return (Centre(leg, j1) - Centre(leg, j0)).normalized;
        }

        /// ... the exported one (the body shape's anchor)
        public Vector2 LegAxis0(int leg, float y)
        {
            float f = Mathf.Clamp((Mathf.Max(y, yc) - y0) / dy, 0f, NV - 1.001f); int j0 = (int)f; float a = f - j0;
            return new Vector2(Mathf.Lerp(ax0[leg][j0], ax0[leg][j0 + 1], a), Mathf.Lerp(az0[leg][j0], az0[leg][j0 + 1], a));
        }

        /// The leg's axis at a height on the leg (heights below yc: at yc) - the hand's mapping over the leg (Snap).
        public Vector2 LegAxis(int leg, float y)
        {
            float f = Mathf.Clamp((Mathf.Max(y, yc) - y0) / dy, 0f, NV - 1.001f); int j0 = (int)f; float a = f - j0;
            return new Vector2(Mathf.Lerp(ax[leg][j0], ax[leg][j0 + 1], a), Mathf.Lerp(az[leg][j0], az[leg][j0 + 1], a));
        }

        /// Leg radius under p and p relative to the row's centre, in the row's plane (same as RadiusAt in SheerCloth.compute).
        public float Radius(int leg, Vector3 p, out float dx, out float dz) => Radius(leg, p, out dx, out dz, out _);
        /// ... and eB: the in-plane direction of dz (mesh space; dx is along x). Out of the leg = dx x + dz eB.
        public float Radius(int leg, Vector3 p, out float dx, out float dz, out Vector3 eB)
        {
            float f = Mathf.Clamp((S(p, out float B, out eB) - s0) / dy, 0f, NV - 1.001f); int j0 = (int)Mathf.Floor(f); float a = f - j0;
            dx = p.x - Mathf.Lerp(ax[leg][j0], ax[leg][j0 + 1], a); dz = B - Mathf.Lerp(az[leg][j0], az[leg][j0 + 1], a);
            float th = Mathf.Atan2(dx, dz) / (2f * Mathf.PI); float g = (th - Mathf.Floor(th)) * NU;
            int i0 = ((int)Mathf.Floor(g)) % NU; float b = g - Mathf.Floor(g); int i1 = (i0 + 1) % NU;
            var r = R[leg];
            return Mathf.Lerp(Mathf.Lerp(r[j0 * NU + i0], r[j0 * NU + i1], b), Mathf.Lerp(r[(j0 + 1) * NU + i0], r[(j0 + 1) * NU + i1], b), a);
        }

        /// Where the hand holds the pinched patch for a cursor ray eye -> W (rest space). Measured in the original: its sails
        /// lie entirely beyond the leg's outline and a tent only shows once the hand has travelled the distance to the
        /// outline, so the patch slides along the skin while the cursor is over the leg and leaves the leg sideways, in the
        /// plane of the leg axis facing the viewer. p0 = the point of the ray closest to the axis, m its distance from it,
        /// R the leg's radius in that (sideways) direction: the patch is put at p0 moved toward the viewer by
        /// 0.9 R (1 - (m / R)^2) - a parabola instead of the leg's own outline, so that it does not race around the leg as
        /// the cursor nears the silhouette - and Collide then pushes it out onto the skin. (tools/sim/run_leash.py: snap)
        public Vector3 Snap(int leg, Vector3 eye, Vector3 W) => Snap(leg, eye, W, out _);

        /// q = how far the ray passes from the leg axis, in leg radii (< 1: over the leg, > 1: past its outline).
        public Vector3 Snap(int leg, Vector3 eye, Vector3 W, out float q)
        {
            Vector3 d = (W - eye).normalized, p0 = W;
            for (int it = 0; it < 2; it++)
            {
                Vector2 la = LegAxis(leg, p0.y);
                var A0 = new Vector3(la.x, p0.y, la.y);
                // (a vertical line through the axis at that height: the fitted axis leans sharply near the foot, and following
                //  its lean below the ankle threw the hand's target toward the viewer)
                Vector3 u = Vector3.up;
                Vector3 w0 = eye - A0; float b = Vector3.Dot(d, u), dd = Vector3.Dot(d, w0), e = Vector3.Dot(u, w0);
                p0 = eye + ((b * e - dd) / Mathf.Max(1f - b * b, 1e-6f)) * d;
            }
            float R = Radius(leg, p0, out float dx, out float dz);
            q = Mathf.Sqrt(dx * dx + dz * dz) / Mathf.Max(R, 1e-6f);
            float qc = Mathf.Min(q, 1f);
            Vector3 pp = p0 - d * (0.9f * R * (1f - qc * qc));
            // (where the section is not round - below the kneecap, the shin's ridge - the parabola runs INSIDE the leg; pushed
            //  out radially from there, the patch slid ~2 cm round the leg: the opening knee pinch became a flap off the
            //  leg's front outline instead of a pocket in the kneecap, independent review 4. There the patch goes to where
            //  the ray meets the surface)
            if (q < 1f && Inside(leg, pp))
            {
                Vector3 a = pp - d * (2f * R + 0.05f), b = pp;
                if (!Inside(leg, a))
                {
                    for (int k = 0; k < 24; k++) { Vector3 m = 0.5f * (a + b); if (Inside(leg, m)) b = m; else a = m; }
                    pp = a;
                }
            }
            return pp;
        }

        /// The column of fabric between the patch (grabbed at node (j, i), rest position c) and the held ankle / top rows
        /// cannot get longer than its locked length: A is kept within that distance of both ends of the column.
        public Vector3 ClampToPins(int leg, int j, int i, Vector3 c, Vector3 A, ClothParams P, Vector3 give = default, float free = 0f)
        {
            for (int e = 0; e < 2; e++)
            {
                int jf = Mathf.Clamp(e == 0 ? P.pinRows + P.pinHold : NV - 1 - P.pinRows - P.pinHold, 0, NV - 1);
                Vector3 pf = Node(leg, jf, i);
                if (e == 0) pf += give;                                  // (the ankle band has moved toward the hand)
                if (e == 0) pf.y -= 0.045f * free;                       // (lifting off, it takes the fabric over the instep along)
                float rf = Mathf.Max((c - pf).magnitude, 0.002f) * (1f + P.lockV);
                Vector3 dv = A - pf; float ln = dv.magnitude;
                if (ln > rf) A = pf + dv * (rf / ln);
            }
            return A;
        }

        /// The patch stays within the stocking: above the floor, below the pinned top.
        public Vector3 ClampHeight(Vector3 p, ClothParams P)
        {
            // (it may hang down past the ankle, to the floor: the original's ankle sails do)
            p.y = Mathf.Clamp(p.y, 0.003f, y1 - (P.pinRows + 1) * dy);
            return p;
        }

        /// The hand's drag over the skin from the grab point c to a (rest space), on the surface: arc round the tube (m), along the
        /// wale (m), and the length over which the fabric going along with it falls off (SheerCloth.compute, _DragU).
        public Vector3 DragField(int leg, Vector3 c, Vector3 a, ClothParams P)
        {
            if (P.dragL0 <= 0f) return Vector3.zero;
            float rc = Radius(leg, c, out float dxc, out float dzc), sc0 = S(c, out float Bc, out _);
            Radius(leg, a, out float dxa, out float dza); float sa = S(a, out _, out _);
            float dth = Mathf.Atan2(dxa, dza) - Mathf.Atan2(dxc, dzc); dth -= 2f * Mathf.PI * Mathf.Round(dth / (2f * Mathf.PI));
            // (metres along the wale: round the bend a step in S is (distance from the bend's axis) / rho of a metre)
            float met = c.y < yc && c.z > zc ? Mathf.Max(Bc - zc, 0f) / rho : 1f;
            var u = new Vector2(Mathf.Clamp(dth * rc, -P.dragRound * rc, P.dragRound * rc), (sa - sc0) * met);
            return new Vector3(u.x, u.y, Mathf.Clamp(P.dragKL * u.magnitude, P.dragL0, Mathf.Max(P.dragLMax, P.dragL0)));
        }

        /// How far p stands off the worn stocking's surface (m; negative inside the leg).
        public float Lift(int leg, Vector3 p) { float r = Radius(leg, p, out float dx, out float dz); return Mathf.Sqrt(dx * dx + dz * dz) - r; }

        /// The outward normal of the worn surface of the LEG near p (rows horizontal there): from its surface points 4 mm
        /// round and along. (The radius from the leg's axis is off the true normal wherever the section is not round -
        /// below the kneecap by ~35 deg.)
        public Vector3 SurfaceNormal(int leg, Vector3 p)
        {
            Radius(leg, p, out float dx, out float dz, out Vector3 eB);
            Vector3 rad = new Vector3(dx, 0f, 0f) + eB * dz;
            if (rad.sqrMagnitude < 1e-12f) return Vector3.forward;
            rad.Normalize();
            Vector3 tA = Vector3.Cross(Vector3.up, rad).normalized;
            const float e = 0.004f;
            Vector3 a = SurfacePoint(leg, p + tA * e) - SurfacePoint(leg, p - tA * e);
            Vector3 b = SurfacePoint(leg, p + Vector3.up * e) - SurfacePoint(leg, p - Vector3.up * e);
            Vector3 n = Vector3.Cross(a, b);
            if (n.sqrMagnitude < 1e-14f) return rad;
            n.Normalize();
            return Vector3.Dot(n, rad) < 0f ? -n : n;
        }
        /// p moved onto the leg's surface along its radius (in its row's plane): the skin point nearest a hand held off the leg
        public Vector3 SurfacePoint(int leg, Vector3 p)
        {
            float r = Radius(leg, p, out float dx, out float dz, out Vector3 eB);
            float rh = Mathf.Max(Mathf.Sqrt(dx * dx + dz * dz), 1e-9f);
            return p + (new Vector3(dx, 0f, 0f) + eB * dz) * ((r - rh) / rh);
        }

        /// Is p inside the worn stocking's surface (the leg / foot)?
        public bool Inside(int leg, Vector3 p) { float r = Radius(leg, p, out float dx, out float dz); return dx * dx + dz * dz < r * r; }

        /// Pushes p out of the leg (to `margin` above its surface), within its row's plane.
        public Vector3 Collide(int leg, Vector3 p, float margin)
        {
            float r = Radius(leg, p, out float dx, out float dz, out Vector3 eB);
            float rh = Mathf.Max(Mathf.Sqrt(dx * dx + dz * dz), 1e-9f);
            float pen = Mathf.Max(r + margin - rh, 0f) / rh;
            return p + (new Vector3(dx, 0f, 0f) + eB * dz) * pen;
        }
    }

    /// Hand -> pinched patch. Measured in the original (two views): across the leg the patch follows the cursor 1:1, along
    /// the leg it only gets ~0.57 of the hand's travel, and its offset saturates at rMax. Past that it only creeps after
    /// the hand, and follows again as soon as the hand comes back inside the pulled length.
    public class HandMap
    {
        public Vector3 S, axis; public float rMax, reachScale = 1f;
        public float alongScale;                        // replay: share of the hand's travel along the leg off the leg (0 = P.along)

        /// C = the hand's drag (mesh space), onLeg = 1 while the cursor is over the leg (the patch is dragged over the skin),
        /// 0 once it is past the outline (the patch is pulled off the leg).
        public Vector3 Update(Vector3 C, float dt, ClothParams P, float onLeg)
        {
            // off the leg the fabric is held along its length; on the leg it is the turn around the leg that binds
            Vector3 al = Vector3.Dot(C, axis) * axis, ar = C - al;
            C = al * Mathf.Lerp(alongScale > 0f ? alongScale : P.along, P.alongOnLeg, onLeg) + ar * Mathf.Lerp(1f, P.aroundOnLeg, onLeg);
            rMax = Mathf.Lerp(P.rMax, P.rMaxOnLeg, onLeg) * reachScale;
            float L = C.magnitude, s = S.magnitude;
            Vector3 T = C * Mathf.Min(1f, rMax / Mathf.Max(L, 1e-9f));
            float sat = Mathf.Clamp01((s / rMax - 0.7f) / 0.3f); sat = sat * sat * (3f - 2f * sat);
            if (L < s) sat = 0f;
            float tau = P.tau + (P.tauLocked - P.tau) * sat;
            S += (T - S) * (1f - Mathf.Exp(-dt / tau));
            return S;
        }
    }

    public class TightsCloth : IDisposable
    {
        public readonly ClothLattice lat;
        public readonly ClothParams P;
        /// a floor under the stocking (mesh space): normal xyz, height w; zero = none. The feet stand on it.
        public Vector4 floor;
        readonly ComputeShader cs;
        readonly int kInit, kReset, kPredict, kSprings, kFinish, kResolve, kGripMask, kGripBlur, gx, gy;
        readonly CommandBuffer cmd = new CommandBuffer { name = "SheerCloth" };

        struct Sub { public Vector3 A, give, dragU; public bool held, kin; public float gather, free, pinchR, kRel, relLeash, damp, press, gatherAlong; }

        class Leg
        {
            public Texture2D rest; public RenderTexture f0, l1, l2, disp, tens, nrm;
            public RenderTexture dispPrev; public bool moved;               // the displacement the previous frame was drawn with
            public RenderTexture cur, prev, pred, tmp;                     // positions now / one substep ago, prediction, spring pass
            public ComputeBuffer axis;
            public Texture2D pinMask;                                       // per node: held (r), held softened (g): the sole on the floor
            public Texture2D ztex;                                          // per node: Z (where it is along its wale) - the hand's tether
            public RenderTexture grip, gripTmp;                             // per node: joined to this grab through intact knit (GripMask)
            public bool awake, held, predHeld; public int freeLeft;
            public Vector3 pinchC, give; public float grabTheta, free; public int gi, gj;
            public readonly List<Sub> queue = new List<Sub>();
        }
        readonly Leg[] legs = new Leg[2];

        static readonly int idRest = Shader.PropertyToID("_Rest"), idF0 = Shader.PropertyToID("_F0"), idX = Shader.PropertyToID("_X"),
            idXp = Shader.PropertyToID("_Xp"), idY = Shader.PropertyToID("_Y"), idP = Shader.PropertyToID("_P"), idL1 = Shader.PropertyToID("_L1"),
            idL2 = Shader.PropertyToID("_L2"), idOut = Shader.PropertyToID("_Out"), idOut2 = Shader.PropertyToID("_Out2"), idOut3 = Shader.PropertyToID("_Out3"),
            idOutDisp = Shader.PropertyToID("_OutDisp"), idOutTens = Shader.PropertyToID("_OutTens"), idOutNrm = Shader.PropertyToID("_OutNrm"),
            idAxis = Shader.PropertyToID("_Axis"), idHeld = Shader.PropertyToID("_Held"), idDamp = Shader.PropertyToID("_Damp"),
            idPinchC = Shader.PropertyToID("_PinchC"), idPinchA = Shader.PropertyToID("_PinchA"), idGrabTheta = Shader.PropertyToID("_GrabTheta"),
            idGrabI = Shader.PropertyToID("_GrabI"), idGrabJ = Shader.PropertyToID("_GrabJ"), idGather = Shader.PropertyToID("_Gather"), idGatherAlong = Shader.PropertyToID("_GatherAlong"),
            idPinGive = Shader.PropertyToID("_PinGive"), idPinchRad = Shader.PropertyToID("_PinchR"), idKRel = Shader.PropertyToID("_KRel"), idRelLeash = Shader.PropertyToID("_RelLeash"),
            idPinMask = Shader.PropertyToID("_PinMask"), idZTex = Shader.PropertyToID("_ZTex"),
            idORest = Shader.PropertyToID("_ORest"), idOAxis = Shader.PropertyToID("_OAxis"), idRel = Shader.PropertyToID("_Rel"),
            idRelBase = Shader.PropertyToID("_RelBase"), idPress = Shader.PropertyToID("_Press"), idDragU = Shader.PropertyToID("_DragU"),
            idOmega = Shader.PropertyToID("_Omega"), idDmgTex = Shader.PropertyToID("_DmgTex"), idDmgInfo = Shader.PropertyToID("_DmgInfo"),
            idOutGrip = Shader.PropertyToID("_OutGrip"), idGrip = Shader.PropertyToID("_Grip");
        /// per leg and height bin: this leg's rest frame -> the other leg's, as both are posed now (TightsSim.BuildPose);
        /// the cloth keeps lifted fabric off the other leg with it
        public const int RelBins = 512;
        readonly ComputeBuffer rel;

        public TightsCloth(ComputeShader shader, ClothLattice lattice, ClothParams prm)
        {
            cs = shader; lat = lattice; P = prm;
            kInit = cs.FindKernel("Init"); kReset = cs.FindKernel("Reset"); kPredict = cs.FindKernel("Predict"); kSprings = cs.FindKernel("Springs");
            kFinish = cs.FindKernel("Finish"); kResolve = cs.FindKernel("Resolve");
            kGripMask = cs.FindKernel("GripMask"); kGripBlur = cs.FindKernel("GripBlur");
            gx = (lat.NU + 7) / 8; gy = (lat.NV + 7) / 8;
            int n = lat.NU * lat.NV;
            for (int l = 0; l < 2; l++)
            {
                var L = legs[l] = new Leg();
                string tag = l == 0 ? "L" : "R";
                var px = new float[4 * n];
                for (int k = 0; k < n; k++) { px[4 * k] = lat.X[l][3 * k]; px[4 * k + 1] = lat.X[l][3 * k + 1]; px[4 * k + 2] = lat.X[l][3 * k + 2]; px[4 * k + 3] = lat.R[l][k]; }
                L.rest = new Texture2D(lat.NU, lat.NV, TextureFormat.RGBAFloat, false, true) { filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, name = "cloth_rest_" + tag };
                L.rest.SetPixelData(px, 0); L.rest.Apply(false, false);          // (kept readable: ReloadRest rewrites it)
                var axd = new Vector2[lat.NV];
                for (int j = 0; j < lat.NV; j++) axd[j] = new Vector2(lat.ax[l][j], lat.az[l][j]);
                L.axis = new ComputeBuffer(lat.NV, 8); L.axis.SetData(axd);
                L.f0 = State("cloth_f0_" + tag); L.l1 = State("cloth_l1_" + tag); L.l2 = State("cloth_l2_" + tag);
                L.cur = State("cloth_cur_" + tag); L.prev = State("cloth_prev_" + tag); L.pred = State("cloth_pred_" + tag); L.tmp = State("cloth_tmp_" + tag);
                // (tension and normal change with mip levels: fabric lying on the leg is read averaged over a centimetre - what
                //  shows there is the knit's fine wrinkles, not the lattice's cells: SheerCloth.hlsl)
                L.disp = Output("cloth_disp_" + tag); L.tens = Output("cloth_tens_" + tag, true); L.nrm = Output("cloth_nrm_" + tag, true);
                L.dispPrev = Output("cloth_disp_prev_" + tag);
                // held nodes: the sole on the floor (the toe tip and the top are held by rows)
                var pm = new float[2 * n];
                for (int k = 0; k < n; k++) { pm[2 * k] = lat.pin[l][k]; pm[2 * k + 1] = lat.pinSoft[l][k]; }
                L.pinMask = new Texture2D(lat.NU, lat.NV, TextureFormat.RGFloat, false, true) { filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, name = "cloth_pins_" + tag };
                L.pinMask.SetPixelData(pm, 0); L.pinMask.Apply(false, false);       // (kept readable: SetTopPin rewrites it)
                L.ztex = lat.ZTexture(l);
                L.grip = GripTex("cloth_grip_" + tag); L.gripTmp = GripTex("cloth_grip_tmp_" + tag);
            }
            rel = new ComputeBuffer(2 * RelBins, 16);
            var id = new Vector4[2 * RelBins];
            for (int k = 0; k < id.Length; k++) id[k] = new Vector4(1f, 0f, 0f, 0f);      // (unposed: both legs in the mesh's frame)
            rel.SetData(id);
            Rebuild();
        }

        /// The lattice's physical rest state changed (a body shape): upload it and recompute the rest tension.
        public void ReloadRest()
        {
            int n = lat.NU * lat.NV;
            for (int l = 0; l < 2; l++)
            {
                var L = legs[l];
                var px = new float[4 * n];
                for (int k = 0; k < n; k++) { px[4 * k] = lat.X[l][3 * k]; px[4 * k + 1] = lat.X[l][3 * k + 1]; px[4 * k + 2] = lat.X[l][3 * k + 2]; px[4 * k + 3] = lat.R[l][k]; }
                L.rest.SetPixelData(px, 0); L.rest.Apply(false, false);
                var axd = new Vector2[lat.NV];
                for (int j = 0; j < lat.NV; j++) axd[j] = new Vector2(lat.ax[l][j], lat.az[l][j]);
                L.axis.SetData(axd);
            }
            Rebuild();
        }

        float topPinY = 2f;
        /// Holds the stocking above a rest height (the top of a thigh-high: its welt grips the leg; nothing above it); 2 = none.
        public void SetTopPin(float yTop)
        {
            topPinY = yTop;
            int n = lat.NU * lat.NV;
            for (int l = 0; l < 2; l++)
            {
                var pm = new float[2 * n];
                for (int k = 0; k < n; k++)
                {
                    float y = lat.X[l][3 * k + 1];
                    float hold = y > yTop ? 1f : 0f, soft = Mathf.Clamp01((y - (yTop - 0.02f)) / 0.02f);
                    pm[2 * k] = Mathf.Max(lat.pin[l][k], hold); pm[2 * k + 1] = Mathf.Max(lat.pinSoft[l][k], soft * soft * (3f - 2f * soft));
                }
                legs[l].pinMask.SetPixelData(pm, 0); legs[l].pinMask.Apply(false, false);
            }
        }

        /// The two legs' relative placement this frame (2 x RelBins: cos, sin of the turn, shift x, z), see SheerCloth.compute.
        public void SetRelative(Vector4[] table) { if (table != null && table.Length == 2 * RelBins) rel.SetData(table); }

        RenderTexture GripTex(string name)
        {
            var rt = new RenderTexture(lat.NU, lat.NV, 0, RenderTextureFormat.RGHalf, RenderTextureReadWrite.Linear)
            { enableRandomWrite = true, filterMode = FilterMode.Point, wrapModeU = TextureWrapMode.Repeat, wrapModeV = TextureWrapMode.Clamp, name = name };
            rt.Create(); return rt;
        }

        /// Which fabric the fingers can hold from this grab: joined to it through intact knit, not behind a hole nor along the
        /// wale inside a ladder (SheerCloth.compute GripMask; computed once, as the hand takes hold).
        static readonly bool noGrip = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerNoGrip") >= 0;   // (experiments: the fingers hold everything, as before review 14)
        void ComputeGrip(Leg L, Texture dmg)
        {
            if (noGrip) dmg = null;
            PushParams();
            cs.SetInt(idGrabI, L.gi); cs.SetInt(idGrabJ, L.gj); cs.SetFloat(idGrabTheta, L.grabTheta);
            cs.SetTexture(kGripMask, idRest, L.rest); cs.SetTexture(kGripMask, idZTex, L.ztex);
            cs.SetTexture(kGripMask, idDmgTex, dmg != null ? dmg : Texture2D.blackTexture);
            cs.SetVector(idDmgInfo, dmg != null ? new Vector4(dmg.width, dmg.height, SheerDamage.ZMin, SheerDamage.RANGE) : Vector4.zero);
            cs.SetTexture(kGripMask, idOutGrip, L.gripTmp);
            cs.Dispatch(kGripMask, gx, gy, 1);
            cs.SetTexture(kGripBlur, idGrip, L.gripTmp); cs.SetTexture(kGripBlur, idOutGrip, L.grip);
            cs.Dispatch(kGripBlur, gx, gy, 1);
        }

        RenderTexture State(string name)
        {
            var rt = new RenderTexture(lat.NU, lat.NV, 0, RenderTextureFormat.ARGBFloat, RenderTextureReadWrite.Linear)
            { enableRandomWrite = true, filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp, name = name };
            rt.Create(); return rt;
        }

        RenderTexture Output(string name, bool mips = false)
        {
            var rt = new RenderTexture(lat.NU, lat.NV, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear)
            { enableRandomWrite = true, filterMode = mips ? FilterMode.Trilinear : FilterMode.Bilinear, wrapModeU = TextureWrapMode.Repeat, wrapModeV = TextureWrapMode.Clamp, name = name,
              useMipMap = mips, autoGenerateMips = false };
            rt.Create(); return rt;
        }

        /// This lattice's parameters - straight to the shader, or recorded into a command buffer (legs and feet share the
        /// compute shader: each flush carries its own).
        void PushParams(CommandBuffer c = null)
        {
            void I(string k, int v) { if (c != null) c.SetComputeIntParam(cs, k, v); else cs.SetInt(k, v); }
            void F(string k, float v) { if (c != null) c.SetComputeFloatParam(cs, k, v); else cs.SetFloat(k, v); }
            void V(string k, Vector4 v) { if (c != null) c.SetComputeVectorParam(cs, k, v); else cs.SetVector(k, v); }
            // (rows by the row parameter S - toe tip, along the foot, round the bend, up the leg: ClothLattice)
            I("_NU", lat.NU); I("_NV", lat.NV); F("_Y0", lat.s0); F("_Dy", lat.dy);
            V("_Sock", new Vector4(lat.yc, lat.zc, lat.rho, lat.sc));
            F("_KSoft", P.kSoft); F("_KDiag", P.kDiag); F("_KComp", P.kComp); F("_KCs", P.kCs);
            F("_KLeash", P.kLeash); F("_Slip", P.slip); F("_KFar", P.kFar); F("_H0", P.h0); F("_H1", P.h1);
            F("_KRel", P.kRel); F("_RelLeash", 0f); F("_Omega", P.omega); F("_PinRows", P.pinRows); F("_PinFade", P.pinFade);
            F("_PinchR", P.pinchR); F("_Gather", P.gather); F("_Reach", P.reach); F("_ReachU", P.reachU);
            F("_PinchElong", P.pinchElong); F("_GatherAlong", P.gatherAlong);
            F("_Jam", P.jam); F("_Fold", P.fold); F("_OrderH0", P.orderH0); F("_OrderH1", P.orderH1);
            F("_JamH0", P.jamH0); F("_JamH1", P.jamH1);
            F("_Press", P.press); F("_PressH0", P.pressH0); F("_PressH1", P.pressH1);
            F("_DragK", P.dragK); V("_DragU", Vector4.zero); F("_TopPinY", topPinY);
            V("_Lock", new Vector4(P.lockU, P.lockV, P.lockD, 0)); V("_Shrink", new Vector4(P.shrinkU, P.shrinkV, P.shrinkD, 0));
            V("_Floor", floor);
            F("_RelBins", RelBins); F("_OtherGap", 0.0015f); F("_MaxStep", 0.0015f);
        }

        /// (Re)computes the rest tension from the parameters and puts both legs to rest.
        public void Rebuild()
        {
            PushParams();
            foreach (var L in legs)
            {
                cs.SetTexture(kInit, idRest, L.rest); cs.SetBuffer(kInit, idAxis, L.axis); cs.SetTexture(kInit, idOut, L.f0);
                cs.SetTexture(kInit, idOut2, L.l1); cs.SetTexture(kInit, idOut3, L.l2);
                cs.Dispatch(kInit, gx, gy, 1);
                ComputeGrip(L, null);
                Sleep(L);
            }
        }

        void Sleep(Leg L)
        {
            PushParams();
            cs.SetTexture(kReset, idRest, L.rest); cs.SetTexture(kReset, idOut, L.cur); cs.SetTexture(kReset, idOut2, L.prev);
            cs.SetTexture(kReset, idOut3, L.pred);                           // at rest the prediction is the rest state, in any mode
            cs.Dispatch(kReset, gx, gy, 1);
            L.awake = false; L.held = false; L.freeLeft = 0; L.queue.Clear(); L.give = Vector3.zero;
            ResolveNow(L);
        }

        void ResolveNow(Leg L)
        {
            PushParams();
            cs.SetTexture(kResolve, idRest, L.rest); cs.SetTexture(kResolve, idX, L.cur);
            cs.SetTexture(kResolve, idOutDisp, L.disp); cs.SetTexture(kResolve, idOutTens, L.tens); cs.SetTexture(kResolve, idOutNrm, L.nrm);
            cs.Dispatch(kResolve, gx, gy, 1);
            L.tens.GenerateMips(); L.nrm.GenerateMips();
            L.moved = true;
        }

        /// Motion vectors: brings the 'previous frame' copy of the displacement up to what was last drawn. Called at the
        /// start of every Flush (before this frame's substeps are resolved) and by the owner on frames without a Flush.
        public void SyncPrev()
        {
            foreach (var L in legs)
                if (L.moved) { Graphics.CopyTexture(L.disp, L.dispPrev); L.moved = false; }
        }
        public int lastFlushFrame = -1;

        public bool Awake(int side) => legs[ClothLattice.Leg(side)].awake;
        public bool Held(int side) => legs[ClothLattice.Leg(side)].held;
        public bool AnyAwake => legs[0].awake || legs[1].awake;
        public Texture Disp(int side) => legs[ClothLattice.Leg(side)].disp;
        public Texture DispPrev(int side) => legs[ClothLattice.Leg(side)].dispPrev;
        public Texture Tens(int side) => legs[ClothLattice.Leg(side)].tens;
        public Texture Nrm(int side) => legs[ClothLattice.Leg(side)].nrm;
        public RenderTexture StateTexture(int side) => legs[ClothLattice.Leg(side)].cur;
        /// how far the ankle band has given toward the hand (rest space)
        public Vector3 Give(int side) => legs[ClothLattice.Leg(side)].give;
        public float Free(int side) => legs[ClothLattice.Leg(side)].free;

        /// The hand pinches the fabric at node (j, i); returns the grab point (rest space). dmg: the leg's damage map (holes,
        /// ladders) - the fingers hold only fabric joined to the grab through intact knit.
        public Vector3 BeginGrab(int side, int j, int i, Texture dmg = null)
        {
            var L = legs[ClothLattice.Leg(side)];
            if (L.awake && !L.held && L.queue.Count == 0) Sleep(L);          // a new pull starts from the worn state
            L.pinchC = lat.Node(ClothLattice.Leg(side), j, i); L.gi = i; L.gj = j;
            L.grabTheta = i * (2f * Mathf.PI / lat.NU);
            ComputeGrip(L, dmg);
            L.awake = true; L.held = true; L.freeLeft = 0;
            if (L.queue.Count == 0) L.predHeld = true;                     // still at rest: the stored prediction holds in any mode
            return L.pinchC;
        }

        public void EndGrab(int side)
        {
            var L = legs[ClothLattice.Leg(side)];
            if (!L.held) return;
            L.held = false; L.freeLeft = Mathf.CeilToInt(P.sleepAfter * P.subRate);
        }

        /// Queues one substep with the hand holding the pinched patch at A (rest space).
        /// pressScale: 1 while the hand holds the fabric ON the leg (gathered fabric is pressed onto the skin: ClothParams.press),
        /// 0 once it has drawn it off into a tent (which stands by its threads)
        /// dragU: the hand's drag over the skin so far - arc round the tube (m), along the wale (m), its fall-off length (m; 0 = none):
        /// the fabric round the pinch goes along with it (DragField)
        public void Step(int side, Vector3 A, float gatherOverride = 0f, float pinchROverride = 0f, float relLeash = 0f, float dampOverride = -1f, float pressScale = 1f, Vector3 dragU = default, float gatherAlongOverride = -1f)
        {
            var L = legs[ClothLattice.Leg(side)];
            // the fingers close on the fabric as they start to pull (no dimple at the mere touch)
            float k = Mathf.SmoothStep(0f, 1f, (A - L.pinchC).magnitude / 0.012f);
            // the ankle band gives toward the hand when the fabric is grabbed within ~7 cm above it (sideways, a little down)
            float wg = Mathf.Clamp01(1f - (L.gj - (P.pinRows + P.pinHold + P.ankleRows)) / 30f);
            Vector3 D = A - L.pinchC; D.y = Mathf.Min(D.y, 0f) * 0.3f;
            Vector3 target = Vector3.ClampMagnitude(D * (P.ankleGive * wg), P.ankleGiveMax);
            L.give += (target - L.give) * (1f - Mathf.Exp(-(1f / P.subRate) / 0.03f));
            L.free += (P.ankleFree * wg * k - L.free) * (1f - Mathf.Exp(-(1f / P.subRate) / 0.03f));
            if (L.held && L.queue.Count < P.maxSubsteps) L.queue.Add(new Sub { A = A, give = L.give, held = true, gather = Mathf.Lerp(1f, gatherOverride > 0f ? gatherOverride : P.gather, k), free = L.free, pinchR = pinchROverride > 0f ? pinchROverride : P.pinchR, relLeash = relLeash, damp = dampOverride, press = P.press * pressScale, dragU = dragU, gatherAlong = Mathf.Lerp(1f, gatherAlongOverride >= 0f ? gatherAlongOverride : P.gatherAlong, k) });
        }

        /// Queues one substep of a released leg (it is drawn back to the worn state, then sleeps).
        public void StepFree(int side)
        {
            var L = legs[ClothLattice.Leg(side)];
            if (!L.awake || L.held || L.freeLeft <= 0) return;
            L.give *= Mathf.Exp(-(1f / P.subRate) / 0.05f);
            L.free *= Mathf.Exp(-(1f / P.subRate) / 0.06f);                 // (the band settles back onto the skin, no snap)
            // (let go, nylon snaps back onto the leg within a frame or two - the original's sails are 90 % gone in 2 frames, ours
            //  took 4 and bulged into a dome on the way, review round 10: a hard pull back for the first 60 ms)
            int age = Mathf.CeilToInt(P.sleepAfter * P.subRate) - L.freeLeft;
            float kR = age < 0.06f * P.subRate ? Mathf.Max(P.kRel, 0.012f) : P.kRel;          // (0.025 threw the 8.05 s dome)
            if (L.queue.Count < P.maxSubsteps) L.queue.Add(new Sub { held = false, give = L.give, gather = P.gather, free = L.free, pinchR = P.pinchR, kRel = kR, press = P.press });
            L.freeLeft--;
        }

        /// Queues one substep of LETTING GO (TightsSim, Pull.State.Recoil): every node's way from its worn position is scaled by r
        /// (< 1) - no springs, no momentum, no hand: the pulled shape goes home whole. (Run dynamically - springs, the bunched
        /// patch opening in the air, a leash - the sail's sheet snapped onto the patch within 8 ms and the patch stood off the
        /// leg as a crumpled star of spikes for ~45 ms, at every release: review 14 at 13.27 / 27.97 / 30.33 s.)
        public void StepRecoil(int side, float r)
        {
            var L = legs[ClothLattice.Leg(side)];
            if (!L.held || L.queue.Count >= P.maxSubsteps) return;
            L.give *= Mathf.Exp(-(1f / P.subRate) / 0.05f);
            L.free *= Mathf.Exp(-(1f / P.subRate) / 0.06f);
            L.queue.Add(new Sub { held = false, kin = true, give = L.give, gather = P.gather, free = L.free, pinchR = P.pinchR, kRel = Mathf.Clamp01(1f - r), press = 0f });
        }

        /// Runs the queued substeps of both legs and refreshes their textures.
        public int Flush()
        {
            int total = 0;
            SyncPrev(); lastFlushFrame = Time.frameCount;
            cmd.Clear();
            PushParams(cmd);
            bool any = false;
            foreach (var L in legs)
            {
                if (L.queue.Count == 0) continue;
                any = true; total += L.queue.Count;
                cmd.SetComputeTextureParam(cs, kPredict, idPinMask, L.pinMask); cmd.SetComputeTextureParam(cs, kFinish, idPinMask, L.pinMask);
                cmd.SetComputeTextureParam(cs, kSprings, idF0, L.f0); cmd.SetComputeTextureParam(cs, kSprings, idL1, L.l1);
                cmd.SetComputeTextureParam(cs, kSprings, idL2, L.l2);
                cmd.SetComputeTextureParam(cs, kFinish, idRest, L.rest); cmd.SetComputeTextureParam(cs, kFinish, idL1, L.l1);
                cmd.SetComputeTextureParam(cs, kFinish, idZTex, L.ztex); cmd.SetComputeTextureParam(cs, kFinish, idGrip, L.grip);
                var O = legs[L == legs[0] ? 1 : 0];                          // the other leg
                cmd.SetComputeTextureParam(cs, kFinish, idORest, O.rest); cmd.SetComputeBufferParam(cs, kFinish, idOAxis, O.axis);
                cmd.SetComputeBufferParam(cs, kFinish, idRel, rel); cmd.SetComputeIntParam(cs, idRelBase, L == legs[0] ? 0 : RelBins);
                cmd.SetComputeBufferParam(cs, kFinish, idAxis, L.axis);
                cmd.SetComputeTextureParam(cs, kPredict, idRest, L.rest); cmd.SetComputeBufferParam(cs, kPredict, idAxis, L.axis);   // (PinRadial)
                cmd.SetComputeVectorParam(cs, idPinchC, L.pinchC); cmd.SetComputeFloatParam(cs, idGrabTheta, L.grabTheta);
                cmd.SetComputeIntParam(cs, idGrabI, L.gi); cmd.SetComputeIntParam(cs, idGrabJ, L.gj);
                foreach (var q in L.queue)
                {
                    cmd.SetComputeFloatParam(cs, idHeld, q.held ? 1f : 0f);
                    cmd.SetComputeFloatParam(cs, idDamp, q.held ? (q.damp >= 0f ? q.damp : P.damp) : q.kin ? 0f : P.dampRel);
                    cmd.SetComputeFloatParam(cs, idOmega, q.kin ? 0f : P.omega);
                    cmd.SetComputeFloatParam(cs, idKRel, q.held ? P.kRel : q.kRel);
                    cmd.SetComputeFloatParam(cs, idRelLeash, q.held ? q.relLeash : 0f);
                    cmd.SetComputeVectorParam(cs, idPinchA, q.A);
                    cmd.SetComputeVectorParam(cs, idPinGive, new Vector4(q.give.x, q.give.y, q.give.z, q.free));
                    cmd.SetComputeFloatParam(cs, idGather, q.gather);
                    cmd.SetComputeFloatParam(cs, idGatherAlong, q.gatherAlong);
                    cmd.SetComputeFloatParam(cs, idPinchRad, q.pinchR);
                    cmd.SetComputeFloatParam(cs, idPress, q.press);
                    cmd.SetComputeVectorParam(cs, idDragU, q.held ? (Vector4)q.dragU : Vector4.zero);
                    if (q.held != L.predHeld)
                    {   // grabbed or released since the prediction was made: redo it with this substep's leash
                        cmd.SetComputeTextureParam(cs, kPredict, idX, L.cur); cmd.SetComputeTextureParam(cs, kPredict, idXp, L.prev);
                        cmd.SetComputeTextureParam(cs, kPredict, idOut, L.pred);
                        cmd.DispatchCompute(cs, kPredict, gx, gy, 1);
                        L.predHeld = q.held;
                    }
                    cmd.SetComputeTextureParam(cs, kSprings, idP, L.pred); cmd.SetComputeTextureParam(cs, kSprings, idOut, L.tmp);
                    cmd.DispatchCompute(cs, kSprings, gx, gy, 1);
                    cmd.SetComputeTextureParam(cs, kFinish, idY, L.tmp); cmd.SetComputeTextureParam(cs, kFinish, idX, L.cur);
                    cmd.SetComputeTextureParam(cs, kFinish, idOut, L.prev); cmd.SetComputeTextureParam(cs, kFinish, idOut2, L.pred);
                    cmd.DispatchCompute(cs, kFinish, gx, gy, 1);
                    var t = L.cur; L.cur = L.prev; L.prev = t;             // the new positions were written over the previous ones
                }
                L.queue.Clear();
                cmd.SetComputeTextureParam(cs, kResolve, idRest, L.rest); cmd.SetComputeTextureParam(cs, kResolve, idX, L.cur);
                cmd.SetComputeTextureParam(cs, kResolve, idOutDisp, L.disp); cmd.SetComputeTextureParam(cs, kResolve, idOutTens, L.tens);
                cmd.SetComputeTextureParam(cs, kResolve, idOutNrm, L.nrm);
                cmd.DispatchCompute(cs, kResolve, gx, gy, 1);
                cmd.GenerateMips(L.tens); cmd.GenerateMips(L.nrm);
                L.moved = true;
            }
            if (any) Graphics.ExecuteCommandBuffer(cmd);
            foreach (var L in legs) if (L.awake && !L.held && L.freeLeft <= 0) Sleep(L);
            return total;
        }

        /// Blocking read of a leg's node positions (x, y, z, height above the leg) — tests / diagnostics only.
        public float[] ReadState(int side)
        {
            var req = AsyncGPUReadback.Request(StateTexture(side), 0, TextureFormat.RGBAFloat);
            req.WaitForCompletion();
            return req.GetData<float>().ToArray();
        }

        public void Dispose()
        {
            foreach (var L in legs)
            {
                if (L == null) continue;
                if (L.rest) { if (Application.isPlaying) UnityEngine.Object.Destroy(L.rest); else UnityEngine.Object.DestroyImmediate(L.rest); }
                if (L.pinMask) { if (Application.isPlaying) UnityEngine.Object.Destroy(L.pinMask); else UnityEngine.Object.DestroyImmediate(L.pinMask); }
                if (L.ztex) { if (Application.isPlaying) UnityEngine.Object.Destroy(L.ztex); else UnityEngine.Object.DestroyImmediate(L.ztex); }
                L.axis?.Release();
                foreach (var rt in new[] { L.f0, L.l1, L.l2, L.disp, L.dispPrev, L.tens, L.nrm, L.cur, L.prev, L.pred, L.tmp, L.grip, L.gripTmp }) if (rt) rt.Release();
            }
            rel?.Release();
            cmd.Release();
        }
    }
}
