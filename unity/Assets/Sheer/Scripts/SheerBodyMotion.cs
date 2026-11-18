// SHEER — how the character stands and moves: like a girl waiting on her feet - restless, never still, never two mirrored
// legs. An anime 'uchimata' in every pose: the knees turned in and POINTING in (the leg turned about its own axis, the
// kneecaps facing each other), the toes in.
//   NEUTRAL - weight on both legs: knees together and a little bent, or a little apart;
//   LEFT    - weight on the left (+x) leg: it stands straight, the hips go well over it (~5 cm), the right leg relaxes -
//             its knee comes forward and in, in front of the other knee, the leg and its foot turned in;
//   RIGHT   - the same the other way round.
// She changes pose every 3.5 - 7.5 s with a weight shift of about a second; while holding one, every 1 - 3 s she shifts
// around it (a knee, the other, the hips, a foot); every few seconds a fidget runs over it (a knee dipping, the knees
// rubbing past each other, a foot turning on the spot, the hips swaying - smooth noise, never a rhythm); a slow drift runs
// under everything; a big toe - sometimes both - lifts and settles.
// (User, 2026-11-17: 'still way too static / robotic. She needs to move more, both more frequently and with more
//  emphasis ... when resting on one leg more than the other, it needs to be much more pronounced ... knees are bent
//  inward in a sense, but not really pointing inward'. Until then: a pose every 11 - 19 s, hips 2 cm over the standing
//  leg, the relaxed knee 3 cm forward, the knees turned 3 - 14 degrees.)
// While the ORIGINAL's session is replayed (calm) she stands as quietly as in the video, so its presses land where they
// did there. No reflex after tears (the knee flinch at every hole deformed the legs, user 2026-11-16).
// The pose itself - leg sections shifted and turned at hip, knee, ankle and the big toes' joints - is built in TightsSim.
using UnityEngine;

namespace Sheer
{
    [System.Serializable]
    public struct LegPose
    {
        [Tooltip("How far the knee has moved toward the other leg (m), hip and foot in place.")] public float kneeIn;
        [Tooltip("How far the knee has come forward (m) - a bent, relaxed leg.")] public float kneeFwd;
        [Tooltip("Inward turn of the leg about its own axis at the knee (rad): the kneecap faces the other knee.")] public float twist;
        [Tooltip("Toes turned in (rad), the foot turning about the ankle.")] public float footYaw;
        [Tooltip("Big toe lifted (rad) about its joint.")] public float toe;
    }

    [System.Serializable]
    public class SheerBodyMotion
    {
        [Header("Stance")]
        [Tooltip("Toes turned in (rad) of the left (+x) / right foot.")] public float footYawL = 0.18f, footYawR = 0.22f;
        [Tooltip("Hips shifted over the standing leg in the one-leg poses (rad of lean: 0.165 = ~5 cm at the hips).")] public float weightLean = 0.165f;
        [Tooltip("How far the relaxed leg's knee comes forward (m) / in (m) in the one-leg poses.")] public float relaxFwd = 0.062f, relaxIn = 0.030f;
        [Header("Life")]
        [Tooltip("Seconds between changes of pose (random in this range).")] public Vector2 poseEvery = new Vector2(3.5f, 7.5f);
        [Tooltip("Seconds between small shifts within a pose (random in this range).")] public Vector2 shiftEvery = new Vector2(1.2f, 3.2f);
        [Tooltip("Seconds between fidgets (random in this range).")] public Vector2 fidgetEvery = new Vector2(3.5f, 8f);
        [Tooltip("Seconds between big-toe lifts (random in this range).")] public Vector2 toeEvery = new Vector2(3f, 8f);
        public float motionScale = 1f;
        [Tooltip("Tests: she barely moves (small poses, no fidgets).")] public bool calm;
        [Tooltip("The original's session is being replayed (0..1): the weight shifts smaller - its cursor was aimed at legs that " +
                 "stood about where ours stand - but the fidgets and the drift go on: the original never stands still.")]
        public float quiet;
        [Tooltip("The music's tempo and position (SheerAudio).")] public float bpm; public double beatTime;
        public bool toeLifts = true;
        public static bool log = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerLogPose") >= 0;

        [System.NonSerialized] public LegPose L, R;     // this frame's pose
        [System.NonSerialized] public float lean;       // rad: + = hips over the left (+x) leg
        [System.NonSerialized] public int stand;        // 0 neutral, 1 weight on the left (+x) leg, 2 on the right
        [System.NonSerialized] public bool close;       // the knees closer together

        // channel springs: knee in / forward / twist / foot turn of both legs, lean, toes
        struct Ch { public float x, v, target, tau; }
        Ch inL, inR, fwL, fwR, twL, twR, ywL, ywR, leanC, toeL, toeR;
        // the pose held now (targets) and the small shift within it
        float pInL, pInR, pFwL, pFwR, pTwL, pTwR, pYwL, pYwR, pLean, sInL, sInR, sFwL, sFwR, sTwL, sTwR, sYwL, sYwR, sLean;
        float nextPose, nextShift, nextToe, nextFidget, toeOffL = -1f, toeOffR = -1f, t; int lastSide = 2;
        // the fidget running now: kind (0 none), its start, length, the leg it is on
        int fid, fidLeg; float fidT0, fidLen;
        System.Random rng = new System.Random(20261116);

        float U(float a, float b) => a + (b - a) * (float)rng.NextDouble();

        public void Reset(int seed = 20261116)
        {
            rng = new System.Random(seed); t = 0f; toeOffL = toeOffR = -1f; fid = 0;
            inL = inR = fwL = fwR = twL = twR = ywL = ywR = leanC = toeL = toeR = new Ch { tau = 0.35f };
            sInL = sInR = sFwL = sFwR = sTwL = sTwR = sYwL = sYwR = sLean = 0f;
            stand = 0; lastSide = rng.NextDouble() < 0.5 ? 1 : 2; close = rng.NextDouble() < 0.5; SetPose();
            Aim(0.35f);
            // (start where the pose is, not easing into it)
            inL.x = inL.target; inR.x = inR.target; fwL.x = fwL.target; fwR.x = fwR.target; twL.x = twL.target; twR.x = twR.target;
            ywL.x = ywL.target; ywR.x = ywR.target; leanC.x = leanC.target;
            nextPose = U(2.5f, 4.5f); nextShift = U(1.2f, 2.5f); nextToe = U(2.5f, 5f); nextFidget = U(3f, 6f);
            Advance(0f);
        }

        /// The poses: targets of every channel (offsets of each leg in m / rad; lean in rad).
        void SetPose()
        {
            float c = close ? 1f : 0f;
            switch (stand)
            {
                case 1:     // weight on the left leg: it stands straight, the right one relaxes in front of it, turned in
                    pInL = 0.001f + 0.003f * c; pFwL = -0.006f; pTwL = 0.10f + 0.05f * c; pYwL = footYawL;
                    pInR = relaxIn + 0.006f * c; pFwR = relaxFwd * U(0.82f, 1.1f); pTwR = 0.42f + 0.08f * c; pYwR = footYawR + U(0.06f, 0.12f);
                    pLean = weightLean * U(0.85f, 1.1f); break;
                case 2:     // weight on the right leg
                    pInR = 0.001f + 0.003f * c; pFwR = -0.006f; pTwR = 0.11f + 0.05f * c; pYwR = footYawR;
                    pInL = relaxIn * 0.93f + 0.006f * c; pFwL = relaxFwd * U(0.8f, 1.05f); pTwL = 0.40f + 0.08f * c; pYwL = footYawL + U(0.06f, 0.12f);
                    pLean = -weightLean * U(0.85f, 1.1f); break;
                default:    // weight on both - never mirrored: one knee a little further in and forward, the hips a little off centre
                    pInL = 0.003f + 0.0065f * c; pFwL = 0.004f + 0.010f * c; pTwL = 0.17f + 0.14f * c; pYwL = footYawL + 0.05f * c;
                    pInR = 0.004f + 0.0065f * c; pFwR = 0.008f + 0.012f * c; pTwR = 0.20f + 0.14f * c; pYwR = footYawR + 0.05f * c;
                    pLean = U(-0.022f, 0.022f); break;
            }
        }

        void Aim(float tau)
        {
            inL.target = pInL + sInL; inR.target = pInR + sInR; fwL.target = pFwL + sFwL; fwR.target = pFwR + sFwR;
            twL.target = pTwL + sTwL; twR.target = pTwR + sTwR; ywL.target = pYwL + sYwL; ywR.target = pYwR + sYwR; leanC.target = pLean + sLean;
            inL.tau = inR.tau = fwL.tau = fwR.tau = twL.tau = twR.tau = tau; ywL.tau = ywR.tau = tau * 0.9f; leanC.tau = tau * 1.25f;
        }

        /// One step of the springs + the clocks.
        public void Advance(float dt)
        {
            t += dt;
            float tau = -1f;
            if (t >= nextPose)
            {
                // from both legs onto one; from one leg back onto both, or straight over onto the other
                // (from both legs mostly onto the leg that did not carry her last time: she alternates)
                int prev = stand;
                if (prev == 0) stand = rng.NextDouble() < 0.72 ? 3 - lastSide : lastSide;
                else stand = rng.NextDouble() < 0.45 ? 0 : 3 - prev;
                if (stand != 0) lastSide = stand;
                close = rng.NextDouble() < 0.6;
                sInL = sInR = sFwL = sFwR = sTwL = sTwR = sYwL = sYwR = sLean = 0f;
                SetPose();
                if (log) Debug.Log($"[motion] t={t:0.0} stand {(stand == 0 ? "both legs" : stand == 1 ? "left (+x) leg" : "right leg")}, knees {(close ? "closer" : "apart")}");
                nextPose = t + U(poseEvery.x, poseEvery.y);
                nextShift = t + U(shiftEvery.x, shiftEvery.y);
                tau = U(0.30f, 0.44f);
            }
            else if (t >= nextShift)
            {
                // a shift within the pose: one knee, the other, both, the hips, a foot
                float r = (float)rng.NextDouble();
                if (r < 0.26f) { sInL = U(-0.004f, 0.005f); sFwL = U(-0.006f, 0.010f); sTwL = U(-0.07f, 0.09f); }
                else if (r < 0.52f) { sInR = U(-0.004f, 0.005f); sFwR = U(-0.006f, 0.010f); sTwR = U(-0.07f, 0.09f); }
                else if (r < 0.70f) { float d = U(-0.003f, 0.004f); sInL = d + U(-0.001f, 0.001f); sInR = d + U(-0.001f, 0.001f); sTwL = sTwR = d * 14f; sFwL = U(-0.003f, 0.007f); sFwR = U(-0.003f, 0.007f); }
                else if (r < 0.86f) sLean = U(-0.035f, 0.035f);
                else if (rng.NextDouble() < 0.5) sYwL = U(-0.07f, 0.10f); else sYwR = U(-0.07f, 0.10f);
                nextShift = t + U(shiftEvery.x, shiftEvery.y);
                tau = U(0.30f, 0.55f);
            }
            if (tau > 0f) Aim(tau);
            if (t >= nextToe && !toeLifts) nextToe = t + 1f;
            if (t >= nextToe)
            {
                // a big toe lifts - more often the relaxed leg's - sometimes both
                float r = (float)rng.NextDouble(), a = U(0.13f, 0.27f), hold = U(0.7f, 2.2f);
                float pl = stand == 2 ? 0.75f : stand == 1 ? 0.25f : 0.5f;   // chance it is the left one
                bool both = r >= 0.82f, left = both || (float)rng.NextDouble() < pl, right = both || !left;
                if (left) { toeL.target = a; toeL.tau = 0.10f; toeOffL = t + hold; }
                if (right) { toeR.target = both ? a * U(0.7f, 1f) : a; toeR.tau = 0.10f; toeOffR = t + hold * U(0.8f, 1.2f); }
                nextToe = t + U(toeEvery.x, toeEvery.y);
            }
            if (toeOffL > 0f && t >= toeOffL) { toeL.target = 0f; toeL.tau = 0.18f; toeOffL = -1f; }
            if (toeOffR > 0f && t >= toeOffR) { toeR.target = 0f; toeR.tau = 0.18f; toeOffR = -1f; }
            if (fid == 0 && t >= nextFidget)
            {
                // a fidget: 1 a knee dips, 2 the knees rub past each other, 3 a foot turns on the spot (the relaxed leg's, else either),
                // 4 the hips sway
                fid = 1 + rng.Next(4); fidT0 = t;
                fidLen = fid == 1 ? U(1.0f, 1.6f) : fid == 2 ? U(1.6f, 2.6f) : fid == 3 ? U(1.4f, 2.2f) : U(2.8f, 4.2f);
                fidLeg = stand == 1 ? 1 : stand == 2 ? 0 : rng.Next(2);          // 0 = left (+x)
            }
            float fFw = 0f, fFwAlt = 0f, fIn = 0f, fYaw = 0f, fLean = 0f;
            if (fid != 0)
            {
                float u = (t - fidT0) / Mathf.Max(fidLen, 1e-3f), q = t - fidT0;
                if (u >= 1f) { fid = 0; nextFidget = t + U(fidgetEvery.x, fidgetEvery.y); }
                else
                {
                    float e = Mathf.Sin(Mathf.PI * u); e *= e;                 // eases in and out
                    // (smooth noise, never a rhythm: the 'vibe' style's dips on the beat read as the legs jerking every half
                    //  second, user 2026-11-17)
                    float sd = fidT0 * 3.7f;
                    switch (fid)
                    {
                        case 1: fFw = 0.010f * e * (0.6f + 0.4f * N(q * 1.1f, sd)); break;                               // a knee dips, once
                        case 2: fFwAlt = 0.008f * e * N(q * 0.9f, sd); fIn = 0.003f * e; break;                         // the knees rub past each other
                        case 3: fYaw = 0.07f * e * N(q * 1.0f, sd); break;                                               // a foot turns on the spot
                        case 4: fLean = 0.032f * e * N(q * 0.45f, sd); break;                                            // the hips sway
                    }
                }
            }
            for (int c = 0; c < 11; c++) Spring(c, dt);
            // (the original's session replayed: as quiet as in the video - small versions of the same poses, no fidgets)
            // (calm: 0.3 / no fidgets - the replay stood frozen for seconds, independent review 2026-11-17; quiet: the replay)
            float qk = Mathf.Clamp01(quiet);
            float m = motionScale * (calm ? 0.3f : Mathf.Lerp(1f, 0.45f, qk)), fm = calm ? 0f : motionScale * Mathf.Lerp(1f, 0.85f, qk);
            float yawK = calm ? 0.55f : Mathf.Lerp(1f, 0.8f, qk);
            // a slow restless drift of every channel (two octaves, incommensurate rates): never the same twice. Applied in full
            // in the replay too (md): the original's legs drift all the time - their outline moves a median 7 px per 0.25 s
            // (540 px wide), still only 9 % of the time; ours 3 px, still a third of the time (2026-11-17): the knees' drift x4, the hips' x2.2 - the original's knees move
            // 1 - 2.5 cm every half second; the lean alone moves a knee only ~28 % of its shift.
            float md = motionScale * (calm ? 0.3f : 1f);
            L.kneeIn = m * inL.x + md * (0.0055f * N(t * 0.23f, 1.3f) + 0.0040f * N(t * 0.75f, 7.1f)) + fm * fIn;
            R.kneeIn = m * inR.x + md * (0.0055f * N(t * 0.21f, 4.2f) + 0.0040f * N(t * 0.81f, 2.9f)) + fm * fIn;
            L.kneeFwd = m * fwL.x + md * (0.0080f * N(t * 0.19f, 9.4f) + 0.0030f * N(t * 0.53f, 3.7f)) + fm * (fFw + fFwAlt);
            R.kneeFwd = m * fwR.x + md * (0.0085f * N(t * 0.25f, 5.5f) + 0.0030f * N(t * 0.59f, 8.1f)) + fm * (fFw - fFwAlt);
            L.twist = m * twL.x + md * 0.045f * N(t * 0.20f, 3.3f);
            R.twist = m * twR.x + md * 0.048f * N(t * 0.22f, 8.8f);
            L.footYaw = yawK * ywL.x + fm * (fidLeg == 0 ? fYaw : 0f); R.footYaw = yawK * ywR.x + fm * (fidLeg == 1 ? fYaw : 0f);
            if (motionScale <= 0f) { L.footYaw = yawK * footYawL; R.footYaw = yawK * footYawR; }      // (-sheerStill: the plain stance)
            L.toe = Mathf.Max(toeL.x, 0f) * (motionScale > 0f ? 1f : 0f); R.toe = Mathf.Max(toeR.x, 0f) * (motionScale > 0f ? 1f : 0f);
            lean = m * leanC.x + md * (0.016f * N(t * 0.11f, 6.6f) + 0.010f * N(t * 0.45f, 1.9f) + 0.006f * N(t * 0.85f, 4.4f)) + fm * fLean;
        }

        void Spring(int c, float dt)
        {
            ref Ch ch = ref inL;
            switch (c) { case 1: ch = ref inR; break; case 2: ch = ref fwL; break; case 3: ch = ref fwR; break; case 4: ch = ref twL; break;
                         case 5: ch = ref twR; break; case 6: ch = ref leanC; break; case 7: ch = ref toeL; break; case 8: ch = ref toeR; break;
                         case 9: ch = ref ywL; break; case 10: ch = ref ywR; break; }
            // critically damped spring, exact step (any dt): settles in ~4 tau, no overshoot
            float w = 1f / Mathf.Max(ch.tau, 1e-3f), x = ch.x - ch.target, v = ch.v, e = Mathf.Exp(-w * dt);
            float x1 = (x + (v + w * x) * dt) * e, v1 = (v - (v + w * x) * w * dt) * e;
            ch.x = ch.target + x1; ch.v = v1;
        }

        // smooth 1-D value noise in -1 .. 1 (quintic interpolation of hashed lattice values)
        static float N(float x, float seed)
        {
            x += seed * 17.13f;
            float i = Mathf.Floor(x), f = x - i;
            float a = H(i), b = H(i + 1f), s = f * f * f * (f * (f * 6f - 15f) + 10f);
            return Mathf.Lerp(a, b, s);
        }
        static float H(float i) { float h = Mathf.Sin(i * 127.1f + 311.7f) * 43758.5453f; return 2f * (h - Mathf.Floor(h)) - 1f; }
    }
}
