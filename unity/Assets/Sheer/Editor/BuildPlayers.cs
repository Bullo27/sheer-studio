// SHEER — player builds from the command line:
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.BuildPlayers.Linux -quit
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.BuildPlayers.Windows -quit
// Output: ../builds/linux/Sheer.x86_64, ../builds/windows/Sheer.exe (StreamingAssets meshes + replay data included).
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.Rendering;

namespace SheerEditor
{
    public static class BuildPlayers
    {
        const string Scene = "Assets/Sheer/Scenes/Sheer.unity";
        // the player's first scene: the loading screen alone (Sheer.SheerBoot), which loads the simulator behind its banner
        const string Boot = "Assets/Sheer/Scenes/Boot.unity";

        static void EnsureBoot()
        {
            if (!File.Exists(Boot))
            {
                var sc = UnityEditor.SceneManagement.EditorSceneManager.NewScene(UnityEditor.SceneManagement.NewSceneSetup.EmptyScene, UnityEditor.SceneManagement.NewSceneMode.Single);
                new GameObject("Boot").AddComponent<Sheer.SheerBoot>();
                UnityEditor.SceneManagement.EditorSceneManager.SaveScene(sc, Boot);
                AssetDatabase.Refresh();
                Debug.Log("[BuildPlayers] created " + Boot);
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(Boot, true), new EditorBuildSettingsScene(Scene, true) };
        }

        [MenuItem("Sheer/Build/Linux Player")]
        public static void Linux() => Build(BuildTarget.StandaloneLinux64, "../builds/linux/Sheer.x86_64");

        [MenuItem("Sheer/Build/Windows Player")]
        public static void Windows() => Build(BuildTarget.StandaloneWindows64, "../builds/windows/Sheer.exe");

        static void Build(BuildTarget target, string path)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            SheerAssets.Ensure();                                  // the runtime materials (Resources/Materials)
            EnsureBoot();
            // (our own loading banner is the first thing on the screen: no engine splash before it)
            PlayerSettings.SplashScreen.show = false; PlayerSettings.SplashScreen.showUnityLogo = false;
            PlayerSettings.enableFrameTimingStats = true;         // -sheerPerfLog reports CPU / GPU time per frame
            if (target == BuildTarget.StandaloneWindows64)
            {
                // Vulkan first: the path every test ran on (Linux Vulkan); the player falls back to D3D12 when a
                // device cannot start Vulkan (-force-d3d12 picks it explicitly)
                PlayerSettings.SetUseDefaultGraphicsAPIs(target, false);
                PlayerSettings.SetGraphicsAPIs(target, new[] { GraphicsDeviceType.Vulkan, GraphicsDeviceType.Direct3D12 });
            }
            var opts = new BuildPlayerOptions
            {
                scenes = new[] { Boot, Scene },
                locationPathName = path,
                target = target,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.None,
            };
            var report = BuildPipeline.BuildPlayer(opts);
            var s = report.summary;
            // the bundled fonts' licences, readable next to the game (SIL OFL 1.1: each copy carries the notice + licence)
            if (s.result == BuildResult.Succeeded)
            {
                var lic = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(path)), "licenses");
                Directory.CreateDirectory(lic);
                foreach (var f in Directory.GetFiles("Assets/Sheer/Resources/Fonts", "*.txt"))
                    File.Copy(f, Path.Combine(lic, Path.GetFileName(f)), true);
                File.WriteAllText(Path.Combine(lic, "README.txt"),
                    "Third-party material bundled with Sheer:\n" +
                    "  - M PLUS Rounded 1c and Inter fonts - SIL Open Font License 1.1 (OFL.txt).\n" +
                    "  - The tonemapping LUT is baked from Blender's AgX view transform (AgX by Troy Sobotka; Blender's\n" +
                    "    version by Eary Chow, Mark Faderbauer and Sakari Kapanen).\n" +
                    "The music and sound effects were synthesized for this game (original compositions).\n");
            }
            Debug.Log($"[BuildPlayers] {target}: {s.result}, {s.totalSize / (1024 * 1024)} MB, {s.totalErrors} errors, {s.totalTime} -> {Path.GetFullPath(path)}");
            if (Application.isBatchMode) EditorApplication.Exit(s.result == BuildResult.Succeeded ? 0 : 1);
        }
    }
}
