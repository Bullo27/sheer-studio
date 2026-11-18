// SHEER — one-shot project configuration, runnable in batch mode (independent of the runtime assembly,
// so it works even while the Sheer scripts still have compile errors):
//   Unity -batchmode -projectPath unity -ignoreCompilerErrors -executeMethod SheerSetup.ProjectSetup.Run -quit
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

namespace SheerSetup
{
    public static class ProjectSetup
    {
        const string PipelinePath = "Assets/Settings/SheerHDRP.asset";

        [MenuItem("Sheer/Setup/Configure Project")]
        public static void Run()
        {
            // player: linear colour, portrait window with the original's game-view aspect (1080 x 1890)
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.companyName = "Sheer";
            PlayerSettings.productName = "Sheer";
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 608;
            PlayerSettings.defaultScreenHeight = 1064;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;
            SetPlayerProperty("activeInputHandler", 2);           // old Input Manager + Input System: our UI uses the old one
            // HDRP needs Vulkan on Linux (OpenGL strips every HDRP subshader)
            PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.StandaloneLinux64, false);
            PlayerSettings.SetGraphicsAPIs(BuildTarget.StandaloneLinux64, new[] { GraphicsDeviceType.Vulkan });

            // HDRP asset
            var asset = AssetDatabase.LoadAssetAtPath<HDRenderPipelineAsset>(PipelinePath);
            if (asset == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(PipelinePath));
                asset = ScriptableObject.CreateInstance<HDRenderPipelineAsset>();
                AssetDatabase.CreateAsset(asset, PipelinePath);
            }
            var s = asset.currentPlatformRenderPipelineSettings;
            s.supportSubsurfaceScattering = true;                 // skin under the sheer nylon
            s.supportTransparentDepthPrepass = true;              // sorted, depth-correct sheer layer
            s.supportTransparentDepthPostpass = true;             // DOF/motion vectors see the tights
            s.supportTransparentBackface = true;
            s.supportLightLayers = true;                          // Blender's light linking -> rendering layers
            s.supportedLitShaderMode = RenderPipelineSettings.SupportedLitShaderMode.Both;
            s.supportMotionVectors = true;
            s.supportDecals = false;
            s.supportRayTracing = false;
            s.supportSSGI = true;                                 // floor bounce onto the feet / lower legs (VIEW 02)
            s.supportVolumetrics = false;
            s.supportVolumetricClouds = false;
            s.supportWater = false;
            asset.currentPlatformRenderPipelineSettings = s;
            EditorUtility.SetDirty(asset);

            GraphicsSettings.defaultRenderPipeline = asset;
            int cur = QualitySettings.GetQualityLevel();
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = null;              // every level uses the default asset
            }
            QualitySettings.SetQualityLevel(cur, false);

            // HDRP global settings (the class and its Ensure() are internal in HDRP 17.6: reach them by reflection;
            // Ensure creates and registers the asset when missing)
            var gsType = typeof(HDRenderPipelineAsset).Assembly.GetType("UnityEngine.Rendering.HighDefinition.HDRenderPipelineGlobalSettings");
            var ensure = gsType?.GetMethod("Ensure", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            if (ensure == null) Debug.LogWarning("[SheerSetup] HDRenderPipelineGlobalSettings.Ensure not found");
            object gs = null;
            try { gs = ensure?.Invoke(null, new object[] { true }); }
            catch (System.Exception e) { Debug.LogWarning("[SheerSetup] global settings: " + e.InnerException?.Message); }

            AssetDatabase.SaveAssets();
            Debug.Log("[SheerSetup] done: pipeline " + AssetDatabase.GetAssetPath(GraphicsSettings.defaultRenderPipeline)
                      + ", global settings " + (gs is Object o ? AssetDatabase.GetAssetPath(o) : "none")
                      + ", colour space " + PlayerSettings.colorSpace);
        }

        static void SetPlayerProperty(string name, int value)
        {
            var ps = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (ps == null || ps.Length == 0) return;
            var so = new SerializedObject(ps[0]);
            var p = so.FindProperty(name);
            if (p == null) { Debug.LogWarning("[SheerSetup] no player property " + name); return; }
            p.intValue = value;
            so.ApplyModifiedPropertiesWithoutUndo();
        }
    }
}
