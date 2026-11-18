// SHEER — the LOADING SCREEN (user, 2026-11-17: 'the initial screen stays black for 10 - 15 seconds ... so the user knows
// it's all ok'). The player's first scene (Scenes/Boot.unity) holds only this: it draws a banner at once - no camera, no
// render pipeline to start - and loads the simulator's scene behind it. The banner stays over the simulator's first
// frames (their shaders are prepared then) and fades when the picture runs.
// The bar follows what can be followed: the scene's files arriving (the first half), then the simulator setting itself
// up and drawing its first frames (the window does not repaint during those seconds: the banner says so).
using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Sheer
{
    public class SheerBoot : MonoBehaviour
    {
        Canvas canvas; Image fill; Text status, hint; CanvasGroup group; RectTransform dots;
        float shown;

        IEnumerator Start()
        {
            float t0 = Time.realtimeSinceStartup;
            // tests and captures in batch mode have no window: straight on
            if (Application.isBatchMode) { SceneManager.LoadScene(1); yield break; }
            DontDestroyOnLoad(gameObject);
            SheerStudio.FirstRunLayout();                 // (the window's first-run size BEFORE the banner: no jump under it)
            SheerKit.Init();
            Build();
            Set(0.04f, "Loading");
            yield return null; yield return null;         // the banner is on the screen
            Debug.Log($"[boot] banner up at {Time.realtimeSinceStartup:0.00} s (boot scene took {Time.realtimeSinceStartup - t0:0.00} s)");
            var op = SceneManager.LoadSceneAsync(1, LoadSceneMode.Single);
            while (!op.isDone)
            {
                // (progress runs 0 .. 0.9 while the files load, then the scene wakes up in one long frame)
                Set(0.04f + 0.50f * Mathf.Clamp01(op.progress / 0.9f), op.progress < 0.89f ? "Loading" : "Setting up the simulator");
                yield return null;
            }
            Debug.Log($"[boot] scene awake at {Time.realtimeSinceStartup:0.00} s");
            Set(0.70f, "Preparing the first picture");
            // the simulator's first frames prepare their shaders (long frames): wait until the picture runs
            int smooth = 0, frames = 0; float tw = Time.realtimeSinceStartup;
            while (smooth < 3 && Time.realtimeSinceStartup - tw < 20f)
            {
                yield return null; frames++;
                smooth = Time.unscaledDeltaTime < 0.12f ? smooth + 1 : 0;
                Set(Mathf.Min(0.97f, 0.70f + 0.06f * frames), "Preparing the first picture");
            }
            Set(1f, "Ready");
            Debug.Log($"[boot] picture running at {Time.realtimeSinceStartup:0.00} s ({frames} frames)");
            for (float f = 0f; f < 1f; f += Time.unscaledDeltaTime / 0.45f) { group.alpha = 1f - f; yield return null; }
            Destroy(gameObject);
        }

        void Set(float k, string s)
        {
            shown = Mathf.Max(shown, k);
            if (fill) fill.rectTransform.anchorMax = new Vector2(shown, 1f);
            if (status) status.text = s;
        }

        void Update()
        {
            if (canvas) SheerKit.SetScale(canvas, Mathf.Min(SheerKit.UiScale(), 0.9f * Screen.width / 560f));
            // three dots walking: the window is alive whenever it repaints
            if (dots) for (int i = 0; i < dots.childCount; i++)
                {
                    float ph = Mathf.Repeat(Time.unscaledTime * 1.6f - i * 0.22f, 1f);
                    dots.GetChild(i).localScale = Vector3.one * (0.7f + 0.5f * Mathf.Max(0f, Mathf.Sin(ph * Mathf.PI)));
                }
        }

        void Build()
        {
            var cgo = new GameObject("LoadingUI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            cgo.transform.SetParent(transform, false);
            canvas = cgo.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceOverlay; canvas.sortingOrder = 500;
            SheerKit.SetScale(canvas, Mathf.Min(SheerKit.UiScale(), 0.9f * Screen.width / 560f));
            group = cgo.AddComponent<CanvasGroup>();
            // the whole window (no camera draws under it in the boot scene: this is also what clears the screen)
            var bg = SheerKit.Img(cgo.transform, "Bg", null, new Color32(26, 22, 30, 255), false); SheerKit.Fill(bg.rectTransform); bg.raycastTarget = true;
            var box = SheerKit.Rect(cgo.transform, "Box"); box.anchorMin = box.anchorMax = new Vector2(0.5f, 0.5f); box.sizeDelta = new Vector2(520, 260);
            var title = SheerKit.Label(box, "<color=#E84888>S</color><color=#FF7AAC>HEER</color>", 84, SheerKit.White, TextAnchor.MiddleCenter, true);
            var tr = title.rectTransform; tr.anchorMin = new Vector2(0, 1); tr.anchorMax = new Vector2(1, 1); tr.pivot = new Vector2(0.5f, 1); tr.sizeDelta = new Vector2(0, 110); tr.anchoredPosition = Vector2.zero;
            title.horizontalOverflow = HorizontalWrapMode.Overflow;
            var sub = SheerKit.Label(box, "a sheer-tights simulator", 20, new Color32(200, 180, 205, 255), TextAnchor.MiddleCenter, false);
            var sr = sub.rectTransform; sr.anchorMin = new Vector2(0, 1); sr.anchorMax = new Vector2(1, 1); sr.pivot = new Vector2(0.5f, 1); sr.sizeDelta = new Vector2(0, 30); sr.anchoredPosition = new Vector2(0, -108);
            // the bar
            var track = SheerKit.Img(box, "Track", SheerKit.Pill, new Color32(70, 58, 76, 255), true, 4f);
            var kr = track.rectTransform; kr.anchorMin = new Vector2(0.5f, 1); kr.anchorMax = new Vector2(0.5f, 1); kr.pivot = new Vector2(0.5f, 1); kr.sizeDelta = new Vector2(360, 10); kr.anchoredPosition = new Vector2(0, -168);
            fill = SheerKit.Img(track.transform, "Fill", SheerKit.Pill, SheerKit.Pink, true, 4f);
            var fr = fill.rectTransform; fr.anchorMin = Vector2.zero; fr.anchorMax = new Vector2(0.04f, 1f); fr.offsetMin = fr.offsetMax = Vector2.zero;
            status = SheerKit.Label(box, "Loading", 18, SheerKit.White, TextAnchor.MiddleRight, true);
            var st = status.rectTransform; st.anchorMin = st.anchorMax = new Vector2(0.5f, 1); st.pivot = new Vector2(1f, 1); st.sizeDelta = new Vector2(330, 30); st.anchoredPosition = new Vector2(150, -188);
            status.horizontalOverflow = HorizontalWrapMode.Overflow;
            dots = SheerKit.Rect(box, "Dots"); dots.anchorMin = dots.anchorMax = new Vector2(0.5f, 1); dots.pivot = new Vector2(0f, 1); dots.sizeDelta = new Vector2(40, 30); dots.anchoredPosition = new Vector2(156, -188);
            for (int i = 0; i < 3; i++)
            {
                var d = SheerKit.Img(dots, "Dot", SheerKit.Circle, SheerKit.Pink, false);
                var dr = d.rectTransform; dr.anchorMin = dr.anchorMax = new Vector2(0, 0.5f); dr.sizeDelta = new Vector2(7, 7); dr.anchoredPosition = new Vector2(6 + 12 * i, 0);
            }
            hint = SheerKit.Label(box, "The first start takes a little longer. The window may pause for a few seconds while the picture is prepared.", 15, new Color32(170, 150, 176, 255), TextAnchor.UpperCenter, false);
            var hr = hint.rectTransform; hr.anchorMin = new Vector2(0, 1); hr.anchorMax = new Vector2(1, 1); hr.pivot = new Vector2(0.5f, 1); hr.sizeDelta = new Vector2(0, 44); hr.anchoredPosition = new Vector2(0, -224);
        }
    }
}
