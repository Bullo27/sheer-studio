// SHEER — creates HDRP's default Shader Graphs (through HDRP's own "Create" menu items, so the target/sub-target
// settings are serialized by Unity itself) at Assets/Sheer/Graphs/<Name>.shadergraph. tools/patch_shadergraph.py
// then injects the Sheer custom-function wiring and material settings into the JSON.
//   Unity -batchmode -projectPath unity -executeMethod SheerSetup.GraphSetup.CreateDefaults -quit
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace SheerSetup
{
    public static class GraphSetup
    {
        const string Dir = "Assets/Sheer/Graphs";
        static readonly (string menu, string name)[] Graphs =
        {
            ("Assets/Create/Shader Graph/HDRP/StackLit Shader Graph", "SheerTights"),
            ("Assets/Create/Shader Graph/HDRP/Lit Shader Graph", "SheerSkin"),
            ("Assets/Create/Shader Graph/HDRP/Lit Shader Graph", "SheerSkirt"),
            ("Assets/Create/Shader Graph/HDRP/Lit Shader Graph", "SheerFloor"),
            ("Assets/Create/Shader Graph/HDRP/Unlit Shader Graph", "SheerBackdrop"),
            ("Assets/Create/Shader Graph/HDRP/Fabric Shader Graph", "SheerSkirtFabric"),
            ("Assets/Create/Shader Graph/HDRP/Lit Shader Graph", "SheerTightsLit"),
        };

        [MenuItem("Sheer/Setup/Create Default Graphs")]
        public static void CreateDefaults()
        {
            Directory.CreateDirectory(Dir);
            AssetDatabase.Refresh();
            foreach (var (menu, name) in Graphs)
            {
                string target = Dir + "/" + name + ".shadergraph";
                if (File.Exists(target)) { Debug.Log("[SheerSetup] exists: " + target); continue; }
                var before = new HashSet<string>(AssetDatabase.FindAssets("t:Shader").Select(AssetDatabase.GUIDToAssetPath)
                    .Concat(Directory.GetFiles("Assets", "*.shadergraph", SearchOption.AllDirectories).Select(p => p.Replace('\\', '/'))));
                Selection.activeObject = AssetDatabase.LoadAssetAtPath<Object>(Dir);
                if (!EditorApplication.ExecuteMenuItem(menu)) { Debug.LogError("[SheerSetup] menu failed: " + menu); continue; }
                AssetDatabase.Refresh();
                var created = Directory.GetFiles("Assets", "*.shadergraph", SearchOption.AllDirectories)
                    .Select(p => p.Replace('\\', '/')).Where(p => !before.Contains(p)).ToList();
                if (created.Count != 1) { Debug.LogError("[SheerSetup] expected one new graph for " + name + ", got " + created.Count); continue; }
                string err = AssetDatabase.MoveAsset(created[0], target);
                Debug.Log("[SheerSetup] created " + target + (string.IsNullOrEmpty(err) ? "" : " (move error: " + err + ")"));
            }
            AssetDatabase.SaveAssets();
        }
    }
}
