// SHEER — look-development switches from the command line (no scene rebuild needed between experiments):
//   -sheerLight NAME=SCALE[,NAME=SCALE...]   scale light intensities (names from the Lights group)
//   -sheerNoBarn                             remove all barn doors
//   -sheerBarn NAME=LENGTH[,...]             set barn-door lengths (m)
//   -sheerMat MATERIAL.PROP=VALUE[,...]      set a float on a material instance (e.g. Skin._SkinNylonShadow=0.2)
//   -sheerVec MATERIAL.PROP=r:g:b:a[,...]    set a vector/colour on a material instance
//   -sheerTension FIELD=VALUE[,...]          set a TensionData (inspector) field, e.g. frostBodyCoverage=0.75
//   -sheerHide NAME[,NAME...]                disable renderers of these GameObjects (e.g. Body)
//   -sheerVol COMPONENT.FIELD=VALUE[,...]    set a float/int/bool volume parameter (e.g. GradientSky.multiplier=0)
//   -sheerShadows NAME=0|1[,...]             light shadows off/on
//   -sheerAim NAME=x:y:z[,...]               point a light at a world position (Unity axes)
//   -sheerOrbit NAME=DEG[:ELEV][,...]        orbit a light around the character's vertical axis (+ = towards +x / image
//                                            right from the front) and optionally raise it by ELEV degrees
//   -sheerAA N                               camera anti-aliasing: 0 none, 1 FXAA, 2 TAA, 3 SMAA
//   -sheerSharpen S[:H]                      TAA sharpening strength [and history sharpening]
//   -sheerDebug MODE                         HDRP full-screen debug view (DepthOfFieldCoc, MotionVectors, None)
// Profiling: -sheerVsync 0|1, -sheerPass MATERIAL.PASS=0|1[,...] (shader pass by LightMode), -sheerTriFrac NAME=FRACTION,
//   -sheerDynMesh (keep the render meshes' buffers 'dynamic' as they were while the CPU deformed them)
// Variant sweeps (ReplayDriver -sheerVariants "spec;spec;..."): every spec starts from the scene's state (ResetAll).
using System;
using System.Globalization;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

namespace Sheer
{
    public static class DevTweaks
    {
        static string Arg(string[] a, string key) { for (int i = 0; i + 1 < a.Length; i++) if (a[i] == key) return a[i + 1]; return null; }
        static float F(string s) => float.Parse(s, CultureInfo.InvariantCulture);

        static System.Collections.Generic.Dictionary<Light, float> baseIntensity;

        public static void Apply() => ApplyArgs(Environment.GetCommandLineArgs());

        // ---- snapshot of the tweakable state, so that sweep variants do not accumulate
        static string tensionJson;
        static System.Collections.Generic.Dictionary<Light, LightShadows> baseShadows;
        static System.Collections.Generic.Dictionary<Light, (Vector3, Quaternion)> basePose;
        static System.Collections.Generic.Dictionary<Renderer, (bool, Material[])> baseRenderers;
        static UnityEngine.Rendering.VolumeProfile baseProfile;

        static void Snapshot()
        {
            if (baseRenderers != null) return;
            var td = UnityEngine.Object.FindAnyObjectByType<TensionData>();
            tensionJson = td ? JsonUtility.ToJson(td) : null;
            baseIntensity = new System.Collections.Generic.Dictionary<Light, float>();
            baseShadows = new System.Collections.Generic.Dictionary<Light, LightShadows>();
            basePose = new System.Collections.Generic.Dictionary<Light, (Vector3, Quaternion)>();
            foreach (var l in UnityEngine.Object.FindObjectsByType<Light>(FindObjectsInactive.Include, FindObjectsSortMode.None)) { baseIntensity[l] = l.intensity; baseShadows[l] = l.shadows; basePose[l] = (l.transform.position, l.transform.rotation); }
            baseRenderers = new System.Collections.Generic.Dictionary<Renderer, (bool, Material[])>();
            foreach (var r in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None)) baseRenderers[r] = (r.enabled, r.sharedMaterials);
            var vol = UnityEngine.Object.FindAnyObjectByType<UnityEngine.Rendering.Volume>();
            if (vol) baseProfile = UnityEngine.Object.Instantiate(vol.sharedProfile);
        }

        public static void ResetAll()
        {
            Snapshot();
            var td = UnityEngine.Object.FindAnyObjectByType<TensionData>();
            if (td && tensionJson != null) JsonUtility.FromJsonOverwrite(tensionJson, td);
            foreach (var kv in baseIntensity) if (kv.Key) { kv.Key.intensity = kv.Value; kv.Key.shadows = baseShadows[kv.Key]; kv.Key.transform.SetPositionAndRotation(basePose[kv.Key].Item1, basePose[kv.Key].Item2); }
            foreach (var kv in baseRenderers) if (kv.Key) { kv.Key.enabled = kv.Value.Item1; kv.Key.sharedMaterials = kv.Value.Item2; }
            var vol = UnityEngine.Object.FindAnyObjectByType<UnityEngine.Rendering.Volume>();
            if (vol && baseProfile) vol.profile = UnityEngine.Object.Instantiate(baseProfile);
            var hdrp = UnityEngine.Rendering.RenderPipelineManager.currentPipeline as HDRenderPipeline;
            if (hdrp != null) hdrp.debugDisplaySettings.SetFullScreenDebugMode(FullScreenDebugMode.None);
        }

        /// A variant spec "light:key=0.5,fill=1|tension:frostBodyCoverage=0.9|vol:Exposure.mode=0|mat:...|vec:...|shadows:...|hide:..."
        public static void ApplySpec(string spec)
        {
            ResetAll();
            var list = new System.Collections.Generic.List<string>();
            foreach (var part in spec.Split('|'))
            {
                int c = part.IndexOf(':'); if (c < 0) continue;
                string key = part.Substring(0, c), val = part.Substring(c + 1);
                string flag = key switch { "light" => "-sheerLight", "tension" => "-sheerTension", "vol" => "-sheerVol", "mat" => "-sheerMat",
                                           "vec" => "-sheerVec", "shadows" => "-sheerShadows", "hide" => "-sheerHide", "orbit" => "-sheerOrbit", "aim" => "-sheerAim", "barn" => "-sheerBarn", "pos" => "-sheerPos", "size" => "-sheerSize", "layers" => "-sheerLayers", "aa" => "-sheerAA", "debug" => "-sheerDebug", "sharpen" => "-sheerSharpen", "global" => "-sheerGlobal", _ => null };
                if (flag == null) continue;
                int at = list.IndexOf(flag);                     // repeated keys merge ("mat:a=1|mat:b=2" = "mat:a=1,b=2")
                if (at >= 0) list[at + 1] += "," + val; else { list.Add(flag); list.Add(val); }
            }
            ApplyArgs(list.ToArray());
        }

        public static void ApplyArgs(string[] a)
        {
            var lights = UnityEngine.Object.FindObjectsByType<Light>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            Snapshot();
            if (Array.IndexOf(a, "-sheerNoBarn") >= 0)
                foreach (var l in lights) { var hd = l.GetComponent<HDAdditionalLightData>(); if (hd) { hd.barnDoorAngle = 90f; hd.barnDoorLength = 0f; } }
            var s = Arg(a, "-sheerLight");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    foreach (var l in lights) if (l.name == p[0]) { l.intensity = baseIntensity[l] * F(p[1]); Debug.Log($"[tweak] light {l.name} x{p[1]} -> {l.intensity:0}"); }
                }
            s = Arg(a, "-sheerOrbit");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var q = p[1].Split(':');
                    float deg = F(q[0]), elev = q.Length > 1 ? F(q[1]) : 0f;
                    foreach (var l in lights)
                    {
                        if (l.name != p[0]) continue;
                        var (bp, br) = basePose[l];
                        // Unity: the camera looks along +z from -z; a light at azimuth a (from the front) sits at x = -z sin a.
                        // Orbiting towards image right = rotating about +y by -deg; elevation about the horizontal axis
                        var yaw = Quaternion.AngleAxis(-deg, Vector3.up);
                        var pos = yaw * bp; var rot = yaw * br;
                        if (elev != 0f)
                        {
                            var axis = Vector3.Cross(Vector3.up, new Vector3(pos.x, 0, pos.z)).normalized;
                            var pitch = Quaternion.AngleAxis(-elev, axis);
                            pos = pitch * pos; rot = pitch * rot;
                        }
                        l.transform.SetPositionAndRotation(pos, rot);
                        Debug.Log($"[tweak] orbit {l.name} {deg} deg, elev {elev} -> {pos}");
                    }
                }
            s = Arg(a, "-sheerPos");                              // move a light (before -sheerAim, which points it)
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var c = p[1].Split(':'); if (c.Length != 3) continue;
                    foreach (var l in lights) if (l.name == p[0]) l.transform.position = new Vector3(F(c[0]), F(c[1]), F(c[2]));
                }
            s = Arg(a, "-sheerLayers");                           // light layer mask (1 all, 2 char, 4 legs, 8 floor)
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    foreach (var l in lights) if (l.name == p[0]) { var hd = l.GetComponent<HDAdditionalLightData>(); if (hd) hd.lightlayersMask = (UnityEngine.Rendering.HighDefinition.RenderingLayerMask)int.Parse(p[1]); }
                }
            s = Arg(a, "-sheerSize");                             // area light size w:h
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var c = p[1].Split(':'); if (c.Length != 2) continue;
                    foreach (var l in lights) if (l.name == p[0]) l.areaSize = new Vector2(F(c[0]), F(c[1]));
                }
            s = Arg(a, "-sheerAim");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var c = p[1].Split(':'); if (c.Length != 3) continue;
                    var at = new Vector3(F(c[0]), F(c[1]), F(c[2]));
                    foreach (var l in lights) if (l.name == p[0]) { l.transform.rotation = Quaternion.LookRotation(at - l.transform.position, Vector3.up); Debug.Log($"[tweak] aim {l.name} -> {at}"); }
                }
            s = Arg(a, "-sheerShadows");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    foreach (var l in lights) if (l.name == p[0]) { l.shadows = p[1] == "1" ? LightShadows.Soft : LightShadows.None; Debug.Log($"[tweak] {l.name} shadows {l.shadows}"); }
                }
            s = Arg(a, "-sheerBarn");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    foreach (var l in lights) if (l.name == p[0]) { var hd = l.GetComponent<HDAdditionalLightData>(); hd.barnDoorAngle = 90f; hd.barnDoorLength = F(p[1]); }
                }
            var rends = UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            void SetMat(string spec, bool vec)
            {
                foreach (var kv in spec.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var mp = p[0].Split('.'); if (mp.Length != 2) continue;
                    foreach (var r in rends)
                        foreach (var m in r.materials)                     // instances: the asset is untouched
                        {
                            if (!m || !m.name.StartsWith(mp[0])) continue;
                            if (vec) { var c = p[1].Split(':'); m.SetVector(mp[1], new Vector4(F(c[0]), F(c[1]), F(c[2]), c.Length > 3 ? F(c[3]) : 1f)); }
                            else m.SetFloat(mp[1], F(p[1]));
                            Debug.Log($"[tweak] {m.name}.{mp[1]} = {p[1]}");
                        }
                }
            }
            s = Arg(a, "-sheerTension");
            if (s != null)
            {
                var td = UnityEngine.Object.FindAnyObjectByType<TensionData>();
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2 || !td) continue;
                    var f = typeof(TensionData).GetField(p[0]);
                    if (f == null) { Debug.LogWarning("[tweak] no TensionData field " + p[0]); continue; }
                    if (f.FieldType == typeof(int)) f.SetValue(td, Mathf.RoundToInt(F(p[1])));
                    else if (f.FieldType.IsEnum) f.SetValue(td, System.Enum.ToObject(f.FieldType, Mathf.RoundToInt(F(p[1]))));
                    else f.SetValue(td, F(p[1]));
                    Debug.Log($"[tweak] TensionData.{p[0]} = {p[1]}");
                }
            }
            s = Arg(a, "-sheerHide");
            if (s != null)
                foreach (var n in s.Split(','))
                    foreach (var r in rends) if (r.gameObject.name == n) { r.enabled = false; Debug.Log("[tweak] hidden " + n); }
            s = Arg(a, "-sheerVol");
            if (s != null)
            {
                var vol = UnityEngine.Object.FindAnyObjectByType<UnityEngine.Rendering.Volume>();
                var prof = vol ? vol.profile : null;                     // instance: the asset is untouched
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); var cf = p[0].Split('.');
                    if (p.Length != 2 || cf.Length != 2 || prof == null) continue;
                    // a component the scene's profile does not carry yet (e.g. MotionBlur, which HDRP's default profile enables)
                    bool has = false;
                    foreach (var comp in prof.components) if (comp.GetType().Name == cf[0]) has = true;
                    if (!has)
                    {
                        var ct = typeof(DepthOfField).Assembly.GetType("UnityEngine.Rendering.HighDefinition." + cf[0]);
                        if (ct != null) prof.Add(ct, false); else { Debug.LogWarning("[tweak] no volume component " + cf[0]); continue; }
                    }
                    foreach (var comp in prof.components)
                    {
                        if (comp.GetType().Name != cf[0]) continue;
                        var fld = comp.GetType().GetField(cf[1]);
                        var par = fld?.GetValue(comp) as UnityEngine.Rendering.VolumeParameter;
                        if (par == null) { Debug.LogWarning("[tweak] no parameter " + p[0]); continue; }
                        par.overrideState = true;
                        var vp = par.GetType().GetProperty("value");
                        var vt = vp.PropertyType;
                        object v = vt == typeof(bool) ? (object)(p[1] == "1" || p[1] == "true") : vt == typeof(int) ? (object)Mathf.RoundToInt(F(p[1])) : vt.IsEnum ? Enum.ToObject(vt, Mathf.RoundToInt(F(p[1]))) : (object)F(p[1]);
                        vp.SetValue(par, v);
                        Debug.Log($"[tweak] volume {p[0]} = {p[1]}");
                    }
                }
            }
            s = Arg(a, "-sheerAA");                               // camera anti-aliasing: 0 none, 1 FXAA, 2 TAA, 3 SMAA
            if (s != null)
                foreach (var hc in UnityEngine.Object.FindObjectsByType<HDAdditionalCameraData>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                { hc.antialiasing = (HDAdditionalCameraData.AntialiasingMode)Mathf.RoundToInt(F(s)); Debug.Log("[tweak] antialiasing " + hc.antialiasing); }
            s = Arg(a, "-sheerGlobal");                           // global shader floats: NAME=VALUE[,...]
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    Shader.SetGlobalFloat(p[0], F(p[1])); Debug.Log($"[tweak] global {p[0]} = {p[1]}");
                }
            s = Arg(a, "-sheerSharpen");                          // TAA sharpening: strength[:history sharpening]
            if (s != null)
                foreach (var hc in UnityEngine.Object.FindObjectsByType<HDAdditionalCameraData>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                {
                    var q = s.Split(':');
                    hc.taaSharpenStrength = F(q[0]); if (q.Length > 1) hc.taaHistorySharpening = F(q[1]);
                    if (q.Length > 2) hc.taaSharpenMode = (HDAdditionalCameraData.TAASharpenMode)Mathf.RoundToInt(F(q[2]));   // 0 low, 1 post, 2 CAS
                    if (q.Length > 3) hc.taaAntiHistoryRinging = F(q[3]) > 0.5f;
                    Debug.Log($"[tweak] TAA sharpen {hc.taaSharpenStrength} history {hc.taaHistorySharpening}");
                }
            s = Arg(a, "-sheerDebug");                            // HDRP full-screen debug view (DepthOfFieldCoc, MotionVectors, ...)
            if (s != null)
            {
                var hdrp = UnityEngine.Rendering.RenderPipelineManager.currentPipeline as HDRenderPipeline;
                if (!Enum.TryParse<FullScreenDebugMode>(s, true, out var mode)) Debug.LogWarning("[tweak] no debug view " + s);
                else if (hdrp != null) { hdrp.debugDisplaySettings.SetFullScreenDebugMode(mode); Debug.Log("[tweak] debug view " + mode); }
                else
                {   // before the first frame there is no pipeline instance yet: set it when rendering starts
                    void Late(UnityEngine.Rendering.ScriptableRenderContext c, System.Collections.Generic.List<Camera> cams)
                    {
                        var hp = UnityEngine.Rendering.RenderPipelineManager.currentPipeline as HDRenderPipeline;
                        if (hp == null) return;
                        hp.debugDisplaySettings.SetFullScreenDebugMode(mode); Debug.Log("[tweak] debug view " + mode);
                        UnityEngine.Rendering.RenderPipelineManager.beginContextRendering -= Late;
                    }
                    UnityEngine.Rendering.RenderPipelineManager.beginContextRendering += Late;
                }
            }
            s = Arg(a, "-sheerCloth");                            // NAME=VALUE[,...]: fields of TightsSim.cloth (ClothParams)
            if (s != null)
            {
                var sim = UnityEngine.Object.FindAnyObjectByType<TightsSim>();
                if (sim != null)
                    foreach (var kv in s.Split(','))
                    {
                        var p = kv.Split('='); if (p.Length != 2) continue;
                        var f = typeof(ClothParams).GetField(p[0]);
                        if (f == null) { Debug.LogWarning("[tweak] no cloth field " + p[0]); continue; }
                        if (f.FieldType == typeof(int)) f.SetValue(sim.cloth, Mathf.RoundToInt(F(p[1]))); else f.SetValue(sim.cloth, F(p[1]));
                        Debug.Log($"[tweak] cloth.{p[0]} = {p[1]}");
                    }
                if (sim != null) sim.RefreshFootHand();
            }
            s = Arg(a, "-sheerSim");                              // NAME=VALUE[,...]: TightsSim's own numbers (fatigueTear, recoilTau, tearAtReach ...)
            if (s != null)
            {
                var sim = UnityEngine.Object.FindAnyObjectByType<TightsSim>();
                if (sim != null)
                    foreach (var kv in s.Split(','))
                    {
                        var p = kv.Split('='); if (p.Length != 2) continue;
                        var f = typeof(TightsSim).GetField(p[0]);
                        if (f == null || f.FieldType != typeof(float)) { Debug.LogWarning("[tweak] no sim number " + p[0]); continue; }
                        f.SetValue(sim, F(p[1]));
                        Debug.Log($"[tweak] sim.{p[0]} = {p[1]}");
                    }
            }
            s = Arg(a, "-sheerMat"); if (s != null) SetMat(s, false);
            // -sheerMatPass MATERIAL.PASS=0|1[,...]: a shader pass on / off on the material instances (e.g. Pantyhose.TransparentDepthPrepass=0)
            s = Arg(a, "-sheerMatPass");
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var mp = p[0].Split('.'); if (mp.Length != 2) continue;
                    foreach (var r in rends)
                        foreach (var m in r.materials)
                        {
                            if (!m || !m.name.StartsWith(mp[0])) continue;
                            m.SetShaderPassEnabled(mp[1], F(p[1]) != 0f);
                            Debug.Log($"[tweak] {m.name} pass {mp[1]} = {m.GetShaderPassEnabled(mp[1])}");
                        }
                }
            s = Arg(a, "-sheerVec"); if (s != null) SetMat(s, true);
            // ---- profiling
            s = Arg(a, "-sheerVsync");                            // 0 = no vertical sync (true frame cost), 1 = default
            if (s != null && !Application.isBatchMode)            // (no swapchain in batch mode: setting it there segfaults the player)
            { QualitySettings.vSyncCount = Mathf.RoundToInt(F(s)); Application.targetFrameRate = -1; Debug.Log("[tweak] vsync " + QualitySettings.vSyncCount); }
            s = Arg(a, "-sheerPass");                             // MATERIAL.PASS=0|1[,...]: switch a shader pass (LightMode) off / on
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    var mp = p[0].Split('.'); if (mp.Length != 2) continue;
                    foreach (var r in rends)
                        foreach (var m in r.materials)
                        {
                            if (!m || !m.name.StartsWith(mp[0])) continue;
                            m.SetShaderPassEnabled(mp[1], p[1] == "1");
                            Debug.Log($"[tweak] {m.name} pass {mp[1]} = {p[1]}");
                        }
                }
            s = Arg(a, "-sheerTriFrac");                          // NAME=FRACTION[,...]: draw only the first part of every submesh
            if (s != null)
                foreach (var kv in s.Split(','))
                {
                    var p = kv.Split('='); if (p.Length != 2) continue;
                    foreach (var r in rends)
                    {
                        if (r.gameObject.name != p[0]) continue;
                        var mf = r.GetComponent<MeshFilter>(); var me = mf ? mf.sharedMesh : null; if (!me) continue;
                        for (int k = 0; k < me.subMeshCount; k++)
                        {
                            var d = me.GetSubMesh(k);
                            d.indexCount = Mathf.Max(3, (int)(d.indexCount * F(p[1]) / 3f) * 3);
                            me.SetSubMesh(k, d, UnityEngine.Rendering.MeshUpdateFlags.DontRecalculateBounds | UnityEngine.Rendering.MeshUpdateFlags.DontValidateIndices);
                        }
                        Debug.Log($"[tweak] {p[0]} draws {p[1]} of its triangles");
                    }
                }
        }
    }
}
