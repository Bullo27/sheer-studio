// SHEER — batch-mode shader validation: compiles the fragment stage of every pass of the Sheer graph shaders
// for Vulkan (Linux) and logs every compiler message, so HLSL errors surface without rendering anything.
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerSetup.ShaderCheck.Run -quit
using System.Linq;
using UnityEditor;
using UnityEditor.Rendering;
using UnityEngine;
using UnityEngine.Rendering;

namespace SheerSetup
{
    public static class ShaderCheck
    {
        static readonly string[] Graphs = { "SheerTights", "SheerSkin", "SheerSkirt", "SheerFloor" };

        [MenuItem("Sheer/Setup/Check Shaders")]
        public static void Run()
        {
            int errors = 0;
            foreach (var name in Graphs)
            {
                string path = "Assets/Sheer/Graphs/" + name + ".shadergraph";
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                var shader = AssetDatabase.LoadAssetAtPath<Shader>(path);
                if (shader == null) { Debug.LogError("[ShaderCheck] no shader at " + path); errors++; continue; }
                foreach (var m in ShaderUtil.GetShaderMessages(shader))
                    Debug.Log($"[ShaderCheck] {name} import {m.severity}: {m.message} ({m.file}:{m.line})");
                var data = ShaderUtil.GetShaderData(shader);
                Debug.Log($"[ShaderCheck] {name}: supported={shader.isSupported} subshaders={data.SubshaderCount}");
                for (int s = 0; s < data.SubshaderCount; s++)
                {
                    var sub = data.GetSerializedSubshader(s);
                    for (int p = 0; p < sub.PassCount; p++)
                    {
                        var pass = sub.GetPass(p);
                        var info = pass.CompileVariant(ShaderType.Fragment, new string[0], ShaderCompilerPlatform.Vulkan,
                                                       BuildTarget.StandaloneLinux64);
                        var bad = info.Messages.Where(m => m.severity == ShaderCompilerMessageSeverity.Error).ToArray();
                        errors += bad.Length;
                        Debug.Log($"[ShaderCheck] {name} sub{s} pass '{pass.Name}': {(info.Success ? "ok" : "FAILED")}" +
                                  (bad.Length > 0 ? "" : $" ({info.Messages.Length} msgs)"));
                        foreach (var m in info.Messages.Take(12))
                            Debug.Log($"[ShaderCheck]    {m.severity}: {m.message} ({m.file}:{m.line}) {m.messageDetails}");
                        if (bad.Length > 0) break;              // one failing pass is enough to see the error
                    }
                }
            }
            Debug.Log("[ShaderCheck] done, errors: " + errors);
        }

        // Writes Shader Graph's generated source of each graph to ../unity_logs/<name>.generated.shader
        // (ShaderGraphImporter.GetShaderText is internal: reached by reflection).
        [MenuItem("Sheer/Setup/Dump Generated Shaders")]
        public static void DumpGenerated()
        {
            var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetName().Name == "Unity.ShaderGraph.Editor");
            var imp = asm?.GetType("UnityEditor.ShaderGraph.ShaderGraphImporter");
            var m = imp?.GetMethods(System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public)
                .FirstOrDefault(x => x.Name == "GetShaderText" && x.GetParameters().Length == 4);   // (path, out textures, assetCollection, out graph)
            if (m == null)
            {
                Debug.LogError($"[ShaderCheck] GetShaderText not found (asm {asm?.FullName ?? "null"}, type {imp?.FullName ?? "null"}); " +
                               "ShaderGraph assemblies: " + string.Join(", ", System.AppDomain.CurrentDomain.GetAssemblies()
                                   .Select(a => a.GetName().Name).Where(n => n.Contains("ShaderGraph"))));
                if (imp != null)
                    foreach (var x in imp.GetMethods(System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Public))
                        Debug.Log("[ShaderCheck]   method " + x);
                return;
            }
            System.IO.Directory.CreateDirectory("../unity_logs");
            foreach (var name in Graphs)
            {
                var args = new object[] { "Assets/Sheer/Graphs/" + name + ".shadergraph", null, null, null };
                var text = (string)m.Invoke(null, args);
                System.IO.File.WriteAllText("../unity_logs/" + name + ".generated.shader", text ?? "");
                Debug.Log($"[ShaderCheck] generated {name}: {text?.Length ?? 0} chars");
            }
        }
    }
}
