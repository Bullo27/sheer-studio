// SHEER — builds the playable scene from the exported data (meshes in StreamingAssets, lights in Data/scene_lights.json),
// creates the materials from the Sheer Shader Graphs, the HDRP volume (fixed exposure matched to Cycles, physical DOF,
// dim cool ambient), the camera rig, backdrop, UI and simulation objects. Also a batch-mode look-dev capture.
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.SceneBuilder.Build -quit
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.SceneBuilder.CaptureViews -quit
using System.IO;
using Sheer;
using UnityEditor;
using UnityEditor.Rendering.HighDefinition;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;
using HDLayers = UnityEngine.Rendering.HighDefinition.RenderingLayerMask;

namespace SheerEditor
{
    public static class SceneBuilder
    {
        public const string ScenePath = "Assets/Sheer/Scenes/Sheer.unity";
        const string MatDir = "Assets/Sheer/Materials", SettingsDir = "Assets/Sheer/Settings";
        const string SkinProfileGuid = "404820c4cf36ad944862fa59c56064f0";      // HDRP package SkinDiffusionProfile.asset
        // rendering layers (Blender light linking): 0 everything, 1 character, 2 legs, 3 floor
        const uint L_ALL = 1u << 0, L_CHAR = 1u << 1, L_LEGS = 1u << 2, L_FLOOR = 1u << 3;
        // 4 = fabric lit by the back rims (stocking, skirt): the rims are far too strong for bare skin facing them (the other
        // leg's inner thigh blew out to white through the nylon)
        const uint L_RIM = 1u << 4;

        [System.Serializable] class LightSpec { public string name; public float[] position, forward, up, color; public float lumen, width, height, spreadDeg, barnDoorLength; public uint layerMask; public bool enabled; }
        [System.Serializable] class LightFile { public LightSpec[] lights; public float blenderExposure, lumenPerWatt; }

        static Vector3 V(float[] a) => new Vector3(a[0], a[1], a[2]);

        // per-light calibration against the original video (bare skin in holes and the floor cloth matched in both
        // views); "name=k,name=k" in SHEER_LIGHT_CAL overrides for experiments
        static float LightCal(string name)
        {
            // fitted (tools/fit_lights_skin.py) to the bare skin in the original's holes at 10 / 23.5 s (VIEW 01) and 26.5 / 33 s
            // (VIEW 02), ~18k px, and to the white drop cloth: one scale for the character lights keeps the Blender balance
            // rims x4 on top: the original's back-lit teal line along the leg silhouettes (sh2v1 / strip sweeps)
            // low fill x5 / fill x1.5 on top: the original's lower legs (VIEW 02) are as bright as its thighs (luma profiles)
            // rims x20 of the base scale: the original's teal line along the right silhouettes of both legs (rimo sweep: ~2000 px)
            var cal = new System.Collections.Generic.Dictionary<string, float> { { "key", 0.228f }, { "fill", 0.405f }, { "lowfill", 1.55f }, { "rim", 1.5f }, { "rim3", 0f }, { "top", 0.95f }, { "sidefill", 0.7f } };
            // (2026-11-14 night, fit of the leg's colour profile at 0.5 s, 5 points across the leg at 4 heights, rms 19 -> 11.7:
            //  key 15 deg back toward the left, wider (2.2 x 1.7 m) and x0.82: the original's thigh is bright from 30 % to 70 %
            //  of its width, ours had a narrow central ridge. rim3 off: the original has no teal line along knee / shin.)
            var env = System.Environment.GetEnvironmentVariable("SHEER_LIGHT_CAL");
            if (!string.IsNullOrEmpty(env))
                foreach (var kv in env.Split(',')) { var p = kv.Split('='); if (p.Length == 2) cal[p[0]] = float.Parse(p[1], System.Globalization.CultureInfo.InvariantCulture); }
            return cal.TryGetValue(name, out var k) ? k : 1f;
        }

        static Material Mat(string graph, string name)
        {
            Directory.CreateDirectory(MatDir);
            string path = MatDir + "/" + name + ".mat";
            var shader = AssetDatabase.LoadAssetAtPath<Shader>("Assets/Sheer/Graphs/" + graph + ".shadergraph");
            if (!shader) throw new System.Exception("missing graph " + graph);
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            var fresh = new Material(shader);                      // property values = the graph's current defaults
            if (m == null) { m = fresh; AssetDatabase.CreateAsset(m, path); }
            else { EditorUtility.CopySerialized(fresh, m); m.name = name; }   // keep the asset (scene references), drop stale values
            HDMaterial.ValidateMaterial(m);                     // HDRP keywords / passes for the graph's settings
            EditorUtility.SetDirty(m);
            return m;
        }

        static GameObject MeshObject(string name, Transform parent, string file, Material mat, int submeshes, uint layers, bool dynamicStretch = false)
        {
            var go = new GameObject(name);
            go.SetActive(false);                                  // OnEnable must see the right file
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>();
            var mr = go.AddComponent<MeshRenderer>();
            var mats = new Material[submeshes]; for (int i = 0; i < submeshes; i++) mats[i] = mat;
            mr.sharedMaterials = mats;
            mr.renderingLayerMask = layers;
            var src = go.AddComponent<SheerMeshSource>();
            src.file = file; src.dynamicStretchUV3 = dynamicStretch;
            go.SetActive(true);
            return go;
        }

        [MenuItem("Sheer/Build Scene")]
        public static void Build()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
            Directory.CreateDirectory(SettingsDir);
            var spec = JsonUtility.FromJson<LightFile>(File.ReadAllText("Assets/Sheer/Data/scene_lights.json"));

            // ---- materials
            var tightsGraph = System.Environment.GetEnvironmentVariable("SHEER_TIGHTS_GRAPH");
            var mTights = Mat(string.IsNullOrEmpty(tightsGraph) ? "SheerTights" : tightsGraph, "Pantyhose");
            var mSkin = Mat("SheerSkin", "Skin");
            var mSkirt = Mat("SheerSkirtFabric", "Skirt");
            var mFloor = Mat("SheerFloor", "DropCloth");
            var mBack = Mat("SheerBackdrop", "Backdrop");

            // ---- character
            var root = new GameObject("Character").transform;
            var body = MeshObject("Body", root, "body.smesh", mSkin, 1, L_ALL | L_CHAR | L_LEGS);
            var tights = MeshObject("Pantyhose", root, "tights.smesh", mTights, 2, L_ALL | L_CHAR | L_LEGS | L_RIM, dynamicStretch: true);
            var floor = MeshObject("DropCloth", null, "floor.smesh", mFloor, 1, L_ALL | L_FLOOR);
            // the original's drop cloth ends ~0.70 m behind the feet (its far edge sits at 70 % of the VIEW 02 frame height;
            // ours at 0.95 m sat at 66 %): compress the depth behind the character
            floor.transform.localScale = new Vector3(1f, 1f, 0.74f);
            var skirtGo = new GameObject("Skirt");
            skirtGo.transform.SetParent(root, false);
            var smr = skirtGo.AddComponent<SkinnedMeshRenderer>();
            smr.sharedMaterial = mSkirt; smr.renderingLayerMask = L_ALL | L_CHAR | L_RIM;
            var skirt = skirtGo.AddComponent<SkirtCloth>();

            // sheer nylon 0.6 mm above the skin must not shadow it opaquely (HDRP transparents cast solid shadows)
            tights.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;
            // optional fibre-sheen pass (additive Fabric, same mesh): OFF - a Charlie sheen lobe brightens every silhouette under the
            // front lights, while the original's leg edges stay dark with only the back-lit teal line (measured, sh2v1 sweep)
            Renderer sheenMr = null;
            if (System.Environment.GetEnvironmentVariable("SHEER_SHEEN_PASS") == "1")
            {
                var mSheen = Mat("SheerTightsSheen", "PantyhoseSheen");
                mSheen.SetFloat("_TransparentSortPriority", 1f);
                UnityEngine.Rendering.HighDefinition.HDMaterial.ValidateMaterial(mSheen);
                var sheenGo = new GameObject("PantyhoseSheen");
                sheenGo.transform.SetParent(tights.transform, false);
                sheenGo.AddComponent<MeshFilter>();
                var sheenRend = sheenGo.AddComponent<MeshRenderer>();
                sheenRend.sharedMaterials = new[] { mSheen, mSheen };
                sheenRend.renderingLayerMask = L_ALL | L_CHAR | L_LEGS | L_RIM;
                sheenRend.shadowCastingMode = ShadowCastingMode.Off;
                sheenGo.AddComponent<SheerMeshMirror>().source = tights.GetComponent<SheerMeshSource>();
                sheenMr = sheenRend;
            }
            var tension = tights.AddComponent<TensionData>();
            tension.pantyhoseRenderers = sheenMr ? new Renderer[] { tights.GetComponent<MeshRenderer>(), sheenMr } : new Renderer[] { tights.GetComponent<MeshRenderer>() };
            tension.skinRenderers = new Renderer[] { body.GetComponent<MeshRenderer>() };

            var simGo = new GameObject("Simulation");
            var sim = simGo.AddComponent<TightsSim>();
            sim.tights = tights.GetComponent<SheerMeshSource>();
            sim.sheenRenderer = sheenMr;
            sim.body = body.GetComponent<SheerMeshSource>();
            sim.damageRaster = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/Sheer/Shaders/DamageRaster.compute");
            sim.clothCompute = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/Sheer/Shaders/SheerCloth.compute");
            if (!sim.clothCompute) throw new System.Exception("missing Assets/Sheer/Shaders/SheerCloth.compute");
            skirt.sim = sim;

            // ---- camera (VIEW 01), backdrop
            var camGo = new GameObject("Main Camera") { tag = "MainCamera" };
            var cam = camGo.AddComponent<Camera>();
            var hdCam = camGo.AddComponent<HDAdditionalCameraData>();
            cam.nearClipPlane = 0.05f; cam.farClipPlane = 40f;
            cam.usePhysicalProperties = true; cam.gateFit = Camera.GateFitMode.Vertical;
            // Anti-aliasing = real supersampling (SheerSuperSample in the player, -sheerCapSS in captures) + SMAA on what is
            // left. Temporal AA needed a sharpening pass to keep the knit crisp, and that pass drew a dark, stair-stepped
            // halo along every silhouette and round every hole (review round 3); without it TAA was soft.
            hdCam.antialiasing = HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            hdCam.SMAAQuality = HDAdditionalCameraData.SMAAQualityLevel.High;
            // (kept for -sheerAA 2: gentle settings, no contrast-adaptive sharpening)
            hdCam.TAAQuality = HDAdditionalCameraData.TAAQualityLevel.High;
            hdCam.taaSharpenMode = HDAdditionalCameraData.TAASharpenMode.LowQuality;
            hdCam.taaSharpenStrength = 0.2f;
            hdCam.taaHistorySharpening = 0.2f;
            hdCam.taaAntiHistoryRinging = true;
            var rig = camGo.AddComponent<CameraRig>();
            rig.Params(0, 0, 1f, 0, 0, 1f, out var loc, out var tgt, out var lens, out var focus, out var fstop);
            rig.ApplyParams(loc, tgt, lens, focus, fstop);
            var input = camGo.AddComponent<SheerInput>();
            input.sim = sim; input.cam = cam;
            var replay = camGo.AddComponent<ReplayDriver>();
            replay.sim = sim; replay.rig = rig; replay.input = input; replay.skirt = skirt;

            var back = GameObject.CreatePrimitive(PrimitiveType.Quad);
            back.name = "Backdrop";
            Object.DestroyImmediate(back.GetComponent<Collider>());
            back.transform.SetParent(camGo.transform, false);
            back.transform.localPosition = new Vector3(0, 0, 12f);
            back.transform.localScale = new Vector3(16f, 9f, 1f);
            var br = back.GetComponent<MeshRenderer>();
            br.sharedMaterial = mBack; br.shadowCastingMode = ShadowCastingMode.Off; br.receiveShadows = false;
            br.renderingLayerMask = L_ALL;                       // mask 0 would filter it out of every draw

            // ---- UI
            var uiGo = new GameObject("UI");
            var ui = uiGo.AddComponent<SheerUI>();
            ui.rig = rig; ui.tension = tension; ui.sim = sim;
            replay.ui = ui;

            // ---- lights (Blender area lights, linked through rendering layers)
            var lightsRoot = new GameObject("Lights").transform;
            foreach (var L in spec.lights)
            {
                var go = new GameObject(L.name);
                go.transform.SetParent(lightsRoot, false);
                go.transform.SetPositionAndRotation(V(L.position), Quaternion.LookRotation(V(L.forward), V(L.up)));
                // key orbited +20 deg (to the camera's azimuth): the original's thigh is dark at BOTH silhouettes with a centred
                // peak (luma profile across the thigh, VIEW 01 and VIEW 02); from 20 deg left of the camera it lit the inner thigh
                // (2026-11-15: 14 deg further toward the right. Refitted at 7.0 s with the body at rest and the camera corrected:
                //  the original's thigh and shin are equally bright left and right of their middle, ours were +10 / -10 levels)
                if (L.name == "key") { var yaw = Quaternion.AngleAxis(-19f, Vector3.up); go.transform.SetPositionAndRotation(yaw * go.transform.position, yaw * go.transform.rotation); }
                // floor light (floor layer only): small and low in front of the feet - the original's drop cloth is white around
                // the feet and falls off to blue-grey towards its far edge (the large overhead panel lit it uniformly)
                if (L.name == "top")
                {
                    go.transform.position = new Vector3(0f, 0.35f, -0.8f);
                    go.transform.rotation = Quaternion.LookRotation(new Vector3(0f, 0f, -0.35f) - go.transform.position, Vector3.up);
                }
                // rims: 20 deg further to the right behind the legs (the original lights the right silhouettes of both legs)
                if (L.name == "rim" || L.name == "rim3") { var yaw = Quaternion.AngleAxis(20f, Vector3.up); go.transform.SetPositionAndRotation(yaw * go.transform.position, yaw * go.transform.rotation); }
                // rim: at thigh height behind-right, aimed at the hero thigh -> the original's teal line along its right silhouette
                // (rimkey sweep: 1296 teal px there vs the original's 1180; from 0.95 m it lit the skirt instead)
                if (L.name == "rim") go.transform.SetPositionAndRotation(new Vector3(1.0f, 0.6f, 1.1f), Quaternion.LookRotation(new Vector3(0.09f, 0.6f, 0f) - new Vector3(1.0f, 0.6f, 1.1f), Vector3.up));
                // low fill: +23 deg towards the camera axis and 14 deg lower (shins / calves, VIEW 02 profile)
                if (L.name == "lowfill")
                {
                    var yaw = Quaternion.AngleAxis(-23f, Vector3.up);
                    var p = yaw * go.transform.position; var r = yaw * go.transform.rotation;
                    var axis = Vector3.Cross(Vector3.up, new Vector3(p.x, 0, p.z)).normalized;
                    var pitch = Quaternion.AngleAxis(14f, axis);
                    go.transform.SetPositionAndRotation(pitch * p, pitch * r);
                }
                // rim: a narrow spot from behind-right at hip height. In the original the teal rim light only touches the upper
                // thighs right below the skirt and the skirt's right edge (teal mask of 8 frames: nothing below mid-thigh,
                // nothing in VIEW 02), and it lights the SKIN under the nylon: the band of nylon beyond the skin's outline
                // stays dark. (The area light from 0.6 m drew a teal line along both legs down to the shin.)
                bool spot = L.name == "rim";
                if (spot)
                {
                    var from = new Vector3(0.95f, 0.80f, 1.05f); var at = new Vector3(0.10f, 0.70f, 0.0f);
                    go.transform.SetPositionAndRotation(from, Quaternion.LookRotation(at - from, Vector3.up));
                }
                var hd = go.AddHDLight(spot ? LightType.Spot : LightType.Rectangle);
                var light = go.GetComponent<Light>();
                light.areaSize = L.name == "top" ? new Vector2(0.4f, 0.4f) : L.name == "key" ? new Vector2(2.2f, 1.7f) : new Vector2(L.width, L.height);
                if (spot)
                {
                    light.spotAngle = 13f; light.innerSpotAngle = 6f; light.range = 4f;
                    light.lightUnit = LightUnit.Candela; light.intensity = 1350f * LightCal(L.name);   // (sweep 0.06-8 x 9000 cd: 0.15 matches the original's band)
                }
                else { light.lightUnit = LightUnit.Lumen; light.intensity = L.lumen * LightCal(L.name); }
                light.useColorTemperature = false;
                light.color = new Color(L.color[0], L.color[1], L.color[2]);
                // the original's rim highlight inverts (through the view transform) to scene RGB (0, 1.13, 1.43): no red at all
                if (L.name == "rim" || L.name == "rim3") light.color = new Color(0f, 0.92f, 1f);
                light.shadows = (L.name == "key" || L.name == "top") ? LightShadows.Soft : LightShadows.None;   // (the rim's body-only shadows: CameraRig)
                hd.lightlayersMask = (HDLayers)(L.name == "rim3" ? L_RIM : L.layerMask);
                if (L.barnDoorLength > 0f && L.name != "rim") { hd.barnDoorAngle = 90f; hd.barnDoorLength = L.barnDoorLength; }
                go.SetActive(L.enabled);
            }

            // ---- volume
            string profPath = SettingsDir + "/SheerVolume.asset";
            AssetDatabase.DeleteAsset(profPath);
            var prof = ScriptableObject.CreateInstance<VolumeProfile>();
            AssetDatabase.CreateAsset(prof, profPath);
            // Blender's view transform (AgX 'Punchy', baked LUT) at its fixed exposure: matched against the original's
            // frames (ACES + automatic exposure, HDRP's default, renders the skin orange and the nylon brown)
            var exposure = prof.Add<Exposure>(true);
            exposure.mode.value = ExposureMode.Fixed;
            exposure.fixedExposure.value = Mathf.Log(spec.lumenPerWatt / 1.2f, 2f) - spec.blenderExposure;
            var tm = prof.Add<Tonemapping>(true);
            tm.mode.value = TonemappingMode.External;
            tm.lutTexture.value = AgxLut(); tm.lutContribution.value = 1f;
            var ve = prof.Add<VisualEnvironment>(true);
            ve.skyType.value = (int)SkyType.Gradient;
            ve.skyAmbientMode.value = SkyAmbientMode.Dynamic;
            var sky = prof.Add<GradientSky>(true);
            sky.top.value = new Color(0.018f, 0.024f, 0.03f);         // Blender world for non-camera rays
            sky.middle.value = new Color(0.012f, 0.0155f, 0.019f);
            sky.bottom.value = new Color(0.006f, 0.007f, 0.008f);
            sky.gradientDiffusion.value = 1f;
            sky.skyIntensityMode.value = SkyIntensityMode.Multiplier;
            sky.multiplier.value = spec.lumenPerWatt;
            // Depth of field OFF: in the original both legs, the skirt and the toes are sharp in every frame (glints stay
            // points on the far leg too). The physical camera at f/8-f/11 kept only a ~9 cm slab sharp: the sides of the
            // thigh, the far leg, the skirt and the foot went soft. (-sheerVol DepthOfField.focusMode=2 switches it on.)
            var dof = prof.Add<DepthOfField>(true);
            dof.focusMode.value = DepthOfFieldMode.Off;
            dof.focusDistanceMode.value = FocusDistanceMode.Camera;        // the rig's focus distance (default: volume, 10 m)
            var fog = prof.Add<Fog>(true); fog.enabled.value = false;
            var gi = prof.Add<GlobalIllumination>(true);                  // screen-space bounce (white floor -> feet)
            gi.enable.value = false; gi.tracing.value = RayCastingMode.RayMarching; gi.fullResolutionSS.value = true;   // off: no measurable
            // contribution in the sweeps (GlobalIllumination.enable=0 changed nothing) and several ms per frame
            var bloom = prof.Add<Bloom>(true); bloom.intensity.value = 0f;
            // HDRP's default profile adds motion blur (0.5): the original's fast pulls are crisp in every frame
            var mblur = prof.Add<MotionBlur>(true); mblur.intensity.value = 0f;
            var shadows = prof.Add<HDShadowSettings>(true); shadows.maxShadowDistance.value = 8f;
            var skinProfile = AssetDatabase.LoadAssetAtPath<DiffusionProfileSettings>(AssetDatabase.GUIDToAssetPath(SkinProfileGuid));
            var dpl = prof.Add<DiffusionProfileList>(true);
            dpl.diffusionProfiles.value = skinProfile ? new[] { skinProfile } : new DiffusionProfileSettings[0];
            // components added by script must be stored as sub-assets of the profile, else they are lost on reload
            foreach (var c in prof.components) { c.name = c.GetType().Name; AssetDatabase.AddObjectToAsset(c, prof); }
            EditorUtility.SetDirty(prof);
            AssetDatabase.SaveAssets();
            var volGo = new GameObject("Volume");
            var vol = volGo.AddComponent<Volume>();
            vol.isGlobal = true; vol.sharedProfile = prof;

            // ---- save + build settings
            AssetDatabase.SaveAssets();
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log("[SceneBuilder] built " + ScenePath + " (skin profile " + (skinProfile ? skinProfile.name : "MISSING") +
                      ", exposure EV100 " + exposure.fixedExposure.value.ToString("0.00") + ")");
        }

        // Blender AgX + 'Punchy' baked by blender/make_agx_lut.py (float32 RGB, x = R fastest, LogC-encoded input)
        static Texture3D AgxLut()
        {
            const string raw = "Assets/Sheer/Data/agx_punchy_lut32.raw", path = SettingsDir + "/AgXPunchy_LUT.asset";
            if (!File.Exists(raw)) { Debug.LogWarning("[SceneBuilder] no LUT " + raw); return null; }
            var bytes = File.ReadAllBytes(raw);
            int n = Mathf.RoundToInt(Mathf.Pow(bytes.Length / 12, 1f / 3f));
            var f = new float[bytes.Length / 4];
            System.Buffer.BlockCopy(bytes, 0, f, 0, bytes.Length);
            var px = new Color[n * n * n];
            for (int i = 0; i < px.Length; i++) px[i] = new Color(f[3 * i], f[3 * i + 1], f[3 * i + 2], 1f);
            var tex = new Texture3D(n, n, n, TextureFormat.RGBAHalf, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "AgXPunchy_LUT" };
            tex.SetPixels(px); tex.Apply(false);
            AssetDatabase.DeleteAsset(path);
            AssetDatabase.CreateAsset(tex, path);
            return tex;
        }

        // ------------------------------------------------------------------------------------ look-dev capture
        [MenuItem("Sheer/Capture Views")]
        public static void CaptureViews()
        {
            EditorSceneManager.OpenScene(ScenePath);
            var cam = Camera.main;
            var rig = cam.GetComponent<CameraRig>();
            foreach (var t in Object.FindObjectsByType<TensionData>(FindObjectsSortMode.None)) t.Push();
            string dir = Path.GetFullPath("../unity_logs/capture");
            Directory.CreateDirectory(dir);
            int W = 540, H = 945;                                  // original game view 1080 x 1890, half size
            var rt = new RenderTexture(W, H, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB) { antiAliasing = 1 };
            rt.Create();
            var tex = new Texture2D(W, H, TextureFormat.RGB24, false);
            for (int v = 0; v < 2; v++)
            {
                rig.Params(v, v, 1f, 0, 0, 1f, out var loc, out var tgt, out var lens, out var focus, out var fstop);
                rig.ApplyParams(loc, tgt, lens, focus, fstop);
                cam.targetTexture = rt;
                for (int i = 0; i < 12; i++) cam.Render();            // converge TAA / temporal effects
                RenderTexture.active = rt;
                tex.ReadPixels(new Rect(0, 0, W, H), 0, 0); tex.Apply();
                RenderTexture.active = null;
                File.WriteAllBytes(Path.Combine(dir, "view0" + (v + 1) + ".png"), tex.EncodeToPNG());
            }
            cam.targetTexture = null;
            Debug.Log("[SceneBuilder] captured views to " + dir);
        }
    }
}
