// SHEER — the two camera views of the original (VIEW 01: the whole legs, VIEW 02: close on the feet),
// smooth switch between them (1.3 s smootherstep, like the original), player orbit (right drag) and
// zoom (wheel), physical-camera depth of field. Positions come from the shot-matched Blender cameras
// (Unity axes: x = Blender x, y = Blender z, z = Blender y).
using UnityEngine;

namespace Sheer
{
    [RequireComponent(typeof(Camera))]
    public class CameraRig : MonoBehaviour
    {
        [System.Serializable]
        public struct View { public string name; public Vector3 position, target; public float lensMM, fStop, focusDistance; }

        public View[] views =
        {
            // joint fit over 0.1/2.2/10/20 s (tools/fit_camera_joint.py), then 9.9 mm to the left: two of those frames have the body
            // leaning ~3 deg to the left, which the fit had absorbed as a shift (outlines at rest - 1.0 / 7.0 / 16.0 s - were 36 px off)
            new View { name = "VIEW 01", position = new Vector3(0.0778f, 0.4921f, -1.2622f), target = new Vector3(0.0947f, 0.5604f, -0.0082f), lensMM = 87.11f, fStop = 8f, focusDistance = 1.1993f },
            new View { name = "VIEW 02", position = new Vector3(-0.0495f, 0.1862f, -1.1030f), target = new Vector3(-0.0488f, 0.1638f, 0.0114f), lensMM = 86.42f, fStop = 11f, focusDistance = 1.1318f },   // fitted to the original (tools/fit_camera.py)
        };
        public float switchSeconds = 1.3f;
        public float aspect = 1890f / 1080f;            // the original window; rays for the replay use it
        [Header("Player camera")] public bool playerControl = true;
        public float orbitYawLimit = 55f, orbitPitchLimit = 12f, dollyMin = 0.6f, dollyMax = 1.25f;
        // orbit pivot on the view axis, x the target distance. The original's three camera moves are ~45 deg orbits (at
        // 8.6 s the hole column on the front of the thigh sits at the left edge of the silhouette and the hollow of the knee
        // shows on the right) that slide the leg 66 mm to the left: a pivot ~9 cm behind the leg.
        public float orbitPivotDepth = 1.074f;

        public int current { get; private set; }
        int from; float switchT0 = -10f;
        public float orbitYaw, orbitPitch, dolly = 1f;   // player (or replay) offsets
        float yawVel, pitchVel, dollyVel, yawGoal, pitchGoal, dollyGoal = 1f;
        Camera cam;

        void Awake()
        {
            cam = GetComponent<Camera>(); cam.usePhysicalProperties = true; cam.gateFit = Camera.GateFitMode.Vertical; Apply();
            // (dithered output: the backdrop's gradient showed 1-level banding, review round 7)
            var hd = GetComponent<UnityEngine.Rendering.HighDefinition.HDAdditionalCameraData>(); if (hd) hd.dithering = true;
            // (captures in batch mode render through ReplayDriver.CaptureOffscreen, which supersamples on its own)
            if (Application.isPlaying && !Application.isBatchMode && !GetComponent<SheerSuperSample>()) gameObject.AddComponent<SheerSuperSample>();
        }

        /// the camera's clock: real time in play (orbit, zoom and view blends work while the scene is paused or slowed - the
        /// Studio's bullet time), game time in captures and batch runs (frame-exact, as the replay's evaluations need)
        static bool GameClock => Application.isBatchMode || Time.captureFramerate > 0;
        static float Now => GameClock ? Time.time : Time.unscaledTime;
        static float Dt => GameClock ? Time.deltaTime : Time.unscaledDeltaTime;

        public void SwitchTo(int v, bool instant = false)
        {
            if (v == current && Now - switchT0 > switchSeconds) { yawGoal = pitchGoal = 0; dollyGoal = 1; return; }
            from = instant ? v : current; current = v; switchT0 = instant ? -1e6f : Now;
            yawGoal = pitchGoal = 0; dollyGoal = 1;
            if (instant) { orbitYaw = orbitPitch = 0; dolly = 1; }
        }

        static float Smoother(float x) { x = Mathf.Clamp01(x); return x * x * x * (x * (x * 6 - 15) + 10); }

        /// Camera parameters for a blend between views (w = 0..1) plus orbit/dolly offsets.
        public void Params(int a, int b, float w, float yaw, float pitch, float k, out Vector3 loc, out Vector3 tgt, out float lens, out float focus, out float fstop)
        {
            View A = views[a], B = views[b];
            loc = Vector3.Lerp(A.position, B.position, w); tgt = Vector3.Lerp(A.target, B.target, w);
            lens = Mathf.Lerp(A.lensMM, B.lensMM, w); focus = Mathf.Lerp(A.focusDistance, B.focusDistance, w); fstop = Mathf.Lerp(A.fStop, B.fStop, w);
            rigYaw = yaw; rigPivot = loc + (tgt - loc) * orbitPivotDepth;
            if (yaw == 0 && pitch == 0 && k == 1f) return;
            // orbit / zoom about a pivot on the view axis BEHIND the framed leg (orbitPivotDepth x the target distance): fitted
            // to the original's camera moves (at 8.8 s the recorded 12 deg / 0.86 reproduce the leg's silhouette and its hole
            // column only with the pivot ~24 cm behind the leg; pivoting on the leg kept it centred, the original slides left)
            Vector3 pivot = loc + (tgt - loc) * orbitPivotDepth;
            float Dp = (pivot - loc).magnitude;
            Vector3 d = loc - pivot;
            if (yaw != 0)
            {
                // same sense as the Blender rig's orbit about +Z (Unity: about +Y, mirrored axes)
                float ang = yaw * Mathf.Deg2Rad, c = Mathf.Cos(ang), s = Mathf.Sin(ang);
                d = new Vector3(d.x * c - d.z * s, d.y, d.x * s + d.z * c);
            }
            if (pitch != 0) d = Quaternion.AngleAxis(pitch, Vector3.Cross(Vector3.up, d).normalized) * d;
            loc = pivot + d * k; tgt = pivot; focus += (k - 1f) * Dp;
        }

        /// The Studio's light controls: the key light turned about the character (KeyPivot), the side fill and orbit rim scaled.
        public static Quaternion KeyTurn = Quaternion.identity;
        public static Vector3 KeyPivot = new Vector3(0f, 0.42f, 0f);
        public static float SideFillMul = 1f, OrbitRimMul = 1f;
        /// Studio: f-number for the photo mode's depth of field (0 = the view's own)
        public static float ApertureOverride = 0f;
        bool dragFromUi;
        public static bool Turntable; float turnT;

        void Update()
        {
            if (playerControl)
            {
                // (not while the pointer works the Studio panel: its scroll wheel / drags are the panel's)
                bool overUi = UnityEngine.EventSystems.EventSystem.current != null && UnityEngine.EventSystems.EventSystem.current.IsPointerOverGameObject();
                if (Input.GetMouseButtonDown(1)) dragFromUi = overUi;
                if (Input.GetMouseButton(1) && !dragFromUi)
                {
                    yawGoal = Mathf.Clamp(yawGoal + Input.GetAxis("Mouse X") * 2.0f, -orbitYawLimit, orbitYawLimit);
                    pitchGoal = Mathf.Clamp(pitchGoal - Input.GetAxis("Mouse Y") * 1.2f, -orbitPitchLimit, orbitPitchLimit);
                }
                // TURNTABLE (the Studio's camera tab): a slow sweep round her and back, within the orbit's range; a right drag
                // takes over (and the sweep carries on from there when it is let go)
                if (Turntable && !Input.GetMouseButton(1))
                {
                    turnT += Time.unscaledDeltaTime;
                    yawGoal = orbitYawLimit * 0.8f * Mathf.Sin(turnT * 2f * Mathf.PI / 16f); pitchGoal = orbitPitchLimit * 0.35f * Mathf.Sin(turnT * 2f * Mathf.PI / 11f);
                }
                float wheel = overUi ? 0f : Input.mouseScrollDelta.y;
                if (wheel != 0) dollyGoal = Mathf.Clamp(dollyGoal * Mathf.Pow(0.93f, wheel), dollyMin, dollyMax);
                orbitYaw = Mathf.SmoothDamp(orbitYaw, yawGoal, ref yawVel, 0.12f, Mathf.Infinity, Dt);
                orbitPitch = Mathf.SmoothDamp(orbitPitch, pitchGoal, ref pitchVel, 0.12f, Mathf.Infinity, Dt);
                dolly = Mathf.SmoothDamp(dolly, dollyGoal, ref dollyVel, 0.15f, Mathf.Infinity, Dt);
            }
            Apply();
        }

        public void Apply()
        {
            float w = Smoother((Now - switchT0) / switchSeconds);
            Params(from, current, w, orbitYaw, orbitPitch, dolly, out var loc, out var tgt, out var lens, out var focus, out var fstop);
            ApplyParams(loc, tgt, lens, focus, fstop);
        }

        public void ApplyParams(Vector3 loc, Vector3 tgt, float lens, float focus, float fstop)
        {
            if (!cam) cam = GetComponent<Camera>();
            transform.position = loc;
            transform.rotation = Quaternion.LookRotation(tgt - loc, Vector3.up);
            cam.sensorSize = new Vector2(36f * aspect, 36f);
            cam.focalLength = lens;
            cam.aperture = ApertureOverride > 0f ? ApertureOverride : fstop;
            cam.focusDistance = focus;
            // The lights go round with the camera when it orbits (review round 6: in the original's orbit views the leg keeps
            // its front-view lighting - key from the front left, the cyan rim on the right-hand outline, the edges going
            // dark - so its rig turns with the view; ours stayed put, the rim never grazed the visible outline and the leg
            // read as tinted skin). About the vertical through the orbit pivot, by the same angle as the camera.
            if (rigLights == null)
            {
                rigLights = new System.Collections.Generic.List<(Light l, Vector3 p, Quaternion r)>();
                foreach (var l in FindObjectsByType<Light>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                {
                    if (l.name == "sidefill" || l.type == LightType.Directional) continue;
                    // (the cyan rim aimed 3.5 cm further toward the hero leg: centred between the legs, its cone washed the
                    //  far leg's inner side 30 - 40 px wide - the original has a 5 - 11 px rim there, review round 6)
                    if (l.name == "rim" && rimAim != Vector3.zero) l.transform.rotation = Quaternion.LookRotation(rimAim - l.transform.position, Vector3.up);
                    // (the rim casts shadows: it stands behind the leg, and without them it lit the walls of a fold on the FRONT
                    //  of the thigh through the leg - a straight teal line along the crease of the 2.7 - 3.9 s funnel, review
                    //  round 13. The orbit rim, cloned below, inherits them)
                    // (only the BODY casts them - its own layer bit 5: with the skirt casting too, the hem cut the rim off the
                    //  thigh's outline right below it, where the original has its strongest teal rim)
                    if (l.name == "rim")
                    {
                        l.shadows = rimShadowRes > 0f ? LightShadows.Soft : LightShadows.None;
                        foreach (var r in FindObjectsByType<MeshRenderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                            if (r.name == "Body") r.renderingLayerMask |= 1u << 5;
                        var hd = l.GetComponent<UnityEngine.Rendering.HighDefinition.HDAdditionalLightData>();
                        // (dimmed to 0.85: the original keeps a thin rim on the far leg's inner edge, which the near leg shades)
                        if (hd != null)
                        {
                            var lm = hd.lightlayersMask; hd.SetLightLayer(lm, (UnityEngine.Rendering.HighDefinition.RenderingLayerMask)(1 << 5)); hd.shadowDimmer = 0.85f;
                            if (rimShadowRes >= 16f) { hd.SetShadowResolutionOverride(true); hd.SetShadowResolution((int)rimShadowRes); }
                            if (rimNormalBias >= 0f) hd.normalBias = rimNormalBias;
                            // (a light of some SIZE: as a point the cyan rim was a 3 px neon line on the near leg's outline - the
                            //  original's is a soft teal sheen ~20 px wide that shows the knit through it, review 14; the cone
                            //  is unchanged, so the far leg does not wash teal as a wider cone did, round 12)
                            if (rimRadius > 0f) hd.shapeRadius = rimRadius;
                            if (rimSlopeBias >= 0f) hd.slopeBias = rimSlopeBias;
                        }
                    }
                    // (round 12: the original's rim runs down the thigh's outline toward the knee - ours was a patch under the hem)
                    // (a wider cone - tried 19 deg - washed the far leg's whole side teal: the cone stays, aimed a little lower)
                    rigLights.Add((l, l.transform.position, l.transform.rotation));
                    // the orbit rim: a copy of the cyan rim aimed at the back of the knee with a wider cone, faded in as the
                    // camera goes round (review round 9: the original's orbit views keep a cyan rim and sheen all down the
                    // back outline and on the knee-pit folds; ours went pure black there). Off from the front.
                    if (l.name == "rim" && orbitRim == null)
                    {
                        orbitRim = Instantiate(l.gameObject, l.transform.parent).GetComponent<Light>();
                        orbitRim.name = "orbitrim"; orbitRimBase = l.intensity;
                        orbitRim.spotAngle = 52f; orbitRim.innerSpotAngle = 30f;
                        // (further behind the leg than the rim: from the side it lit a 32 px band, the original's is ~12 px)
                        var yb = Quaternion.AngleAxis(-18f, Vector3.up); var pv = new Vector3(0.1f, 0f, 0f);
                        orbitRim.transform.position = pv + yb * (orbitRim.transform.position - pv);
                        orbitRim.transform.rotation = Quaternion.LookRotation(new Vector3(0.12f, 0.56f, 0.02f) - orbitRim.transform.position, Vector3.up);
                        orbitRim.intensity = 0f;
                        orbitRim.color = new Color(0.35f, 0.78f, 0.88f);       // (round 10: pure turquoise band; the original's is a grey-cyan sheen)
                        // (the legs only: it put a teal sheen on the skirt's panels in the orbits)
                        var hdo = orbitRim.GetComponent<UnityEngine.Rendering.HighDefinition.HDAdditionalLightData>();
                        if (hdo) hdo.lightlayersMask = (UnityEngine.Rendering.HighDefinition.RenderingLayerMask)(1u << 2);
                    }
                }
                if (orbitRim) rigLights.Add((orbitRim, orbitRim.transform.position, orbitRim.transform.rotation));
            }
            if (rigFollow)
            {
                // (half the way round: turned fully with the view the leg was lit flat from the eye in the orbit views -
                //  5 - 95 % brightness spread 10 - 30 levels vs the original's 54 - 76, review round 8; fixed, the far half
                //  went black)
                Quaternion R = Quaternion.AngleAxis(-rigYaw * rigFollowFrac, Vector3.up);
                // (the rim all the way round: it stays on the outline the camera sees - turned with the rest only 30 % it left
                //  the back of the leg a 30 px pure-black band in the orbits, where the original keeps a cyan rim and sheen
                //  on the knee-pit folds, review round 9)
                Quaternion Rr = Quaternion.AngleAxis(-rigYaw, Vector3.up);
                foreach (var e in rigLights)
                {
                    if (!e.l) continue;
                    var q = e.l.name == "rim" || e.l.name == "rim3" || e.l.name == "orbitrim" ? Rr : R;
                    Vector3 bp = e.p; Quaternion br = e.r;
                    if (e.l.name == "key") { bp = KeyPivot + KeyTurn * (e.p - KeyPivot); br = KeyTurn * e.r; }
                    e.l.transform.SetPositionAndRotation(rigPivot + q * (bp - rigPivot), q * br);
                }
            }
            else
                foreach (var e in rigLights)
                    if (e.l && e.l.name == "key") e.l.transform.SetPositionAndRotation(KeyPivot + KeyTurn * (e.p - KeyPivot), KeyTurn * e.r);
            // The side fill comes up as the camera goes round to the right: from there the far side of the legs is what the
            // key light never reaches (the original's side view at 8.6 s keeps 60 - 75 % of the front's brightness; ours was
            // black). From the front it is off - it would lift the right-hand outline the look was calibrated on.
            if (!sideFill && !sideFillSearched)
            {
                sideFillSearched = true;
                foreach (var l in FindObjectsByType<Light>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                    if (l.name == "sidefill") { sideFill = l; sideFillBase = l.intensity; }
            }
            if (sideFill)
            {
                // (it rides with the camera, up and to the left of it: from the right-hand side of the stage it lit the
                //  orbit views' near outline more than the leg's middle - a pale halo where the original's nylon goes dark
                //  toward the edge, review round 5)
                Vector3 fw = (tgt - loc).normalized, rt = Vector3.Cross(Vector3.up, fw).normalized;
                sideFill.transform.position = loc + rt * sideFillOffset + Vector3.up * 0.30f;
                sideFill.transform.rotation = Quaternion.LookRotation(tgt - sideFill.transform.position, Vector3.up);
                Vector3 f = tgt - loc; float yaw = Mathf.Abs(Mathf.Atan2(f.x, f.z) * Mathf.Rad2Deg);
                float q = Mathf.Clamp01((yaw - 6f) / 30f);
                sideFill.intensity = sideFillBase * sideFillGain * q * q * (3f - 2f * q) * SideFillMul;
                if (orbitRim) orbitRim.intensity = orbitRimBase * orbitRimGain * q * q * (3f - 2f * q) * OrbitRimMul;
            }
        }
        Light sideFill; float sideFillBase; bool sideFillSearched;
        Light orbitRim; float orbitRimBase;
        public static float orbitRimGain = RigArg("-sheerOrbitRim", 0.3f);
        /// experiments: the cyan rim's shadow map (resolution in texels, 0 = no shadows, 1 = the quality tier's; biases < 0 =
        /// HDRP's own)
        public static float rimShadowRes = RigArg("-sheerRimShadowRes", 1f), rimNormalBias = RigArg("-sheerRimNormalBias", -1f),
                            rimSlopeBias = RigArg("-sheerRimSlopeBias", -1f), rimRadius = RigArg("-sheerRimRadius", 0.12f);
        System.Collections.Generic.List<(Light l, Vector3 p, Quaternion r)> rigLights; float rigYaw; Vector3 rigPivot;
        [Tooltip("Where the cyan rim light aims (world; zero = as placed in the scene).")]
        public Vector3 rimAim = new Vector3(0.135f, 0.70f, 0f);
        /// experiments: -sheerRigFixed keeps the lights in place when the camera orbits
        public static bool rigFollow = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerRigFixed") < 0;
        public static float rigFollowFrac = RigArg("-sheerRigFrac", 0.3f);
        static float RigArg(string name, float def)
        {
            var a = System.Environment.GetCommandLineArgs(); int i = System.Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length && float.TryParse(a[i + 1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : def;
        }
        /// experiments: -sheerSideFill GAIN scales the side fill
        // (0.5 m to the camera's right, x0.8: at 8.6 s the thigh then reads 40 / 55 / 58 / 83 from its outline inward like the
        //  original's - ours was 79 at the outline from the stage-right position, 8 with the light on the camera's left)
        // (off since the whole rig turns with the camera, review round 6)
        public static float sideFillGain = SideFillArg("-sheerSideFill", 0.7f), sideFillOffset = SideFillArg("-sheerSideFillX", 0.5f);
        static float SideFillArg(string key, float def)
        {
            var a = System.Environment.GetCommandLineArgs();
            for (int i = 0; i + 1 < a.Length; i++) if (a[i] == key) return float.Parse(a[i + 1], System.Globalization.CultureInfo.InvariantCulture);
            return def;
        }

        /// World ray through normalized original-window coordinates (x right, y down from the top),
        /// independent of the actual window aspect (as in the Blender replay).
        public static Ray RayThrough(Vector3 loc, Vector3 tgt, float lens, float aspect, float x, float y)
        {
            Vector3 f = (tgt - loc).normalized;
            Vector3 r = Vector3.Cross(Vector3.up, f).normalized;       // camera right (left-handed)
            Vector3 u = Vector3.Cross(f, r);
            float k = lens / 36f;
            float sx = (x - 0.5f) / (aspect * k), sy = (0.5f - y) / k;
            return new Ray(loc, (f + r * sx + u * sy).normalized);
        }
    }
}
