// SHEER — sound: six original background tracks (synthesized for the game: Resources/Audio/Music) with cross-fades, and
// the sound of the fabric - a nylon creak that rises with the pull's tension, the rip of a tear, the dry zip of a ladder
// running, the snap of a release - plus the panel's little pops and chimes (Resources/Audio/Sfx). Also tells the body's
// motion where the beat is (the 'vibe' style sways with it).
using System.Collections.Generic;
using UnityEngine;

namespace Sheer
{
    public class SheerAudio : MonoBehaviour
    {
        public static SheerAudio I;
        public static readonly string[] TrackFiles = { "sakura_lofi", "kawaii_future_bass", "pixel_heart_8bit", "music_box_dream", "city_pop_night", "koto_breeze" };
        public static readonly string[] TrackNames =
        {
            "Sakura Lo-fi|桜ローファイ", "Kawaii Future Bass|ふわふわベース", "Pixel Heart|ピクセルハート", "Music Box Dream|オルゴールの夢",
            "City Pop Night|シティポップの夜", "Koto Breeze|琴の風",
        };
        public static float[] TrackBpm = { 80f, 150f, 140f, 84f, 108f, 72f };

        public TightsSim sim; public SkirtCloth skirt;
        public float musicVolume = 0.55f, sfxVolume = 0.8f;
        public bool musicOn = true;
        public int track = -1;
        AudioSource musicA, musicB, stretch, zip;
        readonly AudioSource[] voices = new AudioSource[6]; int voice;    // (one-shots: each its own pitch - one shared source re-pitched sounds still playing)
        readonly Dictionary<string, AudioClip> clips = new Dictionary<string, AudioClip>();
        readonly AudioClip[] tracks = new AudioClip[TrackFiles.Length];
        float fade = 1f; bool aIsCurrent = true; float lastWind;

        public static void Ui(string name) { if (I) I.Play(name, 0.45f); }
        public static void Fx(string name, float vol = 1f, float pitch = 1f) { if (I) I.Play(name, vol, pitch); }

        void Awake()
        {
            I = this;
            AudioSource Src(bool loop) { var s = gameObject.AddComponent<AudioSource>(); s.playOnAwake = false; s.loop = loop; s.spatialBlend = 0f; return s; }
            musicA = Src(true); musicB = Src(true); stretch = Src(true); zip = Src(true);
            for (int i = 0; i < voices.Length; i++) voices[i] = Src(false);
            foreach (var c in Resources.LoadAll<AudioClip>("Audio/Sfx")) clips[c.name] = c;
            for (int i = 0; i < TrackFiles.Length; i++) tracks[i] = Resources.Load<AudioClip>("Audio/Music/" + TrackFiles[i]);
            if (clips.TryGetValue("stretch_loop", out var st)) { stretch.clip = st; stretch.volume = 0f; stretch.Play(); }
            if (clips.TryGetValue("zip_loop", out var zp)) { zip.clip = zp; zip.volume = 0f; zip.Play(); }
            TightsSim.Grabbed += OnGrab; TightsSim.Released += OnRelease; TightsSim.Snagged += OnSnag;
            Debug.Log($"[audio] {clips.Count} sounds, {System.Array.FindAll(tracks, t => t != null).Length} / {tracks.Length} tracks");
        }
        void OnDestroy() { TightsSim.Grabbed -= OnGrab; TightsSim.Released -= OnRelease; TightsSim.Snagged -= OnSnag; if (I == this) I = null; }
        void OnSnag(int side, float z) { Play("snap", 0.45f, Random.Range(1.6f, 1.9f)); SheerFun.OnSnag(z); }

        void OnGrab(Pull p) => Play("tick", 0.6f, 0.8f);
        void OnRelease(Pull p, bool burst)
        {
            if (burst) { Play("rip", 1f, Random.Range(0.92f, 1.08f)); SheerFun.OnTear(p); }
            else if (p.maxT > 0.15f) Play("snap", Mathf.Clamp01(0.3f + p.maxT), Random.Range(0.95f, 1.1f));
        }

        public void Play(string name, float vol = 1f, float pitch = 1f)
        {
            if (!clips.TryGetValue(name, out var c) || sfxVolume <= 0f) return;
            // a free voice (else the one that started longest ago)
            AudioSource s = null;
            for (int i = 0; i < voices.Length; i++) { var v = voices[(voice + i) % voices.Length]; if (!v.isPlaying) { s = v; voice = (voice + i + 1) % voices.Length; break; } }
            if (s == null) { s = voices[voice]; voice = (voice + 1) % voices.Length; }
            s.Stop(); s.clip = c; s.pitch = pitch; s.volume = Mathf.Clamp01(vol * sfxVolume); s.Play();
        }

        public bool HasTrack(int i) => i >= 0 && i < tracks.Length && tracks[i] != null;

        public void SetTrack(int i)
        {
            if (i == track) return;
            track = i;
            var next = aIsCurrent ? musicB : musicA;
            next.clip = HasTrack(i) ? tracks[i] : null;
            if (next.clip) { next.time = 0f; next.volume = 0f; next.Play(); }
            aIsCurrent = !aIsCurrent; fade = 0f;
        }

        void Update()
        {
            var cur = aIsCurrent ? musicA : musicB; var old = aIsCurrent ? musicB : musicA;
            fade = Mathf.MoveTowards(fade, 1f, Time.unscaledDeltaTime / 1.2f);
            float mv = musicOn ? musicVolume : 0f;
            cur.volume = mv * fade; old.volume = mv * (1f - fade);
            if (fade >= 1f && old.isPlaying) old.Stop();
            // the fabric: creak with the held pull's tension, zip while ladders run
            float tension = 0f;
            if (sim) foreach (var p in sim.pulls) if (p.state == Pull.State.Held) tension = Mathf.Max(tension, p.tension);
            float sv = sfxVolume * Mathf.Clamp01((tension - 0.15f) * 1.4f) * 0.55f;
            stretch.volume = Mathf.MoveTowards(stretch.volume, sv, Time.unscaledDeltaTime * 3f);
            stretch.pitch = 0.75f + 0.6f * Mathf.Clamp01(tension);
            float zs = 0f;
            if (sim) foreach (var d in sim.damage.Values) zs += d.zipSpeed;
            zip.volume = Mathf.MoveTowards(zip.volume, sfxVolume * Mathf.Clamp01(zs * 0.25f) * 0.7f, Time.unscaledDeltaTime * 8f);
            zip.pitch = 0.8f + Mathf.Clamp01(zs * 0.1f) * 0.6f;
            // a gust of wind
            if (skirt)
            {
                float w = skirt.WindLevel;
                if (w > 0.6f && lastWind <= 0.6f) Play("whoosh", 0.35f * Mathf.Clamp01(w), Random.Range(0.9f, 1.1f));
                lastWind = w;
            }
            // the beat for the body's 'vibe'
            if (sim != null)
            {
                sim.motion.bpm = musicOn && HasTrack(track) && cur.isPlaying ? TrackBpm[track] : 0f;
                sim.motion.beatTime = cur.isPlaying ? cur.time : 0.0;
            }
        }
    }
}
