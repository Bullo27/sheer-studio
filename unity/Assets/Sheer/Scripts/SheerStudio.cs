// SHEER — the side panel and the look of the scene.
// THE MINIMAL SIMULATOR (user, 2026-11-17): what the original video shows - one sheer pantyhose, VIEW 01 / VIEW 02, the
// original's material inspector (key I: SheerInspectorUI) - plus a few cosmetic choices in a small panel: the stocking's
// colour and thickness, a few skirts, the skin, the background, the music. Everything else the 'Studio' of 2026-11-16 /
// 17 offered (other stocking kinds, patterns, finishes, leg shapes, light presets, camera filters, props, stickers ...)
// is parked: SheerLook.Sanitize holds those fields at their defaults; the full panel's code is kept outside the game
// (drafts/parked_studio_2026-11-17).
// The panel is sized for reading (SheerKit.UiScale) and follows the window; its sections fold.
// Keys: Tab panel, I the original's inspector, H hide all UI, F12 photo, R repair, M music, Space pause, F1 help.
// Command line: -sheerLook <file.json> (a look for captures / tests), -sheerStudioTest <dir> (the self-test),
// -sheerResetAll (the original look, the first-run window forgotten).
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;
using UnityEngine.UI;

namespace Sheer
{
    public partial class SheerStudio : MonoBehaviour
    {
        public static SheerStudio I;
        public SheerLook look = new SheerLook();
        public TightsSim sim; public TensionData tension; public CameraRig rig; public SkirtCloth skirt;
        SheerAudio audioSys; Volume volume; Exposure exposure; DepthOfField dofC; float baseExposure;
        struct LightBase { public Light l; public float intensity; public Color color; public string kind; }
        readonly List<LightBase> lights = new List<LightBase>();
        Canvas canvas; RectTransform panel, content; SheerForm form; bool open = true, hidden;
        GameObject reopenBtn; Image flash;
        float saveAt = -1f; bool capture;
        public const float PanelW = 400f;                // (units of the panel's scale: SheerKit.UiScale)
        public bool Capture => capture;
        /// tests (-sheerStudioTest, -sheerNoSave): nothing is written to the player's saved look
        public static bool NoSave => Has("-sheerStudioTest") || Has("-sheerShowcase") || Has("-sheerNoSave") || Application.isBatchMode;

        static string Arg(string key) { var a = Environment.GetCommandLineArgs(); for (int i = 0; i + 1 < a.Length; i++) if (a[i] == key) return a[i + 1]; return null; }
        static bool Has(string key) => Array.IndexOf(Environment.GetCommandLineArgs(), key) >= 0;

        void Start()
        {
            I = this;
            SheerKit.Init();
            sim = FindAnyObjectByType<TightsSim>(); tension = FindAnyObjectByType<TensionData>(); rig = FindAnyObjectByType<CameraRig>(); skirt = FindAnyObjectByType<SkirtCloth>();
            volume = FindAnyObjectByType<Volume>();
            capture = Application.isBatchMode || Has("-sheerCapture");
            if (Has("-sheerResetAll"))
            {
                // (the original look, the first-run layout and the chosen panel forgotten; in batch mode: just that, then quit)
                ResetEverything(false, true);
                foreach (var k in new[] { "sheer_studio_layout", "sheer_panel_skin" }) PlayerPrefs.DeleteKey(k);
                PlayerPrefs.Save();
                if (Application.isBatchMode) { Debug.Log("[studio] reset all: done"); Application.Quit(); return; }
            }
            var lf = Arg("-sheerLook");
            string lfText = lf != null && File.Exists(lf) ? File.ReadAllText(lf) : null;
            if (lfText != null) look = SheerLook.FromJson(lfText) ?? new SheerLook();
            else if (!capture) look = SheerLook.Load() ?? new SheerLook();
            audioSys = gameObject.AddComponent<SheerAudio>(); audioSys.sim = sim; audioSys.skirt = skirt;
            gameObject.AddComponent<SheerFun>();
            CacheLights(); SetupVolume();
            if (!capture) { FirstRunLayout(); BuildUI(); if (!NoSave && PlayerPrefs.GetInt("sheer_panel_skin", 0) == 1) SetSkin(1); if (Has("-sheerPanelClosed")) SetOpen(false); }
            ApplyAll(true);
            if (capture) look.track = -1;                      // (no music in captures)
            if (tension) look.tension.From(tension);
            lastJson = JsonUtility.ToJson(look);                   // (the first change can be undone)
            var test = Arg("-sheerStudioTest");
            if (test != null) StartCoroutine(SelfTest(test));
            var showcase = Arg("-sheerShowcase");
            if (showcase != null && !capture) StartCoroutine(Showcase(showcase));
        }

        // ------------------------------------------------------------------ window
        /// The first time: a landscape window with room for the panel beside the game (the original's game view + its
        /// inspector) instead of the portrait game view alone. (Also called by the loading screen, before its banner.)
        public static void FirstRunLayout()
        {
            if (Application.isBatchMode) return;
            if (!Screen.fullScreen && Screen.width < Screen.height * 1.2f && (PlayerPrefs.GetInt("sheer_studio_layout", 0) == 0 || NoSave))
            {
                var res = Screen.currentResolution;
                int h = Mathf.Clamp(res.height - 140, 600, 1000), w = Mathf.Clamp(Mathf.RoundToInt(h * 1.66f), 900, Mathf.Max(900, res.width - 80));
                Screen.SetResolution(w, h, FullScreenMode.Windowed);
                if (!NoSave) { PlayerPrefs.SetInt("sheer_studio_layout", 1); PlayerPrefs.Save(); }
            }
        }

        float uiScale = 1f;
        void Update()
        {
            if (!capture)
            {
                // (uGUI's Submit is Space / Enter: a button keeping the selection after a click was 'clicked' again by the pause
                //  key. Only a text field keeps the keyboard.)
                var es = UnityEngine.EventSystems.EventSystem.current;
                if (es) { var so = es.currentSelectedGameObject; if (so && !so.GetComponent<InputField>()) es.SetSelectedGameObject(null); }
                // the panel's scale: sized for reading, following the window (SheerKit.UiScale)
                if (canvas && (Screen.width != scrW || Screen.height != scrH))
                {
                    scrW = Screen.width; scrH = Screen.height;
                    uiScale = SheerKit.UiScale(PanelW + 12f);
                    SheerKit.SetScale(canvas, uiScale);
                    if (helpGo) SheerKit.SetScale(helpGo.GetComponent<Canvas>(), HelpScale());
                }
                float used = skin == 1 ? SheerInspectorUI.WidthPx : (PanelW + 12f) * uiScale;
                SheerSuperSample.ViewFraction = open && !hidden ? Mathf.Clamp01(1f - used / Mathf.Max(Screen.width, 1)) : 1f;
                if (HotkeysOk)
                {
                    if (Input.GetKeyDown(KeyCode.I)) SetSkin(1 - skin);
                    if (Input.GetKeyDown(KeyCode.F1)) ToggleHelp();
                    if (Input.GetKeyDown(KeyCode.M)) { look.musicOn = !look.musicOn; ApplyMusic(); RefreshTab(); Changed(); SheerFun.Toast(look.musicOn ? "Music on" : "Music off"); }
                    bool ctrl = Input.GetKey(KeyCode.LeftControl) || Input.GetKey(KeyCode.RightControl) || Input.GetKey(KeyCode.LeftCommand) || Input.GetKey(KeyCode.RightCommand);
                    bool shift = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
                    if (ctrl && Input.GetKeyDown(KeyCode.Z)) { if (shift) Redo(); else Undo(); }
                    if (ctrl && Input.GetKeyDown(KeyCode.Y)) Redo();
                    if (Input.GetKeyDown(KeyCode.Tab)) SetOpen(!open);
                    if (Input.GetKeyDown(KeyCode.H)) SetHidden(!hidden);
                    if (Input.GetKeyDown(KeyCode.F12)) Photo();
                    if (Input.GetKeyDown(KeyCode.R) && !Input.GetMouseButton(0)) Repair();
                    if (Input.GetKeyDown(KeyCode.Space)) { look.timeScale = look.timeScale > 0f ? 0f : 1f; ApplyPro(); SheerFun.Toast(look.timeScale > 0f ? "Running" : "Paused (Space)"); }
                    if (Input.GetKeyDown(KeyCode.Escape)) { if (helpGo) ToggleHelp(); else if (hidden) SetHidden(false); }
                }
                if (saveAt > 0f && Time.unscaledTime > saveAt) { saveAt = -1f; look.Save(); }
            }
            else SheerSuperSample.ViewFraction = 1f;
            if (flash && flash.color.a > 0f) flash.color = new Color(1f, 1f, 1f, Mathf.MoveTowards(flash.color.a, 0f, Time.unscaledDeltaTime * 2.5f));
        }

        public void Changed()
        {
            if (tension) look.tension.From(tension);
            TrackUndo();
            if (!capture && !NoSave) saveAt = Time.unscaledTime + 1.0f;
        }

        // ---- undo / redo (Ctrl+Z / Ctrl+Y): the look before each gesture (changes closer than 0.6 s are one gesture)
        readonly List<string> undo = new List<string>(), redo = new List<string>(); string lastJson; float lastChange = -10f;
        void TrackUndo()
        {
            var j = JsonUtility.ToJson(look);
            if (lastJson == null) { lastJson = j; return; }
            if (j == lastJson) return;
            if (Time.unscaledTime - lastChange > 0.6f) { undo.Add(lastJson); if (undo.Count > 50) undo.RemoveAt(0); redo.Clear(); }
            lastChange = Time.unscaledTime; lastJson = j;
        }
        public void Undo() => Step(undo, redo, "Undo");
        public void Redo() => Step(redo, undo, "Redo");
        void Step(List<string> from, List<string> to, string msg)
        {
            if (from.Count == 0) { SheerFun.Toast(from == undo ? "Nothing to undo" : "Nothing to redo"); return; }
            to.Add(JsonUtility.ToJson(look));
            var j = from[from.Count - 1]; from.RemoveAt(from.Count - 1);
            var L = SheerLook.FromJson(j); if (L == null) return;
            look = L; ApplyAll(true); RefreshTab();
            lastJson = JsonUtility.ToJson(look); lastChange = -10f;
            if (!capture && !NoSave) saveAt = Time.unscaledTime + 1.0f;
            SheerAudio.Ui("tick"); SheerFun.Toast(msg);
        }
        int scrW, scrH;
        /// key commands are off while a WORD is being typed (a letter within 0.35 s of the previous one: 'kawaii' must not toggle
        /// the panel twice, 'kuma' must not mute the music) or a text field has the keyboard
        static int hkFrame = -1; static bool hkOk = true; static float lastLetter = -10f;
        public static bool HotkeysOk
        {
            get
            {
                if (hkFrame == Time.frameCount) return hkOk;
                hkFrame = Time.frameCount;
                bool letter = false; foreach (char c in Input.inputString) if (char.IsLetter(c)) letter = true;
                hkOk = !Typing && !(letter && Time.unscaledTime - lastLetter < 0.35f);
                if (letter) lastLetter = Time.unscaledTime;
                return hkOk;
            }
        }
        /// a text field has the keyboard (the classic inspector's numbers): no key commands then
        public static bool Typing
        {
            get
            {
                var es = UnityEngine.EventSystems.EventSystem.current; var go = es ? es.currentSelectedGameObject : null;
                var f = go ? go.GetComponent<InputField>() : null; return f && f.isFocused;
            }
        }
        // ---- the panel's skin: 0 the Studio, 1 the CLASSIC INSPECTOR (the original video's panel, SheerInspectorUI)
        public int skin; SheerInspectorUI insp;
        public void SetSkin(int s)
        {
            skin = Mathf.Clamp(s, 0, 1);
            if (skin == 1 && !insp) insp = SheerInspectorUI.Create(transform);
            if (!NoSave) { PlayerPrefs.SetInt("sheer_panel_skin", skin); PlayerPrefs.Save(); }
            SetOpen(true); SheerAudio.Ui("pop");
            if (skin == 1) SheerFun.Event("classic"); else RefreshTab();
        }

        /// the original look again (the panel's button; -sheerResetAll)
        public void ResetEverything(bool apply = true, bool force = false)
        {
            var m = look;
            look = new SheerLook();
            if (apply) { look.musicVolume = m.musicVolume; look.sfxVolume = m.sfxVolume; look.track = m.track; look.musicOn = m.musicOn; }
            if (!NoSave || force) look.Save();
            if (apply) { if (tension) tension.ResetToVideoValues(); ApplyAll(true); RefreshTab(); Changed(); SheerFun.Toast("The original look"); }   // (can be undone)
        }

        public void SetOpen(bool v)
        {
            open = v;
            if (panel) panel.gameObject.SetActive(open && !hidden && skin == 0);
            if (insp) insp.SetOpen(open && !hidden && skin == 1);
            if (reopenBtn) reopenBtn.SetActive(!open && !hidden);
        }
        public void SetHidden(bool v)
        {
            hidden = v;
            if (canvas) canvas.enabled = !hidden;
            SheerUI.SetVisible(!hidden);
            SheerFun.SetVisible(!hidden);
            SetOpen(open);
        }

        // ------------------------------------------------------------------ the panel
        void BuildUI()
        {
            var cgo = new GameObject("StudioUI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            cgo.transform.SetParent(transform, false);
            canvas = cgo.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceOverlay; canvas.sortingOrder = 20;
            uiScale = SheerKit.UiScale(PanelW + 12f); SheerKit.SetScale(canvas, uiScale);
            panel = SheerKit.Rect(cgo.transform, "Panel");
            panel.anchorMin = new Vector2(1, 0); panel.anchorMax = new Vector2(1, 1); panel.pivot = new Vector2(1, 0.5f);
            panel.sizeDelta = new Vector2(PanelW, -12); panel.anchoredPosition = new Vector2(-6, 0);
            var shadow = SheerKit.Img(panel, "Shadow", SheerKit.Shadow, new Color(0.35f, 0.1f, 0.25f, 0.28f), true, 1f); SheerKit.Fill(shadow.rectTransform, -22, -26, -22, -18);
            var bg = SheerKit.Img(panel, "Bg", SheerKit.Round22, SheerKit.Panel, true, 1f); SheerKit.Fill(bg.rectTransform); bg.raycastTarget = true;
            // header: the name; the original's inspector, help, close
            var head = SheerKit.Rect(panel, "Header"); head.anchorMin = new Vector2(0, 1); head.anchorMax = new Vector2(1, 1); head.pivot = new Vector2(0.5f, 1); head.sizeDelta = new Vector2(0, 64); head.anchoredPosition = Vector2.zero;
            var hb = SheerKit.Img(head, "Ribbon", SheerKit.Round22, SheerKit.PinkSoft, true, 1f); SheerKit.Fill(hb.rectTransform, 8, 6, 8, 8);
            var logo = SheerKit.Label(hb.transform, "<color=#E84888>S</color><color=#FF7AAC>HEER</color>", 28, SheerKit.Ink, TextAnchor.MiddleLeft, true);
            SheerKit.Fill(logo.rectTransform, 16, 0, 60, 0);
            var close = SheerKit.Button(hb.transform, "›", SheerKit.Pink, SheerKit.White, () => SetOpen(false), 24, SheerKit.Circle);
            var cr = (RectTransform)close.transform; cr.anchorMin = cr.anchorMax = new Vector2(1, 0.5f); cr.sizeDelta = new Vector2(36, 36); cr.anchoredPosition = new Vector2(-26, 0);
            var help = SheerKit.Button(hb.transform, "?", SheerKit.Lavender, SheerKit.White, ToggleHelp, 20, SheerKit.Circle);
            var hpr = (RectTransform)help.transform; hpr.anchorMin = hpr.anchorMax = new Vector2(1, 0.5f); hpr.sizeDelta = new Vector2(36, 36); hpr.anchoredPosition = new Vector2(-68, 0);
            var classic = SheerKit.Button(hb.transform, "Inspector", new Color32(96, 88, 104, 255), SheerKit.White, () => SetSkin(1), 15, SheerKit.Pill);
            var clr = (RectTransform)classic.transform; clr.anchorMin = clr.anchorMax = new Vector2(1, 0.5f); clr.sizeDelta = new Vector2(104, 36); clr.anchoredPosition = new Vector2(-144, 0);
            // the content
            var scroll = SheerKit.Rect(panel, "Scroll"); scroll.anchorMin = Vector2.zero; scroll.anchorMax = Vector2.one; scroll.offsetMin = new Vector2(10, 68); scroll.offsetMax = new Vector2(-6, -68);
            var sr = scroll.gameObject.AddComponent<ScrollRect>(); sr.horizontal = false; sr.scrollSensitivity = 40f; sr.movementType = ScrollRect.MovementType.Clamped; sr.inertia = true; sr.decelerationRate = 0.12f;
            var vp = SheerKit.Rect(scroll, "Viewport"); SheerKit.Fill(vp); vp.gameObject.AddComponent<RectMask2D>();
            var vpi = vp.gameObject.AddComponent<Image>(); vpi.color = new Color(0, 0, 0, 0); vpi.raycastTarget = true;
            content = SheerKit.Rect(vp, "Content"); content.anchorMin = new Vector2(0, 1); content.anchorMax = new Vector2(1, 1); content.pivot = new Vector2(0.5f, 1); content.sizeDelta = Vector2.zero;
            var vl = content.gameObject.AddComponent<VerticalLayoutGroup>(); vl.childControlHeight = true; vl.childControlWidth = true; vl.childForceExpandHeight = false; vl.childForceExpandWidth = true; vl.spacing = 3; vl.padding = new RectOffset(2, 8, 4, 18);
            content.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            sr.viewport = vp; sr.content = content;
            form = new SheerForm(content) { width = PanelW - 10 - 6 - 2 - 8 };
            // footer
            var foot = SheerKit.Rect(panel, "Footer"); foot.anchorMin = new Vector2(0, 0); foot.anchorMax = new Vector2(1, 0); foot.pivot = new Vector2(0.5f, 0); foot.sizeDelta = new Vector2(-16, 52); foot.anchoredPosition = new Vector2(0, 8);
            var fl = foot.gameObject.AddComponent<HorizontalLayoutGroup>(); fl.spacing = 8; fl.childControlWidth = true; fl.childControlHeight = true; fl.childForceExpandWidth = true;
            SheerKit.Layout(SheerKit.Button(foot, "Repair  <size=13>(R)</size>", SheerKit.Pink, SheerKit.White, Repair, 17), -1, -1, 1);
            SheerKit.Layout(SheerKit.Button(foot, "Photo  <size=13>(F12)</size>", SheerKit.Mint, SheerKit.White, Photo, 17), -1, -1, 1);
            // reopen (when the panel is closed): a round button at the right edge
            var rb = SheerKit.Button(cgo.transform, "‹", SheerKit.Pink, SheerKit.White, () => SetOpen(true), 26, SheerKit.Circle);
            var rbr = (RectTransform)rb.transform; rbr.anchorMin = rbr.anchorMax = new Vector2(1, 0.5f); rbr.sizeDelta = new Vector2(46, 46); rbr.anchoredPosition = new Vector2(-30, 0);
            reopenBtn = rb.gameObject; reopenBtn.SetActive(false);
            // the photo flash
            var fgo = new GameObject("Flash", typeof(Canvas)); fgo.transform.SetParent(transform, false);
            var fc = fgo.GetComponent<Canvas>(); fc.renderMode = RenderMode.ScreenSpaceOverlay; fc.sortingOrder = 100;
            flash = SheerKit.Img(fgo.transform, "White", null, new Color(1, 1, 1, 0), false); SheerKit.Fill(flash.rectTransform);
            BuildForm();
        }

        // ---- the choices: a few skirts, a few backgrounds (each one checked on the game's own pictures before it was offered)
        struct SkirtOpt { public string name; public int style; public bool own; public Color col, acc, acc2; }
        static readonly SkirtOpt[] Skirts =
        {
            new SkirtOpt { name = "Charcoal", style = 0, own = false, col = SheerLook.DefaultSkirt, acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
            new SkirtOpt { name = "Black", style = 0, own = true, col = new Color(0.03f, 0.03f, 0.035f), acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
            new SkirtOpt { name = "Navy", style = 0, own = true, col = new Color(0.08f, 0.11f, 0.24f), acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
            new SkirtOpt { name = "Wine", style = 0, own = true, col = new Color(0.27f, 0.035f, 0.06f), acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
            new SkirtOpt { name = "Camel", style = 0, own = true, col = new Color(0.82f, 0.68f, 0.45f), acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
            // (a red tartan was here until 2026-11-17: a tartan pleated mini reads as a school uniform - not offered)
            new SkirtOpt { name = "Grey", style = 0, own = true, col = new Color(0.30f, 0.30f, 0.32f), acc = new Color(0.93f, 0.93f, 0.95f), acc2 = new Color(0.12f, 0.30f, 0.18f) },
        };
        struct BackOpt { public string name; public int backdrop, floor; }
        static readonly BackOpt[] Backs =
        {
            new BackOpt { name = "Studio", backdrop = 0, floor = 0 }, new BackOpt { name = "Dusk", backdrop = 1, floor = 1 }, new BackOpt { name = "Night", backdrop = 6, floor = 5 },
            new BackOpt { name = "Pastel", backdrop = 3, floor = 4 }, new BackOpt { name = "Shoji", backdrop = 4, floor = 2 }, new BackOpt { name = "Gym", backdrop = 5, floor = 3 },
        };
        static bool Same(Color a, Color b) => Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b) < 0.02f;
        int SkirtIndex()
        {
            for (int i = 0; i < Skirts.Length; i++)
                if (Skirts[i].style == look.skirtStyle && Skirts[i].own == look.skirtOwnColor && (!Skirts[i].own || Same(Skirts[i].col, look.skirtColor))) return i;
            return -1;
        }
        public void SetSkirt(int k)
        {
            var s = Skirts[Mathf.Clamp(k, 0, Skirts.Length - 1)];
            look.skirtStyle = s.style; look.skirtOwnColor = s.own; look.skirtColor = s.col; look.skirtAccent = s.acc; look.skirtAccent2 = s.acc2; look.skirtPatternScale = 1f;
        }
        int BackIndex() { for (int i = 0; i < Backs.Length; i++) if (Backs[i].backdrop == look.backdrop && Backs[i].floor == look.floor) return i; return -1; }
        public void SetBackground(int k) { var b = Backs[Mathf.Clamp(k, 0, Backs.Length - 1)]; look.backdrop = b.backdrop; look.floor = b.floor; }
        public static int SkirtCount => Skirts.Length;
        public static int BackgroundCount => Backs.Length;

        void BuildForm()
        {
            var f = form; f.Clear();
            f.Section("Stockings", Tint(0), "Thin is sheer and tears easily; thick is opaque and tougher.");
            f.Swatches("Colour", SheerLook.YarnMinimal, () => look.color, c => { look.color = c; ApplyStockings(false); Changed(); });
            f.Slider("Thickness", SheerLook.DenierMin, SheerLook.DenierMax, () => look.denier, v => { look.denier = v; ApplyStockings(true); Changed(); }, "0", false, " den");
            f.Section("Skirt", Tint(1));
            var sn = new string[Skirts.Length]; for (int i = 0; i < sn.Length; i++) sn[i] = Skirts[i].name;
            f.Chips(null, sn, SkirtIndex, k => { SetSkirt(k); ApplySkirt(); Changed(); }, 3);
            f.Section("Skin", Tint(4));
            f.Chips(null, SheerLook.SkinTones, () => look.skinTone, k => { look.skinTone = k; ApplySkin(); ApplyStockings(false); Changed(); }, 4);
            f.Section("Background", Tint(2));
            var bn = new string[Backs.Length]; for (int i = 0; i < bn.Length; i++) bn[i] = Backs[i].name;
            f.Chips(null, bn, BackIndex, k => { SetBackground(k); ApplyScene(); Changed(); }, 3);
            f.Section("Sound", Tint(3));
            var names = new string[SheerAudio.TrackNames.Length + 1];
            for (int i = 0; i < SheerAudio.TrackNames.Length; i++) names[i] = SheerAudio.TrackNames[i];
            names[names.Length - 1] = "No music";
            f.Chips(null, names, () => look.track < 0 || !look.musicOn ? names.Length - 1 : look.track,
                    k => { if (k == names.Length - 1) look.musicOn = false; else { look.track = k; look.musicOn = true; } ApplyMusic(); Changed(); }, 2);
            f.Slider("Music", 0f, 1f, () => look.musicVolume, v => { look.musicVolume = v; ApplyMusic(); Changed(); }, "0%");
            f.Slider("Effects", 0f, 1f, () => look.sfxVolume, v => { look.sfxVolume = v; ApplyMusic(); Changed(); }, "0%");
            f.Section("More", Tint(0));
            f.Buttons(("Back to the original look", () => ResetEverything(), SheerKit.PinkSoft));
            f.Buttons(("How to play  (F1)", ToggleHelp, SheerKit.Lavender));
            content.anchoredPosition = Vector2.zero;
        }
        void RefreshTab() => form?.Refresh();
        /// the panel's values again (something outside it changed the look: the classic inspector)
        public void RefreshPanel() => RefreshTab();
        // (a change in the last second before quitting is saved too)
        void OnApplicationQuit() { if (saveAt > 0f && !capture && !NoSave) { saveAt = -1f; look.Save(); } }
        Color Tint(int k) => SheerKit.SectionTints[k % SheerKit.SectionTints.Length];

        // ------------------------------------------------------------------ actions
        public void Repair()
        {
            if (sim == null) return;
            sim.MendDamage();                                      // (the tears shrink away over a moment, then are gone)
            SheerAudio.Fx("sparkle"); SheerFun.Event("repair");
        }

        public void Photo() { if (!capture && !photoBusy) StartCoroutine(PhotoCo()); }
        bool photoBusy;
        /// where photos go: Pictures/Sheer, else the game's data folder
        static string PhotoDir()
        {
            string dir = null;
            try { dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "Sheer"); Directory.CreateDirectory(dir); }
            catch (Exception) { dir = null; }
            if (string.IsNullOrEmpty(dir)) { dir = Path.Combine(Application.persistentDataPath, "Photos"); try { Directory.CreateDirectory(dir); } catch (Exception) { } }
            return dir;
        }
        IEnumerator PhotoCo()
        {
            photoBusy = true;
            bool was = hidden; string file = null;
            try
            {
                SetHidden(true);
                yield return null; yield return null; yield return new WaitForEndOfFrame();
                file = Path.Combine(PhotoDir(), $"sheer_{DateTime.Now:yyyyMMdd_HHmmss}.png");
                ScreenCapture.CaptureScreenshot(file);
                yield return null; yield return null;
            }
            finally { photoBusy = false; SetHidden(was); }      // (also if something above failed)
            if (flash) flash.color = new Color(1f, 1f, 1f, 0.85f);
            SheerAudio.Fx("shutter");
            SheerFun.Toast("Photo saved: " + file.Replace(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "~"));
            SheerFun.Event("photo");
        }

        // ---- F1 / '?': a card with every control
        GameObject helpGo;
        static float HelpScale() => Mathf.Min(SheerKit.UiScale(), 0.94f * Screen.width / 700f, 0.94f * Screen.height / 640f);
        public void ToggleHelp()
        {
            if (helpGo) { Destroy(helpGo); helpGo = null; return; }
            helpGo = new GameObject("Help", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster)); helpGo.transform.SetParent(transform, false);
            var cv = helpGo.GetComponent<Canvas>(); cv.renderMode = RenderMode.ScreenSpaceOverlay; cv.sortingOrder = 95;
            SheerKit.SetScale(cv, HelpScale());
            var dim = SheerKit.Img(helpGo.transform, "Dim", null, new Color(0.2f, 0.08f, 0.16f, 0.45f), false); SheerKit.Fill(dim.rectTransform); dim.raycastTarget = true;
            dim.gameObject.AddComponent<Button>().onClick.AddListener(ToggleHelp);
            string[,] rows =
            {
                { "Left drag", "pinch the nylon and pull - drag far or hold long and it tears" },
                { "Shift + click", "a fingernail snag: a pinhole that may run into a ladder" },
                { "Right drag  ·  wheel", "orbit  ·  zoom" },
                { "1  /  2", "VIEW 01 / VIEW 02, the original video's cameras" },
                { "R", "repair: the tears mend" },
                { "Tab", "show / hide the panel" },
                { "I", "the original video's inspector panel, and back" },
                { "H", "hide every control for a clean picture (H or Esc: back)" },
                { "F12", "photo, saved to Pictures/Sheer" },
                { "M  ·  Space", "music on / off  ·  pause" },
                { "Ctrl+Z  /  Ctrl+Y", "undo / redo a change of the look" },
                { "P", "replay the original video's session on this simulator" },
                { "F1", "this card" },
            };
            int n = rows.GetLength(0);
            var card = SheerKit.Img(helpGo.transform, "Card", SheerKit.Round22, SheerKit.Panel, true, 1f).rectTransform;
            card.anchorMin = card.anchorMax = new Vector2(0.5f, 0.5f); card.sizeDelta = new Vector2(700, 112 + 36 * n + 44);
            var title = SheerKit.Label(card, "How to play", 28, SheerKit.Ink, TextAnchor.UpperLeft, true);
            SheerKit.Fill(title.rectTransform, 34, 0, 30, 24);
            for (int i = 0; i < n; i++)
            {
                var k = SheerKit.Label(card, $"<b>{rows[i, 0]}</b>", 17, SheerKit.PinkDeep, TextAnchor.MiddleLeft, true);
                var kr = k.rectTransform; kr.anchorMin = kr.anchorMax = new Vector2(0, 1); kr.pivot = new Vector2(0, 0.5f); kr.sizeDelta = new Vector2(190, 34); kr.anchoredPosition = new Vector2(36, -92 - 36 * i);
                var v = SheerKit.Label(card, rows[i, 1], 16, SheerKit.Ink, TextAnchor.MiddleLeft, false);
                var vr = v.rectTransform; vr.anchorMin = vr.anchorMax = new Vector2(0, 1); vr.pivot = new Vector2(0, 0.5f); vr.sizeDelta = new Vector2(450, 34); vr.anchoredPosition = new Vector2(228, -92 - 36 * i);
            }
            var foot = SheerKit.Label(card, "Click anywhere to close.", 15, SheerKit.InkSoft, TextAnchor.LowerCenter, false);
            SheerKit.Fill(foot.rectTransform, 20, 18, 20, 0);
            SheerAudio.Ui("pop");
        }

        // ------------------------------------------------------------------ applying the look
        public void ApplyAll(bool fabric)
        {
            ApplyBody();
            if (tension && fabric && !look.tension.set) tension.ResetToVideoValues();     // (a preset: the video's inspector, then its fabric)
            ApplyStockings(fabric);
            if (tension && fabric && look.tension.set) look.tension.To(tension);         // (a saved / pasted / undone look: its inspector)
            ApplySkin(); ApplySkirt(); ApplyScene(); ApplyLight(); ApplyMusic(); ApplyCamera(); ApplyPro(); ApplyMotion();
            SheerFun.I?.SetMascot(look.mascot);
            RefreshTab();
        }

        static Vector4 Lin(Color c, float a = 1f) { var l = c.linear; return new Vector4(l.r, l.g, l.b, a); }

        public void ApplyStockings(bool fabric)
        {
            var L = look;
            Color yl = L.color.linear, dl = SheerLook.DefaultYarn.linear;
            bool plainOriginal = Close(L.color, SheerLook.DefaultYarn) && L.finish == 1;
            float lum = 0.2126f * yl.r + 0.7152f * yl.g + 0.0722f * yl.b;
            float shadowK = 1f - 0.65f * Mathf.Clamp01((Mathf.Sqrt(lum) - 0.23f) / 0.70f);
            float gloss = L.finish == 2 ? 0.35f : L.finish == 3 ? 0.85f : L.finish == 4 ? 0.3f : 0f, glitter = L.finish == 4 ? 1f : 0f;
            Shader.SetGlobalVector("_SheerTint", plainOriginal ? Vector4.zero : new Vector4(yl.r / dl.r, yl.g / dl.g, yl.b / dl.b, 1f));
            Shader.SetGlobalVector("_SheerTint2", new Vector4(shadowK, gloss, glitter, 0f));
            Shader.SetGlobalVector("_SheerPat", new Vector4(L.pattern, L.patternScale, L.fishnetSheer, L.seamAlways ? 1f : 0f));
            Shader.SetGlobalVector("_SheerPatCol", Lin(L.patternColor));
            Shader.SetGlobalVector("_SheerSkinK", new Vector4(L.pattern == 2 ? 1f - Mathf.Clamp01(L.fishnetSheer) : 0f, 0f, 0f, 0f));
            Shader.SetGlobalVector("_SheerToeStyle", new Vector4(L.sandalToe ? 1f : 0f, 0f, 0f, 0f));
            float top = SheerLook.StyleTop[L.style];
            float welt = L.style == 1 || L.style == 2 ? 0.045f : L.style == 3 ? 0.03f : 0.022f;
            bool lace = L.lace && (L.style == 1 || L.style == 2);
            Shader.SetGlobalVector("_SheerBand", top < 0.99f ? new Vector4(top, welt, lace ? 1f : 0f, L.style <= 2 ? 0.0008f : 0.0005f) : Vector4.zero);
            Shader.SetGlobalVector("_SheerBandCol", Lin(L.weltColor, L.weltOwnColor ? 1f : 0f));
            // the light that crosses a coloured yarn onto the skin takes some of its colour
            float mx = Mathf.Max(yl.r, Mathf.Max(yl.g, yl.b), 1e-4f);
            var chroma = new Color(yl.r / mx, yl.g / mx, yl.b / mx);
            Color.RGBToHSV(L.color, out _, out float sat, out _);
            var nt = Color.Lerp(Color.white, chroma, 0.45f * sat);
            Shader.SetGlobalVector("_SheerNylonTint", plainOriginal ? Vector4.zero : new Vector4(nt.r, nt.g, nt.b, 1f));
            if (sim != null)
            {
                // (a new top under the fingers: let go first - the band would hold the fabric the hand is pulling)
                if (!Mathf.Approximately(sim.bandTop, top)) foreach (var p in sim.pulls) if (p.state == Pull.State.Held) sim.Release(p, false);
                sim.SetBand(top, welt);
                sim.denier = L.denier; sim.fabricStrength = L.strength;
                foreach (var d in sim.damage.Values) { d.runTendency = L.runTendency * (L.pattern == 2 ? 0.03f : 1f); d.holeSize = L.holeSize; }
            }
            if (fabric && tension)
            {
                // (Beer-Lambert in the yarn's weight, through the calibrated video values at 20 denier exactly)
                tension.frostBodyCoverage = 1f - Mathf.Pow(1f - 0.829f, L.denier / 20f);
                tension.frostFootCoverage = 1f - Mathf.Pow(1f - 0.889f, L.denier / 20f);
                switch (L.finish)
                {
                    case 0: tension.frostMatteSmoothness = 0.35f; tension.pearlSpecularStrength = 0.35f; tension.pearlGlintStrength = 0.45f; tension.pearlGlintDensity = 0.08f; break;
                    case 2: tension.frostMatteSmoothness = 1f; tension.pearlSpecularStrength = 1.2f; tension.pearlGlintStrength = 1.1f; tension.pearlGlintDensity = 0.14f; break;
                    case 3: tension.frostMatteSmoothness = 1f; tension.pearlSpecularStrength = 2.2f; tension.pearlGlintStrength = 1.4f; tension.pearlGlintDensity = 0.16f; break;
                    case 4: tension.frostMatteSmoothness = 0.9f; tension.pearlSpecularStrength = 1.0f; tension.pearlGlintStrength = 3f; tension.pearlGlintDensity = 0.35f; break;
                    default: tension.frostMatteSmoothness = 0.837f; tension.pearlSpecularStrength = 0.64f; tension.pearlGlintStrength = 0.85f; tension.pearlGlintDensity = 0.117f; break;
                }
            }
        }
        static bool Close(Color a, Color b) => Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b) < 0.015f;

        public void ApplyBody() { if (sim != null && sim.lattice != null) sim.SetShape(look.legShape); }
        // the ten toenails on the body mesh (rest space): centre, half width / normal, half length - found from the toe tips'
        // front-most points (big toe at x +-0.086, little toe at +-0.139), each nail a few mm back on the toe's top (the big
        // toe's 5.5 mm back, reaching to the tip: further back it lay on the flat top, seen edge-on from the feet view)
        static readonly Vector4[] NailC =
        {
            new Vector4(0.0862f, 0.0219f, -0.1260f, 0.0064f), new Vector4(0.1056f, 0.0171f, -0.1192f, 0.0038f), new Vector4(0.1173f, 0.0172f, -0.1108f, 0.0034f),
            new Vector4(0.1285f, 0.0173f, -0.1004f, 0.0030f), new Vector4(0.1376f, 0.0148f, -0.0915f, 0.0025f),
            new Vector4(-0.0872f, 0.0223f, -0.1252f, 0.0064f), new Vector4(-0.1044f, 0.0174f, -0.1190f, 0.0038f), new Vector4(-0.1179f, 0.0172f, -0.1106f, 0.0034f),
            new Vector4(-0.1280f, 0.0175f, -0.1003f, 0.0030f), new Vector4(-0.1377f, 0.0148f, -0.0915f, 0.0025f),
        };
        static readonly Vector4[] NailN =
        {
            new Vector4(0.011f, 0.991f, -0.137f, 0.0064f), new Vector4(0.148f, 0.693f, -0.706f, 0.0036f), new Vector4(0.077f, 0.527f, -0.846f, 0.0032f),
            new Vector4(0.203f, 0.402f, -0.893f, 0.0028f), new Vector4(0.012f, 0.794f, -0.608f, 0.0023f),
            new Vector4(0.035f, 0.993f, -0.110f, 0.0064f), new Vector4(-0.042f, 0.812f, -0.582f, 0.0036f), new Vector4(-0.149f, 0.501f, -0.852f, 0.0032f),
            new Vector4(0.021f, 0.541f, -0.841f, 0.0028f), new Vector4(0.071f, 0.813f, -0.578f, 0.0023f),
        };
        bool nailsSet;

        public void ApplySkin()
        {
            var L = look;
            if (!nailsSet)
            {
                var nn = new Vector4[10];
                for (int i = 0; i < 10; i++) { var v = new Vector3(NailN[i].x, NailN[i].y, NailN[i].z).normalized; nn[i] = new Vector4(v.x, v.y, v.z, NailN[i].w); }
                Shader.SetGlobalVectorArray("_SheerNails", NailC); Shader.SetGlobalVectorArray("_SheerNailsN", nn); nailsSet = true;
            }
            Shader.SetGlobalVector("_SheerPolish", L.polish ? Lin(L.polishColor, 1f) : Vector4.zero);
            if (L.skinTone == 0) Shader.SetGlobalVector("_SheerSkinTone", Vector4.zero);
            else
            {
                var m = L.skinTone > 0 ? SheerLook.SkinToneMul[L.skinTone] : L.skinCustom.linear;
                Shader.SetGlobalVector("_SheerSkinTone", new Vector4(m.r, m.g, m.b, 1f));
            }
        }

        public void ApplySkirt()
        {
            var L = look;
            Shader.SetGlobalVector("_SheerSkirt", new Vector4(L.skirtStyle, L.skirtPatternScale, 0f, 0f));
            Shader.SetGlobalVector("_SheerSkirtCol", L.skirtOwnColor ? Lin(L.skirtColor) : Vector4.zero);
            Shader.SetGlobalVector("_SheerSkirtAcc", Lin(L.skirtAccent));
            Shader.SetGlobalVector("_SheerSkirtAcc2", Lin(L.skirtAccent2));
        }

        public void ApplyScene()
        {
            var L = look;
            Shader.SetGlobalVector("_SheerBack", new Vector4(L.backdrop, L.backBrightness, 1f, 0f));
            Shader.SetGlobalVector("_SheerBackCol0", Lin(L.backTop)); Shader.SetGlobalVector("_SheerBackCol1", Lin(L.backBottom));
            Shader.SetGlobalVector("_SheerFloor", new Vector4(L.floor, 0f, 0f, 0f));
            Shader.SetGlobalVector("_SheerFloorCol", L.floorOwnColor ? Lin(L.floorTint) : Vector4.zero);
            if (skirt) { skirt.windAmplitude = L.windOn ? L.wind : 0f; skirt.gustiness = L.gusts; }
            // hard floors lie flat (the drop cloth keeps its soft folds; a rug and a meadow a little of them)
            if (!floorGo) { var fg = GameObject.Find("DropCloth"); if (fg) { floorGo = fg.transform; floorScale = floorGo.localScale; } }
            if (floorGo) floorGo.localScale = new Vector3(floorScale.x, floorScale.y * (L.floor == 0 ? 1f : L.floor == 4 || L.floor == 6 ? 0.35f : 0.03f), floorScale.z);
            SheerFun.I?.SetProps(L.petals, L.plushie, L);
        }

        // lights: per preset key / fill / rim / floor multipliers and colours, exposure (EV)
        struct LightPreset { public float key, fill, rim, top, ev; public Color keyC, fillC, rimC, topC; }
        static readonly LightPreset[] LightPresets =
        {
            new LightPreset { key = 1f, fill = 1f, rim = 1f, top = 1f, ev = 0f },
            new LightPreset { key = 1.1f, fill = 0.75f, rim = 1.5f, top = 0.85f, ev = 0.1f, keyC = new Color(1f, 0.70f, 0.42f), fillC = new Color(0.55f, 0.65f, 1f), rimC = new Color(1f, 0.55f, 0.25f), topC = new Color(1f, 0.78f, 0.6f) },
            new LightPreset { key = 0.6f, fill = 0.55f, rim = 1.6f, top = 0.55f, ev = -0.1f, keyC = new Color(0.55f, 0.70f, 1f), fillC = new Color(0.4f, 0.5f, 0.95f), rimC = new Color(0.65f, 0.88f, 1f), topC = new Color(0.6f, 0.7f, 1f) },
            new LightPreset { key = 0.85f, fill = 0.95f, rim = 2.2f, top = 0.7f, ev = 0f, keyC = new Color(1f, 0.38f, 0.82f), fillC = new Color(0.38f, 0.32f, 1f), rimC = new Color(0.1f, 0.92f, 1f), topC = new Color(0.8f, 0.45f, 1f) },
            new LightPreset { key = 0.75f, fill = 1.9f, rim = 0.45f, top = 1.15f, ev = 0.15f, keyC = new Color(1f, 0.97f, 0.94f), fillC = new Color(0.92f, 0.96f, 1f), rimC = new Color(0.8f, 0.9f, 1f), topC = new Color(1f, 1f, 1f) },
            new LightPreset { key = 1.6f, fill = 0.25f, rim = 1.7f, top = 0.5f, ev = -0.1f, keyC = new Color(1f, 0.95f, 0.88f), fillC = new Color(0.7f, 0.75f, 1f), rimC = Color.white, topC = new Color(1f, 0.95f, 0.9f) },
            new LightPreset { key = 1f, fill = 1.15f, rim = 1.3f, top = 1f, ev = 0.05f, keyC = new Color(1f, 0.87f, 0.91f), fillC = new Color(1f, 0.76f, 0.95f), rimC = new Color(1f, 0.6f, 0.86f), topC = new Color(1f, 0.86f, 0.93f) },
        };

        void CacheLights()
        {
            foreach (var l in FindObjectsByType<Light>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                string n = l.name;
                string kind = n == "key" ? "key" : n == "fill" || n == "lowfill" ? "fill" : n == "rim" || n == "rim3" ? "rim" : n == "top" ? "top" : n == "sidefill" ? "side" : "";
                if (kind.Length > 0) lights.Add(new LightBase { l = l, intensity = l.intensity, color = l.color, kind = kind });
            }
        }

        public void ApplyLight()
        {
            var L = look; var P = LightPresets[Mathf.Clamp(L.lightPreset, 0, LightPresets.Length - 1)];
            var warm = L.warmth >= 0f ? Color.Lerp(Color.white, new Color(1f, 0.82f, 0.62f), L.warmth) : Color.Lerp(Color.white, new Color(0.72f, 0.84f, 1f), -L.warmth);
            foreach (var b in lights)
            {
                if (!b.l) continue;
                float mul = 1f; Color c = b.color;
                switch (b.kind)
                {
                    case "key": mul = P.key * L.keyIntensity; if (P.keyC.a > 0f) c = P.keyC; break;
                    case "fill": mul = P.fill * L.fillIntensity; if (P.fillC.a > 0f) c = P.fillC; break;
                    case "rim": mul = P.rim * L.rimIntensity; if (P.rimC.a > 0f) c = P.rimC; if (L.rimOwnColor) c = L.rimColor; break;
                    case "top": mul = P.top; if (P.topC.a > 0f) c = P.topC; break;
                    case "side": mul = 1f; break;
                }
                if (b.kind != "side") b.l.intensity = b.intensity * mul;
                b.l.color = b.kind == "rim" ? c : c * warm;
            }
            CameraRig.SideFillMul = P.fill * L.fillIntensity;
            CameraRig.OrbitRimMul = P.rim * L.rimIntensity;
            CameraRig.KeyTurn = Quaternion.AngleAxis(L.keyYaw, Vector3.up) * Quaternion.AngleAxis(-L.keyPitch, Vector3.right);
            if (exposure) exposure.fixedExposure.value = baseExposure - (P.ev + L.exposure);
        }

        void SetupVolume()
        {
            if (!volume) return;
            var prof = volume.profile;                             // (an instance: the asset stays as built)
            if (prof.TryGet(out exposure)) baseExposure = exposure.fixedExposure.value;
            prof.TryGet(out dofC);
            // the camera filters' overrides (switched off for 'None': the grade stays the original's)
            if (prof.TryGet(out bloomC)) { bloomBase = bloomC.intensity.value; bloomThrBase = bloomC.threshold.value; bloomScBase = bloomC.scatter.value; }
            T Get<T>() where T : VolumeComponent { if (!prof.TryGet(out T c)) c = prof.Add<T>(false); c.active = false; return c; }
            colorC = Get<ColorAdjustments>(); vignetteC = Get<Vignette>(); grainC = Get<FilmGrain>(); whiteC = Get<WhiteBalance>(); chromaC = Get<ChromaticAberration>();
        }
        Bloom bloomC; ColorAdjustments colorC; Vignette vignetteC; FilmGrain grainC; WhiteBalance whiteC; ChromaticAberration chromaC;
        float bloomBase, bloomThrBase = 1f, bloomScBase = 0.7f;

        /// camera filters: Dreamy (soft bloom, pink haze), Film (grain, warm, vignette), Mono, Pastel, Vivid, VHS
        void ApplyFilter(int f)
        {
            if (!colorC) return;
            colorC.active = vignetteC.active = grainC.active = whiteC.active = chromaC.active = f != 0;
            if (bloomC) { bloomC.intensity.Override(bloomBase); bloomC.threshold.Override(bloomThrBase); bloomC.scatter.Override(bloomScBase); }
            if (f == 0) return;
            float sat = 0f, con = 0f, post = 0f, temp = 0f, tint = 0f, vig = 0f, grain = 0f, chroma = 0f, bloom = 0f; Color cf = Color.white, vc = Color.black;
            var gt = FilmGrainLookup.Thin1;
            switch (f)
            {
                case 1: sat = -8f; con = -12f; post = 0.12f; cf = new Color(1f, 0.93f, 0.97f); bloom = 0.32f; vig = 0.22f; vc = new Color(0.35f, 0.12f, 0.24f); break;
                case 2: sat = -18f; con = 6f; temp = 14f; tint = 4f; vig = 0.34f; grain = 0.42f; chroma = 0.10f; gt = FilmGrainLookup.Medium3; break;
                case 3: sat = -100f; con = 14f; vig = 0.26f; grain = 0.22f; break;
                case 4: sat = -28f; con = -22f; post = 0.28f; cf = new Color(1f, 0.97f, 1f); temp = -4f; break;
                case 5: sat = 28f; con = 14f; bloom = 0.08f; break;
                case 6: sat = -22f; con = 10f; temp = 8f; tint = -6f; vig = 0.3f; grain = 0.65f; chroma = 0.55f; gt = FilmGrainLookup.Large02; break;
            }
            colorC.saturation.Override(sat); colorC.contrast.Override(con); colorC.postExposure.Override(post); colorC.colorFilter.Override(cf);
            whiteC.temperature.Override(temp); whiteC.tint.Override(tint);
            vignetteC.intensity.Override(vig); vignetteC.color.Override(vc); vignetteC.smoothness.Override(0.45f);
            grainC.type.Override(gt); grainC.intensity.Override(grain); grainC.response.Override(0.8f);
            chromaC.intensity.Override(chroma);
            if (bloomC && bloom > 0f) { bloomC.intensity.Override(bloom); bloomC.threshold.Override(0.85f); bloomC.scatter.Override(0.75f); }
        }

        public void ApplyCamera()
        {
            var L = look;
            if (dofC) dofC.focusMode.value = L.dof ? DepthOfFieldMode.UsePhysicalCamera : DepthOfFieldMode.Off;
            CameraRig.ApertureOverride = L.dof ? L.aperture : 0f;
            CameraRig.Turntable = L.turntable && !capture;
            ApplyFilter(capture ? 0 : L.filter);
        }

        public void ApplyMusic()
        {
            if (!audioSys) return;
            audioSys.musicVolume = look.musicVolume; audioSys.sfxVolume = look.sfxVolume; audioSys.musicOn = look.musicOn && !capture;
            audioSys.SetTrack(capture ? -1 : look.track);
        }

        public void ApplyPro()
        {
            if (tension) tension.debugView = look.debugView;
            Time.timeScale = capture ? 1f : Mathf.Clamp(look.timeScale, 0f, 2f);
        }

        public void ApplyMotion()
        {
            if (sim == null) return;
            sim.motion.toeLifts = look.toeLifts;
            if (!Has("-sheerStill")) sim.motion.motionScale = look.motionAmount;
        }

        Transform floorGo, backGo; Vector3 floorScale; Camera camC;
        /// the backdrop card fills the view whatever the lens (wide views showed its edges)
        void LateUpdate()
        {
            if (!backGo) { var b = GameObject.Find("Backdrop"); if (b) backGo = b.transform; camC = rig ? rig.GetComponent<Camera>() : Camera.main; }
            if (!backGo || !camC) return;
            float d = backGo.localPosition.z, h = 2f * d * Mathf.Tan(camC.fieldOfView * 0.5f * Mathf.Deg2Rad) * 1.15f;
            float asp = Mathf.Max(camC.aspect, 0.3f);
            backGo.localScale = new Vector3(Mathf.Max(16f, h * asp), Mathf.Max(9f, h), 1f);
        }
    }
}
