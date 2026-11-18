// SHEER — a small uGUI kit for the Studio panel, built in code: rounded, anti-aliased sprites drawn from signed distances
// (9-sliced), the M PLUS Rounded 1c font (Resources/Fonts, OFL), a pastel theme, and the widgets the panel is made of -
// sections, sliders, chips, colour swatches with a custom picker, switches, buttons. Every widget reads and writes the
// value it shows through a getter / setter, and refreshes when the look changes elsewhere (presets, randomize, load).
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Sheer
{
    public static class SheerKit
    {
        // ---- theme
        public static readonly Color Panel = new Color32(255, 248, 252, 244), Rail = new Color32(255, 230, 241, 255);
        public static readonly Color Pink = new Color32(255, 122, 172, 255), PinkDeep = new Color32(232, 72, 136, 255), PinkSoft = new Color32(255, 214, 231, 255);
        public static readonly Color Lavender = new Color32(186, 160, 255, 255), Mint = new Color32(118, 214, 190, 255), Sky = new Color32(132, 190, 255, 255);
        public static readonly Color Lemon = new Color32(255, 214, 120, 255);
        public static readonly Color Ink = new Color32(78, 54, 86, 255), InkSoft = new Color32(150, 118, 152, 255), White = Color.white;
        public static readonly Color Track = new Color32(240, 222, 234, 255), Chip = new Color32(255, 255, 255, 255), ChipLine = new Color32(240, 205, 224, 255);
        public static readonly Color[] SectionTints = { new Color32(255, 214, 231, 255), new Color32(226, 214, 255, 255), new Color32(204, 240, 228, 255), new Color32(214, 232, 255, 255), new Color32(255, 236, 200, 255) };

        public static Font Bold, Medium;
        public static Sprite Round8, Round14, Round22, Pill, Circle, Ring, Shadow, Heart, Star, Petal, Check, Chevron;
        static bool ready;

        public static void Init()
        {
            if (ready) return;
            ready = true;
            Bold = Resources.Load<Font>("Fonts/MPLUSRounded1c-Bold");
            Medium = Resources.Load<Font>("Fonts/MPLUSRounded1c-Medium");
            var fallback = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (!Bold) Bold = fallback;
            if (!Medium) Medium = Bold;
            Round8 = RoundRect(8); Round14 = RoundRect(14); Round22 = RoundRect(22); Pill = RoundRect(32);
            Circle = Shape(128, (x, y) => Mathf.Sqrt(x * x + y * y) - 60f);
            Ring = Shape(128, (x, y) => Mathf.Abs(Mathf.Sqrt(x * x + y * y) - 54f) - 7f);
            Heart = Shape(128, (x, y) => SdHeart(new Vector2(x, -y) / 92f + new Vector2(0f, 0.62f)) * 92f);
            Star = Shape(128, (x, y) => { float a = Mathf.Atan2(y, x), r = Mathf.Sqrt(x * x + y * y); return r - 56f * (0.62f + 0.38f * Mathf.Pow(Mathf.Abs(Mathf.Cos(2.5f * a)), 1.6f)); });
            Petal = Shape(128, (x, y) => { float yy = y + 8f; float w = 40f * Mathf.Sqrt(Mathf.Max(0f, 1f - (yy / 58f) * (yy / 58f))) * (1f - 0.35f * Mathf.Max(0f, yy / 58f)); float notch = yy > 40f ? 10f - Mathf.Abs(x) * 0.9f : -1e3f; return Mathf.Max(Mathf.Abs(x) - w, notch); });
            Check = Shape(128, (x, y) => Mathf.Min(SegD(new Vector2(x, y), new Vector2(-34, 2), new Vector2(-8, -24)), SegD(new Vector2(x, y), new Vector2(-8, -24), new Vector2(38, 28))) - 9f);
            Chevron = Shape(128, (x, y) => Mathf.Min(SegD(new Vector2(x, y), new Vector2(-36, 20), new Vector2(0, -18)), SegD(new Vector2(x, y), new Vector2(0, -18), new Vector2(36, 20))) - 11f);
            Shadow = SoftRect(28);
        }

        /// The UI's scale for this window, sized for READING (user, 2026-11-17: 'font size of the panel is plainly unreadable at
        /// my resolution'): 1 at a window 720 px high - where the panel's labels are 15 - 16 px - and growing with the window;
        /// never so large that a panel `panelW` units wide takes more than `maxShare` of the window's width; never below `min`.
        /// (Until then the panel was laid out for 1080 px and scaled DOWN with the window: 9 px labels on a 700 px window.)
        public static float UiScale(float panelW = 0f, float maxShare = 0.36f, float min = 0.8f)
        {
            float s = Screen.height / 720f;
            if (panelW > 0f) s = Mathf.Min(s, maxShare * Screen.width / panelW);
            return Mathf.Clamp(s, min, 4f);
        }
        /// ... applied to a canvas (constant pixel size x the scale)
        public static void SetScale(Canvas c, float s)
        {
            if (!c) return;
            var scl = c.GetComponent<CanvasScaler>(); if (!scl) return;
            scl.uiScaleMode = CanvasScaler.ScaleMode.ConstantPixelSize;
            if (!Mathf.Approximately(scl.scaleFactor, s)) scl.scaleFactor = s;
        }

        static float SegD(Vector2 p, Vector2 a, Vector2 b) { Vector2 ab = b - a; float t = Mathf.Clamp01(Vector2.Dot(p - a, ab) / ab.sqrMagnitude); return (a + ab * t - p).magnitude; }
        public static float SdHeart(Vector2 p)
        {
            p.x = Mathf.Abs(p.x);
            if (p.y + p.x > 1f) return (p - new Vector2(0.25f, 0.75f)).magnitude - 0.35355339f;
            Vector2 a = p - new Vector2(0f, 1f), b = p - 0.5f * Mathf.Max(p.x + p.y, 0f) * Vector2.one;
            return Mathf.Sqrt(Mathf.Min(a.sqrMagnitude, b.sqrMagnitude)) * Mathf.Sign(p.x - p.y);
        }

        /// A white shape from a signed distance (pixels, centre of an N x N texture at 0), anti-aliased over a pixel.
        public static Sprite Shape(int N, Func<float, float, float> sd)
        {
            var tex = new Texture2D(N, N, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Trilinear, name = "kit_shape" };
            var px = new Color32[N * N];
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float d = sd(x + 0.5f - N * 0.5f, y + 0.5f - N * 0.5f);
                    byte a = (byte)(Mathf.Clamp01(0.5f - d) * 255f);
                    px[y * N + x] = new Color32(255, 255, 255, a);
                }
            tex.SetPixels32(px); tex.Apply(true, true);
            return Sprite.Create(tex, new Rect(0, 0, N, N), new Vector2(0.5f, 0.5f), 100f);
        }

        /// A rounded rectangle for 9-slicing (corner radius r texels; Image.pixelsPerUnitMultiplier scales it).
        public static Sprite RoundRect(int r)
        {
            int N = 2 * r + 4;
            var tex = new Texture2D(N, N, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "kit_round" };
            var px = new Color32[N * N];
            float h = N * 0.5f;
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float qx = Mathf.Abs(x + 0.5f - h) - (h - r - 0.5f), qy = Mathf.Abs(y + 0.5f - h) - (h - r - 0.5f);
                    float d = new Vector2(Mathf.Max(qx, 0f), Mathf.Max(qy, 0f)).magnitude + Mathf.Min(Mathf.Max(qx, qy), 0f) - r;
                    px[y * N + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(0.5f - d) * 255f));
                }
            tex.SetPixels32(px); tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, N, N), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, new Vector4(r + 1, r + 1, r + 1, r + 1));
        }

        /// A soft drop shadow (9-sliced): alpha falls off over r texels outside a rounded core.
        static Sprite SoftRect(int r)
        {
            int N = 4 * r + 4;
            var tex = new Texture2D(N, N, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "kit_shadow" };
            var px = new Color32[N * N];
            float h = N * 0.5f;
            for (int y = 0; y < N; y++)
                for (int x = 0; x < N; x++)
                {
                    float qx = Mathf.Abs(x + 0.5f - h) - (h - 2 * r), qy = Mathf.Abs(y + 0.5f - h) - (h - 2 * r);
                    float d = new Vector2(Mathf.Max(qx, 0f), Mathf.Max(qy, 0f)).magnitude + Mathf.Min(Mathf.Max(qx, qy), 0f);
                    float a = Mathf.Clamp01(1f - d / (1.6f * r)); a = a * a * (3f - 2f * a);
                    px[y * N + x] = new Color32(0, 0, 0, (byte)(a * 255f));
                }
            tex.SetPixels32(px); tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, N, N), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect, new Vector4(2 * r, 2 * r, 2 * r, 2 * r));
        }

        // ------------------------------------------------------------------ building blocks
        public static RectTransform Rect(Transform parent, string name)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            return (RectTransform)go.transform;
        }
        public static RectTransform Fill(RectTransform r, float l = 0, float b = 0, float rt = 0, float t = 0)
        {
            r.anchorMin = Vector2.zero; r.anchorMax = Vector2.one; r.offsetMin = new Vector2(l, b); r.offsetMax = new Vector2(-rt, -t);
            return r;
        }
        public static Image Img(Transform parent, string name, Sprite s, Color c, bool sliced = true, float ppu = 1f)
        {
            var r = Rect(parent, name);
            var im = r.gameObject.AddComponent<Image>();
            im.sprite = s; im.color = c; im.type = sliced && s && s.border != Vector4.zero ? Image.Type.Sliced : Image.Type.Simple;
            im.pixelsPerUnitMultiplier = ppu; im.raycastTarget = false;
            return im;
        }
        public static Text Label(Transform parent, string s, int size, Color c, TextAnchor a = TextAnchor.MiddleLeft, bool bold = false)
        {
            var r = Rect(parent, "Text");
            var t = r.gameObject.AddComponent<Text>();
            t.font = bold ? Bold : Medium; t.fontSize = size; t.color = c; t.alignment = a; t.text = s;
            t.raycastTarget = false; t.horizontalOverflow = HorizontalWrapMode.Wrap; t.verticalOverflow = VerticalWrapMode.Overflow;
            t.supportRichText = true;
            return t;
        }
        public static LayoutElement Layout(Component c, float h = -1, float w = -1, float flexW = -1)
        {
            var le = c.GetComponent<LayoutElement>() ?? c.gameObject.AddComponent<LayoutElement>();
            if (h >= 0) le.preferredHeight = h; if (w >= 0) le.preferredWidth = w; if (flexW >= 0) le.flexibleWidth = flexW;
            return le;
        }
        /// "English|日本語" -> the English, and the Japanese small and soft after it
        public static string Bi(string s, int jpSize = 0)
        {
            int k = s.IndexOf('|');
            if (k < 0) return s;
            string en = s.Substring(0, k), jp = s.Substring(k + 1);
            return jpSize > 0 ? $"{en} <size={jpSize}><color=#{ColorUtility.ToHtmlStringRGB(InkSoft)}>{jp}</color></size>" : en;
        }
        public static string En(string s) { int k = s.IndexOf('|'); return k < 0 ? s : s.Substring(0, k); }
        public static string Jp(string s) { int k = s.IndexOf('|'); return k < 0 ? "" : s.Substring(k + 1); }

        /// A button with a rounded plate, a press bounce, and a click sound.
        public static Button Button(Transform parent, string text, Color plate, Color ink, Action onClick, int size = 15, Sprite s = null)
        {
            var im = Img(parent, "Button", s ? s : Round14, plate, true, 1f);
            im.raycastTarget = true;
            var b = im.gameObject.AddComponent<Button>();
            b.targetGraphic = im;
            var cb = b.colors; cb.normalColor = Color.white; cb.highlightedColor = new Color(1f, 0.96f, 0.98f); cb.pressedColor = new Color(0.9f, 0.85f, 0.9f); cb.fadeDuration = 0.08f; b.colors = cb;
            var t = Label(im.transform, text, size, ink, TextAnchor.MiddleCenter, true); Fill(t.rectTransform, 4, 0, 4, 0);
            b.onClick.AddListener(() => { SheerAudio.Ui("pop"); onClick?.Invoke(); });
            im.gameObject.AddComponent<SheerBounce>();
            return b;
        }
    }

    /// Hover / press feedback: grows a little under the pointer, squashes when pressed.
    public class SheerBounce : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler, IPointerDownHandler, IPointerUpHandler
    {
        float target = 1f, s = 1f, v;
        public void OnPointerEnter(PointerEventData e) => target = 1.04f;
        public void OnPointerExit(PointerEventData e) => target = 1f;
        public void OnPointerDown(PointerEventData e) => target = 0.94f;
        public void OnPointerUp(PointerEventData e) => target = 1.04f;
        void OnDisable() { s = target = 1f; v = 0f; transform.localScale = Vector3.one; }
        void Update()
        {
            // (idle once settled: writing the scale of every chip each frame made the panel's canvas rebuild every frame)
            if (s == target && v == 0f) return;
            s = Mathf.SmoothDamp(s, target, ref v, 0.06f, 50f, Time.unscaledDeltaTime);
            if (Mathf.Abs(s - target) < 0.0005f && Mathf.Abs(v) < 0.01f) { s = target; v = 0f; }
            transform.localScale = new Vector3(s, s, 1f);
        }
    }

    /// The panel's widgets in one vertical list; every widget refreshes from the look on Refresh(). Sized for reading: at
    /// scale 1 (a window 720 px high) labels are 15 - 16 px and the scale grows with the window (SheerKit.UiScale).
    /// Sections fold: a click on a section's header hides or shows its rows.
    public class SheerForm
    {
        public readonly RectTransform root;
        public float width = 372f;                       // content width (units of the panel's scale)
        readonly List<Action> refresh = new List<Action>();
        List<GameObject> group;                          // the rows of the section being filled
        public SheerForm(RectTransform content) { root = content; }
        public void Refresh() { foreach (var r in refresh) r(); }
        public void Clear() { refresh.Clear(); group = null; for (int i = root.childCount - 1; i >= 0; i--) UnityEngine.Object.Destroy(root.GetChild(i).gameObject); }

        public RectTransform Row(float h)
        {
            var r = SheerKit.Rect(root, "Row");
            SheerKit.Layout(r, h);
            group?.Add(r.gameObject);
            return r;
        }

        /// A section's header; the rows added after it are its content (folded away by a click on the header).
        public void Section(string title, Color tint, string hint = null)
        {
            group = null;
            var r = Row(48);
            var bg = SheerKit.Img(r, "Header", SheerKit.Round14, tint, true, 1.2f); bg.raycastTarget = true;
            SheerKit.Fill(bg.rectTransform, 0, 3, 0, 7);
            var chev = SheerKit.Img(bg.transform, "Chevron", SheerKit.Chevron, SheerKit.Ink, false);
            var cr = chev.rectTransform; cr.anchorMin = cr.anchorMax = new Vector2(0, 0.5f); cr.sizeDelta = new Vector2(16, 16); cr.anchoredPosition = new Vector2(20, 0);
            var t = SheerKit.Label(bg.transform, SheerKit.En(title), 18, SheerKit.Ink, TextAnchor.MiddleLeft, true);
            SheerKit.Fill(t.rectTransform, 38, 0, 8, 0);
            var rows = new List<GameObject>(); group = rows;
            bool isOpen = true;
            var b = bg.gameObject.AddComponent<Button>(); b.targetGraphic = bg; b.transition = Selectable.Transition.None;
            b.onClick.AddListener(() =>
            {
                isOpen = !isOpen; SheerAudio.Ui("pop");
                foreach (var g in rows) if (g) g.SetActive(isOpen);
                cr.localRotation = Quaternion.Euler(0f, 0f, isOpen ? 0f : 90f);
            });
            if (hint != null) Note(hint);
        }

        public void Note(string text, int size = 14)
        {
            var t = SheerKit.Label(root, text, size, SheerKit.InkSoft, TextAnchor.UpperLeft);
            string plain = System.Text.RegularExpressions.Regex.Replace(text, "<.*?>", "");
            int lines = Mathf.CeilToInt(plain.Length / Mathf.Max(width / (size * 0.54f), 20f));
            SheerKit.Layout(t, Mathf.Max(size + 8, (size + 5) * lines + 6));
            group?.Add(t.gameObject);
        }

        public Slider Slider(string label, float min, float max, Func<float> get, Action<float> set, string fmt = "0.00", bool whole = false, string unit = "")
        {
            var r = Row(42);
            var l = SheerKit.Label(r, SheerKit.En(label), 15, SheerKit.Ink); var lr = l.rectTransform; lr.anchorMin = new Vector2(0, 0); lr.anchorMax = new Vector2(0.36f, 1); lr.offsetMin = new Vector2(6, 0); lr.offsetMax = Vector2.zero;
            var v = SheerKit.Label(r, "", 14, SheerKit.InkSoft, TextAnchor.MiddleRight); var vr = v.rectTransform; vr.anchorMin = new Vector2(0.84f, 0); vr.anchorMax = new Vector2(1, 1); vr.offsetMin = Vector2.zero; vr.offsetMax = new Vector2(-4, 0);
            var sgo = SheerKit.Rect(r, "Slider"); sgo.anchorMin = new Vector2(0.37f, 0); sgo.anchorMax = new Vector2(0.83f, 1); sgo.offsetMin = sgo.offsetMax = Vector2.zero;
            var track = SheerKit.Img(sgo, "Track", SheerKit.Pill, SheerKit.Track, true, 4f); var tr = track.rectTransform; tr.anchorMin = new Vector2(0, 0.5f); tr.anchorMax = new Vector2(1, 0.5f); tr.sizeDelta = new Vector2(0, 10);
            var fillArea = SheerKit.Rect(sgo, "FillArea"); fillArea.anchorMin = new Vector2(0, 0.5f); fillArea.anchorMax = new Vector2(1, 0.5f); fillArea.sizeDelta = new Vector2(0, 10);
            var fill = SheerKit.Img(fillArea, "Fill", SheerKit.Pill, SheerKit.Pink, true, 4f); SheerKit.Fill(fill.rectTransform);
            var handleArea = SheerKit.Rect(sgo, "HandleArea"); SheerKit.Fill(handleArea, 12, 0, 12, 0);
            var handle = SheerKit.Img(handleArea, "Handle", SheerKit.Circle, SheerKit.White, false); handle.rectTransform.sizeDelta = new Vector2(26, 26);
            var ring = SheerKit.Img(handle.transform, "Ring", SheerKit.Ring, SheerKit.Pink, false); SheerKit.Fill(ring.rectTransform, -1, -1, -1, -1);
            var s = sgo.gameObject.AddComponent<Slider>();
            s.fillRect = fill.rectTransform; s.handleRect = handle.rectTransform; s.targetGraphic = handle; handle.raycastTarget = true; track.raycastTarget = true;
            s.minValue = min; s.maxValue = max; s.wholeNumbers = whole;
            bool busy = false; float lastTick = 0f;
            Action rf = () => { busy = true; float x = get(); s.SetValueWithoutNotify(x); v.text = x.ToString(fmt) + unit; busy = false; };
            rf(); refresh.Add(rf);
            s.onValueChanged.AddListener(x =>
            {
                if (busy) return;
                set(x); v.text = x.ToString(fmt) + unit;
                if (Time.unscaledTime - lastTick > 0.05f) { SheerAudio.Ui("tick"); lastTick = Time.unscaledTime; }
            });
            return s;
        }

        void Caption(string label)
        {
            if (string.IsNullOrEmpty(label)) return;
            var lr = Row(26); var l = SheerKit.Label(lr, SheerKit.En(label), 15, SheerKit.Ink); SheerKit.Fill(l.rectTransform, 6, 0, 0, 0);
        }

        /// One choice among labelled chips, cols per row.
        public void Chips(string label, string[] options, Func<int> get, Action<int> set, int cols = 3, Color? accent = null)
        {
            Caption(label);
            int rows = (options.Length + cols - 1) / cols;
            var grid = Row(rows * 48 + 2);
            var g = grid.gameObject.AddComponent<GridLayoutGroup>();
            g.cellSize = new Vector2((width - 8f - (cols - 1) * 6f) / cols, 42); g.spacing = new Vector2(6, 6); g.childAlignment = TextAnchor.UpperCenter;
            g.constraint = GridLayoutGroup.Constraint.FixedColumnCount; g.constraintCount = cols;
            var acc = accent ?? SheerKit.Pink;
            var plates = new List<Image>(); var borders = new List<Image>(); var texts = new List<Text>();
            for (int i = 0; i < options.Length; i++)
            {
                int k = i;
                var im = SheerKit.Img(grid, "Chip", SheerKit.Round14, SheerKit.ChipLine, true, 1.4f); im.raycastTarget = true;
                var plate = SheerKit.Img(im.transform, "Plate", SheerKit.Round14, SheerKit.Chip, true, 1.4f); SheerKit.Fill(plate.rectTransform, 1.5f, 1.5f, 1.5f, 1.5f);
                var t = SheerKit.Label(plate.transform, SheerKit.En(options[i]), 15, SheerKit.Ink, TextAnchor.MiddleCenter, true); SheerKit.Fill(t.rectTransform, 2, 0, 2, 0);
                var b = im.gameObject.AddComponent<Button>(); b.targetGraphic = im; b.transition = Selectable.Transition.None;
                b.onClick.AddListener(() => { SheerAudio.Ui("pop"); set(k); Refresh(); });
                im.gameObject.AddComponent<SheerBounce>();
                plates.Add(plate); borders.Add(im); texts.Add(t);
            }
            Action rf = () =>
            {
                int cur = get();
                for (int i = 0; i < plates.Count; i++)
                {
                    bool on = i == cur;
                    plates[i].color = on ? acc : SheerKit.Chip;
                    borders[i].color = on ? Color.Lerp(acc, SheerKit.Ink, 0.25f) : SheerKit.ChipLine;
                    texts[i].color = on ? SheerKit.White : SheerKit.Ink;
                }
            };
            rf(); refresh.Add(rf);
        }

        /// Colour swatches: one choice among the given colours.
        public void Swatches(string label, Color[] colors, Func<Color> get, Action<Color> set)
        {
            Caption(label);
            int n = colors.Length, cols = Mathf.Max(4, Mathf.FloorToInt((width - 4f) / 52f));
            var grid = Row(((n + cols - 1) / cols) * 50 + 2);
            var g = grid.gameObject.AddComponent<GridLayoutGroup>(); g.cellSize = new Vector2(44, 44);
            g.spacing = new Vector2(Mathf.Floor((width - 8f - cols * 44f) / (cols - 1)), 6);
            g.constraint = GridLayoutGroup.Constraint.FixedColumnCount; g.constraintCount = cols; g.padding = new RectOffset(4, 0, 0, 0);
            var rings = new List<Image>();
            for (int i = 0; i < n; i++)
            {
                var cell = SheerKit.Rect(grid, "Swatch");
                var ring = SheerKit.Img(cell, "Ring", SheerKit.Ring, SheerKit.Pink, false); ring.rectTransform.sizeDelta = new Vector2(44, 44);
                // (a hairline round every dot: white and near-white swatches on the pale panel)
                var rim = SheerKit.Img(cell, "Rim", SheerKit.Circle, new Color32(214, 190, 208, 255), false); rim.rectTransform.sizeDelta = new Vector2(34, 34);
                var dot = SheerKit.Img(cell, "Dot", SheerKit.Circle, colors[i], false); dot.rectTransform.sizeDelta = new Vector2(32, 32); dot.raycastTarget = true;
                rings.Add(ring);
                int k = i;
                var b = dot.gameObject.AddComponent<Button>(); b.targetGraphic = dot; b.transition = Selectable.Transition.None;
                b.onClick.AddListener(() => { SheerAudio.Ui("pop"); set(colors[k]); Refresh(); });
                dot.gameObject.AddComponent<SheerBounce>();
            }
            Action rf = () =>
            {
                Color c = get();
                for (int i = 0; i < colors.Length; i++) rings[i].color = Close(colors[i], c) ? SheerKit.PinkDeep : new Color(0, 0, 0, 0);
            };
            rf(); refresh.Add(rf);
        }
        static bool Close(Color a, Color b) => Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b) < 0.02f;

        /// An on / off switch.
        public void Switch(string label, Func<bool> get, Action<bool> set)
        {
            var r = Row(42);
            var l = SheerKit.Label(r, SheerKit.En(label), 15, SheerKit.Ink); var lr = l.rectTransform; lr.anchorMin = Vector2.zero; lr.anchorMax = new Vector2(0.8f, 1); lr.offsetMin = new Vector2(6, 0); lr.offsetMax = Vector2.zero;
            var plate = SheerKit.Img(r, "Switch", SheerKit.Pill, SheerKit.Track, true, 2f); plate.raycastTarget = true;
            var pr = plate.rectTransform; pr.anchorMin = pr.anchorMax = new Vector2(1, 0.5f); pr.pivot = new Vector2(1, 0.5f); pr.sizeDelta = new Vector2(54, 30); pr.anchoredPosition = new Vector2(-6, 0);
            var knob = SheerKit.Img(plate.transform, "Knob", SheerKit.Circle, SheerKit.White, false); knob.rectTransform.sizeDelta = new Vector2(24, 24);
            var sw = plate.gameObject.AddComponent<SheerSwitchAnim>(); sw.knob = knob.rectTransform; sw.plate = plate;
            var b = plate.gameObject.AddComponent<Button>(); b.targetGraphic = plate; b.transition = Selectable.Transition.None;
            b.onClick.AddListener(() => { bool v = !get(); SheerAudio.Ui(v ? "toggle_on" : "toggle_off"); set(v); Refresh(); });
            Action rf = () => sw.on = get();
            rf(); sw.Snap(); refresh.Add(rf);
        }

        /// A row of buttons sharing the width.
        public void Buttons(params (string text, Action act, Color plate)[] bs)
        {
            var r = Row(50);
            var hl = r.gameObject.AddComponent<HorizontalLayoutGroup>(); hl.spacing = 6; hl.childControlWidth = true; hl.childControlHeight = true; hl.childForceExpandWidth = true; hl.padding = new RectOffset(2, 2, 3, 3);
            foreach (var (text, act, plate) in bs)
            {
                var b = SheerKit.Button(r, text, plate, plate.grayscale > 0.75f ? SheerKit.Ink : SheerKit.White, act, 15);
                SheerKit.Layout(b, -1, -1, 1);
            }
        }

        /// A live line of text.
        public Text Live(Func<string> text, int size = 14, float h = 24)
        {
            var t = SheerKit.Label(root, text(), size, SheerKit.Ink, TextAnchor.UpperLeft);
            SheerKit.Layout(t, h);
            t.gameObject.AddComponent<SheerLiveText>().source = text;
            group?.Add(t.gameObject);
            return t;
        }
    }

    public class SheerSwitchAnim : MonoBehaviour
    {
        public RectTransform knob; public Image plate; public bool on; float x;
        public void Snap() { x = on ? 1f : 0f; Apply(); }
        void Update() { float g = on ? 1f : 0f; if (x == g) return; x = Mathf.MoveTowards(x, g, Time.unscaledDeltaTime * 7f); Apply(); }   // (idle when there)
        void Apply()
        {
            float e = x * x * (3f - 2f * x);
            if (knob) knob.anchoredPosition = new Vector2(Mathf.Lerp(-12f, 12f, e), 0f);
            if (plate) plate.color = Color.Lerp(SheerKit.Track, SheerKit.Pink, e);
        }
    }

    public class SheerLiveText : MonoBehaviour
    {
        public Func<string> source; Text t; float next;
        void Update()
        {
            if (Time.unscaledTime < next || source == null) return;
            next = Time.unscaledTime + 0.25f;
            t ??= GetComponent<Text>();
            try { t.text = source(); } catch (Exception) { }
        }
    }
}
