// SHEER — "TensionData: Pantyhose": the original demo's inspector, field for field (names, sections,
// slider ranges read off the video, default values = the values shown in the video). Pushes the values
// to the stocking material every frame, so they are live player controls (also from the in-game panel).
using UnityEngine;

namespace Sheer
{
    // (Both first: 0 is what every saved look and the scene hold - written when the mode did nothing, it must keep the full
    //  look now that it works)
    public enum TensionMode { Both, Stretch, Compression }

    [ExecuteAlways]
    public class TensionData : MonoBehaviour
    {
        [Range(0f, 1.6f)] public float normalStrength = 1f;     // (its knob sits at 0.626 of the track for 1 in the video)
        public int weaveTiling = 12;
        public Texture2D weaveNormalMap;
        [Range(0f, 1f)] public float weaveNormalStrength = 0.845f;
        [Range(0f, 1f)] public float weaveContrast = 0.025f;

        [Header("Tension & Wrinkles")]
        [Tooltip("Which strain draws creases: Stretch - the lines along a pull; Compression - the buckled folds; Both (default).")]
        public TensionMode tensionMode = TensionMode.Both;
        public Texture2D baseWrinkleMap;
        public Texture2D wrinkleMap;
        public float wrinkleStrength = 9f;
        [Range(0f, 4f)] public float tensionNormalBoost = 1.5f;

        [Header("Pearl Sheen & Glints")]
        [Range(0f, 1f)] public float pearlStrength = 0.387f;
        [Range(0f, 1000f)] public float pearlGrainScale = 572f;
        [Range(0f, 1f)] public float pearlRandomness = 0.435f;
        [Range(0f, 4f)] public float pearlSpecularStrength = 0.64f;
        [Range(0f, 1f)] public float pearlEdgeStrength = 0.128f;
        [Range(0f, 1f)] public float pearlEdgeStart = 0f;
        [Range(0f, 5f)] public float pearlEdgeWidthPower = 0.54f;
        [Range(0.001f, 0.04f)] public float pearlPullEdgeWidth = 0.0122f;
        [Range(0f, 2f)] public float pearlGlintStrength = 0.85f;      // (up to 1: how many glints flash; 1 - 2: how bright)
        [Range(0f, 1f)] public float pearlGlintDensity = 0.117f;

        [Header("Frost & Sheerness")]
        [Range(0f, 1f)] public float frostBodyCoverage = 0.829f;
        [Range(0f, 1f)] public float frostFootCoverage = 0.889f;
        [Range(0f, 1f)] public float frostClearAtStretch = 1f;
        [Range(0f, 1f)] public float frostMatteSmoothness = 0.837f;
        public Texture2D frostFootMask;
        [Range(0f, 1f)] public float frostBoundaryStrength = 1f;
        [Range(0f, 32f)] public float frostBoundaryWidthPx = 5.9f;

        [Header("Look-dev (Studio's pro tab)")]
        [Tooltip("0 final, 1 tension, 2 wales / courses, 3 ladder fields, 4 opacity, 5 holes, 6 cloth lattice")] public int debugView;

        [Header("Targets")]
        public Renderer[] pantyhoseRenderers;
        public Renderer[] skinRenderers;               // under-nylon light uses the body coverage

        public void ResetToVideoValues()
        {
            normalStrength = 1f; weaveTiling = 12; weaveNormalStrength = 0.845f; weaveContrast = 0.025f;
            tensionMode = TensionMode.Both; wrinkleStrength = 9f; tensionNormalBoost = 1.5f;
            pearlStrength = 0.387f; pearlGrainScale = 572f; pearlRandomness = 0.435f; pearlSpecularStrength = 0.64f;
            pearlEdgeStrength = 0.128f; pearlEdgeStart = 0f; pearlEdgeWidthPower = 0.54f; pearlPullEdgeWidth = 0.0122f;
            pearlGlintStrength = 0.85f; pearlGlintDensity = 0.117f;
            frostBodyCoverage = 0.829f; frostFootCoverage = 0.889f; frostClearAtStretch = 1f; frostMatteSmoothness = 0.837f;
            frostBoundaryStrength = 1f; frostBoundaryWidthPx = 5.9f;
        }

        MaterialPropertyBlock mpb;
        Texture2D generatedWeave; float knitMean = 0.86f;

        void Awake() { EnsureWeave(); }
        void LateUpdate() { Push(); }
        void OnValidate() { Push(); }

        void EnsureWeave()
        {
            if (weaveNormalMap || generatedWeave) return;
            generatedWeave = SheerWeave.Build(out knitMean);
            generatedWeave.hideFlags = HideFlags.DontSave;
        }

        public void Push()
        {
            if (skinRenderers != null)
                foreach (var r in skinRenderers)
                {
                    if (!r) continue;
                    mpb ??= new MaterialPropertyBlock();
                    r.GetPropertyBlock(mpb);
                    mpb.SetFloat("_FrostBodyCoverage", frostBodyCoverage);
                    r.SetPropertyBlock(mpb);
                }
            if (pantyhoseRenderers == null) return;
            EnsureWeave();
            mpb ??= new MaterialPropertyBlock();
            foreach (var r in pantyhoseRenderers)
            {
                if (!r) continue;
                int nm = Mathf.Max(1, r.sharedMaterials.Length);
                for (int mi = 0; mi < nm; mi++)            // per-material blocks (they also carry each leg's tear map)
                {
                    r.GetPropertyBlock(mpb, mi);
                    mpb.SetFloat("_NormalStrength", normalStrength);
                    mpb.SetFloat("_WeaveTiling", weaveTiling);
                    mpb.SetFloat("_WeaveNormalStrength", weaveNormalStrength);
                    mpb.SetFloat("_WeaveContrast", weaveContrast);
                    mpb.SetFloat("_TensionMode", (float)tensionMode);
                    mpb.SetFloat("_WrinkleStrength", wrinkleStrength);
                    mpb.SetFloat("_TensionNormalBoost", tensionNormalBoost);
                    mpb.SetFloat("_PearlStrength", pearlStrength);
                    mpb.SetFloat("_PearlGrainScale", pearlGrainScale);
                    mpb.SetFloat("_PearlRandomness", pearlRandomness);
                    mpb.SetFloat("_PearlSpecularStrength", pearlSpecularStrength);
                    mpb.SetFloat("_PearlEdgeStrength", pearlEdgeStrength);
                    mpb.SetFloat("_PearlEdgeStart", pearlEdgeStart);
                    mpb.SetFloat("_PearlEdgeWidthPower", pearlEdgeWidthPower);
                    mpb.SetFloat("_PearlPullEdgeWidth", pearlPullEdgeWidth);
                    mpb.SetFloat("_PearlGlintStrength", pearlGlintStrength);
                    mpb.SetFloat("_PearlGlintDensity", pearlGlintDensity);
                    mpb.SetFloat("_FrostBodyCoverage", frostBodyCoverage);
                    mpb.SetFloat("_FrostFootCoverage", frostFootCoverage);
                    mpb.SetFloat("_FrostClearAtStretch", frostClearAtStretch);
                    mpb.SetFloat("_FrostMatteSmoothness", frostMatteSmoothness);
                    mpb.SetFloat("_FrostBoundaryStrength", frostBoundaryStrength);
                    mpb.SetFloat("_FrostBoundaryWidthM", frostBoundaryWidthPx * 0.0076f);   // foot-mask texel ~7.6 mm of leg
                    mpb.SetFloat("_KnitMean", knitMean);
                    mpb.SetFloat("_DebugTension", debugView);
                    var weave = weaveNormalMap ? weaveNormalMap : generatedWeave;
                    if (weave) mpb.SetTexture("_WeaveMap", weave);
                    r.SetPropertyBlock(mpb, mi);
                }
            }
        }
    }
}
