// SHEER — batch-mode play test: opens the scene and enters play mode; the ReplayDriver reads its own command-line
// arguments (-sheerReplay -sheerCapture DIR -sheerFrom S -sheerTo S), captures offscreen and exits the editor.
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.PlayTest.Run -sheerReplay ...
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace SheerEditor
{
    public static class PlayTest
    {
        public static void Run()
        {
            EditorSceneManager.OpenScene(SceneBuilder.ScenePath);
            EditorApplication.playModeStateChanged += s => Debug.Log("[PlayTest] " + s);
            // safety net: never hang a batch job
            double deadline = EditorApplication.timeSinceStartup + 1800;
            EditorApplication.update += () => { if (EditorApplication.timeSinceStartup > deadline) { Debug.LogError("[PlayTest] timeout"); EditorApplication.Exit(2); } };
            EditorApplication.EnterPlaymode();
        }
    }
}
