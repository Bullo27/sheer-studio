// SHEER — supersampling in the player: the camera renders into a texture larger than the window, which a full-screen
// RawImage shows scaled down (bilinear = an exact box filter at 2x). Edges, knit and glints get real sub-pixel samples,
// so no temporal anti-aliasing (it smeared moving fabric) and no sharpening pass (it drew dark halos round every hole and
// along every silhouette) are needed. The frame hardly depends on the pixel count (RTX 3060: 5 ms at 0.4 MP, 6 ms at 1 MP).
//   -sheerSS F     samples per pixel side (1 = off, 1.5, 2; default: 2 while the render stays under ~6 megapixels)
// ADAPTIVE (the default, in play): the Studio's landscape window at 2x is ~6 MP - ~20 ms of GPU on an RTX 3060, i.e. 30 fps
// with vsync. So the factor steps down (2 -> 1.5 -> 1) while the GPU can't hold ~60 fps, and back up when it has room;
// captures and the Studio's screenshot test keep the fixed choice.
using System.Globalization;
using UnityEngine;
using UnityEngine.UI;

namespace Sheer
{
    [RequireComponent(typeof(Camera))]
    public class SheerSuperSample : MonoBehaviour
    {
        public float factor = 0f;                 // 0 = automatic
        public float pixelBudget = 6.2e6f;
        /// camera pixels per window pixel (mouse rays)
        public static float Scale { get; private set; } = 1f;
        /// share of the window's width the game view takes, from the left (the Studio panel sits on the right)
        public static float ViewFraction = 1f;
        float viewFrac = -1f;

        Camera cam; RenderTexture rt; RawImage img; GameObject imgCanvas;   // (the canvas itself: img.canvas is null while it is inactive)

        bool adaptive;
        void Awake()
        {
            cam = GetComponent<Camera>();
            var a = System.Environment.GetCommandLineArgs();
            for (int i = 0; i + 1 < a.Length; i++)
                if (a[i] == "-sheerSS") factor = float.Parse(a[i + 1], CultureInfo.InvariantCulture);
            adaptive = factor <= 0f && !Application.isBatchMode && System.Array.IndexOf(a, "-sheerCapture") < 0 && System.Array.IndexOf(a, "-sheerStudioTest") < 0 && System.Array.IndexOf(a, "-sheerShowcase") < 0;
            coolUntil = 4f;                                       // (no judging while the scene loads and the GPU clocks up)
        }

        // ---- adaptive factor: the GPU's own frame time (the frame time where the platform doesn't report it), averaged
        static readonly float[] Steps = { 1f, 1.5f, 2f };       // (whole and half steps: 2x is an exact box filter, 1.5x close)
        int step = -1; float acc, accF, accN, windowT, coolUntil; readonly FrameTiming[] ft = new FrameTiming[1];
        /// the factor in use (the Studio's HUD)
        public static float Current { get; private set; } = 1f;
        float Adaptive()
        {
            float maxF = Auto();
            int maxStep = maxF >= 2f ? 2 : maxF >= 1.5f ? 1 : 0;
            if (step < 0 || step > maxStep) step = maxStep;
            FrameTimingManager.CaptureFrameTimings();
            float frameMs = Time.unscaledDeltaTime * 1000f, ms = frameMs;
            if (FrameTimingManager.GetLatestTimings(1, ft) > 0 && ft[0].gpuFrameTime > 0.0) ms = (float)ft[0].gpuFrameTime;
            if (Time.unscaledTime < coolUntil) { acc = accF = accN = windowT = 0f; return Steps[step]; }
            acc += Mathf.Min(ms, 100f); accF += Mathf.Min(frameMs, 100f); accN++; windowT += Time.unscaledDeltaTime;
            if (windowT >= 1.5f)
            {
                // down only when the frames really come late AND the GPU is what holds them up (a GPU timer that counts the
                // vsync wait reads ~16.7 ms at a smooth 60 fps: the frame rate decides); up when the GPU has plenty of room
                float avg = acc / Mathf.Max(accN, 1f), avgF = accF / Mathf.Max(accN, 1f);
                if (avgF > 18f && avg > 14f && step > 0) { step--; coolUntil = Time.unscaledTime + 3f; Debug.Log($"[supersample] {avgF:0.0} ms a frame (gpu {avg:0.0}): down to {Steps[step]:0.#}x"); }
                else if (avg < 9.5f && avgF < 17.5f && step < maxStep) { step++; coolUntil = Time.unscaledTime + 6f; Debug.Log($"[supersample] {avgF:0.0} ms a frame (gpu {avg:0.0}): up to {Steps[step]:0.#}x"); }
                acc = accF = accN = windowT = 0f;
            }
            return Steps[step];
        }

        float Auto()
        {
            float p = Screen.width * (float)Screen.height;
            return p * 4f <= pixelBudget ? 2f : p * 2.25f <= pixelBudget ? 1.5f : 1f;
        }

        void LateUpdate()
        {
            float f = Mathf.Clamp(factor > 0f ? factor : adaptive ? Adaptive() : Auto(), 1f, 3f);
            Current = f;
            float vf = Mathf.Clamp(ViewFraction, 0.2f, 1f);
            if (f <= 1.001f) { Release(); cam.rect = new Rect(0f, 0f, vf, 1f); return; }
            cam.rect = new Rect(0f, 0f, 1f, 1f);
            int w = Mathf.RoundToInt(Screen.width * vf * f), h = Mathf.RoundToInt(Screen.height * f);
            if (rt && rt.width == w && rt.height == h && Mathf.Approximately(viewFrac, vf)) return;
            viewFrac = vf;
            Release();
            rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
            { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp, name = "supersample" };
            cam.targetTexture = rt;
            if (!img)
            {
                var go = new GameObject("SuperSampleView", typeof(Canvas)); imgCanvas = go;
                go.transform.SetParent(transform, false);
                var cv = go.GetComponent<Canvas>(); cv.renderMode = RenderMode.ScreenSpaceOverlay; cv.sortingOrder = -100;
                var ig = new GameObject("View", typeof(RectTransform)); ig.transform.SetParent(go.transform, false);
                var r = ig.GetComponent<RectTransform>(); r.anchorMin = Vector2.zero; r.anchorMax = Vector2.one; r.offsetMin = r.offsetMax = Vector2.zero;
                img = ig.AddComponent<RawImage>(); img.raycastTarget = false;
            }
            img.texture = rt; imgCanvas.SetActive(true);
            img.rectTransform.anchorMax = new Vector2(vf, 1f);
            Scale = (float)w / (Screen.width * vf);
            Shader.SetGlobalFloat("_SheerPixelScale", Scale);
            Debug.Log($"[supersample] {f:0.##}x: {w} x {h} for a {Screen.width} x {Screen.height} window");
        }

        void Release()
        {
            if (!rt) return;
            if (cam) cam.targetTexture = null;
            if (imgCanvas) imgCanvas.SetActive(false);
            rt.Release(); Destroy(rt); rt = null; Scale = 1f;
            Shader.SetGlobalFloat("_SheerPixelScale", 1f);
        }

        void OnDestroy() { Release(); }
    }
}
