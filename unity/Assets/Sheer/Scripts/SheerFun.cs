// SHEER — the fun layer: USAGI the bunny (a little mascot who comments on what you do, in Japanese and English), toasts,
// STICKERS (achievements, some secret) and stats kept between sessions, Easter eggs (the Konami code; typing 'uwu',
// 'kawaii', 'neko', 'kuma', 'kotori' or 'usagi'; poking things), and the scene's props: sakura petals drifting in the
// skirt's wind, and a plushie friend on the floor (Usagi's twin, a bear, a cat or a chick - click it).
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Sheer
{
    public class SheerFun : MonoBehaviour
    {
        public static SheerFun I;
        /// THE MINIMAL SIMULATOR (user, 2026-11-17): of all this only the toasts run - a line of feedback at the top of the view
        /// ('Photo saved: ...'). The mascot, her speech, the stickers, the secrets, the props and the tension gauge are parked.
        public static readonly bool Minimal = true;
        public static float Fps = 60f;
        public static int LastSubsteps;

        // ---- stickers
        [Serializable] class Save { public List<string> got = new List<string>(); public int pulls, tears, photos, repairs, surprises, colorChanges; public float longest, maxTension; public List<string> tracks = new List<string>(); public List<int> friends = new List<int>(); }
        Save save = new Save();
        static readonly (string id, string title, string hint, bool secret)[] Stickers =
        {
            ("first_pull", "First touch|はじめてのタッチ", "Pull the stockings", false),
            ("first_tear", "Oopsie!|やっちゃった", "Tear them", false),
            ("snag", "Snagged!|ひっかけ", "Shift + click: a fingernail snag", false),
            ("ladder30", "Runaway ladder|大伝線", "A ladder 30 cm long", false),
            ("holes10", "Swiss cheese|穴だらけ", "Ten holes at once", false),
            ("foot", "Toe trouble|つま先注意", "A tear on the foot", false),
            ("fishnet", "Unladderable|伝線しない", "Tear a fishnet", false),
            ("colors5", "Fashionista|おしゃれさん", "Five stocking colours", false),
            ("zettai", "Zettai ryōiki|絶対領域", "Thigh-highs or over-knees", false),
            ("dj", "DJ Usagi|DJうさぎ", "Four different tracks", false),
            ("photo", "Shutterbug|カメラマン", "Take a photo", false),
            ("storm", "Kamikaze|神風", "Turn the wind way up", false),
            ("vibe", "Groovy|ノリノリ", "Let her vibe to the music", false),
            ("lookdev", "Look-dev nerd|ルックデブの達人", "Open a look-dev view", false),
            ("slowmo", "Bullet time|スローモー", "Slow time right down", false),
            ("repair5", "Mending queen|お直し名人", "Repair five times", false),
            ("macro", "Pixel peeper|拡大鏡", "The macro view", false),
            ("surprise10", "Gacha luck|ガチャ運", "Surprise me ×10", false),
            ("classic", "Old school|原作派", "Open the original's panel", false),
            ("filters3", "Film buff|フィルム通", "Three camera filters", false),
            ("ribbon", "Ribbon dancer|リボンの舞", "The gymnast's ribbon", false),
            ("pedicure", "Pedicure|ペディキュア", "Paint her toenails", false),
            ("purikura", "Purikura!|プリクラ！", "Take a purikura sheet", false),
            ("boop", "Boop!|ぷにっ", "???", true),
            ("magical", "Magical girl|魔法少女", "???", true),
            ("uwu", "uwu|うゅ", "???", true),
            ("plush", "Dizzy bun|目が回る", "???", true),
            ("friends", "Plushie party|ぬいぐるみ会", "???", true),
        };

        // ---- UI
        RectTransform gaugeRoot; Image gauge, gaugeHeart; float gaugeShown;
        public static Vector2? GaugeAt;                        // (tests: where the cursor would be)
        Canvas canvas; RectTransform toastRoot, mascotRoot, bubble; Text bubbleText; Image eyeL, eyeR, blushL, blushR; Text mouth;
        readonly Queue<string> toasts = new Queue<string>(); float toastT = -1f; RectTransform toastCard; Text toastText;
        float bubbleUntil, nextTip = 25f, mascotPoke; int pokes; bool uwuMode, mascotOn = true, visible = true;
        float hop, hopV, blinkAt = 3f, shock;
        string typed = "";
        static readonly KeyCode[] Konami = { KeyCode.UpArrow, KeyCode.UpArrow, KeyCode.DownArrow, KeyCode.DownArrow, KeyCode.LeftArrow, KeyCode.RightArrow, KeyCode.LeftArrow, KeyCode.RightArrow, KeyCode.B, KeyCode.A };
        int konami;

        // ---- little emotes floating up from Usagi: notes on the beat, '!' at a tear, hearts for a photo, stars for a sticker
        struct Floater { public RectTransform r; public Graphic g; public float t, life, spin; public Vector2 p0, v0; }
        readonly List<Floater> floaters = new List<Floater>(); long lastBar = -1;
        void Float(string glyph, Sprite s, Color c, float size, Vector2 offset, float life = 1.5f)
        {
            if (!mascotRoot || !mascotOn || !visible || floaters.Count > 24) return;
            Graphic g;
            if (s != null) { var im = SheerKit.Img(mascotRoot, "Float", s, c, false); im.rectTransform.sizeDelta = new Vector2(size, size); g = im; }
            else { var tx = SheerKit.Label(mascotRoot, glyph, Mathf.RoundToInt(size), c, TextAnchor.MiddleCenter, true); tx.rectTransform.sizeDelta = new Vector2(size * 1.6f, size * 1.6f); g = tx; }
            g.raycastTarget = false;
            var r = g.rectTransform; r.anchorMin = r.anchorMax = new Vector2(0.5f, 0f); r.anchoredPosition = new Vector2(offset.x, 112f + offset.y);
            floaters.Add(new Floater { r = r, g = g, life = life, p0 = r.anchoredPosition, v0 = new Vector2(UnityEngine.Random.Range(-22f, 22f), UnityEngine.Random.Range(48f, 78f)), spin = UnityEngine.Random.Range(-40f, 40f) });
        }
        public static void Emote(string kind)
        {
            if (!I || Minimal) return;
            switch (kind)
            {
                case "photo": for (int k = 0; k < 3; k++) I.Float(null, SheerKit.Heart, SheerKit.Pink, 18f + 4f * k, new Vector2(-24f + 24f * k, 6f * k)); break;
                case "sticker": I.Float(null, SheerKit.Star, SheerKit.Lemon, 22f, new Vector2(-16f, 0f)); I.Float(null, SheerKit.Star, SheerKit.Lemon, 16f, new Vector2(18f, 10f)); break;
                case "tear": I.Float("!", null, SheerKit.PinkDeep, 30f, new Vector2(30f, 4f), 1.1f); break;
                case "snag": I.Float("!?", null, SheerKit.PinkDeep, 22f, new Vector2(30f, 4f), 1.1f); break;
            }
        }
        void UpdateFloaters()
        {
            for (int i = floaters.Count - 1; i >= 0; i--)
            {
                var f = floaters[i]; f.t += Time.unscaledDeltaTime; floaters[i] = f;
                if (!f.r || f.t >= f.life) { if (f.r) Destroy(f.r.gameObject); floaters.RemoveAt(i); continue; }
                float k = f.t / f.life, pop = Mathf.Min(1f, f.t / 0.15f);
                f.r.anchoredPosition = f.p0 + f.v0 * f.t + new Vector2(Mathf.Sin(f.t * 6f + f.spin) * 6f, 0f);
                f.r.localScale = Vector3.one * (0.6f + 0.4f * pop) * (1f + 0.15f * Mathf.Sin(f.t * 9f));
                f.r.localRotation = Quaternion.Euler(0, 0, f.spin * k);
                var c = f.g.color; c.a = 1f - k * k; f.g.color = c;
            }
        }

        // ---- props
        SheerRibbon ribbon; SkirtCloth skirtC;
        ParticleSystem petals; GameObject plush; float plushSquash; int plushClicks; float plushSpin;
        TightsSim sim; float heldTension; bool tensionLine;

        void Awake() { I = this; LoadSave(); }
        void Start()
        {
            sim = FindAnyObjectByType<TightsSim>();
            TightsSim.Grabbed += OnGrab;
            if (SheerStudio.I && SheerStudio.I.Capture) return;
            BuildUI();
        }
        void OnDestroy() { TightsSim.Grabbed -= OnGrab; if (I == this) I = null; }

        // ------------------------------------------------------------------ static entry points
        public static void Toast(string s) { if (I && !Quiet) I.toasts.Enqueue(s); }
        /// (the README's stills: no toasts or speech bubbles over the picture)
        public static bool Quiet;
        public static void SetVisible(bool v) { if (I) { I.visible = v; if (I.canvas) I.canvas.enabled = v; } }
        public static void Boop(Vector3 at)
        {
            if (!I || Minimal) return;
            SheerAudio.Fx("boing", 0.6f, 1.3f); I.Say("Hey, that's skin! ♡|そこは肌だよ！"); I.Unlock("boop");
        }
        public static void OnTear(Pull p)
        {
            if (!I || Minimal) return;
            I.save.tears++; I.Unlock("first_tear");
            if (p != null && p.z < 0.07f) I.Unlock("foot");
            if (SheerStudio.I && SheerStudio.I.look.pattern == 2) I.Unlock("fishnet");
            I.shock = 1f; Emote("tear");
            I.Say(UnityEngine.Random.value < 0.5f ? "Kyaa! A hole!|きゃっ！穴が！" : "Ahh, my tights...!|あ～タイツが…");
            I.Persist();
        }
        public static void OnSnag(float z)
        {
            if (!I || Minimal) return;
            I.Unlock("snag"); I.shock = 0.6f; Emote("snag");
            I.Say(UnityEngine.Random.value < 0.5f ? "A snag! Watch it run...|ひっかけちゃった！" : "Careful with those nails~|爪に気をつけて～");
        }
        public static void Event(string e)
        {
            if (!I || Minimal) return;
            var s = I.save;
            switch (e)
            {
                case "repair": s.repairs++; if (s.repairs >= 5) I.Unlock("repair5"); I.Say("Good as new ✧|新品みたい✧"); break;
                case "photo": s.photos++; I.Unlock("photo"); I.Say("Say cheese!|はい、チーズ！"); Emote("photo"); break;
                case "surprise": s.surprises++; if (s.surprises >= 10) I.Unlock("surprise10"); I.Say(UnityEngine.Random.value < 0.5f ? "Ooh, cute!|かわいい！" : "What a look!|いいね！"); break;
                case "preset": I.Say("Cute!|かわいい！"); break;
                case "color": break;
                case "storm": I.Unlock("storm"); I.Say("Whoa, hold the skirt!|スカート押さえて！"); break;
                case "vibe": I.Unlock("vibe"); I.Say("♪ Let's dance!|ノリノリ♪"); break;
                case "lookdev": I.Unlock("lookdev"); break;
                case "slowmo": I.Unlock("slowmo"); break;
                case "macro": I.Unlock("macro"); I.Say("Look at the knit!|編み目が見える！"); break;
                case "glitter": I.Say("Sparkly~!|キラキラ～！"); break;
                case "ribbon": I.Unlock("ribbon"); I.Say("Rhythmic gymnastics ✧|新体操だ✧"); break;
                case "classic": I.Unlock("classic"); I.Say("The original's panel ✧|原作のパネルだよ"); break;
                case "polish": I.Unlock("pedicure"); I.Say("Cute toes ♡|ペディキュアかわいい♡"); break;
                case "purikura": s.photos++; I.Unlock("purikura"); I.Say("Purikura time ♡|プリクラだよ♡"); Emote("photo"); break;
                default:
                    if (e.StartsWith("style") && (e == "style1" || e == "style2")) { I.Unlock("zettai"); I.Say("Zettai ryōiki ✧|絶対領域✧"); }
                    if (e.StartsWith("track") && e != "track-1") { if (!s.tracks.Contains(e)) s.tracks.Add(e); int nt = 0; foreach (var x in s.tracks) if (x.StartsWith("track")) nt++; if (nt >= 4) I.Unlock("dj"); }
                    if (e.StartsWith("color:")) { if (!s.tracks.Contains(e)) s.tracks.Add(e); int nc = 0; foreach (var x in s.tracks) if (x.StartsWith("color:")) nc++; s.colorChanges = nc; if (nc >= 5) I.Unlock("colors5"); }
                    if (e.StartsWith("filter") && e != "filter0") { if (!s.tracks.Contains(e)) s.tracks.Add(e); int nf = 0; foreach (var x in s.tracks) if (x.StartsWith("filter")) nf++; if (nf >= 3) I.Unlock("filters3"); }
                    break;
            }
            I.Persist();
        }

        void OnGrab(Pull p)
        {
            if (Minimal) return;
            save.pulls++; Unlock("first_pull");
            if (UnityEngine.Random.value < 0.25f) Say(UnityEngine.Random.value < 0.5f ? "Ehehe~|えへへ" : "Gently~!|やさしくね～");
        }

        // ------------------------------------------------------------------ stickers & stats
        void LoadSave()
        {
            try { var j = PlayerPrefs.GetString("sheer_fun", ""); if (j.Length > 0) save = JsonUtility.FromJson<Save>(j) ?? new Save(); } catch (Exception) { save = new Save(); }
        }
        void Persist() { if (!SheerStudio.NoSave) PlayerPrefs.SetString("sheer_fun", JsonUtility.ToJson(save)); }
        public void ResetProgress() { save = new Save(); }
        public void Unlock(string id)
        {
            if (Minimal || save.got.Contains(id) || (SheerStudio.I && SheerStudio.I.Capture)) return;
            save.got.Add(id); Persist(); if (!SheerStudio.NoSave) PlayerPrefs.Save();
            foreach (var st in Stickers) if (st.id == id) { Toast($"✦ Sticker: <b>{SheerKit.En(st.title)}</b>  <size=12>{SheerKit.Jp(st.title)}</size>"); break; }
            SheerAudio.Fx("achievement", 0.8f); Emote("sticker");
        }
        public void BuildStickers(SheerForm f)
        {
            int cols = 3, n = Stickers.Length, rows = (n + cols - 1) / cols;
            var grid = f.Row(rows * 74 + 4);
            var g = grid.gameObject.AddComponent<GridLayoutGroup>(); g.cellSize = new Vector2((f.width - 12f) / cols, 70); g.spacing = new Vector2(6, 4);
            g.constraint = GridLayoutGroup.Constraint.FixedColumnCount; g.constraintCount = cols;
            foreach (var st in Stickers)
            {
                bool got = save.got.Contains(st.id);
                var card = SheerKit.Img(grid, "Sticker", SheerKit.Round14, got ? new Color32(255, 236, 246, 255) : new Color32(242, 236, 242, 255), true, 1.4f);
                var icon = SheerKit.Img(card.transform, "Icon", got ? (st.secret ? SheerKit.Heart : SheerKit.Star) : SheerKit.Circle, got ? (st.secret ? SheerKit.PinkDeep : SheerKit.Lemon) : new Color32(215, 205, 215, 255), false);
                var ir = icon.rectTransform; ir.anchorMin = ir.anchorMax = new Vector2(0.5f, 1); ir.sizeDelta = new Vector2(26, 26); ir.anchoredPosition = new Vector2(0, -18);
                var t = SheerKit.Label(card.transform, got || !st.secret ? $"<b>{SheerKit.En(st.title)}</b>\n<size=9>{(got ? SheerKit.Jp(st.title) : st.hint)}</size>" : "<b>???</b>\n<size=9>secret</size>", 11, got ? SheerKit.Ink : SheerKit.InkSoft, TextAnchor.LowerCenter);
                SheerKit.Fill(t.rectTransform, 3, 4, 3, 0); t.lineSpacing = 0.9f;
            }
            f.Note($"{save.got.Count} / {Stickers.Length} stickers", 12);
        }
        public string StatsText()
        {
            float longestNow = 0f; int holes = 0;
            if (sim != null) foreach (var d in sim.damage.Values) { holes += d.holes.Count; foreach (var r in d.runs) longestNow = Mathf.Max(longestNow, r.hi - r.lo); }
            return $"pulls <b>{save.pulls}</b> · tears <b>{save.tears}</b> · repairs <b>{save.repairs}</b> · photos <b>{save.photos}</b>\n" +
                   $"holes now <b>{holes}</b> · longest ladder ever <b>{save.longest * 100f:0.0} cm</b>\n" +
                   $"highest tension <b>{save.maxTension:0.00}</b> (1 = it gives way)";
        }

        // ------------------------------------------------------------------ mascot
        void BuildUI()
        {
            var cgo = new GameObject("FunUI", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            cgo.transform.SetParent(transform, false);
            canvas = cgo.GetComponent<Canvas>(); canvas.renderMode = RenderMode.ScreenSpaceOverlay; canvas.sortingOrder = 15;
            SheerKit.SetScale(canvas, SheerKit.UiScale());
            // toasts: top centre of the window
            toastRoot = SheerKit.Rect(cgo.transform, "Toasts"); toastRoot.anchorMin = toastRoot.anchorMax = new Vector2(0.5f, 1f); toastRoot.sizeDelta = new Vector2(10, 10);
            var card = SheerKit.Img(toastRoot, "Card", SheerKit.Pill, new Color32(70, 52, 78, 235), true, 1f); toastCard = card.rectTransform;
            toastCard.anchorMin = toastCard.anchorMax = new Vector2(0.5f, 1f); toastCard.pivot = new Vector2(0.5f, 1f); toastCard.sizeDelta = new Vector2(520, 44); toastCard.anchoredPosition = new Vector2(0, 80);
            toastText = SheerKit.Label(card.transform, "", 16, SheerKit.White, TextAnchor.MiddleCenter, true); SheerKit.Fill(toastText.rectTransform, 16, 0, 16, 0);
            toastText.horizontalOverflow = HorizontalWrapMode.Overflow;
            card.gameObject.SetActive(false);
            if (Minimal) return;
            // Usagi, bottom left of the game view (above the VIEW buttons)
            mascotRoot = SheerKit.Rect(cgo.transform, "Usagi"); mascotRoot.anchorMin = mascotRoot.anchorMax = new Vector2(0, 0); mascotRoot.sizeDelta = new Vector2(120, 140); mascotRoot.anchoredPosition = new Vector2(110, 210);
            Color white = new Color32(255, 252, 253, 255), pinkIn = new Color32(255, 182, 206, 255), outline = new Color32(120, 86, 120, 255);
            Image Part(string n, Sprite s, Color c, Vector2 pos, Vector2 size, float rot = 0f)
            {
                var im = SheerKit.Img(mascotRoot, n, s, c, false); var r = im.rectTransform; r.anchorMin = r.anchorMax = new Vector2(0.5f, 0f); r.sizeDelta = size; r.anchoredPosition = pos; r.localRotation = Quaternion.Euler(0, 0, rot); return im;
            }
            Part("EarLo", SheerKit.Petal, outline, new Vector2(-19, 102), new Vector2(31, 64), 12f); Part("EarRo", SheerKit.Petal, outline, new Vector2(19, 104), new Vector2(31, 64), -10f);
            Part("EarL", SheerKit.Petal, white, new Vector2(-19, 102), new Vector2(27, 60), 12f); Part("EarR", SheerKit.Petal, white, new Vector2(19, 104), new Vector2(27, 60), -10f);
            Part("EarLin", SheerKit.Petal, pinkIn, new Vector2(-19, 100), new Vector2(13, 40), 12f); Part("EarRin", SheerKit.Petal, pinkIn, new Vector2(19, 102), new Vector2(13, 40), -10f);
            Part("BodyO", SheerKit.Circle, outline, new Vector2(0, 30), new Vector2(76, 64)); Part("Body", SheerKit.Circle, white, new Vector2(0, 30), new Vector2(72, 60));
            Part("HeadO", SheerKit.Circle, outline, new Vector2(0, 66), new Vector2(88, 76)); var head = Part("Head", SheerKit.Circle, white, new Vector2(0, 66), new Vector2(84, 72));
            eyeL = Part("EyeL", SheerKit.Circle, new Color32(60, 40, 60, 255), new Vector2(-17, 68), new Vector2(11, 13)); eyeR = Part("EyeR", SheerKit.Circle, new Color32(60, 40, 60, 255), new Vector2(17, 68), new Vector2(11, 13));
            Part("ShineL", SheerKit.Circle, Color.white, new Vector2(-15, 71), new Vector2(4, 4)); Part("ShineR", SheerKit.Circle, Color.white, new Vector2(19, 71), new Vector2(4, 4));
            blushL = Part("BlushL", SheerKit.Circle, new Color32(255, 140, 170, 150), new Vector2(-27, 57), new Vector2(15, 9)); blushR = Part("BlushR", SheerKit.Circle, new Color32(255, 140, 170, 150), new Vector2(27, 57), new Vector2(15, 9));
            mouth = SheerKit.Label(mascotRoot, "ω", 15, new Color32(120, 70, 100, 255), TextAnchor.MiddleCenter, true);
            var mr = mouth.rectTransform; mr.anchorMin = mr.anchorMax = new Vector2(0.5f, 0f); mr.sizeDelta = new Vector2(30, 20); mr.anchoredPosition = new Vector2(0, 58);
            Part("Bow", SheerKit.Heart, SheerKit.PinkDeep, new Vector2(27, 98), new Vector2(18, 16), 20f);
            Part("FootL", SheerKit.Circle, white, new Vector2(-16, 4), new Vector2(24, 13)); Part("FootR", SheerKit.Circle, white, new Vector2(16, 4), new Vector2(24, 13));
            head.raycastTarget = true;
            var btn = head.gameObject.AddComponent<Button>(); btn.transition = Selectable.Transition.None; btn.onClick.AddListener(PokeMascot);
            // speech bubble, to the right of her head
            var bub = SheerKit.Img(mascotRoot, "Bubble", SheerKit.Round14, new Color32(255, 255, 255, 240), true, 1.4f); bubble = bub.rectTransform;
            bubble.anchorMin = bubble.anchorMax = new Vector2(0.5f, 0f); bubble.pivot = new Vector2(0f, 0f); bubble.sizeDelta = new Vector2(250, 58); bubble.anchoredPosition = new Vector2(48, 96);
            var tail = SheerKit.Img(bubble, "Tail", SheerKit.Circle, new Color32(255, 255, 255, 240), false); var tr = tail.rectTransform; tr.anchorMin = tr.anchorMax = new Vector2(0, 0); tr.sizeDelta = new Vector2(14, 14); tr.anchoredPosition = new Vector2(2, 6);
            bubbleText = SheerKit.Label(bubble, "", 14, SheerKit.Ink, TextAnchor.MiddleLeft, true); SheerKit.Fill(bubbleText.rectTransform, 12, 4, 10, 4);
            bubble.gameObject.SetActive(false);
            // the tension gauge: a ring by the cursor that fills as the pull nears tearing (mint -> amber -> pink)
            gaugeRoot = SheerKit.Rect(cgo.transform, "Gauge"); gaugeRoot.anchorMin = gaugeRoot.anchorMax = Vector2.zero; gaugeRoot.sizeDelta = new Vector2(44, 44);
            var gb = SheerKit.Img(gaugeRoot, "Track", SheerKit.Ring, new Color(1f, 1f, 1f, 0.35f), false); SheerKit.Fill(gb.rectTransform);
            gauge = SheerKit.Img(gaugeRoot, "Fill", SheerKit.Ring, SheerKit.Pink, false); SheerKit.Fill(gauge.rectTransform);
            gauge.type = Image.Type.Filled; gauge.fillMethod = Image.FillMethod.Radial360; gauge.fillOrigin = (int)Image.Origin360.Top; gauge.fillClockwise = true;
            gaugeHeart = SheerKit.Img(gaugeRoot, "Heart", SheerKit.Heart, SheerKit.Pink, false); var ghr = gaugeHeart.rectTransform; ghr.anchorMin = ghr.anchorMax = new Vector2(0.5f, 0.5f); ghr.sizeDelta = new Vector2(16, 15);
            foreach (var g in gaugeRoot.GetComponentsInChildren<Graphic>()) g.raycastTarget = false;
            gaugeRoot.gameObject.SetActive(false);
            mascotRoot.gameObject.SetActive(mascotOn);            // (the Studio's saved choice arrives before she is built)
            Say("Hi! I'm Usagi ♡ Pull her stockings!|うさぎだよ♡ タイツを引っぱってね！", 5f);
        }

        void PokeMascot()
        {
            pokes++; hopV = 260f; SheerAudio.Fx("boing", 0.7f, UnityEngine.Random.Range(1.0f, 1.3f));
            if (Time.unscaledTime - mascotPoke > 2f) pokes = 1;
            mascotPoke = Time.unscaledTime;
            if (pokes >= 5) { Say("Stop poking me! >_<|つつかないで！"); pokes = 0; }
            else Say(Tips[UnityEngine.Random.Range(0, Tips.Length)]);
        }

        static readonly string[] Tips =
        {
            "Drag the nylon to pull it!|タイツを引っぱってみて！", "Hold a pull long... it might tear!|ずっと引くと…破れちゃうかも！",
            "Fishnets don't ladder - true story|網タイツは伝線しないよ", "H hides the UI for a clean photo|Hでスクショモード",
            "Try 'Vibe' in Body with music on ♪|ノリノリでおどろう♪", "The Pro tab shows the tension field!|プロタブで張力が見えるよ",
            "Thigh-highs leave bare skin above ✧|ニーハイの上は素肌だよ", "Ladders follow the wales - down onto the foot|伝線は足先まで走るよ",
            "R repairs everything ♡|Rでなおせるよ♡", "Tab hides this panel|Tabでパネルを隠す",
            "Shift + click: a fingernail snag|Shift+クリックでひっかけ", "Psst... try typing 'neko'|「neko」って打ってみて",
            "◧ or I: the original demo's panel|◧ か I で原作のパネル", "Ctrl+Z undoes any change ♡|Ctrl+Zで元に戻せるよ",
        };

        public void SetMascot(bool on)
        {
            mascotOn = on;
            if (mascotRoot) mascotRoot.gameObject.SetActive(on);
        }

        public void Say(string s, float secs = 3.2f)
        {
            if (!bubble || !mascotOn || Quiet) return;
            string en = SheerKit.En(s), jp = SheerKit.Jp(s);
            if (uwuMode) en = Uwu(en);
            bubbleText.text = jp.Length > 0 ? $"{en}\n<size=11><color=#{ColorUtility.ToHtmlStringRGB(SheerKit.InkSoft)}>{jp}</color></size>" : en;
            bubble.sizeDelta = new Vector2(Mathf.Clamp(16 + Mathf.Max(en.Length, jp.Length * 1.9f) * 7.4f, 120f, 330f), jp.Length > 0 ? 58 : 40);
            bubble.gameObject.SetActive(true); bubbleUntil = Time.unscaledTime + secs; hopV = Mathf.Max(hopV, 120f);
        }
        static string Uwu(string s) => s.Replace("r", "w").Replace("l", "w").Replace("R", "W").Replace("L", "W").Replace("!", " uwu!").Replace("~", " owo~");

        // ------------------------------------------------------------------ props
        public void SetProps(bool petalsOn, bool plushOn, SheerLook look)
        {
            if (SheerStudio.I && SheerStudio.I.Capture && !petalsOn && !plushOn && (look == null || !look.ribbon)) return;
            if (petalsOn && !petals) petals = MakePetals();
            if (petals) { var em = petals.emission; em.enabled = petalsOn; if (!petalsOn) petals.Clear(); }
            bool ribbonOn = look != null && look.ribbon;
            if (ribbonOn && !ribbon) { var rg = new GameObject("GymRibbon"); rg.transform.position = new Vector3(-0.37f, 0.47f, 0.03f); ribbon = rg.AddComponent<SheerRibbon>(); }
            if (ribbon) ribbon.gameObject.SetActive(ribbonOn);
            int kind = look != null ? Mathf.Clamp(look.plushKind, 0, PlushWords.Length - 1) : 0;
            if (plush && plushOn && kind != plushKind) { Destroy(plush); plush = null; }
            if (plushOn && !plush) { plushKind = kind; plush = MakePlush(kind); }
            if (plush) plush.SetActive(plushOn);
        }

        // the plushie friends: Usagi's twin, Kuma the bear, Neko the cat, Piyo the chick (all of primitives)
        public static readonly string[] PlushNames = { "Usagi|うさぎ", "Kuma|くま", "Neko|ねこ", "Piyo|ひよこ" };
        static readonly string[] PlushWords = { "usagi", "kuma", "neko", "kotori" };       // (typed: 'piyo' would start with P, the replay key)
        static readonly string[] PlushHello = { "My twin is back!|ふたごが来たよ！", "Kuma-chan says hi!|くまちゃんだよ！", "Nya~!|にゃ～！", "Piyo piyo!|ぴよぴよ！" };
        int plushKind = -1;
        void MetFriend(int k)
        {
            save.friends ??= new List<int>();
            if (!save.friends.Contains(k)) save.friends.Add(k);
            if (save.friends.Count >= PlushWords.Length) Unlock("friends");
            Persist();
        }

        ParticleSystem MakePetals()
        {
            var mat = Resources.Load<Material>("Materials/Petal");
            if (!mat) { Debug.LogWarning("[fun] no Resources/Materials/Petal"); return null; }
            var go = new GameObject("SakuraPetals"); go.transform.position = new Vector3(0f, 1.15f, -0.25f);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main; main.duration = 10f; main.loop = true; main.startLifetime = 9f; main.startSpeed = 0.05f; main.startSize = new ParticleSystem.MinMaxCurve(0.011f, 0.018f);
            main.startRotation3D = true; main.startRotationX = new ParticleSystem.MinMaxCurve(0f, 6.28f); main.startRotationY = new ParticleSystem.MinMaxCurve(0f, 6.28f); main.startRotationZ = new ParticleSystem.MinMaxCurve(0f, 6.28f);
            main.gravityModifier = 0.012f; main.maxParticles = 400; main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 0.82f, 0.88f), new Color(1f, 0.66f, 0.78f));
            var em = ps.emission; em.rateOverTime = 14f;
            var sh = ps.shape; sh.shapeType = ParticleSystemShapeType.Box; sh.scale = new Vector3(1.6f, 0.05f, 1.0f);
            var vel = ps.velocityOverLifetime; vel.enabled = true; vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(-0.04f, 0.06f); vel.y = new ParticleSystem.MinMaxCurve(-0.06f, -0.03f); vel.z = new ParticleSystem.MinMaxCurve(-0.05f, 0.02f);
            var noise = ps.noise; noise.enabled = true; noise.strength = 0.08f; noise.frequency = 0.6f; noise.scrollSpeed = 0.3f; noise.separateAxes = false;
            var rot = ps.rotationOverLifetime; rot.enabled = true; rot.separateAxes = true; rot.x = new ParticleSystem.MinMaxCurve(-2f, 2f); rot.y = new ParticleSystem.MinMaxCurve(-2f, 2f); rot.z = new ParticleSystem.MinMaxCurve(-1f, 1f);
            var col = ps.collision; col.enabled = true; col.type = ParticleSystemCollisionType.Planes; col.dampen = 1f; col.bounce = 0f; col.lifetimeLoss = 0f;
            var floorPlane = new GameObject("PetalFloor").transform; floorPlane.SetParent(go.transform, false); floorPlane.position = new Vector3(0f, 0.002f, 0f); col.AddPlane(floorPlane);
            var r = go.GetComponent<ParticleSystemRenderer>(); r.renderMode = ParticleSystemRenderMode.Mesh;
            r.mesh = PetalMesh(); r.material = mat; r.alignment = ParticleSystemRenderSpace.World; r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            r.renderingLayerMask = 0xFFu;                     // (lit by every light: the rig's lights are linked to layers)
            ps.Play();
            return ps;
        }
        static Mesh PetalMesh()
        {
            // a cupped petal: a small fan of triangles, notched tip
            var m = new Mesh { name = "petal" };
            var v = new List<Vector3>(); var t = new List<int>(); var uv = new List<Vector2>();
            int N = 8;
            v.Add(new Vector3(0, -0.5f, 0)); uv.Add(new Vector2(0.5f, 0));
            for (int i = 0; i <= N; i++)
            {
                float a = Mathf.Lerp(-1.2f, 1.2f, i / (float)N);
                float rr = 0.5f + 0.45f * Mathf.Cos(a) - (Mathf.Abs(a) < 0.25f ? 0.12f * (1f - Mathf.Abs(a) / 0.25f) : 0f);
                var p = new Vector3(Mathf.Sin(a) * 0.42f, -0.5f + rr * Mathf.Cos(a) * 1.0f, 0.08f * Mathf.Sin(a) * Mathf.Sin(a));
                v.Add(p); uv.Add(new Vector2(0.5f + p.x, p.y + 0.5f));
                if (i > 0) { t.Add(0); t.Add(i); t.Add(i + 1); }        // (one winding: the material is double-sided - both windings
                                                                       //  on shared vertices had cancelled the normals: black petals)
            }
            m.SetVertices(v); m.SetUVs(0, uv); m.SetTriangles(t, 0); m.RecalculateNormals(); m.RecalculateBounds();
            return m;
        }

        GameObject MakePlush(int kind)
        {
            var white = Resources.Load<Material>("Materials/PlushWhite"); var pink = Resources.Load<Material>("Materials/PlushPink");
            var black = Resources.Load<Material>("Materials/PlushEye"); var red = Resources.Load<Material>("Materials/PlushRibbon");
            if (!white) { Debug.LogWarning("[fun] no plush materials"); return null; }
            var brown = Resources.Load<Material>("Materials/PlushBrown") ?? white; var cream = Resources.Load<Material>("Materials/PlushCream") ?? white;
            var yellow = Resources.Load<Material>("Materials/PlushYellow") ?? white; var orange = Resources.Load<Material>("Materials/PlushOrange") ?? red;
            var grey = Resources.Load<Material>("Materials/PlushGrey") ?? white;
            var root = new GameObject("Plush_" + PlushWords[kind]); root.transform.position = new Vector3(-0.27f, 0f, -0.04f); root.transform.rotation = Quaternion.Euler(0f, 24f, 0f);
            GameObject P(PrimitiveType t, Material m, Vector3 pos, Vector3 scale, Vector3 euler = default, bool collider = false)
            {
                var g = GameObject.CreatePrimitive(t); g.name = "part";
                if (!collider) Destroy(g.GetComponent<Collider>());
                g.transform.SetParent(root.transform, false); g.transform.localPosition = pos; g.transform.localScale = scale; g.transform.localRotation = Quaternion.Euler(euler);
                var mr = g.GetComponent<MeshRenderer>(); mr.sharedMaterial = m; mr.renderingLayerMask = 0xFFu;
                return g;
            }
            if (kind == 1) { MakeBear(P, brown, cream, black, red); return root; }
            if (kind == 2) { MakeCat(P, grey, white, pink, black, red); return root; }
            if (kind == 3) { MakeChick(P, yellow, orange, black, pink); return root; }
            P(PrimitiveType.Sphere, white, new Vector3(0, 0.042f, 0), new Vector3(0.085f, 0.078f, 0.072f), default, true);          // body
            P(PrimitiveType.Sphere, white, new Vector3(0, 0.103f, -0.004f), new Vector3(0.078f, 0.068f, 0.066f), default, true);    // head
            P(PrimitiveType.Capsule, white, new Vector3(-0.017f, 0.155f, 0.004f), new Vector3(0.022f, 0.032f, 0.014f), new Vector3(0, 0, 14f));
            P(PrimitiveType.Capsule, white, new Vector3(0.018f, 0.157f, 0.004f), new Vector3(0.022f, 0.032f, 0.014f), new Vector3(0, 0, -10f));
            P(PrimitiveType.Capsule, pink, new Vector3(-0.0168f, 0.155f, -0.0025f), new Vector3(0.011f, 0.024f, 0.006f), new Vector3(0, 0, 14f));
            P(PrimitiveType.Capsule, pink, new Vector3(0.0178f, 0.157f, -0.0025f), new Vector3(0.011f, 0.024f, 0.006f), new Vector3(0, 0, -10f));
            P(PrimitiveType.Sphere, black, new Vector3(-0.014f, 0.108f, -0.034f), new Vector3(0.008f, 0.0095f, 0.006f));
            P(PrimitiveType.Sphere, black, new Vector3(0.014f, 0.108f, -0.034f), new Vector3(0.008f, 0.0095f, 0.006f));
            P(PrimitiveType.Sphere, pink, new Vector3(0, 0.099f, -0.037f), new Vector3(0.006f, 0.0045f, 0.004f));
            P(PrimitiveType.Sphere, pink, new Vector3(-0.024f, 0.097f, -0.029f), new Vector3(0.011f, 0.006f, 0.004f));
            P(PrimitiveType.Sphere, pink, new Vector3(0.024f, 0.097f, -0.029f), new Vector3(0.011f, 0.006f, 0.004f));
            P(PrimitiveType.Sphere, white, new Vector3(-0.022f, 0.009f, -0.032f), new Vector3(0.026f, 0.018f, 0.03f));
            P(PrimitiveType.Sphere, white, new Vector3(0.022f, 0.009f, -0.032f), new Vector3(0.026f, 0.018f, 0.03f));
            P(PrimitiveType.Sphere, white, new Vector3(0, 0.032f, 0.036f), new Vector3(0.024f, 0.024f, 0.024f));                   // tail
            P(PrimitiveType.Cube, red, new Vector3(-0.009f, 0.068f, -0.03f), new Vector3(0.016f, 0.011f, 0.004f), new Vector3(0, 0, 18f));   // ribbon
            P(PrimitiveType.Cube, red, new Vector3(0.009f, 0.068f, -0.03f), new Vector3(0.016f, 0.011f, 0.004f), new Vector3(0, 0, -18f));
            P(PrimitiveType.Sphere, red, new Vector3(0, 0.068f, -0.032f), new Vector3(0.007f, 0.007f, 0.005f));
            return root;
        }
        delegate GameObject PartFn(PrimitiveType t, Material m, Vector3 pos, Vector3 scale, Vector3 euler = default, bool collider = false);
        static void Face(PartFn P, Material eye, Material blush, float y, float z, float sp)
        {
            P(PrimitiveType.Sphere, eye, new Vector3(-sp, y, z), new Vector3(0.008f, 0.0095f, 0.006f));
            P(PrimitiveType.Sphere, eye, new Vector3(sp, y, z), new Vector3(0.008f, 0.0095f, 0.006f));
            P(PrimitiveType.Sphere, blush, new Vector3(-sp - 0.01f, y - 0.011f, z + 0.005f), new Vector3(0.011f, 0.006f, 0.004f));
            P(PrimitiveType.Sphere, blush, new Vector3(sp + 0.01f, y - 0.011f, z + 0.005f), new Vector3(0.011f, 0.006f, 0.004f));
        }
        static void MakeBear(PartFn P, Material fur, Material cream, Material eye, Material red)
        {
            P(PrimitiveType.Sphere, fur, new Vector3(0, 0.044f, 0), new Vector3(0.088f, 0.082f, 0.074f), default, true);            // body
            P(PrimitiveType.Sphere, cream, new Vector3(0, 0.040f, -0.026f), new Vector3(0.05f, 0.05f, 0.03f));                        // tummy
            P(PrimitiveType.Sphere, fur, new Vector3(0, 0.106f, -0.004f), new Vector3(0.082f, 0.072f, 0.07f), default, true);       // head
            P(PrimitiveType.Sphere, fur, new Vector3(-0.031f, 0.138f, 0.002f), new Vector3(0.028f, 0.028f, 0.018f));                  // ears
            P(PrimitiveType.Sphere, fur, new Vector3(0.031f, 0.138f, 0.002f), new Vector3(0.028f, 0.028f, 0.018f));
            P(PrimitiveType.Sphere, cream, new Vector3(-0.031f, 0.138f, -0.004f), new Vector3(0.016f, 0.016f, 0.01f));
            P(PrimitiveType.Sphere, cream, new Vector3(0.031f, 0.138f, -0.004f), new Vector3(0.016f, 0.016f, 0.01f));
            P(PrimitiveType.Sphere, cream, new Vector3(0, 0.097f, -0.036f), new Vector3(0.03f, 0.022f, 0.016f));                      // muzzle
            P(PrimitiveType.Sphere, eye, new Vector3(0, 0.103f, -0.043f), new Vector3(0.009f, 0.0065f, 0.006f));                     // nose
            Face(P, eye, Resources.Load<Material>("Materials/PlushPink"), 0.113f, -0.032f, 0.016f);
            P(PrimitiveType.Sphere, fur, new Vector3(-0.024f, 0.01f, -0.03f), new Vector3(0.028f, 0.02f, 0.032f));                   // feet
            P(PrimitiveType.Sphere, fur, new Vector3(0.024f, 0.01f, -0.03f), new Vector3(0.028f, 0.02f, 0.032f));
            P(PrimitiveType.Cube, red, new Vector3(-0.009f, 0.071f, -0.031f), new Vector3(0.016f, 0.011f, 0.004f), new Vector3(0, 0, 18f));   // bow
            P(PrimitiveType.Cube, red, new Vector3(0.009f, 0.071f, -0.031f), new Vector3(0.016f, 0.011f, 0.004f), new Vector3(0, 0, -18f));
            P(PrimitiveType.Sphere, red, new Vector3(0, 0.071f, -0.033f), new Vector3(0.007f, 0.007f, 0.005f));
        }
        static void MakeCat(PartFn P, Material fur, Material white, Material pink, Material eye, Material red)
        {
            P(PrimitiveType.Sphere, fur, new Vector3(0, 0.042f, 0), new Vector3(0.082f, 0.076f, 0.07f), default, true);             // body
            P(PrimitiveType.Sphere, white, new Vector3(0, 0.038f, -0.026f), new Vector3(0.046f, 0.05f, 0.03f));                       // bib
            P(PrimitiveType.Sphere, fur, new Vector3(0, 0.104f, -0.004f), new Vector3(0.084f, 0.068f, 0.068f), default, true);      // head
            // pointed ears: soft wedges (a rounded triangle with some thickness), the inner ear pink
            Ear(P(PrimitiveType.Cube, fur, new Vector3(-0.026f, 0.136f, 0.0f), new Vector3(0.034f, 0.044f, 0.012f), new Vector3(0, 0, 18f)));
            Ear(P(PrimitiveType.Cube, fur, new Vector3(0.026f, 0.136f, 0.0f), new Vector3(0.034f, 0.044f, 0.012f), new Vector3(0, 0, -18f)));
            Ear(P(PrimitiveType.Cube, pink, new Vector3(-0.0256f, 0.135f, -0.0063f), new Vector3(0.019f, 0.028f, 0.004f), new Vector3(0, 0, 18f)));
            Ear(P(PrimitiveType.Cube, pink, new Vector3(0.0256f, 0.135f, -0.0063f), new Vector3(0.019f, 0.028f, 0.004f), new Vector3(0, 0, -18f)));
            P(PrimitiveType.Sphere, white, new Vector3(-0.009f, 0.095f, -0.034f), new Vector3(0.02f, 0.015f, 0.012f));               // muzzle
            P(PrimitiveType.Sphere, white, new Vector3(0.009f, 0.095f, -0.034f), new Vector3(0.02f, 0.015f, 0.012f));
            P(PrimitiveType.Sphere, pink, new Vector3(0, 0.101f, -0.039f), new Vector3(0.007f, 0.005f, 0.004f));                     // nose
            Face(P, eye, pink, 0.110f, -0.031f, 0.017f);
            P(PrimitiveType.Capsule, fur, new Vector3(0.036f, 0.03f, 0.03f), new Vector3(0.014f, 0.034f, 0.014f), new Vector3(30f, 0, -40f));  // tail
            P(PrimitiveType.Sphere, white, new Vector3(-0.022f, 0.009f, -0.032f), new Vector3(0.024f, 0.017f, 0.028f));              // paws
            P(PrimitiveType.Sphere, white, new Vector3(0.022f, 0.009f, -0.032f), new Vector3(0.024f, 0.017f, 0.028f));
            P(PrimitiveType.Cylinder, red, new Vector3(0, 0.072f, -0.002f), new Vector3(0.062f, 0.0025f, 0.06f));                    // collar
            P(PrimitiveType.Sphere, Resources.Load<Material>("Materials/PlushYellow") ?? red, new Vector3(0, 0.066f, -0.031f), new Vector3(0.008f, 0.008f, 0.008f));   // bell
        }
        static Mesh earMesh;
        static void Ear(GameObject g)
        {
            if (!earMesh)
            {
                // a wedge: a triangle (base -0.5..0.5 at y -0.5, tip at y 0.5), z -0.5..0.5, its tip rounded off a little
                var v = new List<Vector3>(); var tri = new List<int>();
                Vector3[] f = { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(0.12f, 0.42f, 0), new Vector3(0f, 0.5f, 0), new Vector3(-0.12f, 0.42f, 0) };
                void AddFace(float z, bool flip) { int o = v.Count; foreach (var q in f) v.Add(new Vector3(q.x, q.y, z)); for (int i = 1; i + 1 < f.Length; i++) { if (flip) { tri.Add(o); tri.Add(o + i + 1); tri.Add(o + i); } else { tri.Add(o); tri.Add(o + i); tri.Add(o + i + 1); } } }
                AddFace(-0.5f, true); AddFace(0.5f, false);
                for (int i = 0; i < f.Length; i++)
                {
                    int j = (i + 1) % f.Length, o = v.Count;
                    v.Add(new Vector3(f[i].x, f[i].y, -0.5f)); v.Add(new Vector3(f[j].x, f[j].y, -0.5f)); v.Add(new Vector3(f[j].x, f[j].y, 0.5f)); v.Add(new Vector3(f[i].x, f[i].y, 0.5f));
                    tri.Add(o); tri.Add(o + 2); tri.Add(o + 1); tri.Add(o); tri.Add(o + 3); tri.Add(o + 2);
                }
                earMesh = new Mesh { name = "plush_ear" }; earMesh.SetVertices(v); earMesh.SetTriangles(tri, 0); earMesh.RecalculateNormals(); earMesh.RecalculateBounds();
            }
            g.GetComponent<MeshFilter>().sharedMesh = earMesh;
        }
        static void MakeChick(PartFn P, Material yellow, Material orange, Material eye, Material pink)
        {
            P(PrimitiveType.Sphere, yellow, new Vector3(0, 0.05f, 0), new Vector3(0.092f, 0.092f, 0.084f), default, true);          // round body-head
            P(PrimitiveType.Sphere, yellow, new Vector3(-0.044f, 0.045f, 0.002f), new Vector3(0.016f, 0.036f, 0.034f), new Vector3(0, 0, -20f));   // wings
            P(PrimitiveType.Sphere, yellow, new Vector3(0.044f, 0.045f, 0.002f), new Vector3(0.016f, 0.036f, 0.034f), new Vector3(0, 0, 20f));
            P(PrimitiveType.Cube, orange, new Vector3(0, 0.058f, -0.043f), new Vector3(0.012f, 0.012f, 0.012f), new Vector3(0, 0, 45f));   // beak
            Face(P, eye, pink, 0.07f, -0.037f, 0.018f);
            P(PrimitiveType.Sphere, yellow, new Vector3(-0.004f, 0.1f, 0.0f), new Vector3(0.012f, 0.02f, 0.012f), new Vector3(0, 0, 20f));   // tuft
            P(PrimitiveType.Sphere, yellow, new Vector3(0.005f, 0.101f, 0.0f), new Vector3(0.01f, 0.018f, 0.01f), new Vector3(0, 0, -25f));
            P(PrimitiveType.Sphere, orange, new Vector3(-0.018f, 0.005f, -0.024f), new Vector3(0.018f, 0.008f, 0.024f));             // feet
            P(PrimitiveType.Sphere, orange, new Vector3(0.018f, 0.005f, -0.024f), new Vector3(0.018f, 0.008f, 0.024f));
        }

        // ------------------------------------------------------------------ every frame
        void Update()
        {
            Fps = Mathf.Lerp(Fps, 1f / Mathf.Max(Time.unscaledDeltaTime, 1e-4f), 0.05f);
            // stats from the running simulation
            if (sim != null)
            {
                foreach (var p in sim.pulls) if (p.state == Pull.State.Held) { save.maxTension = Mathf.Max(save.maxTension, Mathf.Min(p.tension, 1f)); heldTension = p.tension; }
                int holes = 0;
                foreach (var d in sim.damage.Values) { holes += d.holes.Count; foreach (var r in d.runs) { float len = r.hi - r.lo; if (len > save.longest) save.longest = len; if (len >= 0.30f) Unlock("ladder30"); } }
                if (holes >= 10) Unlock("holes10");
            }
            if (SheerStudio.I && SheerStudio.I.Capture) return;
            if (Minimal) { if (canvas) SheerKit.SetScale(canvas, SheerKit.UiScale()); Toasts(); return; }
            // the mascot: bob, blink, hop, shock
            if (mascotRoot && mascotOn)
            {
                hopV -= 1400f * Time.unscaledDeltaTime; hop = Mathf.Max(0f, hop + hopV * Time.unscaledDeltaTime); if (hop <= 0f && hopV < 0f) hopV = 0f;
                float bob = Mathf.Sin(Time.unscaledTime * 2.2f) * 2.5f;
                // (with music on she bops on the beat)
                if (sim != null && sim.motion.bpm > 1f)
                {
                    double bt = sim.motion.beatTime * (sim.motion.bpm > 115f ? sim.motion.bpm * 0.5f : sim.motion.bpm) / 60.0;
                    float ph = (float)(bt - Math.Floor(bt)); bob = Mathf.Pow(1f - ph, 4f) * 8f;
                    long bar = (long)Math.Floor(bt / 4.0);                       // a note floats up every four beats
                    if (bar != lastBar) { if (lastBar >= 0) Float(bar % 2 == 0 ? "♪" : "♫", null, new Color32(150, 110, 200, 255), 20f, new Vector2(-34f, 0f), 1.8f); lastBar = bar; }
                }
                else lastBar = -1;
                mascotRoot.anchoredPosition = new Vector2(110, 210 + bob + hop);
                mascotRoot.localScale = new Vector3(1f + 0.03f * Mathf.Sin(Time.unscaledTime * 4.4f), 1f - 0.03f * Mathf.Sin(Time.unscaledTime * 4.4f), 1f);
                float eyeH = 13f;
                if (Time.unscaledTime > blinkAt) { eyeH = 2f; if (Time.unscaledTime > blinkAt + 0.12f) blinkAt = Time.unscaledTime + UnityEngine.Random.Range(2.5f, 6f); }
                shock = Mathf.MoveTowards(shock, 0f, Time.unscaledDeltaTime * 0.8f);
                float big = 1f + 0.5f * shock;
                eyeL.rectTransform.sizeDelta = new Vector2(11 * big, eyeH * big); eyeR.rectTransform.sizeDelta = new Vector2(11 * big, eyeH * big);
                mouth.text = shock > 0.3f ? "o" : heldTension > 0.6f ? "～" : "ω";
                bool tense = heldTension > 0.75f && sim != null && sim.pulls.Exists(p => p.state == Pull.State.Held);
                if (tense && !tensionLine) { Say("It's stretching...!|のびてる…！", 2f); tensionLine = true; }
                if (!tense) tensionLine = false;
                heldTension = 0f;
                if (bubble && bubble.gameObject.activeSelf && Time.unscaledTime > bubbleUntil) bubble.gameObject.SetActive(false);
                if (Time.unscaledTime > nextTip) { nextTip = Time.unscaledTime + UnityEngine.Random.Range(35f, 60f); if (!bubble.gameObject.activeSelf) Say(Tips[UnityEngine.Random.Range(0, Tips.Length)], 4f); }
            }
            UpdateFloaters();
            // the skirt's wind carries the petals and the ribbon too
            if (!skirtC) skirtC = FindAnyObjectByType<SkirtCloth>();
            float wind = skirtC ? skirtC.WindLevel * (skirtC.windAmplitude > 0f ? 1f : 0f) : 0f;
            if (petals && petals.gameObject.activeInHierarchy)
            {
                var fo = petals.forceOverLifetime; fo.enabled = true; fo.space = ParticleSystemSimulationSpace.World;
                fo.x = new ParticleSystem.MinMaxCurve(0.05f * wind, 0.11f * wind); fo.y = new ParticleSystem.MinMaxCurve(0.0f, 0.04f * wind); fo.z = new ParticleSystem.MinMaxCurve(-0.03f * wind, 0.02f * wind);
                var nz = petals.noise; nz.strength = 0.08f + 0.10f * wind;
            }
            if (ribbon) ribbon.wind = wind;
            // the tension gauge by the cursor
            if (gaugeRoot)
            {
                float tens = 0f; bool held = false;
                if (sim != null) foreach (var p in sim.pulls) if (p.state == Pull.State.Held) { held = true; tens = Mathf.Max(tens, p.tension); }
                bool on = held && visible && SheerStudio.I && SheerStudio.I.look.gauge;
                gaugeShown = Mathf.MoveTowards(gaugeShown, on ? 1f : 0f, Time.unscaledDeltaTime * (on ? 8f : 4f));
                gaugeRoot.gameObject.SetActive(gaugeShown > 0.01f);
                if (gaugeShown > 0.01f)
                {
                    float sc = canvas.scaleFactor > 0f ? canvas.scaleFactor : 1f;
                    gaugeRoot.anchoredPosition = (GaugeAt ?? (Vector2)Input.mousePosition) / sc + new Vector2(34f, 30f);
                    float k = Mathf.Clamp01(tens);
                    gauge.fillAmount = k;
                    var c = k < 0.5f ? Color.Lerp(SheerKit.Mint, SheerKit.Lemon, k / 0.5f) : Color.Lerp(SheerKit.Lemon, SheerKit.PinkDeep, (k - 0.5f) / 0.5f);
                    c.a = gaugeShown; gauge.color = c;
                    var hc = gaugeHeart.color; hc.a = gaugeShown; gaugeHeart.color = hc;
                    float shake = k > 0.85f ? (k - 0.85f) / 0.15f : 0f;
                    gaugeHeart.rectTransform.anchoredPosition = new Vector2(Mathf.Sin(Time.unscaledTime * 60f) * 2.2f * shake, Mathf.Cos(Time.unscaledTime * 47f) * 1.6f * shake);
                    gaugeRoot.localScale = Vector3.one * (0.7f + 0.3f * gaugeShown);
                }
            }
            Toasts();
            // the plushie: click it
            if (plush && plush.activeSelf)
            {
                if (Input.GetMouseButtonDown(0) && Camera.main && !(UnityEngine.EventSystems.EventSystem.current && UnityEngine.EventSystems.EventSystem.current.IsPointerOverGameObject()))
                {
                    var ray = Camera.main.ScreenPointToRay(Input.mousePosition * SheerSuperSample.Scale);
                    if (Physics.Raycast(ray, out var hit, 10f) && hit.transform.IsChildOf(plush.transform))
                    {
                        plushSquash = 1f; plushClicks++; SheerAudio.Fx("squeak", 0.8f, UnityEngine.Random.Range(0.9f, 1.2f));
                        MetFriend(Mathf.Max(plushKind, 0));
                        if (plushClicks % 10 == 0) { plushSpin = 1f; Unlock("plush"); Say("So dizzy @_@|目が回る～"); }
                        else if (UnityEngine.Random.value < 0.4f) Say(PlushHello[Mathf.Clamp(plushKind, 0, PlushHello.Length - 1)]);
                    }
                }
                plushSquash = Mathf.MoveTowards(plushSquash, 0f, Time.unscaledDeltaTime * 3f);
                plushSpin = Mathf.MoveTowards(plushSpin, 0f, Time.unscaledDeltaTime * 0.7f);
                float sq = Mathf.Sin(plushSquash * Mathf.PI * 3f) * plushSquash * 0.18f;
                plush.transform.localScale = new Vector3(1f + sq, 1f - sq, 1f + sq);
                plush.transform.rotation = Quaternion.Euler(0f, 24f + (1f - plushSpin) * 0f + Mathf.SmoothStep(0f, 720f, 1f - plushSpin) * (plushSpin > 0f ? 1f : 0f), 0f);
            }
            // secrets typed on the keyboard
            if (SheerStudio.Typing) return;                         // (typing in a field)
            foreach (char ch in Input.inputString)
            {
                if (char.IsLetter(ch)) typed = (typed + char.ToLowerInvariant(ch));
                if (typed.Length > 12) typed = typed.Substring(typed.Length - 12);
                if (typed.EndsWith("uwu")) { uwuMode = !uwuMode; typed = ""; Unlock("uwu"); Say(uwuMode ? "uwu mode ON~!|うゅ～" : "Back to normal!|もどったよ"); }
                if (typed.EndsWith("kawaii")) { typed = ""; if (SheerStudio.I) { var L = SheerStudio.I.look; L.petals = true; L.wind = 1.6f; SheerStudio.I.ApplyScene(); SheerStudio.I.RefreshPanel(); SheerStudio.I.Changed(); } Say("Sakura storm!|桜吹雪！"); }
                for (int k = 0; k < PlushWords.Length; k++)
                    if (typed.EndsWith(PlushWords[k]))
                    {
                        typed = "";
                        if (SheerStudio.I) { var L = SheerStudio.I.look; L.plushie = true; L.plushKind = k; SheerStudio.I.ApplyScene(); SheerStudio.I.RefreshPanel(); SheerStudio.I.Changed(); }
                        SheerAudio.Fx("pop"); Say(PlushHello[k]); MetFriend(k);
                    }
            }
            if (Input.anyKeyDown)
            {
                if (Input.GetKeyDown(Konami[konami])) { konami++; if (konami == Konami.Length) { konami = 0; MagicalGirl(); } }
                else if (!Input.GetKeyDown(KeyCode.Mouse0) && !Input.GetKeyDown(KeyCode.Mouse1)) konami = Input.GetKeyDown(Konami[0]) ? 1 : 0;
            }
        }

        void Toasts()
        {
            if (toastCard)
            {
                if (toastT < 0f && toasts.Count > 0) { toastText.text = toasts.Dequeue(); toastT = 0f; toastCard.gameObject.SetActive(true); }
                if (toastT >= 0f)
                {
                    toastT += Time.unscaledDeltaTime;
                    float a = Mathf.Clamp01(toastT / 0.25f), b = Mathf.Clamp01((3.0f - toastT) / 0.3f), e = Mathf.Min(a, b);
                    toastCard.anchoredPosition = new Vector2(0, Mathf.Lerp(80f, -18f, e * e * (3f - 2f * e)));
                    if (toastT > 3.0f) { toastT = -1f; toastCard.gameObject.SetActive(false); }
                }
            }
            // (the card as wide as its line)
            if (toastCard && toastText && toastCard.gameObject.activeSelf) toastCard.sizeDelta = new Vector2(Mathf.Clamp(toastText.preferredWidth + 48f, 200f, 900f), 44f);
        }

        void MagicalGirl()
        {
            Unlock("magical");
            if (SheerStudio.I)
            {
                var L = SheerStudio.I.look;
                L.finish = 4; L.color = new Color(0.98f, 0.72f, 0.86f); L.pattern = 4; L.patternColor = new Color(1f, 0.96f, 0.98f); L.style = 2; L.lace = true;
                L.skirtStyle = 1; L.skirtOwnColor = true; L.skirtColor = new Color(0.95f, 0.70f, 0.80f); L.skirtAccent = Color.white;
                L.backdrop = 3; L.lightPreset = 6; L.petals = true; L.motion = 4;
                SheerStudio.I.ApplyAll(true); SheerStudio.I.Changed();
            }
            SheerAudio.Fx("sparkle"); SheerAudio.Fx("achievement");
            Toast("✧ Sparkle transformation! ✧  <size=12>キラキラ変身！</size>");
            Say("Bunny sparkle, transform!|うさぎキラキラ、へんしん！", 4f);
        }
    }
}
