// SHEER — the player's LOOK: everything the Studio panel customises - stockings, skirt, body, scene, light, music, camera,
// the pro / debug settings. Plain data (JsonUtility); saved next to the player's data (Application.persistentDataPath:
// sheer_look.json, and three slots), with named presets. Defaults = the calibrated original look (the video's).
using System;
using System.IO;
using UnityEngine;

namespace Sheer
{
    /// The material inspector's values (TensionData, the original's panel) as part of a look: saved, copied, undone with it.
    /// set = false: the look leaves them to the fabric (denier / finish) and the video's values.
    [Serializable]
    public class TensionValues
    {
        public bool set;
        public float normalStrength = 1f, weaveNormalStrength = 0.845f, weaveContrast = 0.025f, wrinkleStrength = 9f, tensionNormalBoost = 1.5f;
        public int weaveTiling = 12, tensionMode;
        public float pearlStrength = 0.387f, pearlGrainScale = 572f, pearlRandomness = 0.435f, pearlSpecularStrength = 0.64f, pearlEdgeStrength = 0.128f,
                     pearlEdgeStart, pearlEdgeWidthPower = 0.54f, pearlPullEdgeWidth = 0.0122f, pearlGlintStrength = 0.85f, pearlGlintDensity = 0.117f;
        public float frostBodyCoverage = 0.829f, frostFootCoverage = 0.889f, frostClearAtStretch = 1f, frostMatteSmoothness = 0.837f,
                     frostBoundaryStrength = 1f, frostBoundaryWidthPx = 5.9f;

        public void From(TensionData t)
        {
            set = true;
            normalStrength = t.normalStrength; weaveNormalStrength = t.weaveNormalStrength; weaveContrast = t.weaveContrast; wrinkleStrength = t.wrinkleStrength;
            tensionNormalBoost = t.tensionNormalBoost; weaveTiling = t.weaveTiling; tensionMode = (int)t.tensionMode;
            pearlStrength = t.pearlStrength; pearlGrainScale = t.pearlGrainScale; pearlRandomness = t.pearlRandomness; pearlSpecularStrength = t.pearlSpecularStrength;
            pearlEdgeStrength = t.pearlEdgeStrength; pearlEdgeStart = t.pearlEdgeStart; pearlEdgeWidthPower = t.pearlEdgeWidthPower; pearlPullEdgeWidth = t.pearlPullEdgeWidth;
            pearlGlintStrength = t.pearlGlintStrength; pearlGlintDensity = t.pearlGlintDensity;
            frostBodyCoverage = t.frostBodyCoverage; frostFootCoverage = t.frostFootCoverage; frostClearAtStretch = t.frostClearAtStretch;
            frostMatteSmoothness = t.frostMatteSmoothness; frostBoundaryStrength = t.frostBoundaryStrength; frostBoundaryWidthPx = t.frostBoundaryWidthPx;
        }
        public void To(TensionData t)
        {
            float C(float v, float a, float b) => float.IsNaN(v) ? a : Mathf.Clamp(v, a, b);
            t.normalStrength = C(normalStrength, 0f, 1.6f); t.weaveNormalStrength = C(weaveNormalStrength, 0f, 1f); t.weaveContrast = C(weaveContrast, 0f, 1f);
            t.wrinkleStrength = C(wrinkleStrength, -100f, 100f); t.tensionNormalBoost = C(tensionNormalBoost, 0f, 4f); t.weaveTiling = Mathf.Clamp(weaveTiling, 1, 256);
            t.tensionMode = (TensionMode)Mathf.Clamp(tensionMode, 0, 2);
            t.pearlStrength = C(pearlStrength, 0f, 1f); t.pearlGrainScale = C(pearlGrainScale, 0f, 1000f); t.pearlRandomness = C(pearlRandomness, 0f, 1f);
            t.pearlSpecularStrength = C(pearlSpecularStrength, 0f, 4f); t.pearlEdgeStrength = C(pearlEdgeStrength, 0f, 1f); t.pearlEdgeStart = C(pearlEdgeStart, 0f, 1f);
            t.pearlEdgeWidthPower = C(pearlEdgeWidthPower, 0f, 5f); t.pearlPullEdgeWidth = C(pearlPullEdgeWidth, 0.001f, 0.04f); t.pearlGlintStrength = C(pearlGlintStrength, 0f, 16f);
            t.pearlGlintDensity = C(pearlGlintDensity, 0f, 1f);
            t.frostBodyCoverage = C(frostBodyCoverage, 0f, 1f); t.frostFootCoverage = C(frostFootCoverage, 0f, 1f); t.frostClearAtStretch = C(frostClearAtStretch, 0f, 1f);
            t.frostMatteSmoothness = C(frostMatteSmoothness, 0f, 1f); t.frostBoundaryStrength = C(frostBoundaryStrength, 0f, 1f); t.frostBoundaryWidthPx = C(frostBoundaryWidthPx, 0f, 32f);
        }
    }

    [Serializable]
    public class SheerLook
    {
        public TensionValues tension = new TensionValues();
        // ---- stockings
        public int style;                       // 0 pantyhose, 1 thigh-high, 2 over-knee, 3 knee-high, 4 ankle socks
        public float denier = 20f;              // 5 .. 120 (sheerness, and how much pull the yarn takes before it tears)
        public Color color = DefaultYarn;       // the yarn (sRGB)
        public int finish = 1;                  // 0 matte, 1 natural, 2 satin, 3 glossy (wet look), 4 glitter
        public int pattern;                     // 0 plain, 1 back seam, 2 fishnet, 3 polka dots, 4 hearts, 5 stripes, 6 argyle
        public Color patternColor = new Color(0.95f, 0.55f, 0.72f);
        public float patternScale = 1f;
        public bool seamAlways;                 // a back seam with any pattern
        public bool lace = true;                // lace edge on the welt of thigh-highs / over-knees
        public Color weltColor = DefaultYarn;
        public bool weltOwnColor;
        public float fishnetSheer = 0f;         // sheer knit kept under a fishnet
        public float strength = 1f;             // fabric strength (x the tear threshold)
        public float runTendency = 1f;          // how far ladders run
        public float holeSize = 1f;

        // ---- skirt
        public int skirtStyle;                  // 0 plain, 1 sailor stripes, 2 tartan, 3 pinstripe, 4 gingham
        public Color skirtColor = DefaultSkirt, skirtAccent = new Color(0.93f, 0.93f, 0.95f), skirtAccent2 = new Color(0.12f, 0.30f, 0.18f);
        public bool skirtOwnColor;              // false: the calibrated charcoal
        public float skirtPatternScale = 1f;

        // ---- body
        public int skinTone;                    // presets (SkinTones); -1 = custom
        public Color skinCustom = new Color(1f, 0.86f, 0.80f);
        public int legShape;                    // 0 default, 1 slender, 2 athletic, 3 curvy, 4 petite (TightsSim.ShapeNames)
        public bool polish;                     // painted toenails (seen through the stockings)
        public Color polishColor = new Color(0.72f, 0.04f, 0.10f);
        public bool sandalToe;                  // no reinforced toe: sheer to the tips (the nails show)
        public int motion;                      // 0 natural, 1 shy, 2 model (one leg), 3 restless, 4 vibe (sways to the music), 5 still
        public float motionAmount = 1f;
        public bool toeLifts = true;

        // ---- scene
        public int backdrop;                    // 0 studio blue (original), 1 sakura dusk, 2 night city, 3 pastel dream, 4 shoji,
                                                // 5 gym, 6 starry night, 7 two colours
        public Color backTop = new Color(0.98f, 0.80f, 0.88f), backBottom = new Color(0.62f, 0.72f, 0.98f);
        public float backBrightness = 1f;
        public int floor;                       // 0 drop cloth (original), 1 oak boards, 2 tatami, 3 gym mat, 4 fluffy rug, 5 marble,
                                                // 6 meadow, 7 stage
        public Color floorTint = new Color(0.06f, 0.16f, 0.42f);
        public bool floorOwnColor;
        public bool petals;                     // sakura petals in the air
        public bool plushie;                    // the bunny on the floor (parked)
        public bool ribbon;                     // a rhythmic-gymnastics ribbon dancing beside her (SheerRibbon)
        public bool windOn = true;
        public float wind = 1f;                 // strength of the air
        public float gusts = 1f;

        // ---- light
        public int lightPreset;                 // 0 studio (original), 1 golden hour, 2 moonlight, 3 neon, 4 soft window, 5 spotlight, 6 sakura
        public float exposure;                  // EV
        public float keyIntensity = 1f, fillIntensity = 1f, rimIntensity = 1f;
        public float keyYaw, keyPitch;          // deg: the key light moved round the character
        public float warmth;                     // -1 cool .. 1 warm
        public Color rimColor = new Color(0f, 0.92f, 1f);
        public bool rimOwnColor;

        // ---- music / sound
        public int track;                       // 0 .. n-1; -1 = silence
        public float musicVolume = 0.55f, sfxVolume = 0.8f;
        public bool musicOn = true;

        // ---- camera
        public bool dof;                        // depth of field (bokeh)
        public bool turntable;                  // the camera sweeps slowly round her (CameraRig.Turntable)
        public int filter;                      // camera filter (Filters): post-processing looks for photos
        public float aperture = 2.8f;

        // ---- pro
        public int debugView;                   // 0 final, 1 tension, 2 wales / courses, 3 ladder fields, 4 opacity, 5 holes
        public bool lattice;                    // simulation lattice overlay
        public bool perfHud;
        public bool gauge;                      // the tension gauge at the cursor while pulling (SheerFun; parked)
        public int plushKind;                   // 0 Usagi, 1 Kuma, 2 Neko, 3 Piyo (SheerFun.PlushNames)
        public int photoFrame;                  // 0 none, 1 instant photo, 2 sakura, 3 film strip (PhotoFrames)
        [NonSerialized] public float timeScale = 1f;    // (a session's: not saved, copied or undone - a saved pause opened the game frozen)
        public bool mascot;                     // (parked)

        public static readonly Color DefaultYarn = new Color(0.27f, 0.247f, 0.265f);   // = the calibrated worn yarn (_FrostColor 0.06, 0.05, 0.058 linear)
        public static readonly Color DefaultSkirt = new Color(0.16f, 0.165f, 0.19f);

        public SheerLook Clone() => JsonUtility.FromJson<SheerLook>(JsonUtility.ToJson(this));

        // ------------------------------------------------------------------ tables shown in the panel
        public static readonly string[] Styles = { "Pantyhose|パンスト", "Thigh-high|ニーハイ上", "Over-knee|オーバーニー", "Knee-high|ハイソックス", "Ankle|アンクル" };
        /// top of the stocking (rest height m) per style; >= 1 = to the waist
        public static readonly float[] StyleTop = { 1f, 0.615f, 0.565f, 0.405f, 0.165f };
        public static readonly string[] Finishes = { "Matte|マット", "Natural|ナチュラル", "Satin|サテン", "Glossy|ツヤ", "Glitter|キラキラ" };
        public static readonly string[] Patterns = { "Plain|無地", "Back seam|バックシーム", "Fishnet|網タイツ", "Polka dots|水玉", "Hearts|ハート", "Stripes|しましま", "Argyle|アーガイル" };
        public static readonly string[] SkirtStyles = { "Plain|無地", "Sailor|セーラー", "Tartan|タータン", "Pinstripe|ピンストライプ", "Gingham|ギンガム" };
        public static readonly string[] Motions = { "Natural|ふつう", "Shy|もじもじ", "Model|モデル立ち", "Restless|そわそわ", "Vibe ♪|ノリノリ", "Still|静止", "Happy feet|ぴょこぴょこ", "Ballet|バレエ" };
        public static readonly string[] Filters = { "None|なし", "Dreamy|ゆめかわ", "Film|フィルム", "Mono|モノクロ", "Pastel|パステル", "Vivid|ビビッド", "VHS|ビデオ" };
        public static readonly string[] PhotoFrames = { "None|なし", "Instant|インスタント", "Sakura|さくら", "Film|フィルム" };
        public static readonly string[] Backdrops = { "Studio|スタジオ", "Sakura dusk|夕桜", "Night city|夜の街", "Pastel dream|パステル", "Shoji|障子", "Gym|体育館", "Starry night|星空", "Two colours|グラデ" };
        public static readonly string[] Floors = { "Drop cloth|布", "Oak boards|フローリング", "Tatami|畳", "Gym mat|マット", "Fluffy rug|ラグ", "Marble|大理石", "Meadow|草原", "Stage|ステージ" };
        public static readonly string[] Lights = { "Studio|スタジオ", "Golden hour|夕暮れ", "Moonlight|月光", "Neon|ネオン", "Soft window|窓辺", "Spotlight|スポット", "Sakura|さくら" };
        public static readonly string[] DebugViews = { "Final|完成", "Tension|張力", "Wales & courses|編み目", "Ladder fields|伝線場", "Opacity|不透明度", "Holes SDF|穴SDF", "Cloth lattice|格子" };

        /// THE MINIMAL SIMULATOR's choices (user, 2026-11-17): the stocking's colours and its thickness range (denier)
        public static readonly Color[] YarnMinimal =
        {
            DefaultYarn, new Color(0.02f, 0.02f, 0.025f), new Color(0.80f, 0.60f, 0.48f), new Color(0.55f, 0.40f, 0.32f), new Color(0.94f, 0.94f, 0.96f),
            new Color(0.10f, 0.13f, 0.32f), new Color(0.55f, 0.06f, 0.10f),
        };
        public const float DenierMin = 8f, DenierMax = 80f;
        /// -sheerFullLooks: looks from a file keep every field (development: the parked looks of the Studio)
        public static readonly bool Full = Array.IndexOf(Environment.GetCommandLineArgs(), "-sheerFullLooks") >= 0;

        public static readonly Color[] YarnSwatches =
        {
            DefaultYarn, new Color(0.02f, 0.02f, 0.025f), new Color(0.80f, 0.60f, 0.48f), new Color(0.55f, 0.40f, 0.32f), new Color(0.94f, 0.94f, 0.96f),
            new Color(0.95f, 0.62f, 0.74f), new Color(0.72f, 0.62f, 0.92f), new Color(0.10f, 0.13f, 0.32f), new Color(0.55f, 0.06f, 0.10f),
            new Color(0.45f, 0.45f, 0.48f), new Color(0.55f, 0.85f, 0.78f), new Color(0.98f, 0.85f, 0.45f),
        };
        public static readonly string[] SkinTones = { "Original|オリジナル", "Porcelain|色白", "Peach|ピーチ", "Tan|小麦", "Olive|オリーブ", "Brown|褐色", "Deep|ダーク" };
        // multipliers of the calibrated (original's) linear albedo (0.95, 0.46, 0.44), aimed at measured skin albedos
        // (linear, approx.): porcelain (0.95, 0.51, 0.48), peach (0.88, 0.47, 0.36), tan (0.55, 0.32, 0.20), olive (0.50,
        // 0.33, 0.18), brown (0.28, 0.14, 0.08), deep (0.12, 0.06, 0.035) - the old ones (applied in linear space) left
        // 'Deep' a light salmon once the skin's red scattering was added
        public static readonly Color[] SkinToneMul =
        {
            new Color(1f, 1f, 1f), new Color(1.0f, 1.10f, 1.10f), new Color(0.93f, 1.02f, 0.82f), new Color(0.58f, 0.70f, 0.45f),
            new Color(0.53f, 0.72f, 0.41f), new Color(0.29f, 0.30f, 0.18f), new Color(0.126f, 0.13f, 0.08f),
        };
        public static readonly Color[] SkirtSwatches =
        {
            DefaultSkirt, new Color(0.08f, 0.11f, 0.24f), new Color(0.03f, 0.03f, 0.035f), new Color(0.55f, 0.08f, 0.12f), new Color(0.95f, 0.70f, 0.80f),
            new Color(0.93f, 0.93f, 0.95f), new Color(0.25f, 0.42f, 0.30f), new Color(0.62f, 0.50f, 0.78f), new Color(0.82f, 0.68f, 0.45f),
        };

        // ------------------------------------------------------------------ presets
        public static readonly string[] PresetNames = { "Original|原作", "Sailor|セーラー服", "Gymnast|新体操", "Sakura|桜", "Night out|夜遊び", "Sweet|スイート", "Zettai ryōiki|絶対領域", "Retro|レトロ", "Ballerina|バレリーナ", "Idol|アイドル" };
        public static SheerLook Preset(int i)
        {
            var L = new SheerLook();
            switch (i)
            {
                case 1:   // the original's sailor skirt, black over-knees
                    L.skirtStyle = 1; L.skirtOwnColor = true; L.skirtColor = new Color(0.07f, 0.09f, 0.20f); L.style = 2; L.denier = 60f;
                    L.color = new Color(0.03f, 0.03f, 0.035f); L.backdrop = 4; L.floor = 2; L.lightPreset = 4; L.track = 0; break;
                case 2:   // gymnast: nude sheer, a gym, a blue mat
                    L.legShape = 2; L.ribbon = true; L.color = new Color(0.80f, 0.60f, 0.48f); L.denier = 12f; L.finish = 2; L.backdrop = 5; L.floor = 3; L.motion = 2;
                    L.skirtOwnColor = true; L.skirtColor = new Color(0.08f, 0.11f, 0.24f); L.lightPreset = 4; L.track = 1; break;
                case 3:   // sakura: pink sheer, petals
                    L.color = new Color(0.95f, 0.62f, 0.74f); L.denier = 15f; L.backdrop = 1; L.floor = 4; L.petals = true; L.lightPreset = 6;
                    L.skirtOwnColor = true; L.skirtColor = new Color(0.93f, 0.93f, 0.95f); L.track = 5; break;
                case 4:   // night out: black fishnets, neon, the city
                    L.pattern = 2; L.color = new Color(0.02f, 0.02f, 0.025f); L.finish = 2; L.fishnetSheer = 0.35f; L.backdrop = 2; L.floor = 7;
                    L.lightPreset = 3; L.skirtOwnColor = true; L.skirtColor = new Color(0.03f, 0.03f, 0.035f); L.track = 4; L.motion = 4; break;
                case 5:   // sweet: white with pink hearts, pastel, a music box
                    L.color = new Color(0.94f, 0.94f, 0.96f); L.pattern = 4; L.patternColor = new Color(0.95f, 0.55f, 0.72f); L.denier = 30f;
                    L.style = 2; L.backdrop = 3; L.floor = 4; L.skirtStyle = 4; L.skirtOwnColor = true; L.skirtColor = new Color(0.95f, 0.70f, 0.80f);
                    L.skirtAccent = new Color(0.98f, 0.96f, 0.98f); L.lightPreset = 6; L.track = 3; L.motion = 1; break;
                case 6:   // zettai ryouiki: black thigh-highs under a tartan
                    L.style = 1; L.denier = 80f; L.color = new Color(0.03f, 0.03f, 0.035f); L.skirtStyle = 2; L.skirtOwnColor = true;
                    L.skirtColor = new Color(0.45f, 0.06f, 0.09f); L.skirtAccent = new Color(0.95f, 0.85f, 0.55f); L.skirtAccent2 = new Color(0.05f, 0.06f, 0.15f);
                    L.backdrop = 6; L.floor = 1; L.lightPreset = 2; L.track = 2; L.motion = 1; break;
                case 7:   // retro: seamed nude stockings, marble, golden hour, city pop
                    L.pattern = 1; L.color = new Color(0.66f, 0.47f, 0.37f); L.denier = 15f; L.finish = 2; L.style = 1; L.backdrop = 7;
                    L.backTop = new Color(0.98f, 0.78f, 0.55f); L.backBottom = new Color(0.55f, 0.32f, 0.42f); L.floor = 5; L.lightPreset = 1;
                    L.skirtOwnColor = true; L.skirtColor = new Color(0.55f, 0.08f, 0.12f); L.track = 4; L.motion = 2; break;
                case 8:   // ballerina: pale pink sheer, sandal toe, pink polish, ballet poise, a music box, soft window light
                    L.color = new Color(0.98f, 0.80f, 0.84f); L.denier = 10f; L.finish = 3; L.sandalToe = true; L.polish = true; L.polishColor = new Color(0.98f, 0.42f, 0.62f);
                    L.motion = 7; L.backdrop = 3; L.floor = 1; L.lightPreset = 4; L.track = 3; L.legShape = 1; L.filter = 1;
                    L.skirtOwnColor = true; L.skirtColor = new Color(0.98f, 0.86f, 0.90f); L.plushie = true; L.plushKind = 0; break;
                case 9:   // idol: white over-knees with lace, a stage, a spotlight, future bass, happy feet
                    L.style = 2; L.lace = true; L.color = new Color(0.97f, 0.97f, 0.98f); L.denier = 40f; L.finish = 3; L.pattern = 4; L.patternColor = new Color(0.98f, 0.42f, 0.62f);
                    L.patternScale = 0.8f; L.backdrop = 2; L.floor = 7; L.lightPreset = 5; L.track = 1; L.motion = 6; L.filter = 5;
                    L.skirtStyle = 4; L.skirtOwnColor = true; L.skirtColor = new Color(0.95f, 0.45f, 0.65f); L.skirtAccent = Color.white; L.petals = true; break;
            }
            return L;
        }

        // ------------------------------------------------------------------ persistence
        public static string Dir => Application.persistentDataPath;
        public static string SlotPath(int slot) => Path.Combine(Dir, slot <= 0 ? "sheer_look.json" : $"sheer_look_{slot}.json");
        public void Save(int slot = 0)
        {
            try { Directory.CreateDirectory(Dir); File.WriteAllText(SlotPath(slot), JsonUtility.ToJson(this, true)); }
            catch (Exception e) { Debug.LogWarning("[look] could not save: " + e.Message); }
        }
        public static SheerLook Load(int slot = 0)
        {
            try { var p = SlotPath(slot); if (File.Exists(p)) return Sanitize(JsonUtility.FromJson<SheerLook>(File.ReadAllText(p))); }
            catch (Exception e) { Debug.LogWarning("[look] could not load: " + e.Message); }
            return null;
        }
        public static SheerLook FromJson(string json)
        {
            try { return Sanitize(JsonUtility.FromJson<SheerLook>(json)); } catch { return null; }
        }
        /// values from a file or the clipboard kept within what the game can show
        public static SheerLook Sanitize(SheerLook L)
        {
            if (L == null) return null;
            L.tension ??= new TensionValues();
            L.style = Mathf.Clamp(L.style, 0, Styles.Length - 1); L.finish = Mathf.Clamp(L.finish, 0, Finishes.Length - 1);
            L.pattern = Mathf.Clamp(L.pattern, 0, Patterns.Length - 1); L.skirtStyle = Mathf.Clamp(L.skirtStyle, 0, SkirtStyles.Length - 1);
            L.skinTone = Mathf.Clamp(L.skinTone, -1, SkinTones.Length - 1); L.legShape = Mathf.Clamp(L.legShape, 0, 4);
            L.filter = Mathf.Clamp(L.filter, 0, Filters.Length - 1);
            L.plushKind = Mathf.Clamp(L.plushKind, 0, 3); L.photoFrame = Mathf.Clamp(L.photoFrame, 0, PhotoFrames.Length - 1); L.motion = Mathf.Clamp(L.motion, 0, Motions.Length - 1);
            L.backdrop = Mathf.Clamp(L.backdrop, 0, Backdrops.Length - 1); L.floor = Mathf.Clamp(L.floor, 0, Floors.Length - 1);
            L.lightPreset = Mathf.Clamp(L.lightPreset, 0, Lights.Length - 1); L.debugView = Mathf.Clamp(L.debugView, 0, DebugViews.Length - 1);
            L.denier = Mathf.Clamp(L.denier, 5f, 120f); L.patternScale = Mathf.Clamp(L.patternScale, 0.4f, 2.5f);
            L.skirtPatternScale = Mathf.Clamp(L.skirtPatternScale, 0.4f, 2.5f); L.fishnetSheer = Mathf.Clamp01(L.fishnetSheer);
            L.strength = Mathf.Clamp(L.strength, 0.3f, 3f); L.runTendency = Mathf.Clamp(L.runTendency, 0f, 2f); L.holeSize = Mathf.Clamp(L.holeSize, 0.4f, 2f);
            L.motionAmount = Mathf.Clamp(L.motionAmount, 0f, 2f); L.wind = Mathf.Clamp(L.wind, 0f, 2f); L.gusts = Mathf.Clamp(L.gusts, 0f, 2.5f);
            L.exposure = Mathf.Clamp(L.exposure, -2f, 2f); L.keyIntensity = Mathf.Clamp(L.keyIntensity, 0f, 3f); L.fillIntensity = Mathf.Clamp(L.fillIntensity, 0f, 3f);
            L.rimIntensity = Mathf.Clamp(L.rimIntensity, 0f, 4f); L.keyYaw = Mathf.Clamp(L.keyYaw, -90f, 90f); L.keyPitch = Mathf.Clamp(L.keyPitch, -30f, 40f);
            L.warmth = Mathf.Clamp(L.warmth, -1f, 1f); L.backBrightness = Mathf.Clamp(L.backBrightness, 0.2f, 2f);
            L.musicVolume = Mathf.Clamp01(L.musicVolume); L.sfxVolume = Mathf.Clamp01(L.sfxVolume); L.aperture = Mathf.Clamp(L.aperture, 1.2f, 16f);
            L.timeScale = Mathf.Clamp(L.timeScale, 0f, 2f);
            if (!Full)
            {
                // THE MINIMAL SIMULATOR (user, 2026-11-17): ONE stocking - the sheer pantyhose of the original - and a few cosmetic
                // choices: its colour and thickness, the skirt, the skin, the background, the music. Everything else a look can
                // hold (other stocking kinds, patterns, finishes, leg shapes, light presets, camera filters, props ...) is parked
                // until each has been studied on its own: held at the original's values, whatever a saved file says.
                var d = new SheerLook();
                L.style = 0; L.sandalToe = false; L.finish = d.finish; L.pattern = 0; L.seamAlways = false; L.fishnetSheer = 0f; L.lace = d.lace; L.weltOwnColor = false;
                L.strength = 1f; L.runTendency = 1f; L.holeSize = 1f; L.legShape = 0; L.polish = false; L.motion = 0; L.motionAmount = 1f; L.toeLifts = true;
                L.petals = false; L.plushie = false; L.ribbon = false; L.windOn = true; L.wind = 1f; L.gusts = 1f; L.backBrightness = 1f; L.floorOwnColor = false;
                L.lightPreset = 0; L.exposure = 0f; L.keyIntensity = L.fillIntensity = L.rimIntensity = 1f; L.keyYaw = L.keyPitch = 0f; L.warmth = 0f; L.rimOwnColor = false;
                L.dof = false; L.turntable = false; L.filter = 0; L.photoFrame = 0; L.lattice = false; L.perfHud = false; L.gauge = false; L.mascot = false;
                L.skirtPatternScale = 1f; L.denier = Mathf.Clamp(L.denier, DenierMin, DenierMax);
                // the panel's skirts (plain colours only: no stripes or tartan - school-uniform looks are not offered) and
                // backgrounds (each backdrop with its floor)
                L.skirtStyle = 0;
                int[] floorOf = { 0, 1, -1, 4, 2, 3, 5, -1 };       // backdrop -> its floor; -1: not offered
                if (L.backdrop < 0 || L.backdrop >= floorOf.Length || floorOf[L.backdrop] < 0) L.backdrop = 0;
                L.floor = floorOf[L.backdrop];
                if (L.skinTone < 0) L.skinTone = 0;                  // (a custom tint)
            }
            return L;
        }
    }
}
