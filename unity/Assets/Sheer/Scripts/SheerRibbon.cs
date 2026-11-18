// SHEER — a rhythmic-gymnastics RIBBON (a Studio prop, Scene tab): a satin ribbon dancing in the air beside her legs.
// Its free end traces the gymnast's figures - spirals (small circles while the centre travels) and snakes - and the rest of
// the ribbon, a fixed length, follows the end's path the way a real ribbon trails its stick: each point lies where the
// end passed a little earlier, measured along the path (arc length), with a slight sag and a slow twist so both satin
// faces catch the light.
using UnityEngine;
using UnityEngine.Rendering;

namespace Sheer
{
    public class SheerRibbon : MonoBehaviour
    {
        const int N = 220, Hist = 4096;
        public float length = 1.15f, width = 0.03f, speed = 1f;
        public float wind;                                           // (SheerFun: the skirt's wind level - the trail streams sideways)
        Mesh mesh; Vector3[] verts, nrm; float t;
        readonly Vector3[] hist = new Vector3[Hist]; int head; const float HistDt = 1f / 240f; float acc;

        void Awake()
        {
            var mf = gameObject.AddComponent<MeshFilter>(); var mr = gameObject.AddComponent<MeshRenderer>();
            mr.sharedMaterial = Resources.Load<Material>("Materials/Ribbon");
            mr.renderingLayerMask = 0xFFu; mr.shadowCastingMode = ShadowCastingMode.On;
            mesh = new Mesh { name = "ribbon" }; mesh.MarkDynamic();
            verts = new Vector3[2 * N]; nrm = new Vector3[2 * N];
            var uv = new Vector2[2 * N]; var tri = new int[6 * (N - 1)];
            for (int i = 0; i < N - 1; i++) { int o = 6 * i, a = 2 * i; tri[o] = a; tri[o + 1] = a + 2; tri[o + 2] = a + 1; tri[o + 3] = a + 1; tri[o + 4] = a + 2; tri[o + 5] = a + 3; }
            for (int i = 0; i < N; i++) { uv[2 * i] = new Vector2(i / (N - 1f), 0f); uv[2 * i + 1] = new Vector2(i / (N - 1f), 1f); }
            mesh.vertices = verts; mesh.uv = uv; mesh.triangles = tri;
            mesh.bounds = new Bounds(Vector3.zero, Vector3.one * 2f);
            mf.sharedMesh = mesh;
            // a past for the trail to follow from the first frame
            for (int i = 0; i < Hist; i++) hist[i] = EndAt(-(Hist - 1 - i) * HistDt);
            head = Hist - 1;
            Build();
        }

        /// The free end's figure (local space, metres): circles of ~9 cm while their centre travels a slow figure-eight -
        /// a spiral - with a vertical snake laid over it.
        static Vector3 EndAt(float tt)
        {
            float w = 4.6f, c = tt * 0.42f;
            var centre = new Vector3(0.05f * Mathf.Sin(c), 0.16f * Mathf.Sin(c * 2f + 0.4f), 0.06f * Mathf.Sin(c * 0.7f));   // (clear of the near leg)
            var loop = new Vector3(0.085f * Mathf.Cos(tt * w), 0.085f * Mathf.Sin(tt * w), 0.03f * Mathf.Sin(tt * w * 0.5f));
            return centre + loop + new Vector3(0f, 0.02f * Mathf.Sin(tt * 1.3f), 0f);
        }

        void LateUpdate()
        {
            float dt = Mathf.Min(Time.deltaTime, 0.1f) * speed;
            t += dt; acc += dt;
            while (acc >= HistDt) { acc -= HistDt; head = (head + 1) % Hist; hist[head] = EndAt(t - acc); }
            Build();
        }

        void Build()
        {
            // walk back along the end's path, one ribbon segment of arc length at a time
            float seg = length / (N - 1);
            var pts = new Vector3[N];
            pts[0] = hist[head];
            int k = head; float carried = 0f; Vector3 a = hist[head];
            for (int i = 1; i < N; i++)
            {
                float need = seg - carried;
                int guard = 0;
                while (guard++ < Hist)
                {
                    int kp = (k - 1 + Hist) % Hist; if (kp == head) break;     // (out of history: the rest bunches at the oldest point)
                    Vector3 b = hist[kp]; float d = Vector3.Distance(a, b);
                    if (d >= need) { a = Vector3.Lerp(a, b, need / Mathf.Max(d, 1e-6f)); carried = 0f; break; }
                    need -= d; a = b; k = kp;
                }
                pts[i] = a;
            }
            // sag (the far part hangs a little) and the satin's slow twist
            for (int i = 0; i < N; i++)
            {
                float s = i / (N - 1f);
                pts[i].y -= 0.05f * s * s * (1f - 0.5f * Mathf.Clamp01(wind));
                pts[i].x -= 0.10f * wind * s * s * (0.8f + 0.2f * Mathf.Sin(t * 2.3f + s * 5f));   // (blown out, away from the legs: it flies at -x)
            }
            for (int i = 0; i < N; i++)
            {
                Vector3 T = (pts[Mathf.Min(i + 1, N - 1)] - pts[Mathf.Max(i - 1, 0)]); if (T.sqrMagnitude < 1e-10f) T = Vector3.up; T.Normalize();
                Vector3 n0 = Vector3.Cross(T, Vector3.forward); if (n0.sqrMagnitude < 1e-6f) n0 = Vector3.Cross(T, Vector3.right); n0.Normalize();
                Vector3 b0 = Vector3.Cross(n0, T);
                float s = i / (N - 1f), phi = 0.9f * Mathf.Sin(s * 7f - t * 1.7f);
                Vector3 W = n0 * Mathf.Cos(phi) + b0 * Mathf.Sin(phi);
                float wd = width * (i == 0 ? 0.5f : Mathf.Lerp(1f, 0.85f, s));
                verts[2 * i] = pts[i] - W * (wd * 0.5f); verts[2 * i + 1] = pts[i] + W * (wd * 0.5f);
                Vector3 nn = Vector3.Cross(T, W).normalized; nrm[2 * i] = nrm[2 * i + 1] = nn;
            }
            mesh.vertices = verts; mesh.normals = nrm;
        }
    }
}
