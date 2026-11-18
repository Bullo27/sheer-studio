// SHEER — replays the original video's session (cursor path measured on the original at 30 fps, presses,
// tears, knee reflex, camera moves, the click on VIEW 02) through the same simulation the player uses,
// optionally capturing every frame at a fixed 30 fps for side-by-side comparison with the original.
// Port of blender/sheer_replay.py (ReplaySim / ReplayPull / CamRig.params).
// Command line: -sheerReplay [-sheerCapture <dir>] [-sheerFrom <s>] [-sheerTo <s>]
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Sheer
{
    // energy: the tear's energy (-1 = from the drag); preT / preLen / preSpeed: when the row of slits starts to grow down from the
    // pinch (s, -1 = 0.7 s after the grab), how far (m) and how fast (m/s) - all read off the original
    [Serializable] public class Press { public float t0, t1, fwd, cap = 0.11f, tear = -1f, lift, outward, pinch, along, gather, pinchR, energy = -1f, preT = -1f, preLen = 0.055f, preSpeed = 0.10f; public int side; public bool burst, pre; }   // lift: pull toward the viewer (fraction of the patch's travel)   // tear: measured tear time (s) in the original, -1 = by tension / at release
    [Serializable] public class CamMove { public float i0, i1, o0, o1, dolly, orbit, pitch; public string view; }
    [Serializable] public class Gust { public float t0, t1, gain; }
    [Serializable] public class Click { public float leave, reach, release, back; }
    [Serializable]
    public class Session
    {
        public float duration, fps; public float[] viewSwitch; public Press[] presses; public CamMove[] camMoves; public Gust[] windGusts;
        public Click clickView02; public float[] t, x, y, knee, wind, lean; public int[] visible;

        /// The original's session, or a test session (-sheerSession FILE: free-play scenarios - generic pulls, idle - for
        /// captures; CLAUDE.md: test free play directly).
        public static Session Load(string file = null) =>
            JsonUtility.FromJson<Session>(File.ReadAllText(string.IsNullOrEmpty(file) ? Path.Combine(Application.streamingAssetsPath, "replay_session.json") : file));

        float Interp(float[] a, float tt)
        {
            float f = (tt - t[0]) * fps; int i = Mathf.Clamp((int)Mathf.Floor(f), 0, t.Length - 2);
            return Mathf.Lerp(a[i], a[i + 1], Mathf.Clamp01(f - i));
        }
        public Vector2 Cursor(float tt) => new Vector2(Interp(x, tt), Interp(y, tt));
        public bool Visible(float tt) => visible[Mathf.Clamp(Mathf.RoundToInt((tt - t[0]) * fps), 0, visible.Length - 1)] != 0;
        public float Knee(float tt) => Interp(knee, tt);
        public float Wind(float tt) => Interp(wind, tt);
        /// The original's lean (tracked from its outlines); NaN = none in this session (the body's own motion leans).
        public float Lean(float tt) => lean != null && lean.Length == t.Length ? Interp(lean, tt) : float.NaN;
        /// ... WITHOUT its after-tear reflexes (the user, 2026-11-16: no flinch after a tear). Every reflex in the track is
        /// an excursion of the knees toward each other - a negative lean of 0.05 - 0.10 rad for 1.3 - 3 s - on a resting
        /// sway of +-0.01; an upper envelope over +-1.6 s, smoothed over +-0.4 s, keeps the rest and drops the excursions.
        /// (Measured on the outlines: at rest the original's leg stays within +-8 px; the free-play drift the replay used
        /// instead wandered +-100 - 140 px, so its presses landed centimetres from where they did in the original - on a
        /// ladder at 5.1 s, beside it at 2.45 s - review 14.)
        public float LeanCalm(float tt)
        {
            if (lean == null || lean.Length != t.Length) return float.NaN;
            if (leanCalm == null)
            {
                int n = lean.Length, W = Mathf.RoundToInt(1.6f * fps), H = Mathf.Max(1, Mathf.RoundToInt(0.4f * fps));
                var mx = new float[n]; leanCalm = new float[n];
                for (int k = 0; k < n; k++) { float m = float.MinValue; for (int q = Mathf.Max(0, k - W); q <= Mathf.Min(n - 1, k + W); q++) m = Mathf.Max(m, lean[q]); mx[k] = m; }
                for (int k = 0; k < n; k++) { float s = 0f; int c = 0; for (int q = Mathf.Max(0, k - H); q <= Mathf.Min(n - 1, k + H); q++) { s += mx[q]; c++; } leanCalm[k] = s / c; }
            }
            return Interp(leanCalm, tt);
        }
        [System.NonSerialized] float[] leanCalm;
        public float WindAt(float tt) => wind != null && wind.Length == t.Length ? Interp(wind, tt) : 1f;
    }

    public class ReplayDriver : MonoBehaviour
    {
        public TightsSim sim;
        public CameraRig rig;
        public SheerInput input;
        public SheerUI ui;
        public SkirtCloth skirt;
        public bool playOnStart;
        public string captureDir;                      // empty = no capture
        public float from = 0f, to = -1f;
        [Tooltip("Scales each press's recorded lift of the hand toward the viewer. 0 = the patch moves in the screen plane, as measured " +
                 "in the original from two views.")]
        public float liftScale = 0f;
        public string sessionFile;                     // empty = the original's session (StreamingAssets/replay_session.json)
        // The original's tracked 'lean' was mostly its knees moving - including the reflex after every tear, which the user
        // did not want (2026-11-16). The ORIGINAL's session leans as the original does at rest - its track with the reflexes
        // taken out (Session.LeanCalm) - on a calm stance, so its presses land where they did there; free play (and a test
        // session) moves as lively as ever (SheerBodyMotion). -sheerTrackedLean: the raw track, reflexes and all;
        // -sheerFreeLean: the replay's body as in free play (the old default: it drifted +-4 - 5 cm from the original's).
        public bool trackedLean, freeLean;
        float LeanNow(float tt) => freeLean ? float.NaN : trackedLean ? S.Lean(tt) : S.LeanCalm(tt);

        class Active
        {
            public Press pr; public Pull pull; public Vector3 W0, h; public float d0; public bool released;
            public Vector3 off;                         // from the lattice node the fabric is held by to the point the cursor grabbed (world)
            public Vector2 c0;                          // the cursor where it took hold
            public Vector2 cOff;                        // drawn cursor -> the point actually grabbed (window, 0..1): see CursorAt
        }

        /// world point -> normalized original-window coordinates (the inverse of CameraRig.RayThrough) at session time t
        Vector2 Project(float t, Vector3 world)
        {
            CamAt(t, out var loc, out var tgt, out var lens, out _, out _);
            Vector3 f = (tgt - loc).normalized, r = Vector3.Cross(Vector3.up, f).normalized, u = Vector3.Cross(f, r);
            Vector3 d = world - loc; float df = Mathf.Max(Vector3.Dot(d, f), 1e-6f), k = lens / 36f;
            return new Vector2(0.5f + Vector3.Dot(d, r) / df * rig.aspect * k, 0.5f - Vector3.Dot(d, u) / df * k);
        }

        readonly List<float> dumpTimes = new List<float>(); string dumpPrefix;
        void DumpCloth()
        {
            while (dumpTimes.Count > 0 && T >= dumpTimes[0] - 1e-4f)
            {
                foreach (int sd in new[] { 1, -1 })
                {
                    var st = sim.Cl.ReadState(sd); var bytes = new byte[st.Length * 4];
                    Buffer.BlockCopy(st, 0, bytes, 0, bytes.Length);
                    File.WriteAllBytes($"{dumpPrefix}_{dumpTimes[0].ToString("0.000", System.Globalization.CultureInfo.InvariantCulture)}_{(sd > 0 ? "L" : "R")}.bin", bytes);
                }
                Debug.Log($"[replay] cloth state dumped at t={T:0.000}");
                dumpTimes.RemoveAt(0);
            }
        }

        Session S;
        readonly List<Active> act = new List<Active>();
        readonly List<int> pending = new List<int>();
        bool running; int frame;
        public bool IsRunning => running;
        public float T { get; private set; }

        void Start()
        {
            var args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "-sheerReplay") playOnStart = true;
                if (args[i] == "-sheerCapture" && i + 1 < args.Length) captureDir = args[i + 1];
                if (args[i] == "-sheerSession" && i + 1 < args.Length) sessionFile = args[i + 1];
                if (args[i] == "-sheerTrackedLean") trackedLean = true;
                if (args[i] == "-sheerFreeLean") freeLean = true;
                if (args[i] == "-sheerFrom" && i + 1 < args.Length) from = float.Parse(args[i + 1], System.Globalization.CultureInfo.InvariantCulture);
                if (args[i] == "-sheerTo" && i + 1 < args.Length) to = float.Parse(args[i + 1], System.Globalization.CultureInfo.InvariantCulture);
                if (args[i] == "-sheerLogPulls") sim.logPulls = true;
                if (args[i] == "-sheerVariants" && i + 1 < args.Length) variants = args[i + 1].Split(';');
                if (args[i] == "-sheerCapScale" && i + 1 < args.Length)
                {   // 2 = the original's full game-view resolution (1080 x 1890): knit + glints get the same downscale as the video
                    float k = float.Parse(args[i + 1], System.Globalization.CultureInfo.InvariantCulture);
                    captureWidth = Mathf.RoundToInt(540 * k); captureHeight = Mathf.RoundToInt(945 * k);
                }
                // supersampling of the capture: render n x n samples per pixel, box-filtered down (1 = off)
                if (args[i] == "-sheerCapSS" && i + 1 < args.Length) captureSS = Mathf.Max(1, int.Parse(args[i + 1]));
                if (args[i] == "-sheerCapJpg" && i + 1 < args.Length) captureJpg = int.Parse(args[i + 1]);
                // frames per second of the capture (default: the session's 30)
                if (args[i] == "-sheerCapFps" && i + 1 < args.Length) captureFps = float.Parse(args[i + 1], System.Globalization.CultureInfo.InvariantCulture);
                // experiments: override every VIEW 01 camera move of the session: orbit:dolly:pitch[:pivotDepth]
                if (args[i] == "-sheerCamOverride" && i + 1 < args.Length) camOverride = args[i + 1];
                // diagnostics: -sheerCamFree "t:px:py:pz:tx:ty:tz[:lens];..." draws the capture from a camera of its own from
                // session time t on (position and target in metres, lens in mm) - close looks at outlines, feet, the hem.
                // The session's presses are still aimed through its own views.
                if (args[i] == "-sheerCamFree" && i + 1 < args.Length)
                    foreach (var seg in args[i + 1].Split(';'))
                    {
                        var q = seg.Split(':'); if (q.Length < 7) continue;
                        var k = new float[q.Length];
                        for (int j = 0; j < q.Length; j++) k[j] = float.Parse(q[j], System.Globalization.CultureInfo.InvariantCulture);
                        camFree.Add(k);
                    }
                if (args[i] == "-sheerNoStretchClear") { var td = FindAnyObjectByType<TensionData>(); if (td) td.frostClearAtStretch = 0f; }
                // diagnostics: -sheerDumpCloth T1,T2,...:PREFIX writes both legs' node positions (x, y, z, lift; float32, NU x NV)
                // at those session times to PREFIX_<t>_L.bin / _R.bin
                if (args[i] == "-sheerDumpCloth" && i + 1 < args.Length)
                {
                    int c = args[i + 1].IndexOf(':');
                    if (c > 0)
                    {
                        dumpPrefix = args[i + 1].Substring(c + 1);
                        foreach (var s in args[i + 1].Substring(0, c).Split(',')) dumpTimes.Add(float.Parse(s, System.Globalization.CultureInfo.InvariantCulture));
                        dumpTimes.Sort();
                    }
                }
            }
            DevTweaks.Apply();
            if (playOnStart) Play();
        }

        public void Play()
        {
            S = Session.Load(sessionFile);
            sim.ResetDamage();
            // (the body's own motion - knees, toes, weight - restarts with its fixed seed: a session renders the same every time)
            // (the ORIGINAL's session: she stands as quietly as in the video, so its presses land where they did there; a test
            //  session - free play - gets her as she is)
            // (the original never stands still - knees flex, weight shifts, 15 - 35 px every half second; the 'calm' replay
            //  stood frozen for seconds: independent review 2026-11-17. Free play's restless motion; -sheerCalm for tests)
            // (the original's session: calm - its body is the original's tracked lean, LeanNow; free play's drift wandered
            //  +-100 - 140 px from where the original's leg stood, review 14)
            sim.motion.calm = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerCalm") >= 0
                              || (string.IsNullOrEmpty(sessionFile) && !freeLean);
            sim.motion.quiet = string.IsNullOrEmpty(sessionFile) ? 1f : 0f;
            sim.ResetMotion();
            sim.externallyDriven = true;
            if (input) input.inputEnabled = false;
            rig.playerControl = false;
            act.Clear(); pending.Clear();
            for (int i = 0; i < S.presses.Length; i++) pending.Add(i);
            T = S.presses != null && S.presses.Length > 0 ? Mathf.Min(S.presses[0].t0 - 0.05f, 0f) : 0f;
            sim.simTime = T;
            running = true; frame = 0;
            if (captureFps <= 0f) captureFps = S.fps;
            if (!string.IsNullOrEmpty(captureDir)) { Directory.CreateDirectory(captureDir); Time.captureFramerate = Mathf.RoundToInt(captureFps); }
            // pre-roll to 'from' (the video starts mid-pinch at t = 0), frame by frame with the pose track like the capture
            // (one big step left the knee pose stale and the cloth jumped when the capture started)
            float target = Mathf.Max(from, 0f), fdt = 1f / S.fps;
            while (T < target - 1e-5f)
            {
                sim.leanOverride = LeanNow(T);
                Step(Mathf.Min(fdt, target - T));
            }
            sim.leanOverride = LeanNow(T);
        }

        // ------------------------------------------------------------------ camera (CamRig.params)
        static float Smoother(float x) { x = Mathf.Clamp01(x); return x * x * x * (x * (x * 6 - 15) + 10); }

        string camOverride; bool camOverrideDone;
        readonly List<float[]> camFree = new List<float[]>();
        /// the camera the capture is DRAWN from: the session's, or -sheerCamFree's
        void DrawCam(float t, out Vector3 loc, out Vector3 tgt, out float lens, out float focus, out float fstop)
        {
            CamAt(t, out loc, out tgt, out lens, out focus, out fstop);
            float[] k = null; foreach (var q in camFree) if (t >= q[0] - 1e-4f) k = q;
            if (k == null) return;
            loc = new Vector3(k[1], k[2], k[3]); tgt = new Vector3(k[4], k[5], k[6]); if (k.Length > 7) lens = k[7];
            focus = (tgt - loc).magnitude; fstop = 16f;
        }
        void CamAt(float t, out Vector3 loc, out Vector3 tgt, out float lens, out float focus, out float fstop)
        {
            if (camOverride != null && !camOverrideDone)
            {
                camOverrideDone = true;
                var q = camOverride.Split(':'); float F(int k) => float.Parse(q[k], System.Globalization.CultureInfo.InvariantCulture);
                foreach (var m in S.camMoves) if (m.view == "VIEW01") { m.orbit = F(0); m.dolly = F(1); m.pitch = F(2); }
                if (q.Length > 3) rig.orbitPivotDepth = F(3);
            }
            float w = Smoother((t - S.viewSwitch[0]) / (S.viewSwitch[1] - S.viewSwitch[0]));
            float yaw = 0, k = 1, pitch = 0;
            foreach (var m in S.camMoves)
            {
                if (t < m.i0 || t > m.o1) continue;
                float mm = t < m.i1 ? Smoother((t - m.i0) / (m.i1 - m.i0)) : t < m.o0 ? 1f : 1f - Smoother((t - m.o0) / (m.o1 - m.o0));
                yaw = m.orbit * mm; k = 1f + (m.dolly - 1f) * mm; pitch = m.pitch * mm;
            }
            rig.Params(0, 1, w, yaw, pitch, k, out loc, out tgt, out lens, out focus, out fstop);
        }

        Ray RayAt(float t, Vector2 c, out Vector3 camPos, out Vector3 camFwd)
        {
            CamAt(t, out var loc, out var tgt, out var lens, out _, out _);
            camPos = loc; camFwd = (tgt - loc).normalized;
            return CameraRig.RayThrough(loc, tgt, lens, rig.aspect, c.x, c.y);
        }

        // ------------------------------------------------------------------ presses (ReplaySim._spawn)
        void Spawn(int i)
        {
            var pr = S.presses[i];
            float t0 = pr.t0;
            Vector2 c = S.Cursor(t0);
            Ray ray = RayAt(t0, c, out var o, out var fwd);
            var Tm = sim.T; var tr = sim.tights.transform;
            Vector3 O = tr.InverseTransformPoint(ray.origin), D = tr.InverseTransformDirection(ray.direction);
            // closest hero-leg vertex to the cursor ray, preferring the near (visible) side
            int best = sim.NearestToRay(O, D, pr.side, out float miss);
            // INPUT ONLY (CLAUDE.md - no reward hacking): the press is grabbed exactly as a user's click would be - same reach,
            // hand shape and gather as free play, tears and their build-up from the fabric's tension. (Until 2026-11-16 the
            // replay scripted per-press caps, shapes, energies, tear times and slit rows: kept for reference only in
            // tools/sim/ref_data/replay_session_scripted_r16.json)
            var pull = sim.Grab(best, scripted: false);
            if (pull == null) { Debug.Log($"[replay] press {i} at t={t0:F2}: bare skin above the stocking's top, nothing to grab"); return; }
            pull.seed = 0.13f + 0.37f * i;
            Vector3 hp = tr.TransformPoint((Vector3)Tm.rest[best] + sim.PoseOffset(Tm.rest[best]));
            float d0 = Vector3.Dot(hp - o, fwd);
            // (a grab below the simulated fabric - on the instep - is held by the lowest free row, centimetres above it: the
            //  hand draws that patch down toward where the cursor took hold, or the sail grew far above the hand, review
            //  round 7. Within a lattice cell of the grab elsewhere: no effect)
            Vector3 nodeW = tr.TransformPoint(sim.PosePoint(sim.PullRest(pull)));
            var a0 = new Active { pr = pr, pull = pull, h = hp, d0 = d0, off = hp - nodeW, c0 = c };
            // (her legs never stand exactly where the original's stood - she shifts her weight in her own time - so a press can
            //  land beside the leg; the nearest stocking is taken, as a user would aim at it. The DRAWN cursor then eases onto
            //  the point taken and back after the release, so pointer and pinch stay together; the hand still follows the
            //  recorded cursor's movement. Nothing of the pull itself changes)
            if (miss > 0.003f) a0.cOff = Project(t0, hp) - c;
            a0.W0 = WorldAt(a0, t0, out _);
            act.Add(a0);
            Debug.Log($"[replay] press {i} at t={t0:F2} side {pr.side} u={pull.u:F3} z={pull.z:F3} (ray miss {miss * 1000:F1} mm)");
        }

        // the video starts mid-pinch: cursor path before t = 0 (grab on the knee, pulled down)
        // (Before the video starts - the first press is at -0.6 s - the session's cursor is its tracked path at t = 0 run back
        //  at the same velocity: it passes through the pocket the original shows at its first frame, (0.46, 0.80). Until
        //  2026-11-18 a hand-made path was used there instead, starting where the original's first holes open (0.37, 0.69) -
        //  chosen for where the tear should land, not where the cursor was: tuning the replay to the result, which CLAUDE.md
        //  forbids. It also put the opening pinch on the knee's inner side, a ribbon along the outline, review 10.)

        Vector3 WorldAt(Active a, float t, out Vector3 camPos)
        {
            Vector2 c = S.Cursor(t);
            Ray r = RayAt(t, c, out camPos, out var fwd);
            return r.origin + r.direction * (a.d0 / Mathf.Max(Vector3.Dot(r.direction, fwd), 1e-6f));
        }

        // ReplayPull.step, called every 1/240 s before the fabric integrates
        void Substep(float h)
        {
            float t = sim.simTime;
            for (int k = pending.Count - 1; k >= 0; k--)
                if (t >= S.presses[pending[k]].t0 - 1e-6f) { Spawn(pending[k]); pending.RemoveAt(k); }
            foreach (var a in act)
            {
                if (a.released) continue;
                var p = a.pull; var pr = a.pr; float tt = t + h;
                Vector3 W = WorldAt(a, Mathf.Min(tt, pr.t1), out var o);
                // (the drag as the cursor has moved ON SCREEN since the grab, in the camera's plane as it is now: during an
                //  orbit the plane of the grab turned away and the drag pulled the patch round behind the leg - the 7.6 s sail
                //  slid back along the outline while the cursor went out, review round 8)
                Vector3 W0 = a.W0;
                if (a.pr.t0 >= 0f)
                {
                    Ray r0 = RayAt(Mathf.Min(tt, pr.t1), a.c0, out _, out var f0);
                    W0 = r0.origin + r0.direction * (a.d0 / Mathf.Max(Vector3.Dot(r0.direction, f0), 1e-6f));
                }
                Vector3 Dv = W - W0;
                Vector3 v = sim.HandOffset(p, Dv, (o - a.h).normalized, 0f);
                if (a.off.sqrMagnitude > 1e-4f) v += a.off * Mathf.SmoothStep(0f, 1f, Dv.magnitude / 0.03f);
                if (v.magnitude > 0.35f) v = v.normalized * 0.35f;           // (free play's limit of the hand, SheerInput.maxPull)
                p.target = sim.tights.transform.InverseTransformVector(v);
                p.eye = sim.tights.transform.InverseTransformPoint(o); p.hasEye = true;
                // (tears, their size and the rows of slits before them come from the fabric's tension, exactly as in free play)
                if (p.state != Pull.State.Held) { a.released = true; continue; }        // the fabric gave way under the hand
                if (tt >= pr.t1) { sim.Release(p, false); a.released = true; }
            }
        }

        void Step(float dt)
        {
            if (dt <= 0) return;
            sim.Advance(dt, Substep);
            T = sim.simTime;
        }

        public int warmupFrames = 45;
        string[] variants; int variantIdx = -1, variantWarm;
        int warm;

        void Update()
        {
            if (!running) return;
            if (variantIdx >= 0)
            {
                // static scene: settle the temporal effects for each variant, then capture it
                DrawCam(T, out var vl, out var vt, out var vlens, out var vf, out var vfs);
                rig.ApplyParams(vl, vt, vlens, vf, vfs);
                if (variantWarm++ < 24) { CaptureOffscreen(null); return; }
                CaptureOffscreen(Path.Combine(captureDir, $"var_{variantIdx:D2}.png"));
                Debug.Log($"[replay] variant {variantIdx}: {variants[variantIdx]}");
                variantIdx++; variantWarm = 0;
                if (variantIdx < variants.Length) { DevTweaks.ApplySpec(variants[variantIdx]); return; }
#if UNITY_EDITOR
                UnityEditor.EditorApplication.Exit(0);
#else
                Application.Quit();
#endif
                return;
            }
            if (!string.IsNullOrEmpty(captureDir) && warm < warmupFrames)
            {
                // render without advancing: HDRP's temporal history and sky ambient probe settle before frame 1
                DrawCam(T, out var wl, out var wt, out var wlens, out var wf, out var wfs);
                rig.ApplyParams(wl, wt, wlens, wf, wfs);
                // (the skirt's clock too: it ran on during the warm-up and the hem jumped to the replay's time two frames
                //  in, review round 8)
                if (skirt) { skirt.gustGain = S.WindAt(T); skirt.SetTime(T); }
                if (Application.isBatchMode) CaptureOffscreen(null);
                warm++;
                return;
            }
            // capture: fixed 1/fps steps; live: real time, but never more than 1/20 s per frame (no catch-up spiral)
            float dt = !string.IsNullOrEmpty(captureDir) ? 1f / captureFps : Mathf.Min(Time.deltaTime, 1f / 20f);
            Step(dt);
            if (dumpTimes.Count > 0) DumpCloth();
            sim.leanOverride = LeanNow(T);
            sim.Apply();                                   // pose + tear maps of THIS step on the GPU before the capture renders
            if (skirt) { skirt.gustGain = S.WindAt(T); skirt.SetTime(T); }
            DrawCam(T, out var loc, out var tgt, out var lens, out var focus, out var fstop);
            rig.ApplyParams(loc, tgt, lens, focus, fstop);
            if (ui)
            {
                var c = S.clickView02;
                ui.SetActiveView(T < c.release ? 0 : 1, pressed: T >= c.reach && T < c.release ? 1 : -1);
                ui.SetSoftwareCursor(CursorAt(T, out bool vis), vis);
            }
            if (!string.IsNullOrEmpty(captureDir))
            {
                string file = Path.Combine(captureDir, $"u_{frame + 1:D4}.png");
                if (Application.isBatchMode) CaptureOffscreen(file);   // no window/game view in batch mode
                else ScreenCapture.CaptureScreenshot(file);
            }
            frame++;
            float end = to > 0 ? to : S.duration;
            if (T >= end)
            {
                if (!string.IsNullOrEmpty(captureDir) && variants != null && variants.Length > 0)
                {
                    // hold the time (sim still externally driven, camera on the replay's path), render the look variants
                    variantIdx = 0; variantWarm = 0;
                    DevTweaks.ApplySpec(variants[0]);
                    return;
                }
                running = false; sim.externallyDriven = false; sim.leanOverride = float.NaN; sim.motion.calm = false; sim.motion.quiet = 0f;
                if (input) input.inputEnabled = true;
                rig.playerControl = true;
                if (!string.IsNullOrEmpty(captureDir))
                {
                    Debug.Log("[replay] captured " + frame + " frames");
#if UNITY_EDITOR
                    UnityEditor.EditorApplication.Exit(0);
#else
                    Application.Quit();
#endif
                }
            }
        }

        RenderTexture capRT, capHalf, capOut; Texture2D capTex;
        public int captureWidth = 540, captureHeight = 945;      // original game view 1080 x 1890, half size
        public int captureSS = 2;                                // samples per pixel = captureSS^2 (true supersampling)
        public float captureFps = -1f; public int captureJpg = 0;
        Texture2D arrow;

        /// The mouse pointer of the recorded session, drawn into the captured frame (the OS cursor is not in a render).
        void DrawCursor()
        {
            Vector2 c = CursorAt(T, out bool vis);
            if (!vis) return;
            if (!arrow) arrow = SheerUI.ArrowTexture();
            float k = captureWidth / 1080f * 1.15f; int w = Mathf.CeilToInt(13f * k), h = Mathf.CeilToInt(21f * k);
            int x0 = Mathf.RoundToInt(c.x * captureWidth), y0 = Mathf.RoundToInt((1f - c.y) * captureHeight);     // the tip: top-left of the arrow
            for (int j = 0; j < h; j++)
                for (int i = 0; i < w; i++)
                {
                    int x = x0 + i, y = y0 - j;
                    if (x < 0 || y < 0 || x >= captureWidth || y >= captureHeight) continue;
                    Color a = arrow.GetPixelBilinear((i + 0.5f) / w, 1f - (j + 0.5f) / h);
                    if (a.a <= 0.01f) continue;
                    Color b = capTex.GetPixel(x, y);
                    capTex.SetPixel(x, y, Color.Lerp(b, new Color(a.r, a.g, a.b, 1f), a.a));
                }
        }

        static RenderTexture CapTarget(int w, int h, int depth) =>
            new RenderTexture(w, h, depth, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB) { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp };

        void CaptureOffscreen(string file)
        {
            var cam = rig.GetComponent<Camera>();
            if (!capRT)
            {
                capRT = CapTarget(captureWidth * captureSS, captureHeight * captureSS, 24);
                if (captureSS > 1) capOut = CapTarget(captureWidth, captureHeight, 0);
                if (captureSS >= 4 && captureSS % 4 == 0) capHalf = CapTarget(captureWidth * captureSS / 2, captureHeight * captureSS / 2, 0);
                capTex = new Texture2D(captureWidth, captureHeight, TextureFormat.RGB24, false);
            }
            var prev = cam.targetTexture;
            cam.targetTexture = capRT;
            Shader.SetGlobalFloat("_SheerPixelScale", captureSS);
            cam.Render();
            cam.targetTexture = prev;
            // box filter down in linear light (sRGB targets: the sampler decodes, the write encodes); a bilinear tap between
            // four texels is their mean, so every halving is exact
            var src = capRT;
            if (capHalf) { Graphics.Blit(src, capHalf); src = capHalf; }
            if (capOut) { Graphics.Blit(src, capOut); src = capOut; }
            var active = RenderTexture.active;
            RenderTexture.active = src;
            capTex.ReadPixels(new Rect(0, 0, captureWidth, captureHeight), 0, 0); capTex.Apply();
            RenderTexture.active = active;
            if (file != null)
            {
                DrawCursor();
                // (-sheerCapJpg Q: frames as JPEG - a 60 fps capture of the session is 2172 frames)
                if (captureJpg > 0) File.WriteAllBytes(Path.ChangeExtension(file, ".jpg"), capTex.EncodeToJPG(captureJpg));
                else File.WriteAllBytes(file, capTex.EncodeToPNG());
            }
        }

        // the click on VIEW 02 (~24.2 s): the cursor travels to the button, presses, leaves (tools/composite.py)
        Vector2 CursorAt(float t, out bool vis)
        {
            var c = S.clickView02;
            Vector2 b = new Vector2((0.049f + 0.21f) / 2 + 0.02f, (0.939f + 0.965f) / 2 + 0.004f);
            vis = true;
            if (t >= c.leave && t <= c.back)
            {
                if (t < c.reach) { float k = Smooth((t - c.leave) / (c.reach - c.leave)); return Vector2.Lerp(new Vector2(0.54f, 0.83f), b, k); }
                if (t < c.release) return b;
                float k2 = Smooth((t - c.release) / (c.back - c.release)); return Vector2.Lerp(b, new Vector2(0.334f, 0.85f), k2);
            }
            vis = t < 0 || S.Visible(t);
            Vector2 cur = S.Cursor(t);
            foreach (var a in act)
            {
                if (a.cOff == Vector2.zero) continue;
                float w = Smooth((t - a.pr.t0) / 0.12f) * (1f - Smooth((t - a.pr.t1) / 0.25f));
                cur += a.cOff * w;
            }
            return cur;
        }
        static float Smooth(float x) { x = Mathf.Clamp01(x); return x * x * (3 - 2 * x); }
    }
}
