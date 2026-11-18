// SHEER — on-screen UI like the original: VIEW 01 / VIEW 02 buttons (bottom left; active = steel blue,
// inactive = translucent dark plate) and the "TensionData: Pantyhose" inspector as an in-game panel
// (Tab), every field live, with "Reset to video values" and "Repair stockings". Built in code (uGUI).
using System;
using System.Reflection;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Sheer
{
    public class SheerUI : MonoBehaviour
    {
        public CameraRig rig;
        public TensionData tension;
        public TightsSim sim;
        public Font font;
        public bool showInspector;
        public KeyCode inspectorKey = KeyCode.Tab;

        static readonly Color Active = new Color32(76, 119, 148, 255), Inactive = new Color32(14, 16, 22, 165), Pressed = new Color32(60, 96, 122, 255);
        Image[] btn = new Image[2];
        GameObject panel;
        RawImage cursorImg;
        int activeView;
        Canvas canvas;

        void Start()
        {
            if (!font) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (!FindAnyObjectByType<EventSystem>())
            {
                var es = new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
                es.transform.SetParent(transform);
            }
            var cgo = new GameObject("UI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            cgo.transform.SetParent(transform, false);
            canvas = cgo.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceOverlay; canvas.sortingOrder = 10;
            // (sized for reading, following the window: SheerKit.UiScale - the original's buttons are 2.6 % of the window high,
            //  18 px on a 700 px window with 8 px lettering)
            SheerKit.SetScale(canvas, SheerKit.UiScale());
            // VIEW buttons: bottom left, VIEW 01 above VIEW 02 as in the original
            string[] labels = { "VIEW 01", "VIEW 02" };
            for (int i = 0; i < 2; i++)
            {
                int v = i;
                var b = Rect(cgo.transform, labels[i], Vector2.zero, Vector2.zero);
                var brt = b.GetComponent<RectTransform>(); brt.pivot = Vector2.zero; brt.sizeDelta = new Vector2(124, 36); brt.anchoredPosition = new Vector2(22, 22 + (1 - i) * 44);
                btn[i] = b.AddComponent<Image>();
                var button = b.AddComponent<Button>(); button.transition = Selectable.Transition.None;
                button.onClick.AddListener(() => { rig.SwitchTo(v); SetActiveView(v); });
                var t = Text(b.transform, labels[i], 15f, TextAnchor.MiddleCenter);
                t.fontStyle = FontStyle.Bold;
            }
            SetActiveView(0);
            // (the old inspector panel is now the Studio's 'Stockings' tab: SheerStudio builds the whole side panel)
            if (!FindAnyObjectByType<SheerStudio>()) gameObject.AddComponent<SheerStudio>();
            I = this;
            var cur = Rect(cgo.transform, "SoftwareCursor", Vector2.zero, Vector2.zero);
            cursorImg = cur.AddComponent<RawImage>(); cursorImg.texture = ArrowTexture(); cursorImg.raycastTarget = false;
            var rt = cur.GetComponent<RectTransform>(); rt.pivot = new Vector2(0, 1); rt.sizeDelta = new Vector2(13, 21) * 0.7f;
            cur.SetActive(false);
        }

        static SheerUI I;
        /// all of this UI on / off (the Studio's H key and photo mode)
        public static void SetVisible(bool v) { if (I && I.canvas) I.canvas.enabled = v; }
        /// a view chosen elsewhere (the Studio's camera tab): light the matching VIEW button
        public static void MarkView(int v) { if (I) I.SetActiveView(v); }

        void Update()
        {
            PerfLog();
            if (canvas) SheerKit.SetScale(canvas, SheerKit.UiScale());
            if (!SheerStudio.HotkeysOk) return;                     // (typing a number in a field, or a word: not a key command)
            if (Input.GetKeyDown(KeyCode.P)) StartReplay();
            if (Input.GetKeyDown(KeyCode.Alpha1)) { rig.SwitchTo(0); SetActiveView(0); }
            if (Input.GetKeyDown(KeyCode.Alpha2)) { rig.SwitchTo(1); SetActiveView(1); }
        }

        public void SetActiveView(int v, int pressed = -1)
        {
            activeView = v;
            for (int i = 0; i < 2; i++) if (btn[i]) btn[i].color = i == pressed ? Pressed : i == v ? Active : Inactive;
        }

        /// Software cursor (for captures of the replay; the OS cursor isn't in screenshots).
        public void SetSoftwareCursor(Vector2 normTopLeft, bool visible)
        {
            if (!cursorImg) return;
            cursorImg.gameObject.SetActive(visible);
            var rt = cursorImg.rectTransform;
            rt.anchorMin = rt.anchorMax = new Vector2(normTopLeft.x, 1f - normTopLeft.y);
            rt.anchoredPosition = Vector2.zero;
        }

        // ------------------------------------------------------------------ inspector panel
        void BuildInspector(Transform parent)
        {
            panel = Rect(parent, "Inspector", new Vector2(0.70f, 0.04f), new Vector2(0.99f, 0.97f));
            panel.AddComponent<Image>().color = new Color(0.12f, 0.12f, 0.13f, 0.92f);
            var scroll = panel.AddComponent<ScrollRect>(); scroll.horizontal = false; scroll.scrollSensitivity = 30;
            var content = Rect(panel.transform, "Content", new Vector2(0, 1), new Vector2(1, 1));
            var crt = content.GetComponent<RectTransform>(); crt.pivot = new Vector2(0.5f, 1);
            var vl = content.AddComponent<VerticalLayoutGroup>(); vl.padding = new RectOffset(12, 12, 10, 10); vl.spacing = 4;
            vl.childControlHeight = true; vl.childControlWidth = true; vl.childForceExpandHeight = false;
            content.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.content = crt; panel.AddComponent<RectMask2D>();
            Row(content.transform, "TensionData: Pantyhose", 17, FontStyle.Bold);
            foreach (var f in typeof(TensionData).GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                var hdr = f.GetCustomAttribute<HeaderAttribute>();
                if (hdr != null && hdr.header != "Targets") Row(content.transform, hdr.header, 15, FontStyle.Bold);
                var rng = f.GetCustomAttribute<RangeAttribute>();
                if (f.FieldType == typeof(float) && rng != null) SliderRow(content.transform, f, rng.min, rng.max);
                else if (f.FieldType == typeof(float)) SliderRow(content.transform, f, 0f, Mathf.Max(1f, (float)f.GetValue(tension) * 4f));
                else if (f.FieldType == typeof(int)) SliderRow(content.transform, f, 1, 64, true);
                else if (f.FieldType == typeof(TensionMode)) Row(content.transform, Nice(f.Name) + ":  " + f.GetValue(tension), 13, FontStyle.Normal);
            }
            ButtonRow(content.transform, "Reset to video values", () => { tension.ResetToVideoValues(); RefreshSliders(); });
            ButtonRow(content.transform, "Repair stockings", () => sim.ResetDamage());
            ButtonRow(content.transform, "Replay the original session (P)", StartReplay);
            Row(content.transform, "Left drag: pull the fabric   Right drag: orbit   Wheel: zoom   1/2: views   Tab: this panel", 12, FontStyle.Italic);
            panel.SetActive(showInspector);
        }

        readonly System.Collections.Generic.List<Action> refreshers = new System.Collections.Generic.List<Action>();
        void RefreshSliders() { foreach (var r in refreshers) r(); }

        static string Nice(string n)
        {
            var s = new System.Text.StringBuilder();
            for (int i = 0; i < n.Length; i++) { if (i > 0 && char.IsUpper(n[i])) s.Append(' '); s.Append(i == 0 ? char.ToUpper(n[i]) : n[i]); }
            return s.ToString();
        }

        void SliderRow(Transform parent, FieldInfo f, float min, float max, bool whole = false)
        {
            var row = new GameObject(f.Name, typeof(RectTransform)); row.transform.SetParent(parent, false);
            row.AddComponent<LayoutElement>().preferredHeight = 22;
            var label = Text(row.transform, Nice(f.Name), 13, TextAnchor.MiddleLeft); Anchor(label.rectTransform, 0, 0.5f);
            var val = Text(row.transform, "", 13, TextAnchor.MiddleRight); Anchor(val.rectTransform, 0.86f, 1f);
            var sgo = new GameObject("Slider", typeof(RectTransform)); sgo.transform.SetParent(row.transform, false);
            Anchor(sgo.GetComponent<RectTransform>(), 0.5f, 0.85f);
            var bg = new GameObject("Bg", typeof(RectTransform)); bg.transform.SetParent(sgo.transform, false);
            var bgr = bg.GetComponent<RectTransform>(); bgr.anchorMin = new Vector2(0, 0.4f); bgr.anchorMax = new Vector2(1, 0.6f); bgr.offsetMin = bgr.offsetMax = Vector2.zero;
            bg.AddComponent<Image>().color = new Color(0.3f, 0.3f, 0.32f);
            var fill = new GameObject("Fill", typeof(RectTransform)); fill.transform.SetParent(sgo.transform, false);
            var fr = fill.GetComponent<RectTransform>(); fr.anchorMin = new Vector2(0, 0.4f); fr.anchorMax = new Vector2(1, 0.6f); fr.offsetMin = fr.offsetMax = Vector2.zero;
            fill.AddComponent<Image>().color = new Color(0.3f, 0.47f, 0.58f);
            var handle = new GameObject("Handle", typeof(RectTransform)); handle.transform.SetParent(sgo.transform, false);
            handle.GetComponent<RectTransform>().sizeDelta = new Vector2(10, 0);
            var hi = handle.AddComponent<Image>(); hi.color = new Color(0.85f, 0.85f, 0.88f);
            var s = sgo.AddComponent<Slider>(); s.fillRect = fr; s.handleRect = handle.GetComponent<RectTransform>(); s.targetGraphic = hi;
            s.minValue = min; s.maxValue = max; s.wholeNumbers = whole;
            Action refresh = () =>
            {
                float v = f.FieldType == typeof(int) ? (int)f.GetValue(tension) : (float)f.GetValue(tension);
                s.SetValueWithoutNotify(v); val.text = whole ? ((int)v).ToString() : v.ToString(v >= 100 ? "F0" : v >= 1 ? "F2" : "F3");
            };
            refresh(); refreshers.Add(refresh);
            s.onValueChanged.AddListener(v =>
            {
                if (f.FieldType == typeof(int)) f.SetValue(tension, Mathf.RoundToInt(v)); else f.SetValue(tension, v);
                refresh();
            });
        }

        void Row(Transform parent, string text, int size, FontStyle style)
        {
            var t = Text(parent, text, size, TextAnchor.MiddleLeft); t.fontStyle = style;
            t.gameObject.AddComponent<LayoutElement>().preferredHeight = size + 8;
        }

        void ButtonRow(Transform parent, string text, Action onClick)
        {
            var go = new GameObject(text, typeof(RectTransform)); go.transform.SetParent(parent, false);
            go.AddComponent<LayoutElement>().preferredHeight = 26;
            go.AddComponent<Image>().color = new Color(0.25f, 0.27f, 0.3f);
            go.AddComponent<Button>().onClick.AddListener(() => onClick());
            Text(go.transform, text, 13, TextAnchor.MiddleCenter);
        }

        // ------------------------------------------------------------------ helpers
        static GameObject Rect(Transform parent, string name, Vector2 aMin, Vector2 aMax)
        {
            var go = new GameObject(name, typeof(RectTransform)); go.transform.SetParent(parent, false);
            var rt = go.GetComponent<RectTransform>(); rt.anchorMin = aMin; rt.anchorMax = aMax; rt.offsetMin = rt.offsetMax = Vector2.zero;
            return go;
        }
        static void Anchor(RectTransform rt, float x0, float x1) { rt.anchorMin = new Vector2(x0, 0); rt.anchorMax = new Vector2(x1, 1); rt.offsetMin = rt.offsetMax = Vector2.zero; }

        Text Text(Transform parent, string s, float size, TextAnchor anchor)
        {
            var go = new GameObject("Text", typeof(RectTransform)); go.transform.SetParent(parent, false);
            var rt = go.GetComponent<RectTransform>(); rt.anchorMin = Vector2.zero; rt.anchorMax = Vector2.one; rt.offsetMin = rt.offsetMax = Vector2.zero;
            var t = go.AddComponent<Text>(); t.font = font; t.text = s; t.fontSize = Mathf.RoundToInt(size); t.alignment = anchor;
            t.color = Color.white; t.raycastTarget = false;
            return t;
        }

        // the original's arrow cursor (polygon from tools/composite.py), white with a black outline
        public static Texture2D ArrowTexture()
        {
            Vector2[] P = { new(0, 0), new(0, 16.5f), new(4.2f, 12.6f), new(7.2f, 19.6f), new(9.6f, 18.6f), new(6.7f, 11.9f), new(12.2f, 11.9f) };
            int W = 13 * 4, H = 21 * 4; var tex = new Texture2D(W, H, TextureFormat.RGBA32, false) { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp };
            var px = new Color32[W * H];
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                {
                    var q = new Vector2((x + 0.5f) / 4f, (H - 1 - y + 0.5f) / 4f);     // texture rows go up; the polygon's y goes down
                    float d = Dist(P, q); bool inside = Inside(P, q);
                    px[y * W + x] = inside ? (d < 0.9f ? new Color32(0, 0, 0, 255) : new Color32(255, 255, 255, 255)) : (d < 0.6f ? new Color32(0, 0, 0, 255) : new Color32(0, 0, 0, 0));
                }
            tex.SetPixels32(px); tex.Apply(); return tex;
        }
        static bool Inside(Vector2[] P, Vector2 q)
        {
            bool c = false;
            for (int i = 0, j = P.Length - 1; i < P.Length; j = i++)
                if (((P[i].y > q.y) != (P[j].y > q.y)) && (q.x < (P[j].x - P[i].x) * (q.y - P[i].y) / (P[j].y - P[i].y) + P[i].x)) c = !c;
            return c;
        }
        static float Dist(Vector2[] P, Vector2 q)
        {
            float best = 1e9f;
            for (int i = 0, j = P.Length - 1; i < P.Length; j = i++)
            {
                Vector2 a = P[j], b = P[i], ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(q - a, ab) / ab.sqrMagnitude);
                best = Mathf.Min(best, (a + ab * t - q).magnitude);
            }
            return best;
        }

        /// Replays the original video's 36 s session (cursor, presses, camera moves) on this simulator.
        void StartReplay()
        {
            var rd = FindAnyObjectByType<ReplayDriver>();
            if (rd && !rd.IsRunning) rd.Play();
        }

        // -sheerPerfLog: mean / worst frame time every 5 s in the player log (real-time check)
        float perfT, perfWorst; int perfN; bool? perfOn;
        double perfCpu, perfMain, perfRender, perfGpu; int perfFt; readonly FrameTiming[] perfFrame = new FrameTiming[1];
        double hSim, hDmg, hApply, hRaster; int hSub, hGc;
        void PerfLog()
        {
            perfOn ??= System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerPerfLog") >= 0;
            if (perfOn != true) return;
            float dt = Time.unscaledDeltaTime; perfT += dt; perfN++; perfWorst = Mathf.Max(perfWorst, dt);
            FrameTimingManager.CaptureFrameTimings();
            if (FrameTimingManager.GetLatestTimings(1, perfFrame) > 0)
            { perfCpu += perfFrame[0].cpuFrameTime; perfMain += perfFrame[0].cpuMainThreadFrameTime; perfRender += perfFrame[0].cpuRenderThreadFrameTime; perfGpu += perfFrame[0].gpuFrameTime; perfFt++; }
            // a slow frame: which system took the time (the counters' growth since the previous frame)
            if (dt > 0.035f && Time.frameCount > 30)
                Debug.Log($"[hitch] {dt * 1000f:0} ms at sim {(sim ? sim.simTime : 0f):0.00} s: cloth {TightsSim.profSimMs - hSim:0.0} ms ({TightsSim.profSubsteps - hSub} substeps), " +
                          $"damage {TightsSim.profDmgMs - hDmg:0.0}, pose+upload {TightsSim.profApplyMs - hApply:0.0}, raster {TightsSim.profRasterMs - hRaster:0.0}; " +
                          $"frame timing main {perfFrame[0].cpuMainThreadFrameTime:0.0} render {perfFrame[0].cpuRenderThreadFrameTime:0.0} gpu {perfFrame[0].gpuFrameTime:0.0}; GC {System.GC.CollectionCount(0) - hGc}");
            hSim = TightsSim.profSimMs; hDmg = TightsSim.profDmgMs; hApply = TightsSim.profApplyMs; hRaster = TightsSim.profRasterMs; hSub = TightsSim.profSubsteps; hGc = System.GC.CollectionCount(0);
            if (perfT >= 5f)
            {
                Debug.Log($"[perf] {perfN / perfT:0.0} fps mean, worst frame {perfWorst * 1000f:0} ms ({Screen.width}x{Screen.height}); per frame: " +
                          $"{TightsSim.profSubsteps / (float)perfN:0.0} substeps, cloth {TightsSim.profSimMs / perfN:0.0} ms, damage {TightsSim.profDmgMs / perfN:0.0} ms, " +
                          $"pose+upload {TightsSim.profApplyMs / perfN:0.0} ms, raster {TightsSim.profRasterMs / perfN:0.0} ms" +
                          (perfFt > 0 ? $"; frame timing: cpu {perfCpu / perfFt:0.0} ms (main {perfMain / perfFt:0.0}, render thread {perfRender / perfFt:0.0}), gpu {perfGpu / perfFt:0.0} ms" : ""));
                perfT = 0; perfN = 0; perfWorst = 0; perfCpu = perfMain = perfRender = perfGpu = 0; perfFt = 0;
                TightsSim.profSimMs = TightsSim.profDmgMs = TightsSim.profApplyMs = TightsSim.profRasterMs = 0; TightsSim.profSubsteps = 0;
                hSim = hDmg = hApply = hRaster = 0; hSub = 0;
            }
        }
    }
}
