// SHEER — the CLASSIC INSPECTOR: the original demo's side panel as its video shows it - a dark editor inspector with the
// "TensionData: Pantyhose" material, field for field, live (it edits the same TensionData as the Studio). Measured off the
// video (2160 px frame, measured at 1932): 1 unit here = 1 px of that frame. Colours (panel #333, slider track #555, knob
// #828282, value boxes #262626, dropdown #494949), positions (labels at 71, sliders 387 - 720 with the knob's centre
// 396 - 711, value boxes 731 - 828, rows 39 apart, texture slots 84 x 113), text (Inter 22) and every slider's range from
// where its knob sits for the value shown. A skin for the side panel: the Studio's ◧ button or I, back with its ✿ tab.
// The 'Hierarchy' tab lists the scene's real objects.
using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Sheer
{
    public class SheerInspectorUI : MonoBehaviour
    {
        public static SheerInspectorUI I;
        public const float PanelW = 892f, RefH = 1932f;
        static Color G(int v) => new Color32((byte)v, (byte)v, (byte)v, 255);
        static readonly Color Bg = G(51), EdgeC = G(19), Strip = G(18), TabOn = G(54), TextC = G(180), ValC = G(172), TabText = G(178), TabDim = G(140),
                              TrackC = G(85), KnobC = G(130), FieldC = G(38), FieldEdge = G(28), DropC = G(73), DropEdge = G(41), ArrowC = G(112),
                              BarC = G(54), LineC = G(62), MenuC = G(56), SelC = new Color32(44, 93, 135, 255), Purple = new Color32(107, 106, 207, 255);

        public static bool Open => I && I.open && I.canvas && I.canvas.enabled;
        /// the panel's width in screen pixels while it is shown (0 when not)
        public static float WidthPx => Open ? PanelW * I.scale : 0f;

        Canvas canvas; RectTransform root, panel, viewport, insContent, hierContent; ScrollRect scroll;
        Font reg, semi; TensionData td;
        readonly List<Action> refreshers = new List<Action>();
        readonly List<(GameObject go, int group)> grouped = new List<(GameObject, int)>();
        readonly Dictionary<int, bool> groupOpen = new Dictionary<int, bool>();
        int curGroup = -1; float nextRefresh, scale = 1f; int scrW, scrH; bool open, showHier, initScroll = true, deselectSoon; GameObject popup;
        Image tabIns, tabHier; Text tabInsT, tabHierT;

        public static SheerInspectorUI Create(Transform parent)
        {
            var go = new GameObject("ClassicInspector"); go.transform.SetParent(parent, false);
            I = go.AddComponent<SheerInspectorUI>(); I.Build(); I.SetOpen(false);
            return I;
        }

        public void SetOpen(bool v)
        {
            open = v;
            if (canvas) canvas.gameObject.SetActive(v);
            if (!v) ClosePopup();
            if (v) { RefreshAll(); if (showHier) BuildHierarchy(); }
        }
        public void SetVisible(bool v) { if (canvas) canvas.enabled = v; }

        // ------------------------------------------------------------------ building
        void Build()
        {
            td = FindAnyObjectByType<TensionData>();
            reg = Resources.Load<Font>("Fonts/Inter-Regular") ?? Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            semi = Resources.Load<Font>("Fonts/Inter-SemiBold") ?? reg;
            var cgo = new GameObject("InspectorCanvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            cgo.transform.SetParent(transform, false);
            canvas = cgo.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceOverlay; canvas.sortingOrder = 21;
            root = (RectTransform)cgo.transform;
            panel = R(root, "Panel"); panel.anchorMin = new Vector2(1, 0); panel.anchorMax = new Vector2(1, 1); panel.pivot = new Vector2(1, 0.5f);
            panel.sizeDelta = new Vector2(PanelW, 0); panel.anchoredPosition = Vector2.zero;
            var bg = Img(panel, "Bg", Bg); Fill(bg.rectTransform); bg.raycastTarget = true;
            var edge = Img(panel, "Edge", EdgeC); var er = edge.rectTransform; er.anchorMin = new Vector2(0, 0); er.anchorMax = new Vector2(0, 1); er.pivot = new Vector2(0, 0.5f); er.sizeDelta = new Vector2(5, 0);
            // the tab strip: Hierarchy | Inspector (| ✿ Studio, ours)
            var strip = Img(panel, "Tabs", Strip).rectTransform; strip.anchorMin = new Vector2(0, 1); strip.anchorMax = new Vector2(1, 1); strip.pivot = new Vector2(0.5f, 1); strip.sizeDelta = new Vector2(0, 45);
            (tabHier, tabHierT) = Tab(strip, "≡  Hierarchy", 10, 168, () => ShowHierarchy(true));
            (tabIns, tabInsT) = Tab(strip, "ⓘ  Inspector", 188, 184, () => ShowHierarchy(false));
            Tab(strip, "✿  Studio", 382, 150, () => SheerStudio.I?.SetSkin(0));
            var dots = Lbl(strip, "⋮", 832, 30, reg, 24, TabDim, TextAnchor.MiddleCenter); dots.rectTransform.anchorMin = dots.rectTransform.anchorMax = new Vector2(0, 0.5f);
            // (the component menu, as the editor's: reset to the video's values, copy / paste the values)
            dots.raycastTarget = true;
            dots.gameObject.AddComponent<Button>().onClick.AddListener(() => ShowMenu(dots.rectTransform, new[] { "Reset to defaults", "Copy values", "Paste values" }, -1, k =>
            {
                if (!td) return;
                if (k == 0) td.ResetToVideoValues();
                else if (k == 1) { var v = new TensionValues(); v.From(td); GUIUtility.systemCopyBuffer = JsonUtility.ToJson(v); SheerFun.Toast("Inspector values copied"); return; }
                else { try { var v = JsonUtility.FromJson<TensionValues>(GUIUtility.systemCopyBuffer); if (v == null || !v.set) { SheerFun.Toast("No inspector values on the clipboard"); return; } v.To(td); } catch (Exception) { SheerFun.Toast("No inspector values on the clipboard"); return; } }
                Edited();
            }, 420f));
            // (no decorative icons: everything on the panel that looks clickable does something - the user, 2026-11-18)
            // the bottom bar: "TensionData: Pantyhose ▾" and the preview's drag handle
            var bar = Img(panel, "Bottom", BarC).rectTransform; bar.anchorMin = new Vector2(0, 0); bar.anchorMax = new Vector2(1, 0); bar.pivot = new Vector2(0.5f, 0); bar.sizeDelta = new Vector2(0, 44); bar.anchoredPosition = new Vector2(0, 6);
            var bt = Lbl(bar, "TensionData: Pantyhose", 15, 600, semi, 22, G(186), TextAnchor.MiddleLeft); bt.rectTransform.anchorMin = bt.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var under = Img(panel, "Under", G(30)).rectTransform; under.anchorMin = new Vector2(0, 0); under.anchorMax = new Vector2(1, 0); under.pivot = new Vector2(0.5f, 0); under.sizeDelta = new Vector2(0, 6);
            // the scrolling content (+ a permanent scrollbar, as in the video)
            var sgo = R(panel, "Scroll"); sgo.anchorMin = Vector2.zero; sgo.anchorMax = Vector2.one; sgo.offsetMin = new Vector2(0, 50); sgo.offsetMax = new Vector2(0, -45);
            scroll = sgo.gameObject.AddComponent<ScrollRect>(); scroll.horizontal = false; scroll.movementType = ScrollRect.MovementType.Clamped; scroll.scrollSensitivity = 40f; scroll.inertia = false;
            viewport = R(sgo, "Viewport"); viewport.anchorMin = Vector2.zero; viewport.anchorMax = Vector2.one; viewport.offsetMin = Vector2.zero; viewport.offsetMax = new Vector2(-26, 0);
            viewport.gameObject.AddComponent<RectMask2D>(); var vi = viewport.gameObject.AddComponent<Image>(); vi.color = new Color(0, 0, 0, 0);
            insContent = MakeContent("Inspector"); hierContent = MakeContent("Hierarchy"); hierContent.gameObject.SetActive(false);
            var sb = Img(sgo, "Scrollbar", G(45)).rectTransform; sb.anchorMin = new Vector2(1, 0); sb.anchorMax = new Vector2(1, 1); sb.pivot = new Vector2(1, 0.5f); sb.sizeDelta = new Vector2(19, 0); sb.anchoredPosition = new Vector2(-2, 0);
            var area = R(sb, "Area"); Fill(area, 2, 2, 2, 2);
            var handle = Img(area, "Handle", G(85)); Fill(handle.rectTransform);
            var bar2 = sb.gameObject.AddComponent<Scrollbar>(); bar2.direction = Scrollbar.Direction.BottomToTop; bar2.handleRect = handle.rectTransform; bar2.targetGraphic = handle;
            var cb = bar2.colors; cb.highlightedColor = new Color(1.2f, 1.2f, 1.2f, 1f); cb.pressedColor = new Color(1.35f, 1.35f, 1.35f, 1f); bar2.colors = cb;
            scroll.viewport = viewport; scroll.content = insContent; scroll.verticalScrollbar = bar2; scroll.verticalScrollbarVisibility = ScrollRect.ScrollbarVisibility.Permanent;
            BuildInspector();
            ShowHierarchy(false);
            edge.transform.SetAsLastSibling();                    // (the panel's dark left edge over the scrolling rows)
        }

        RectTransform MakeContent(string n)
        {
            var c = R(viewport, n); c.anchorMin = new Vector2(0, 1); c.anchorMax = new Vector2(1, 1); c.pivot = new Vector2(0.5f, 1); c.sizeDelta = Vector2.zero;
            var vl = c.gameObject.AddComponent<VerticalLayoutGroup>(); vl.childControlHeight = true; vl.childControlWidth = true; vl.childForceExpandHeight = false; vl.childForceExpandWidth = true;
            vl.padding = new RectOffset(0, 0, 0, 24);
            c.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            return c;
        }

        void BuildInspector()
        {
            var c = insContent;
            Slider(c, "Normal Strength", 0f, 1.6f, () => td.normalStrength, v => td.normalStrength = v);
            NumField(c, "Weave Tiling", true, () => td.weaveTiling, v => td.weaveTiling = Mathf.Max(1, Mathf.RoundToInt(v)));
            Slider(c, "Weave Normal Strength", 0f, 1f, () => td.weaveNormalStrength, v => td.weaveNormalStrength = v);
            Slider(c, "Weave Contrast", 0f, 1f, () => td.weaveContrast, v => td.weaveContrast = v);
            Foldout(c, "Tension & Wrinkles");
            Dropdown(c, "Tension Mode", new[] { "Both", "Stretch", "Compression" }, () => (int)td.tensionMode, k => td.tensionMode = (TensionMode)k);
            NumField(c, "Wrinkle Strength", false, () => td.wrinkleStrength, v => td.wrinkleStrength = v);
            Slider(c, "Tension Normal Boost", 0f, 4f, () => td.tensionNormalBoost, v => td.tensionNormalBoost = v);
            Foldout(c, "Pearl Sheen & Glints");
            Slider(c, "Pearl Strength", 0f, 1f, () => td.pearlStrength, v => td.pearlStrength = v);
            Slider(c, "Pearl Grain Scale", 0f, 1000f, () => td.pearlGrainScale, v => td.pearlGrainScale = v);
            Slider(c, "Pearl Randomness", 0f, 1f, () => td.pearlRandomness, v => td.pearlRandomness = v);
            Slider(c, "Pearl Specular Strength", 0f, 4f, () => td.pearlSpecularStrength, v => td.pearlSpecularStrength = v);
            Slider(c, "Pearl Edge Strength", 0f, 1f, () => td.pearlEdgeStrength, v => td.pearlEdgeStrength = v);
            Slider(c, "Pearl Edge Start", 0f, 1f, () => td.pearlEdgeStart, v => td.pearlEdgeStart = v);
            Slider(c, "Pearl Edge Width Power", 0f, 5f, () => td.pearlEdgeWidthPower, v => td.pearlEdgeWidthPower = v);
            Slider(c, "Pearl Pull Edge Width", 0.001f, 0.04f, () => td.pearlPullEdgeWidth, v => td.pearlPullEdgeWidth = v);
            Slider(c, "Pearl Glint Strength", 0f, 2f, () => td.pearlGlintStrength, v => td.pearlGlintStrength = v);
            Slider(c, "Pearl Glint Density", 0f, 1f, () => td.pearlGlintDensity, v => td.pearlGlintDensity = v);
            Foldout(c, "Frost & Sheerness");
            Slider(c, "Frost Body Coverage", 0f, 1f, () => td.frostBodyCoverage, v => td.frostBodyCoverage = v);
            Slider(c, "Frost Foot Coverage", 0f, 1f, () => td.frostFootCoverage, v => td.frostFootCoverage = v);
            Slider(c, "Frost Clear At Stretch", 0f, 1f, () => td.frostClearAtStretch, v => td.frostClearAtStretch = v);
            Slider(c, "Frost Matte Smoothness", 0f, 1f, () => td.frostMatteSmoothness, v => td.frostMatteSmoothness = v);
            Slider(c, "Frost Boundary Strength", 0f, 1f, () => td.frostBoundaryStrength, v => td.frostBoundaryStrength = v);
            Slider(c, "Frost Boundary Width (px)", 0f, 32f, () => td.frostBoundaryWidthPx, v => td.frostBoundaryWidthPx = v);
            // (the video's 'Advanced Options' - Enable GPU Instancing, Global Illumination - were material flags with no effect
            //  on the simulator: removed, the user 2026-11-18)
            curGroup = -1;
        }

        // ------------------------------------------------------------------ rows
        RectTransform Row(RectTransform parent, float h)
        {
            var r = R(parent, "Row"); r.pivot = new Vector2(0, 0.5f);
            r.gameObject.AddComponent<LayoutElement>().preferredHeight = h;
            if (curGroup >= 0) grouped.Add((r.gameObject, curGroup));
            return r;
        }
        Text LabelIn(RectTransform row, string s, float x = 71f)
        {
            var t = Lbl(row, s, x, 300, reg, 22, TextC, TextAnchor.MiddleLeft); t.rectTransform.anchorMin = t.rectTransform.anchorMax = new Vector2(0, 0.5f);
            if (Tips.TryGetValue(s, out var tip)) { t.raycastTarget = true; var h = t.gameObject.AddComponent<InspTip>(); h.ui = this; h.text = tip; }
            return t;
        }

        // ---- tooltips: what each field does in this simulator (hover a label)
        static readonly Dictionary<string, string> Tips = new Dictionary<string, string>
        {
            { "Normal Strength", "Overall strength of the stocking's surface relief - knit loops and tension creases." },
            { "Weave Tiling", "How many times the knit's weave cell repeats: 12 tiles x 48 wales = 576 wales round the leg." },
            { "Weave Normal Strength", "How strongly the loops catch the light - where the key light glances off them." },
            { "Weave Contrast", "How much the loops vary the coverage: the knit's visible texture over the skin." },
            { "Tension Mode", "Which strain draws creases: Stretch - the fan of fine lines along a pull; Compression - the buckled folds where the knit is pushed together (and the ankle's bend); Both." },
            { "Wrinkle Strength", "Depth of all the drawn creases - the lines along a pull, the buckled folds, the ankle's bend (9 = default, 0 = none)." },
            { "Tension Normal Boost", "Extra relief where the knit is stretched open (the loops stand out)." },
            { "Pearl Strength", "The nylon's pearly sheen toward the outlines: up brightens them, down darkens them (with Pearl Edge Strength)." },
            { "Pearl Grain Scale", "Size of the sheen's grain: bundles of fibres that catch the light together." },
            { "Pearl Randomness", "How unlike each other the glints are - their sizes and brightness (0 = all alike)." },
            { "Pearl Specular Strength", "Brightness of the sheen's highlight." },
            { "Pearl Edge Strength", "The soft pale sheen along the outlines, where the nylon is seen edge-on." },
            { "Pearl Edge Start", "Where (by viewing angle) the edge sheen begins - it shapes the sheen set by Pearl Edge Strength; raise that to see it clearly." },
            { "Pearl Edge Width Power", "How tightly the edge sheen hugs the outline - it shapes the sheen set by Pearl Edge Strength; raise that to see it clearly." },
            { "Pearl Pull Edge Width", "Width of the lit band along the outline of fabric pulled off the leg - a sail's edge." },
            { "Pearl Glint Strength", "The sparkling glints - single fibres flashing in the key light: up to 1 they fade in, from 1 to 2 they get brighter." },
            { "Pearl Glint Density", "How many glints there are (more toward grazing angles and on the foot)." },
            { "Frost Body Coverage", "How much of the skin the knit hides at rest on the leg (the denier look)." },
            { "Frost Foot Coverage", "The same for the reinforced foot - denser than the leg." },
            { "Frost Clear At Stretch", "How much stretching opens the knit: sheerer where it is drawn out." },
            { "Frost Matte Smoothness", "Smoothness of the knit's matte haze." },
            { "Frost Boundary Strength", "How strongly the edges of the holes read: their rolled lip and the paler rim of loosened knit round them." },
            { "Frost Boundary Width (px)", "Width of the soft transition at the ankle where the leg's sheerer knit meets the foot's denser knit." },
        };
        GameObject tipGo; Text tipText; RectTransform tipRect;
        public void ShowTip(string s, Vector2 screen)
        {
            if (!tipGo)
            {
                var bgI = Img(root, "Tooltip", G(24)); tipRect = bgI.rectTransform; tipRect.anchorMin = tipRect.anchorMax = Vector2.zero; tipRect.pivot = new Vector2(0, 1);
                bgI.gameObject.AddComponent<Outline>().effectColor = G(70);
                tipText = Lbl(tipRect, "", 10, 560, reg, 19, G(205), TextAnchor.UpperLeft); tipText.horizontalOverflow = HorizontalWrapMode.Wrap;
                var tr = tipText.rectTransform; tr.anchorMin = Vector2.zero; tr.anchorMax = Vector2.one; tr.offsetMin = new Vector2(12, 8); tr.offsetMax = new Vector2(-12, -8);
                tipGo = bgI.gameObject;
            }
            tipText.text = s;
            float w = 600f, h = 30f + 26f * Mathf.Ceil(s.Length / 52f);
            tipRect.sizeDelta = new Vector2(w, h);
            float sc = canvas ? canvas.scaleFactor : 1f;
            // (beside the pointer, kept on screen: to its left - the panel sits at the window's right edge)
            var p = screen / sc + new Vector2(-w - 16f, -18f);
            p.x = Mathf.Max(8f, p.x); p.y = Mathf.Clamp(p.y, h + 8f, Screen.height / sc - 8f);
            tipRect.anchoredPosition = p; tipGo.SetActive(true); tipGo.transform.SetAsLastSibling();
        }
        public void HideTip() { if (tipGo) tipGo.SetActive(false); }

        void Foldout(RectTransform parent, string title, float x = 44f)
        {
            int g = grouped.Count == 0 && curGroup < 0 ? 0 : curGroup + 1; curGroup = g; groupOpen[g] = true;
            var r = R(parent, "Foldout"); r.pivot = new Vector2(0, 0.5f); r.gameObject.AddComponent<LayoutElement>().preferredHeight = 39;
            var hit = Img(r, "Hit", new Color(0, 0, 0, 0)); Fill(hit.rectTransform); hit.raycastTarget = true;
            var arrow = Lbl(r, "▼", x, 20, reg, 15, ArrowC, TextAnchor.MiddleLeft); arrow.rectTransform.anchorMin = arrow.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var t = Lbl(r, title, x + 27, 400, semi, 22, G(184), TextAnchor.MiddleLeft); t.rectTransform.anchorMin = t.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var b = hit.gameObject.AddComponent<Button>(); b.transition = Selectable.Transition.None;
            b.onClick.AddListener(() => { groupOpen[g] = !groupOpen[g]; arrow.text = groupOpen[g] ? "▼" : "▶"; foreach (var (go, gg) in grouped) if (gg == g) go.SetActive(groupOpen[g]); });
        }

        void Slider(RectTransform parent, string name, float min, float max, Func<float> get, Action<float> set)
        {
            var r = Row(parent, 39); LabelIn(r, name);
            var track = Img(r, "Track", TrackC).rectTransform; Place(track, 387, 333, 3);
            var knob = Img(r, "Knob", KnobC, SheerKit.Circle).rectTransform; Place(knob, 396 - 9, 18, 18);
            var hit = Img(r, "Hit", new Color(0, 0, 0, 0)).rectTransform; Place(hit, 378, 352, 34); hit.GetComponent<Image>().raycastTarget = true;
            var input = Field(r, 731, 97, FieldC, out var txt);
            int dec = Mathf.Clamp(Mathf.CeilToInt(-Mathf.Log10((max - min) / 315f)), 0, 6);
            var drag = hit.gameObject.AddComponent<InspDrag>();
            drag.onDrag = local => { if (!td) return; float k = Mathf.Clamp01((local.x - 396f) / 315f); float v = (float)Math.Round(min + k * (max - min), dec); set(v); Edited(); };
            input.onEndEdit.AddListener(s => { if (td && TryNum(s, out float v)) { set(Mathf.Clamp(v, min, max)); Edited(); } RefreshSoon(); });
            refreshers.Add(() =>
            {
                if (!td) return;
                float v = get(); float k = Mathf.Clamp01((v - min) / (max - min));
                var p = new Vector2(396f - 9f + k * 315f, 0f); if (knob.anchoredPosition != p) knob.anchoredPosition = p;
                if (!input.isFocused) { var s = Fmt(v); if (input.text != s) input.text = s; }
            });
        }

        void NumField(RectTransform parent, string name, bool integer, Func<float> get, Action<float> set)
        {
            var r = Row(parent, 39); var lab = LabelIn(r, name);
            var input = Field(r, 387, 441, FieldC, out _);
            input.contentType = integer ? InputField.ContentType.IntegerNumber : InputField.ContentType.Standard;
            input.onEndEdit.AddListener(s => { if (td && TryNum(s, out float v)) { set(v); Edited(); } RefreshSoon(); });
            // (as in the editor: drag the label sideways to scrub the value)
            lab.raycastTarget = true;
            var scrub = lab.gameObject.AddComponent<InspDrag>(); scrub.relative = true;
            float acc = 0f;                                        // (fractions of a step carried over: slow drags count too)
            scrub.onDrag = d =>
            {
                if (!td) return;
                float v = get(), step = integer ? 0.25f : 0.03f * Mathf.Max(1f, Mathf.Sqrt(Mathf.Abs(v)));
                acc += d.x * step;
                if (integer) { int n = (int)acc; if (n == 0) return; acc -= n; set(v + n); }
                else { float dv = (float)Math.Round(acc, 3); if (dv == 0f) return; acc -= dv; set(v + dv); }
                Edited();
            };
            refreshers.Add(() => { if (!td || input.isFocused) return; var s = Fmt(get()); if (input.text != s) input.text = s; });
        }

        void Dropdown(RectTransform parent, string name, string[] options, Func<int> get, Action<int> set)
        {
            var r = Row(parent, 39); LabelIn(r, name);
            var box = Img(r, "Drop", DropEdge).rectTransform; Place(box, 389, 437, 32);
            var inner = Img(box, "Fill", DropC).rectTransform; Fill(inner, 1, 1, 1, 1);
            var t = Lbl(inner, "", 6, 380, reg, 22, ValC, TextAnchor.MiddleLeft); t.rectTransform.anchorMin = t.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var a = Lbl(inner, "▾", 405, 24, reg, 20, ValC, TextAnchor.MiddleCenter); a.rectTransform.anchorMin = a.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var b = inner.gameObject.AddComponent<Button>(); b.targetGraphic = inner.GetComponent<Image>();
            var cb = b.colors; cb.highlightedColor = new Color(1.12f, 1.12f, 1.12f, 1f); cb.pressedColor = new Color(1.25f, 1.25f, 1.25f, 1f); b.colors = cb;
            b.onClick.AddListener(() => ShowMenu(box, options, get(), k => { set(k); Edited(); }));
            refreshers.Add(() => { if (!td) return; int k = Mathf.Clamp(get(), 0, options.Length - 1); if (t.text != options[k]) t.text = options[k]; });
        }

        InputField Field(RectTransform row, float x, float w, Color fill, out Text txt)
        {
            var box = Img(row, "Field", FieldEdge).rectTransform; Place(box, x, w, 32);
            var inner = Img(box, "Fill", fill); Fill(inner.rectTransform, 1, 1, 1, 1);
            txt = Lbl(inner.rectTransform, "", 6, w - 10, reg, 22, ValC, TextAnchor.MiddleLeft); Fill(txt.rectTransform, 7, 0, 4, 0);
            txt.supportRichText = false;
            var f = inner.gameObject.AddComponent<InputField>(); f.textComponent = txt; f.targetGraphic = inner;
            f.caretColor = G(220); f.selectionColor = new Color(0.17f, 0.36f, 0.53f, 0.9f); f.customCaretColor = true; f.caretWidth = 2;
            f.lineType = InputField.LineType.SingleLine; f.contentType = InputField.ContentType.DecimalNumber;
            f.onEndEdit.AddListener(_ => deselectSoon = true);          // (let go of the keyboard after Enter: see Update)
            var cb = f.colors; cb.highlightedColor = new Color(1.15f, 1.15f, 1.15f, 1f); cb.selectedColor = new Color(1.1f, 1.1f, 1.1f, 1f); f.colors = cb;
            return f;
        }

        // ------------------------------------------------------------------ the dropdown menu
        void ShowMenu(RectTransform under, string[] items, int cur, Action<int> pick, float width = 0f)
        {
            ClosePopup();
            popup = new GameObject("Menu", typeof(RectTransform)); popup.transform.SetParent(root, false);
            var pr = (RectTransform)popup.transform; Fill(pr);
            var blocker = Img(pr, "Blocker", new Color(0, 0, 0, 0)); Fill(blocker.rectTransform); blocker.raycastTarget = true;
            blocker.gameObject.AddComponent<Button>().onClick.AddListener(ClosePopup);
            var corners = new Vector3[4]; under.GetWorldCorners(corners);
            var list = Img(pr, "List", MenuC).rectTransform; list.anchorMin = list.anchorMax = Vector2.zero; list.pivot = new Vector2(0, 1);
            list.sizeDelta = new Vector2(width > 0f ? width : under.rect.width, 34 * items.Length + 8);
            // (below the field; above it when there is no room below - the Global Illumination field at the bottom)
            float hPx = list.sizeDelta.y * (canvas ? canvas.scaleFactor : 1f);
            if (corners[0].y - hPx < 0f) { list.pivot = new Vector2(0, 0); list.position = corners[1]; }
            else list.position = corners[0];
            // (a wide menu opened from the panel's right edge: keep it on screen)
            float wPx = list.sizeDelta.x * (canvas ? canvas.scaleFactor : 1f);
            if (list.position.x + wPx > Screen.width) list.position = new Vector3(Screen.width - wPx - 4f, list.position.y, 0f);
            list.gameObject.AddComponent<Outline>().effectColor = G(25);
            for (int i = 0; i < items.Length; i++)
            {
                int k = i;
                var it = Img(list, "Item", MenuC).rectTransform; it.anchorMin = new Vector2(0, 1); it.anchorMax = new Vector2(1, 1); it.pivot = new Vector2(0.5f, 1); it.sizeDelta = new Vector2(-8, 34); it.anchoredPosition = new Vector2(0, -4 - 34 * i);
                var b = it.gameObject.AddComponent<Button>(); b.targetGraphic = it.GetComponent<Image>();
                var cb = b.colors; cb.normalColor = Color.white; cb.highlightedColor = new Color(SelC.r / MenuC.r, SelC.g / MenuC.g, SelC.b / MenuC.b, 1f); cb.pressedColor = cb.highlightedColor; cb.colorMultiplier = 1f; b.colors = cb;
                var tx = Lbl(it, (i == cur ? "✓  " : "    ") + items[i], 8, 380, reg, 22, ValC, TextAnchor.MiddleLeft); Fill(tx.rectTransform, 8, 0, 0, 0);
                b.onClick.AddListener(() => { pick(k); ClosePopup(); });
            }
        }
        void ClosePopup() { if (popup) Destroy(popup); popup = null; }

        public void TestHierarchy(bool h) => ShowHierarchy(h);
        /// self-test: drive the controls as a pointer / keyboard would - the Normal Strength slider dragged to its middle,
        /// a value typed into its box, the Tension Mode menu, a label scrub on Weave Tiling; returns what failed ("" = all fine)
        public string TestControls()
        {
            if (!td) return "no TensionData";
            string fail = "";
            var drags = insContent.GetComponentsInChildren<InspDrag>(true);
            var fields = insContent.GetComponentsInChildren<InputField>(true);
            if (drags.Length < 20 || fields.Length < 20) return $"controls missing ({drags.Length} drags, {fields.Length} fields)";
            var ns = drags[0]; ns.onDrag(new Vector2(396f + 315f * 0.5f, 0f));
            if (Mathf.Abs(td.normalStrength - 0.8f) > 1e-3f) fail += $" slider->{td.normalStrength}";
            fields[0].onEndEdit.Invoke("1");
            if (Mathf.Abs(td.normalStrength - 1f) > 1e-4f) fail += $" typed->{td.normalStrength}";
            fields[0].onEndEdit.Invoke("abc"); if (Mathf.Abs(td.normalStrength - 1f) > 1e-4f) fail += " junk accepted";
            fields[0].onEndEdit.Invoke("99"); if (td.normalStrength > 1.6f + 1e-4f) fail += " not clamped";
            fields[0].onEndEdit.Invoke("1");
            // Weave Tiling: a label scrub of +40 units (0.25 per unit = +10) then back
            int w0 = td.weaveTiling; var scrub = Array.Find(drags, d => d.relative);
            if (scrub == null) fail += " no scrub"; else { scrub.onDrag(new Vector2(40f, 0f)); if (td.weaveTiling != w0 + 10) fail += $" scrub->{td.weaveTiling}"; scrub.onDrag(new Vector2(-40f, 0f)); }
            // the Tension Mode menu: open, pick 'Both', back to 'Stretch'
            var drop = Array.Find(insContent.GetComponentsInChildren<Button>(true), b => b.transform.parent && b.transform.parent.name == "Drop");
            if (drop == null) fail += " no dropdown";
            else
            {
                drop.onClick.Invoke();
                var items = popup ? popup.GetComponentsInChildren<Button>(true) : new Button[0];
                if (items.Length < 4) fail += " menu"; else { items[3].onClick.Invoke(); if (td.tensionMode != TensionMode.Compression) fail += $" menu->{td.tensionMode}"; }
                td.tensionMode = TensionMode.Both;
                if (popup) fail += " menu stayed open";
            }
            // the panel's '⋮' menu: Reset to defaults puts a changed value back
            var dotsB = Array.Find(GetComponentsInChildren<Button>(true), b => b.GetComponent<Text>() && b.GetComponent<Text>().text == "⋮");
            if (dotsB == null) fail += " no menu button";
            else
            {
                td.pearlStrength = 0.9f; dotsB.onClick.Invoke();
                var mi = popup ? popup.GetComponentsInChildren<Button>(true) : new Button[0];
                if (mi.Length < 4) fail += " no menu"; else { mi[1].onClick.Invoke(); if (Mathf.Abs(td.pearlStrength - 0.387f) > 1e-4f) fail += $" reset->{td.pearlStrength}"; }
                if (popup) { fail += " menu stayed open"; ClosePopup(); }
            }
            RefreshAll();
            return fail;
        }

        // ------------------------------------------------------------------ the hierarchy tab: the scene's real objects
        void ShowHierarchy(bool h)
        {
            showHier = h;
            insContent.gameObject.SetActive(!h); hierContent.gameObject.SetActive(h);
            scroll.content = h ? hierContent : insContent;
            tabIns.color = h ? Strip : TabOn; tabHier.color = h ? TabOn : Strip;
            tabInsT.color = h ? TabDim : TabText; tabHierT.color = h ? TabText : TabDim;
            if (h) BuildHierarchy();
            ClosePopup();
        }
        readonly HashSet<Transform> expanded = new HashSet<Transform>();
        void BuildHierarchy()
        {
            foreach (Transform ch in hierContent) Destroy(ch.gameObject);
            var roots = SceneManager.GetActiveScene().GetRootGameObjects();
            int n = 0;
            var sceneRow = R(hierContent, "Scene"); sceneRow.gameObject.AddComponent<LayoutElement>().preferredHeight = 39;
            var st = Lbl(sceneRow, "▼  ◈ " + SceneManager.GetActiveScene().name, 14, 600, semi, 22, TextC, TextAnchor.MiddleLeft); st.rectTransform.anchorMin = st.rectTransform.anchorMax = new Vector2(0, 0.5f);
            void Add(Transform tr, int depth)
            {
                if (n++ > 400) return;
                var row = R(hierContent, "Item"); row.gameObject.AddComponent<LayoutElement>().preferredHeight = 36;
                bool kids = tr.childCount > 0, ex = expanded.Contains(tr);
                var hit = Img(row, "Hit", new Color(0, 0, 0, 0)); Fill(hit.rectTransform); hit.raycastTarget = true;
                var lab = Lbl(row, (kids ? (ex ? "▼ " : "▶ ") : "    ") + "▣ " + tr.name, 40 + 26 * depth, 760, reg, 21, tr.gameObject.activeInHierarchy ? TextC : G(110), TextAnchor.MiddleLeft);
                lab.rectTransform.anchorMin = lab.rectTransform.anchorMax = new Vector2(0, 0.5f);
                if (kids)
                {
                    var b = hit.gameObject.AddComponent<Button>(); b.transition = Selectable.Transition.None;
                    b.onClick.AddListener(() => { if (!expanded.Add(tr)) expanded.Remove(tr); BuildHierarchy(); });
                }
                if (kids && ex) foreach (Transform c in tr) Add(c, depth + 1);
            }
            foreach (var go in roots) Add(go.transform, 0);
        }

        // ------------------------------------------------------------------ every frame
        void Update()
        {
            if (!open || !canvas) return;
            // the scale: the video's proportions (1932 units = the window's height) but never too small to read (its 22-unit
            // lettering at 16.5 px or more: user, 2026-11-17), never wider than ~45 % of the window
            if (Screen.width != scrW || Screen.height != scrH)
            {
                scrW = Screen.width; scrH = Screen.height;
                var scl = canvas.GetComponent<CanvasScaler>(); scl.uiScaleMode = CanvasScaler.ScaleMode.ConstantPixelSize;
                scale = Mathf.Max(0.2f, Mathf.Min(Mathf.Max(scrH / RefH, 0.75f), 0.45f * scrW / PanelW)); scl.scaleFactor = scale;
            }
            if (Time.unscaledTime >= nextRefresh) { nextRefresh = Time.unscaledTime + 0.1f; foreach (var r in refreshers) r(); }
            // a number entered: the field gives the keyboard back (uGUI's Submit, Space / Enter, would re-open it, and every key
            // command would stay off while a field holds the keyboard)
            if (deselectSoon)
            {
                deselectSoon = false;
                var es = EventSystem.current; var so = es ? es.currentSelectedGameObject : null; var f = so ? so.GetComponent<InputField>() : null;
                if (f && !f.isFocused) es.SetSelectedGameObject(null);
            }
            // (scrolled as in the video the first time: the foot of the Normal Map slot at the top, then Normal Strength)
            if (initScroll && insContent.rect.height > 400f) { insContent.anchoredPosition = new Vector2(0, 84); initScroll = false; }
        }
        void RefreshSoon() => nextRefresh = 0f;
        void Edited() { RefreshSoon(); SheerStudio.I?.Changed(); }       // (saved with the look; one undo step per gesture)
        void RefreshAll() { foreach (var r in refreshers) r(); }

        // ------------------------------------------------------------------ small helpers
        static string Fmt(float v) => v.ToString("0.#######", CultureInfo.InvariantCulture);
        static bool TryNum(string s, out float v) => float.TryParse(s.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out v) && !float.IsNaN(v) && !float.IsInfinity(v);
        static RectTransform R(Transform parent, string n) { var go = new GameObject(n, typeof(RectTransform)); go.transform.SetParent(parent, false); return (RectTransform)go.transform; }
        static Image Img(Transform parent, string n, Color c, Sprite s = null)
        {
            var go = new GameObject(n, typeof(RectTransform), typeof(Image)); go.transform.SetParent(parent, false);
            var im = go.GetComponent<Image>(); im.color = c; im.sprite = s; im.raycastTarget = false; if (s) im.type = Image.Type.Simple;
            return im;
        }
        static void Fill(RectTransform r, float l = 0, float b = 0, float rt = 0, float t = 0) { r.anchorMin = Vector2.zero; r.anchorMax = Vector2.one; r.offsetMin = new Vector2(l, b); r.offsetMax = new Vector2(-rt, -t); }
        static void Place(RectTransform r, float x, float w, float h) { r.anchorMin = r.anchorMax = new Vector2(0, 0.5f); r.pivot = new Vector2(0, 0.5f); r.sizeDelta = new Vector2(w, h); r.anchoredPosition = new Vector2(x, 0); }
        Text Lbl(Transform parent, string s, float x, float w, Font f, int size, Color c, TextAnchor a)
        {
            var go = new GameObject("Text", typeof(RectTransform), typeof(Text)); go.transform.SetParent(parent, false);
            var t = go.GetComponent<Text>(); t.font = f; t.fontSize = size; t.color = c; t.alignment = a; t.text = s; t.raycastTarget = false;
            t.horizontalOverflow = HorizontalWrapMode.Overflow; t.verticalOverflow = VerticalWrapMode.Overflow;
            var r = t.rectTransform; r.pivot = new Vector2(0, 0.5f); r.sizeDelta = new Vector2(w, 34); r.anchoredPosition = new Vector2(x, 0);
            return t;
        }
        (Image, Text) Tab(RectTransform strip, string s, float x, float w, Action click)
        {
            var im = Img(strip, "Tab", Strip); var r = im.rectTransform; r.anchorMin = r.anchorMax = new Vector2(0, 0); r.pivot = new Vector2(0, 0); r.sizeDelta = new Vector2(w, 40); r.anchoredPosition = new Vector2(x, 0);
            im.raycastTarget = true;
            var t = Lbl(r, s, 14, w - 14, reg, 22, TabDim, TextAnchor.MiddleLeft); t.rectTransform.anchorMin = t.rectTransform.anchorMax = new Vector2(0, 0.5f);
            var b = im.gameObject.AddComponent<Button>(); b.transition = Selectable.Transition.None; b.onClick.AddListener(() => click());
            return (im, t);
        }
    }

    /// a label's tooltip: shown after a short hover (as the editor does), hidden on leaving or pressing
    public class InspTip : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler, IPointerDownHandler
    {
        public SheerInspectorUI ui; public string text; float at = -1f; Vector2 pos;
        public void OnPointerEnter(PointerEventData e) { at = Time.unscaledTime + 0.55f; pos = e.position; }
        public void OnPointerExit(PointerEventData e) { at = -1f; if (ui) ui.HideTip(); }
        public void OnPointerDown(PointerEventData e) { at = -1f; if (ui) ui.HideTip(); }
        void Update() { if (at > 0f && Time.unscaledTime >= at) { at = -1f; if (ui) ui.ShowTip(text, pos); } }
        void OnDisable() { if (ui) ui.HideTip(); }
    }

    /// pointer down / drag on a row: absolute (local position in the row) or relative (pointer delta in units)
    public class InspDrag : MonoBehaviour, IPointerDownHandler, IDragHandler, IBeginDragHandler
    {
        public Action<Vector2> onDrag; public bool relative;
        RectTransform row;
        void Awake() { row = transform.parent as RectTransform; }
        public void OnPointerDown(PointerEventData e) { if (!relative) Send(e); }
        public void OnBeginDrag(PointerEventData e) { }
        public void OnDrag(PointerEventData e)
        {
            if (relative) { var c = GetComponentInParent<Canvas>(); onDrag?.Invoke(e.delta / (c ? c.scaleFactor : 1f)); }
            else Send(e);
        }
        void Send(PointerEventData e)
        {
            if (!row) return;
            if (RectTransformUtility.ScreenPointToLocalPointInRectangle(row, e.position, e.pressEventCamera, out var local))
                onDrag?.Invoke(new Vector2(local.x + row.rect.width * row.pivot.x, local.y));
        }
    }
}
