// SHEER — assets the Studio loads at runtime (Resources/Materials): HDRP Lit materials for the plushie and the sakura
// petals. Made from code so they stay in step with the HDRP version; called before every player build.
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

namespace SheerEditor
{
    public static class SheerAssets
    {
        const string Dir = "Assets/Sheer/Resources/Materials";

        [MenuItem("Sheer/Make Studio Assets")]
        public static void Ensure()
        {
            System.IO.Directory.CreateDirectory(Dir);
            Lit("PlushWhite", new Color(0.97f, 0.94f, 0.95f), 0.12f, false);
            Lit("PlushPink", new Color(1f, 0.62f, 0.74f), 0.15f, false);
            Lit("PlushEye", new Color(0.05f, 0.03f, 0.05f), 0.92f, false);
            Lit("PlushRibbon", new Color(0.85f, 0.10f, 0.25f), 0.45f, false);
            Lit("Petal", new Color(1f, 0.74f, 0.83f), 0.35f, true);
            Lit("PlushBrown", new Color(0.62f, 0.43f, 0.30f), 0.15f, false);
            Lit("PlushCream", new Color(1f, 0.92f, 0.80f), 0.15f, false);
            Lit("PlushYellow", new Color(1f, 0.86f, 0.36f), 0.18f, false);
            Lit("PlushOrange", new Color(1f, 0.58f, 0.22f), 0.25f, false);
            Lit("PlushGrey", new Color(0.70f, 0.70f, 0.74f), 0.15f, false);
            Lit("Ribbon", new Color(1f, 0.40f, 0.62f), 0.78f, true);         // satin
            // fonts: OS fallbacks for what the bundled faces lack - the original inspector's simplified-Chinese titles
            // (张 褶 皱 闪 雾 肤) and a few symbols (✦ ✧ ◉ ↺ ✿)
            foreach (var guid in AssetDatabase.FindAssets("t:Font", new[] { "Assets/Sheer/Resources/Fonts" }))
            {
                var fpath = AssetDatabase.GUIDToAssetPath(guid);
                if (!(AssetImporter.GetAtPath(fpath) is TrueTypeFontImporter fi)) continue;
                var own = fi.fontTTFName;
                var want = new[] { own, "Microsoft YaHei", "Microsoft YaHei UI", "Yu Gothic UI", "Segoe UI Symbol", "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans SC", "WenQuanYi Micro Hei", "DejaVu Sans", "Arial Unicode MS" };
                if (fi.includeFontData && fi.fontNames != null && string.Join("|", fi.fontNames) == string.Join("|", want)) continue;
                fi.includeFontData = true; fi.fontNames = want; fi.SaveAndReimport();
            }
            // the music streams from disk (six ~90 s tracks would take ~100 MB decompressed); the effects load decompressed
            foreach (var guid in AssetDatabase.FindAssets("t:AudioClip", new[] { "Assets/Sheer/Resources/Audio" }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!(AssetImporter.GetAtPath(path) is AudioImporter imp)) continue;
                var s = imp.defaultSampleSettings; bool music = path.Contains("/Music/");
                var want = music ? AudioClipLoadType.Streaming : AudioClipLoadType.DecompressOnLoad;
                if (s.loadType == want && (!music || s.compressionFormat == AudioCompressionFormat.Vorbis)) continue;
                s.loadType = want;
                if (music) { s.compressionFormat = AudioCompressionFormat.Vorbis; s.quality = 0.7f; }
                else s.compressionFormat = AudioCompressionFormat.PCM;
                imp.defaultSampleSettings = s; imp.SaveAndReimport();
            }
            AssetDatabase.SaveAssets();
        }

        static void Lit(string name, Color c, float smooth, bool twoSided)
        {
            string path = Dir + "/" + name + ".mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            bool fresh = m == null;
            if (fresh) m = new Material(Shader.Find("HDRP/Lit"));
            m.SetColor("_BaseColor", c); m.SetFloat("_Smoothness", smooth); m.SetFloat("_Metallic", 0f);
            if (twoSided) { m.SetFloat("_DoubleSidedEnable", 1f); m.SetFloat("_DoubleSidedNormalMode", 0f); }
            m.enableInstancing = true;
            HDMaterial.ValidateMaterial(m);
            if (fresh) AssetDatabase.CreateAsset(m, path); else EditorUtility.SetDirty(m);
        }
    }
}
