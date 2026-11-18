// SHEER — tear engine (port of blender/sheer_damage.py). Holes, ladders ("runs"), snags and permanent
// stretch marks evolving in time, per leg. Rasterised on the GPU (DamageRaster.compute) into a UV-space
// texture: R = hole signed distance, G = ladder-band signed distance, B = ladder age, A = 1 - bagging.
// u = angle around the leg (0..1, 0 = back), z = height on the leg (m); below the bend's top (~11 cm, ClothLattice) z runs
// on down each wale round the ankle and along the foot (arc length), so the stocking is one map from the toes to the hem.
// The texture covers z from ZMin to ZMin + 1 m.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace Sheer
{
    public class Hole
    {
        public float u, z, rxT, ryT, rx0 = 0.0005f, ry0 = 0.0007f, rx, ry, angle, rough, seed, t, dur, creep, creepDur;
        // outline: skew = egg / teardrop (> 0 narrower toward the top), pw = superellipse power (2 round .. 4 boxy),
        // cut = flat side at |cut| x ry above (> 0) / below (< 0) the centre; holes of one group flow into each other,
        // different groups always keep a strap of fabric between them
        public float skew, pw = 2f, cut; public int group;
        public float grow0;                                       // (GrowNear: its size before a pull worked it bigger)
        public bool done;
        public bool mending; public float m0x, m0y;              // (Mend: the size it shrinks from)

        public bool Update(float dt)
        {
            if (done) return false;
            t += dt;
            float k = SheerMath.EaseOutBack(t / dur);
            float c = 1f + creep * SheerMath.EaseOutCubic(Mathf.Max(0f, t - dur) / creepDur);
            rx = (rx0 + (rxT - rx0) * k) * c;
            ry = (ry0 + (ryT - ry0) * k) * c;
            if (t >= dur + creepDur) done = true;
            return true;
        }
    }

    public class RunEnd { public float speed, limit, tau, acc, next, jerk, fan; public bool joinTried; }   // fan: length of the frayed end (m)

    public enum HoleKind { Round, Egg, Pin, Moon, Tooth, Slit, Bead, Double }

    public class Run
    {
        public float u, z0, lo, hi, hw, hwT, age, ageT, seed, wobble, taper;
        public bool capLogged;
        public RunEnd up = new RunEnd(), dn = new RunEnd();
        public bool holes = true, pre, done, fast;      // fast: a burst's ladder (opens within a couple of frames)
        public bool mending; public float mlo, mhi, mhw;        // (Mend: what it shrinks from)
    }

    public class Mark { public float u, z, radius, s, sT, t; public bool done; public bool mending; public float m0; }

    public static class SheerMath
    {
        public static float EaseOutBack(float x)
        {
            x = Mathf.Clamp01(x); const float c1 = 1.4f, c3 = c1 + 1f;
            return 1f + c3 * Mathf.Pow(x - 1f, 3) + c1 * Mathf.Pow(x - 1f, 2);
        }
        public static float EaseOutCubic(float x) { x = Mathf.Clamp01(x); return 1f - Mathf.Pow(1f - x, 3); }
        public static float WrapU(float d) => d - Mathf.Floor(d + 0.5f);
        public static float Smooth(float e0, float e1, float x) { float t = Mathf.Clamp01((x - e0) / (e1 - e0)); return t * t * (3 - 2 * t); }
    }

    public class SheerDamage
    {
        public const float RANGE = 0.012f;
        public const int TexW = 1024, TexH = 2048;
        public readonly List<Hole> holes = new List<Hole>();
        public readonly List<Run> runs = new List<Run>();
        public readonly List<Mark> marks = new List<Mark>();
        public bool dirty = true;
        public float zipSpeed;
        public float runTendency = 1f, holeSize = 1f, topZ = 0.665f, cmin;   // runs stop (and fray) a few cm below the skirt's hem
        /// the damage maps' lowest z (the sole's wales end ~20 cm below the bend's top): the textures cover ZMin .. ZMin + 1 m
        public const float ZMin = -0.21f;
        readonly Func<float, float> circ, toeZ;
        readonly System.Random rng;

        /// toeZatU: where the reinforced toe starts on the wale at u (z) - ladders run down the leg, over the ankle and along
        /// the foot, and stop there
        public SheerDamage(Func<float, float> circumferenceAtHeight, int seed, float cmin, Func<float, float> toeZatU)
        {
            circ = circumferenceAtHeight; rng = new System.Random(seed); this.cmin = cmin; toeZ = toeZatU;
        }

        float R(float a, float b) => a + (float)rng.NextDouble() * (b - a);
        float Rnd() => (float)rng.NextDouble();
        public float Circ(float z) => circ(z);
        public float StretchAt(float z) => Mathf.Max(circ(z) / cmin, 1f);
        /// how far a tear opens at height z: (pre-stretch)^1.5, normalised to 1.5 on the thigh (old sqrt law: same there)
        public float OpenScale(float z) => Mathf.Pow(StretchAt(z), 1.5f) / 2.45f;  // (/2.3 merged into a slot, /2.8 gave slits)
        /// How far a tear opens SIDEWAYS, measured on the original: ~36 mm wide round holes on the thigh AND on the knee,
        /// a 22 x 45 mm 'shark tooth' just below the knee, 6-10 mm wide slits on the lower shin (VIEW 02). The knit springs
        /// back by its pre-stretch, which the knee keeps (it bends the fabric) and the shin loses toward the ankle; the
        /// height of a tear comes from the broken courses of the run and does not shrink: on the shin a tear is a tall thin
        /// slit (~8 x 30 mm).
        public const float SlitLen = 1.2f;
        /// the foot (below the ankle, z < ~6 cm along the wales): holes there are middling, a little longer than wide
        public static float FootW(float z) => SheerMath.Smooth(0.11f, 0.06f, z);
        /// how far a tear opens sideways at height z (x the base radius): 1.2 from the knee up, ~0.25 on the lower shin
        public float Wide(float z) => Mathf.Lerp(Mathf.Lerp(0.38f, 1.2f, SheerMath.Smooth(0.17f, 0.46f, z)), 0.65f, FootW(z));   // (0.25: the calf's tears even slits, a 'zipper' - the original's a chain of frayed holes, review 2)
        /// height / width of a tear: round holes on thigh and knee, tall slits on the shin
        public float Slit(float z) => Mathf.Lerp(Mathf.Lerp(3.4f, 1.0f, SheerMath.Smooth(0.25f, 1.0f, Wide(z))), 1.5f, FootW(z));
        /// how far ladders run from a tear at height z: on the shin they stop after a few centimetres
        public float RunReach(float z) => Mathf.Lerp(Mathf.Lerp(0.25f, 1f, SheerMath.Smooth(0.17f, 0.46f, z)), 0.40f, FootW(z));

        /// how far up / down a ladder on the wale at u may run: below the hem; down the leg, over the ankle and along the
        /// foot to the reinforced toe (user, 2026-11-16: the stocking is one tube - a ladder from the shin runs on onto the foot)
        public float TopOf(float z) => topZ;
        public float BottomOf(float u) => toeZ != null ? toeZ(u) + 0.003f : ZMin + 0.01f;

        int groups;
        public int NewGroup() => ++groups;

        public Hole AddHole(float u, float z, float rx, float ry, float dur = 0.16f, float creep = 0.12f, float creepDur = 1.2f,
                            int group = -1, float skew = 0f, float pw = 2f, float cut = 0f, float rough = -1f)
        {
            var h = new Hole { u = u, z = z, rxT = rx, ryT = ry, angle = R(-0.32f, 0.32f), rough = rough >= 0 ? rough : R(0.05f, 0.13f), seed = Rnd(),
                               dur = dur, creep = creep, creepDur = creepDur, group = group >= 0 ? group : NewGroup(), skew = skew, pw = pw, cut = cut };
            h.rx = h.rx0; h.ry = h.ry0;
            holes.Add(h); dirty = true; return h;
        }

        /// Distance (m, first order) from a point to the final outline of the holes of other groups.
        float FinalSdAt(float u, float z, int exceptGroup)
        {
            float best = 1f, C = circ(z);
            foreach (var h in holes)
            {
                if (h.group == exceptGroup) continue;
                float rx = h.rxT * (1f + h.creep) * (1f + 0.5f * Mathf.Abs(h.skew)), ry = h.ryT * (1f + h.creep);
                float dx = SheerMath.WrapU(u - h.u) * C, dy = z - h.z;
                float k = Mathf.Sqrt(dx * dx / (rx * rx) + dy * dy / (ry * ry));
                float g = Mathf.Sqrt(dx * dx / (rx * rx * rx * rx) + dy * dy / (ry * ry * ry * ry)) / Mathf.Max(k, 1e-4f);
                best = Mathf.Min(best, (k - 1f) / Mathf.Max(g, 1e-3f));
            }
            return best;
        }

        /// Shrinks a planned hole until a strap of fabric is left between it and every other tear. False: no room.
        bool Fit(float u, float z, ref float rx, ref float ry, int group, float strap, float margin = 1.3f, float minR = 0.0011f)
        {
            float C = circ(z);
            for (int it = 0; it < 7; it++)
            {
                float worst = FinalSdAt(u, z, group);
                for (int k = 0; k < 12; k++)
                {
                    float a = k * (Mathf.PI / 6f);
                    worst = Mathf.Min(worst, FinalSdAt(u + Mathf.Cos(a) * rx * margin / C, z + Mathf.Sin(a) * ry * margin, group));
                }
                if (worst >= strap) return true;
                rx *= 0.8f; ry *= 0.8f;
                if (Mathf.Min(rx, ry) < minR) return false;
            }
            return false;
        }

        /// A tear of the given kind (measured on the original at 11 s: round / egg-shaped big holes, 'bowling pins' with a
        /// neck, half-moons behind a strap, pointed 'shark teeth' at the end of a ladder, tiny slits and beads at the
        /// junctions). r = half width of a round hole of that size; dir (+1 up / -1 down the leg) = where its narrow /
        /// necked end points, or which way a half-moon bulges. Returns null when no room is left for it.
        public Hole AddShaped(HoleKind kind, float u, float z, float r, float dir, float dur, float creep, int group = -1,
                              float strap = 0.0018f)
        {
            float slit = Slit(z), rx, ry, skew = 0f, pw = 2f, cut = 0f, rough = R(0.05f, 0.10f);
            switch (kind)
            {
                case HoleKind.Egg: rx = r * R(0.8f, 0.95f); ry = rx * slit * R(1.2f, 1.45f); skew = dir * R(0.10f, 0.26f); pw = R(2.0f, 2.25f); break;
                case HoleKind.Pin: rx = r * R(0.62f, 0.8f); ry = rx * Mathf.Max(slit, 1.25f) * R(1.35f, 1.7f); skew = dir * R(0.1f, 0.25f); pw = R(2.1f, 2.5f); break;
                case HoleKind.Moon: rx = r * R(1.0f, 1.3f); ry = rx * R(0.62f, 0.85f); cut = -dir * R(0.4f, 0.7f); pw = R(2.0f, 2.3f); skew = R(-0.25f, 0.25f); rough = R(0.1f, 0.18f); break;
                case HoleKind.Tooth: rx = r * R(0.6f, 0.8f); ry = rx * Mathf.Max(slit, 1.2f) * R(1.4f, 1.8f); skew = dir * R(0.28f, 0.46f); pw = R(2.0f, 2.2f); rough = R(0.06f, 0.11f); break;
                case HoleKind.Slit: rx = r * R(1.2f, 2.0f); ry = r * R(0.45f, 0.7f); pw = R(2.0f, 2.4f); skew = R(-0.3f, 0.3f); rough = R(0.1f, 0.2f); break;
                case HoleKind.Bead: rx = r * R(0.7f, 0.9f); ry = r * R(1.0f, 1.4f); pw = R(2.0f, 2.3f); skew = R(-0.3f, 0.3f); rough = R(0.1f, 0.2f); break;
                case HoleKind.Double: rx = r * R(0.8f, 0.95f); ry = rx * slit * R(0.95f, 1.2f); skew = R(-0.15f, 0.15f); pw = R(2.0f, 2.2f); break;
                default:
                    rx = r; ry = r * slit * R(0.85f, 1.12f); skew = R(-0.14f, 0.14f); pw = R(2.0f, 2.25f);
                    if (Rnd() < 0.3f) cut = -dir * R(0.62f, 0.85f);             // slightly flattened on one side
                    break;
            }
            ry = Mathf.Min(ry, rx * 4.2f);
            int g = group >= 0 ? group : NewGroup();
            if (!Fit(u, z, ref rx, ref ry, g, strap, 1.3f + (kind == HoleKind.Pin || kind == HoleKind.Double ? 0.25f : 0f))) return null;
            var h = AddHole(u, z, rx, ry, dur, creep, 1.2f, g, skew, pw, cut, rough);
            if (kind == HoleKind.Double)
            {   // a second lobe above / below and to one side, run into the first: a boot or a figure of eight with a tongue of
                // fabric left between the two (the original at 23 s)
                float sx = Rnd() < 0.5f ? -1f : 1f, r2 = rx * R(0.62f, 0.85f);
                float z2 = z + dir * (ry * R(0.75f, 1.0f) + r2 * R(0.45f, 0.7f)), u2 = u + sx * rx * R(0.25f, 0.6f) / circ(z2);
                var n2 = AddHole(u2, z2, r2, r2 * Mathf.Max(slit, 1.0f) * R(1.0f, 1.5f), dur * R(1.0f, 1.3f), creep, 1.2f, g, R(-0.2f, 0.2f), 2.1f, 0f, R(0.04f, 0.08f));
                n2.angle = sx * dir * R(0.15f, 0.5f);
            }
            if (kind == HoleKind.Pin)
            {   // the neck: a smaller opening that runs into the body
                float rn = rx * R(0.42f, 0.56f), zn = z + dir * (ry * R(0.92f, 1.05f) + rn * 0.55f);
                var n = AddHole(u + R(-0.15f, 0.15f) * rx / circ(zn), zn, rn, rn * R(1.0f, 1.35f), dur * R(1.0f, 1.4f), creep, 1.2f, g, 0f, 2.2f, 0f, R(0.03f, 0.07f));
                n.angle = 0f;
            }
            return h;
        }

        /// Small holes clinging to a big one behind straps of gathered yarn: a half-moon above / below it (flat side toward
        /// the big hole), sometimes a bead or a slit beside the strap, sometimes a tiny slit beyond.
        public void Cluster(Hole main, float side)
        {
            float C = circ(main.z), big = main.rxT, strap = R(0.0018f, 0.0034f);
            float r1 = big * R(0.3f, 0.6f);
            if (r1 < 0.0016f) return;
            float z1 = main.z + side * (main.ryT * (1f + main.creep) + strap + r1 * 0.45f);
            float u1 = main.u + R(-0.35f, 0.35f) * big / C;
            var m = AddShaped(HoleKind.Moon, u1, z1, r1, side, R(0.05f, 0.1f), R(0.05f, 0.15f), -1, strap);
            // (less often, and mostly slits: beads at 0.75 x 0.8 strung small round 'bubbles' round every hole, reviews 7 / 8 -
            //  the original's extra holes are fewer and of varied shapes)
            if (Rnd() < 0.5f)
            {   // a bead / slit where the strap meets the side of the big hole
                float a = Mathf.Deg2Rad * R(28f, 62f), sx = Rnd() < 0.5f ? -1f : 1f, rs = Mathf.Max(big * R(0.1f, 0.22f), 0.0013f);
                float bu = main.u + sx * (big + rs + strap) * Mathf.Sin(a) / C, bz = main.z + side * (main.ryT * (1f + main.creep) + rs + strap) * Mathf.Cos(a);
                AddShaped(Rnd() < 0.35f ? HoleKind.Bead : HoleKind.Slit, bu, bz, rs, side, R(0.05f, 0.1f), R(0.05f, 0.15f), -1, R(0.0012f, 0.0022f));
            }
            if (m != null && Rnd() < 0.25f)
            {   // a tiny slit beyond the half-moon
                float rs = R(0.0012f, 0.0022f);
                AddShaped(HoleKind.Slit, m.u + R(-0.4f, 0.4f) * m.rxT / C, m.z + side * (m.ryT * 1.15f + R(0.002f, 0.004f) + rs), rs, side, R(0.05f, 0.1f), 0.05f, -1, 0.0012f);
            }
        }

        public Run AddRun(float u, float z, float hw0 = 0.0003f, float hw = -1f, float age0 = 0.15f, float age = 1f,
                          float speedUp = -1f, float speedDn = -1f, float maxUp = -1f, float maxDn = -1f,
                          bool runHoles = true, bool pre = false, float jerk = 1f)
        {
            float tend = runTendency;
            var r = new Run { u = u, z0 = z, lo = z - 0.0008f, hi = z + 0.0008f, hw = hw0, hwT = hw >= 0 ? hw : R(0.003f, 0.0045f),
                              age = age0, ageT = age, seed = Rnd(), wobble = R(0.0002f, 0.0006f), taper = pre ? R(0.004f, 0.007f) : R(0.012f, 0.03f),
                              holes = runHoles, pre = pre };
            float mu = (maxUp >= 0 ? maxUp : R(0.10f, 0.34f)) * tend;
            float md = (maxDn >= 0 ? maxDn : R(0.10f, 0.34f)) * tend;
            // the ends of a ladder fray: the wales stop running one by one (the original: a flame of fine streaks above the
            // top hole of a series, two or three long 'comet tails' below the last one)
            // (frayed ends 3 - 6 cm: at 6 - 11 cm above and 3 - 7 below, a ~20 cm ladder was mostly fraying ends - pink
            //  streaks fanning out, 'brush strokes'; the original's bands keep their width between holes and fray in a short
            //  flame above / a few thin tails below, review 14)
            r.up = new RunEnd { speed = speedUp >= 0 ? speedUp : R(0.35f, 0.8f), limit = Mathf.Min(TopOf(z), z + mu), tau = R(0.18f, 0.55f),
                                acc = 0, next = R(0.02f, 0.07f), jerk = jerk, fan = pre ? 0.004f : R(0.03f, 0.06f) };
            r.dn = new RunEnd { speed = speedDn >= 0 ? speedDn : R(0.35f, 0.8f), limit = Mathf.Max(BottomOf(u), z - md), tau = R(0.18f, 0.55f),
                                acc = 0, next = R(0.02f, 0.07f), jerk = jerk, fan = pre ? 0.004f : R(0.03f, 0.06f) };
            if (r.up.limit < z) r.up.speed = 0;
            if (r.dn.limit > z) r.dn.speed = 0;
            runs.Add(r); dirty = true; return r;
        }

        public Mark AddMark(float u, float z, float radius, float strength)
        {
            var m = new Mark { u = u, z = z, radius = radius, sT = strength };
            marks.Add(m); dirty = true; return m;
        }

        /// A held pull beside a hole works its edge loops loose: the nearest hole within 15 mm of the fingers grows by `k`
        /// (relative) - up to 1.8 x the size it was made at (the original: 'pulling near a hole makes it bigger', review 11)
        public void GrowNear(float u, float z, float k)
        {
            Hole best = null; float bsd = 0.015f, C = circ(z);
            foreach (var h in holes)
            {
                if (h.mending) continue;
                float dx = SheerMath.WrapU(u - h.u) * C, dy = z - h.z;
                float q = Mathf.Sqrt(Mathf.Pow(dx / Mathf.Max(h.rx, 1e-5f), 2) + Mathf.Pow(dy / Mathf.Max(h.ry, 1e-5f), 2));
                float sd = (q - 1f) * Mathf.Min(h.rx, h.ry);
                if (sd < bsd) { bsd = sd; best = h; }
            }
            if (best == null || best.rxT < 0.002f) return;
            if (best.grow0 <= 0f) best.grow0 = best.rxT;
            if (best.rxT >= 1.8f * best.grow0) return;
            float g = 1f + k;
            best.rxT *= g; best.ryT *= g; best.rx *= g; best.ry *= g;
            dirty = true;
        }

        public float HoleSdAt(float u, float z)
        {
            float best = 1f, C = circ(z);
            foreach (var h in holes)
            {
                float dx = SheerMath.WrapU(u - h.u) * C, dy = z - h.z;
                float k = Mathf.Sqrt(Mathf.Pow(dx / Mathf.Max(h.rx, 1e-5f), 2) + Mathf.Pow(dy / Mathf.Max(h.ry, 1e-5f), 2));
                best = Mathf.Min(best, (k - 1f) * Mathf.Min(h.rx, h.ry));
            }
            return best;
        }

        /// A pull exceeded the fabric's strength: hole (+ second lobe) and a ladder; new tears follow an existing ladder.
        /// energy (0.2..1): elastic energy released at the tear relative to a full-length pull - the ladders run (and pop
        /// holes) in proportion; a short pinch (the original's opening knee tear) leaves two holes and short ladders.
        public void Burst(float u, float z, float intensity = 1f, Run preRun = null, float energy = 1f)
        {
            energy = Mathf.Clamp(energy, 0.2f, 1f);
            // tears open wider where the knit is more pre-stretched (thigh): the original's thigh holes are ~3x its shin slits
            float st = OpenScale(z);
            float sizeI = holeSize * Mathf.Min(1.6f, 0.8f + intensity * 0.25f), size = sizeI * st;
            float C0 = circ(z), hwJoin = -1f;
            foreach (var run in runs)
            {
                if (run.pre) continue;
                float du = SheerMath.WrapU(u - run.u) * C0;
                // a tear follows a ladder only when the fingers held the fabric ON it (inside its band: the weak line under
                // the hand gives way along itself). Anywhere else the knit fails where it is pulled - between two ladders too
                // (user, 2026-11-16: within 35 mm every new tear, with the row of slits the pull had opened, jumped onto the
                // nearest ladder - so none could ever open between two of them)
                if (Mathf.Abs(du) < run.hwT * 0.8f && run.lo - 0.02f < z && z < run.hi + 0.02f)
                {
                    u = run.u + R(-0.15f, 0.15f) * run.hwT / C0;
                    if (preRun != null && preRun != run) preRun.u = run.u;
                    hwJoin = run.hwT;                       // (one band: no step where this tear's ladder takes over)
                    break;
                }
            }
            // Measured on the original (11 s, thigh): the main hole of a tear is big and round, ~36 x 34 mm, with one to three
            // small holes clinging to its upper / lower rim behind thin bridges of thread; sometimes a second, smaller hole
            // runs into it (a bowling-pin outline). On the shin (little pre-stretch) the same tear is a tall narrow slit.
            float rb = R(0.0100f, 0.0135f) * sizeI, r0 = rb * Wide(z);     // (main holes 28 - 39 mm wide on the thigh; the original's largest: 37)
            bool near = HoleSdAt(u, z) < 0.01f;
            float pick = Rnd(), dir = Rnd() < 0.5f ? 1f : -1f;
            var kind = pick < 0.36f ? HoleKind.Round : pick < 0.60f ? HoleKind.Egg : pick < 0.80f ? HoleKind.Pin : HoleKind.Double;
            // open within a frame (the original's first tear: the pocket in one frame, the holes in the next), then creep
            var main = AddShaped(kind, u, z, r0, dir, R(0.02f, 0.035f), R(0.08f, 0.22f)) ?? AddShaped(HoleKind.Bead, u, z, r0 * 0.4f, dir, R(0.02f, 0.035f), 0.1f);
            // (satellites now and then, on either side: with them nearly always below, every tear was the same bottle with two
            //  small ovals under it, review 11)
            if (main != null)
            {
                if (Rnd() < 0.45f) Cluster(main, dir);
                if (Rnd() < 0.2f) Cluster(main, -dir);
            }
            float tend = runTendency;
            if (preRun != null && !preRun.done)
            {
                preRun.ageT = 1f; preRun.hwT = hwJoin > 0f ? hwJoin : R(0.0095f, 0.013f); preRun.pre = false; preRun.holes = true;
                preRun.up.speed = Mathf.Max(preRun.up.speed, R(4f, 7f)); preRun.dn.speed = Mathf.Max(preRun.dn.speed, R(4f, 7f));
                preRun.fast = true;
                float rr = RunReach(z);
                preRun.up.limit = Mathf.Min(TopOf(z), z + R(0.08f, 0.3f) * tend * energy * rr); preRun.dn.limit = Mathf.Max(BottomOf(preRun.u), z - R(0.08f, 0.3f) * tend * energy * rr);
                preRun.up.jerk = preRun.dn.jerk = energy;
                preRun.up.fan = R(0.03f, 0.06f); preRun.dn.fan = R(0.03f, 0.06f);
                // (and its band tapers toward its ends as a ladder's does: kept at the slit row's 4 - 7 mm it stayed full
                //  width to the last millimetre - a hard rectangle with square ends under the thigh hole, review 4)
                preRun.taper = R(0.015f, 0.035f);
                preRun.holes = true;                             // short ladders still pop a hole (original: knee tear)
                // the row of slits the pull had opened becomes the ladder: it does not shrink back, and one of its slits
                // gives way too (the original at 4 s: a 'pin' between the new thigh hole and the knee's)
                preRun.dn.limit = Mathf.Min(preRun.dn.limit, preRun.lo); preRun.up.limit = Mathf.Max(preRun.up.limit, preRun.hi);
                // (an energetic tear always frays some centimetres up the leg: the flame of streaks above the original's thigh hole)
                if (energy > 0.5f) preRun.up.limit = Mathf.Max(preRun.up.limit, Mathf.Min(TopOf(z), z + R(0.085f, 0.12f)));
                float span = z - preRun.lo;
                if (span > 0.07f)
                {
                    float hz = z - span * R(0.36f, 0.52f), rr2 = preRun.hwT * R(0.7f, 0.95f) * holeSize * Wide(hz);
                    AddShaped(Rnd() < 0.6f ? HoleKind.Pin : HoleKind.Egg, preRun.u, hz, rr2, Rnd() < 0.5f ? 1f : -1f, R(0.06f, 0.1f), R(0.05f, 0.15f), -1, R(0.002f, 0.004f));
                }
            }
            else if (!near || Rnd() < 0.5f)
                AddRun(u, z, hw: hwJoin > 0f ? hwJoin : R(0.0095f, 0.013f), speedUp: R(4f, 7f), speedDn: R(4f, 7f), maxUp: R(0.10f, 0.34f) * Mathf.Max(energy, 0.5f) * RunReach(z),
                       maxDn: R(0.10f, 0.34f) * Mathf.Max(energy, 0.5f) * RunReach(z), jerk: energy).fast = true;   // (longer: the original's holes end up linked by one ladder from the hem to the shin, review 2)
            // a short tear (the original's opening knee pinch): besides the main hole one more gives way a few centimetres
            // down its short ladder (a 'pin' with its tails below the knee)
            if (energy <= 0.4f && main != null && Rnd() < 0.85f)
            {
                float hz = z - (main.ryT + R(0.022f, 0.034f)), rr3 = R(0.0085f, 0.011f) * sizeI * Wide(hz);
                var low = AddShaped(Rnd() < 0.7f ? HoleKind.Pin : HoleKind.Egg, u + R(-0.2f, 0.2f) * rr3 / C0, hz, rr3, -1f, R(0.07f, 0.1f), R(0.08f, 0.18f), -1, R(0.002f, 0.004f));
                if (preRun != null && low != null) preRun.lo = Mathf.Min(preRun.lo, hz - low.ryT - 0.02f);
            }
        }

        /// The ladder that is only starting while the hand holds the fabric taut: a 9 mm row of level slits growing down
        /// the leg from the pinch (the original: bars appearing one after the other for 0.6 - 0.9 s before every tear of a
        /// long pull - 5 cm at the knee, 17 cm from the upper thigh down to the knee's holes).
        // (both ways from the grab, more below: the original's rungs show inside the stretched tent within 0.15 s and creep
        //  down under the pinch - ours started at the pinch's gathered tip and ran down only, visible at 0.55 s, review
        //  round 8)
        public Run PreRun(float u, float z, float len = 0.055f, float speed = 0.10f, bool up = false) =>
            AddRun(u, z, 0.0003f, 0.0045f, 0.19f, 0.22f, speed * 0.15f, speed, len * 0.15f, len, false, true, 0f);   // (age 0.19: the slits show at once - at 0.14 they took ~0.15 s to come up, review 5; up only a little - the original's column of slits runs DOWN from the pinch, ours grew up as well: a zipper round the fold, review 7)

        // ---- MENDING (the Studio's Repair): every hole, ladder and stretch mark there now shrinks away together over a
        // moment - holes close, ladders zip back to where they started - then they are gone. Tears made meanwhile stay.
        public void BeginMend()
        {
            foreach (var h in holes) { h.mending = true; h.done = true; h.m0x = h.rx; h.m0y = h.ry; }
            foreach (var r in runs) { r.mending = true; r.done = true; r.mlo = r.lo; r.mhi = r.hi; r.mhw = r.hw; }
            foreach (var m in marks) { m.mending = true; m.done = true; m.m0 = m.s; }
            dirty = true;
        }
        public void ApplyMend(float k)
        {
            foreach (var h in holes) if (h.mending) { h.rx = h.m0x * k; h.ry = h.m0y * k; }
            foreach (var r in runs) if (r.mending) { r.lo = r.z0 - (r.z0 - r.mlo) * k; r.hi = r.z0 + (r.mhi - r.z0) * k; r.hw = r.mhw * k; }
            foreach (var m in marks) if (m.mending) m.s = m.m0 * k;
            dirty = true;
        }
        public void EndMend() { holes.RemoveAll(h => h.mending); runs.RemoveAll(r => r.mending); marks.RemoveAll(m => m.mending); dirty = true; }

        public void Snag(float u, float z)
        {
            AddHole(u, z, R(0.0008f, 0.0014f), R(0.0012f, 0.002f), 0.1f, 0.3f, 2.0f);
            AddRun(u, z, 0.0003f, R(0.0022f, 0.0042f), 0.1f, 1f, R(0.15f, 0.45f), R(0.2f, 0.5f), R(0.05f, 0.35f), R(0.08f, 0.4f), Rnd() < 0.25f);
        }

        /// LADDERS JOIN UP: a ladder that stops short of another one in the same wales - within 8 cm of it - runs on into
        /// it. The stretch of whole knit between two ladders on one column carries the tension of both and gives way; the
        /// original's tears, made one after another along the same wales, end up as ONE ladder from the hem to the shin.
        /// (Ours stopped wherever each run's own length ran out: the knee's ladder 6 cm short of the hem tear's, the same
        /// column broken into separate patches, review 14.) Only along the column - a tear beside a ladder still does not
        /// jump onto it (user, 2026-11-16).
        void JoinAhead(Run run, RunEnd end, float sign)
        {
            float at = sign > 0 ? run.hi : run.lo, C = circ(at);
            Run best = null; float bg = 0.08f;
            foreach (var o in runs)
            {
                if (o == run || o.pre || o.mending) continue;
                if (Mathf.Abs(SheerMath.WrapU(o.u - run.u)) * C > 0.6f * Mathf.Max(o.hwT, run.hwT)) continue;
                float gap = sign > 0 ? o.lo - at : at - o.hi;
                if (gap > 0f && gap < bg) { bg = gap; best = o; }
            }
            if (best == null) return;
            // (into the other band, overlapping it by both bands' tapers: each narrows only where the other is full width,
            //  and neither end at the junction frays - the other's frayed end, left as it was, cut the joined band off on a
            //  straight line across it: a pale box with a hard bottom edge under the hem tear at 21 s)
            float ov = run.taper + best.taper + 0.004f;
            end.limit = sign > 0 ? Mathf.Min(TopOf(at), Mathf.Min(best.lo + ov, best.hi)) : Mathf.Max(BottomOf(run.u), Mathf.Max(best.hi - ov, best.lo));
            end.speed = R(0.6f, 1.2f); end.tau = R(0.3f, 0.6f); end.fan = 0.006f;
            if (sign > 0) best.dn.fan = 0.006f; else best.up.fan = 0.006f;
            run.done = false; dirty = true;
        }

        static readonly bool logRuns = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerLogRuns") >= 0;
        float logClock;
        public bool Update(float dt)
        {
            bool changed = false; zipSpeed = 0f;
            if (logRuns && (logClock += dt) >= 0.05f)
            {
                logClock = 0f; var sb = new System.Text.StringBuilder();
                foreach (var r in runs) sb.Append($" [u {r.u:0.000} lo {r.lo:0.000} hi {r.hi:0.000} age {r.age:0.00} pre {(r.pre ? 1 : 0)} hw {r.hw * 1000:0.0} fan {r.up.fan:0.000}/{r.dn.fan:0.000} spd {r.up.speed:0.00}/{r.dn.speed:0.00}]");
                Debug.Log($"[runs] {GetHashCode() % 1000} n={runs.Count}{sb}");
            }
            foreach (var h in holes) changed |= h.Update(dt);
            for (int ri = 0; ri < runs.Count; ri++)
            {
                var run = runs[ri];
                if (run.done) continue;
                changed = true;
                for (int e = 0; e < 2; e++)
                {
                    var end = e == 0 ? run.up : run.dn; float sign = e == 0 ? 1f : -1f;
                    if (end.speed <= 0) continue;
                    float step = end.speed * dt, at;
                    zipSpeed += end.speed;
                    // (no stopping short of another ladder: a cap that held the thigh pull's starting row 12 mm above the knee's
                    //  run left the holes unconnected when it tore - no ladder between them, review round 14's blocker. The X
                    //  and the fan of arcs it was meant to stop came from the slits' pitch, fixed in the shader)
                    if (sign > 0) { run.hi = Mathf.Min(end.limit, run.hi + step); at = run.hi; if (at >= end.limit) end.speed = 0; }
                    else { run.lo = Mathf.Max(end.limit, run.lo - step); at = run.lo; if (at <= end.limit) end.speed = 0; }
                    end.speed *= Mathf.Exp(-dt / end.tau);
                    if (end.jerk > 0 && Rnd() < dt * 2.2f) end.speed += R(0.1f, 0.45f) * end.jerk;
                    if (end.speed < 0.02f) end.speed = 0;
                    if (end.speed == 0 && !run.pre && !end.joinTried) { end.joinTried = true; JoinAhead(run, end, sign); }
                    end.acc += step;
                    if (run.holes && end.acc > end.next)
                    {
                        end.acc = 0f;
                        float st = StretchAt(at);
                        end.next = R(0.05f, 0.1f) / Mathf.Sqrt(st);                 // spacing: distinct holes along a ladder
                        float p = 0.3f * Mathf.Min(st, 2.2f) * runTendency * Mathf.Min(1f, (run.hwT - 0.0015f) / 0.0025f);   // (0.5: holes strung along every ladder like beads, review 12)   // (0.36: by 24 s two big holes where the original has 8 - 10, review 2)
                        if (Rnd() < p)
                        {
                            // behind the frayed end; the last tear before a ladder stops is pointed along it ('shark tooth')
                            float hz = at - sign * (end.fan + R(0.004f, 0.012f)), C = circ(hz);
                            if ((hz - run.z0) * sign > 0.012f)
                            {
                                float rb = run.hwT * R(0.65f, 1.25f) * holeSize, r = rb * Wide(hz);
                                float hu = run.u + R(-0.25f, 0.25f) * run.hwT / C;
                                bool last = end.speed < 0.9f || Mathf.Abs(end.limit - at) < 0.07f;
                                float pk = Rnd();
                                var kind = last && Rnd() < 0.3f ? HoleKind.Tooth : pk < 0.32f ? HoleKind.Round : pk < 0.54f ? HoleKind.Egg : pk < 0.72f ? HoleKind.Pin : pk < 0.87f ? HoleKind.Double : HoleKind.Moon;
                                float dir = kind == HoleKind.Tooth ? sign : Rnd() < 0.5f ? 1f : -1f;
                                var h = AddShaped(kind, hu, hz, kind == HoleKind.Moon ? r * 0.7f : r, dir, R(0.04f, 0.08f), R(0.05f, 0.15f), -1, R(0.002f, 0.004f));
                                if (h != null && kind != HoleKind.Tooth && Rnd() < 0.30f) Cluster(h, Rnd() < 0.5f ? 1f : -1f);   // (0.55: clusters of bubbles, reviews 7 / 8)
                                // a ladder rarely runs on far beyond a tear: often this one was its last, and the band ends
                                // a few centimetres further in its frayed tails (the original at 9.5 s: tails right below
                                // the lowest hole; ours ran on down the whole shin as a ribbon)
                                if (h != null && Rnd() < (hz < 0.44f ? 0.6f : 0.3f))
                                {
                                    float stop = at + sign * (h.ryT + end.fan * R(0.5f, 0.9f));
                                    end.limit = sign > 0 ? Mathf.Min(end.limit, stop) : Mathf.Max(end.limit, stop);
                                }
                            }
                        }
                    }
                }
                // (a tear's run is there within a frame, like its hole: at 30 / s it opened over 2 - 3 frames as a wide pale slab
                //  under a slot, review 11 at 0.27 / 3.33 / 27.7 s - the original's tear is complete in the next frame)
                run.hw += (run.hwT - run.hw) * (1f - Mathf.Exp(-dt * (run.fast ? 90f : run.pre ? 12f : 5f)));
                run.age += (run.ageT - run.age) * (1f - Mathf.Exp(-dt * (run.fast ? 90f : 6f)));
                if (!run.pre && run.up.speed == 0 && run.dn.speed == 0 && Mathf.Abs(run.hw - run.hwT) < 3e-5f && Mathf.Abs(run.age - run.ageT) < 0.01f)
                { run.hw = run.hwT; run.age = run.ageT; run.done = true; }
            }
            foreach (var m in marks)
            {
                if (m.done) continue;
                m.t += dt; m.s = m.sT * SheerMath.EaseOutCubic(m.t / 0.4f);
                if (m.t >= 0.4f) m.done = true;
                changed = true;
            }
            if (changed) dirty = true;
            return changed;
        }
    }
}
