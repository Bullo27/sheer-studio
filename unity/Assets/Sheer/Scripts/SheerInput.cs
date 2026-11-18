// SHEER — the player's hand: left-click on the stocking grabs the fabric under the cursor, dragging pulls
// it in the plane facing the camera (the pinched patch follows as far as the knit gives: TightsSim / HandMap),
// releasing lets it spring back. Dragged much further than the fabric can follow, the nylon tears (holes +
// ladders) — exactly the mapping used to replay the original session.
using UnityEngine;
using UnityEngine.EventSystems;

namespace Sheer
{
    public class SheerInput : MonoBehaviour
    {
        public TightsSim sim;
        public Camera cam;
        [Tooltip("Colliders that hide the stocking (skirt): clicks on them don't grab the fabric.")]
        public Collider[] blockers;
        [Range(0f, 0.6f)] public float liftTowardsViewer = 0f;    // extra pull toward the viewer (0 = as measured in the original)
        public float maxPull = 0.35f;                             // how far the hand itself may go (the fabric follows ~8.5 cm)
        public bool inputEnabled = true;

        Pull active;
        Vector3 h, W0; float d0;

        void Update()
        {
            if (!inputEnabled || sim == null) return;
            if (Input.GetMouseButtonDown(0) && !OverUI())
            {
                if (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift)) TrySnag(Input.mousePosition);   // a fingernail snag
                else TryGrab(Input.mousePosition);
            }
            if (active != null)
            {
                if (active.state != Pull.State.Held) { active = null; return; }       // it tore
                if (Input.GetMouseButton(0)) Drag(Input.mousePosition);
                else { sim.Release(active, false); active = null; }
            }
        }

        static bool OverUI() => EventSystem.current != null && EventSystem.current.IsPointerOverGameObject();

        public bool TryGrab(Vector2 screen)
        {
            Ray ray = cam.ScreenPointToRay(screen * SheerSuperSample.Scale);
            int v = sim.Pick(ray, out Vector3 hit, out float dist);
            if (v < 0) return false;
            if (blockers != null)
                foreach (var b in blockers)
                    if (b && b.Raycast(ray, out var bh, dist - 0.002f)) return false;
            active = sim.Grab(v);
            if (active == null) { SheerFun.Boop(hit); return false; }      // bare skin above a thigh-high's top: nothing to pull
            h = hit;
            d0 = Vector3.Dot(h - cam.transform.position, cam.transform.forward);
            W0 = WorldAt(screen); grabScreen = screen;
            // (a grab below the simulated fabric - on the foot - is held by the lowest free row, centimetres above: the hand
            //  draws that patch toward where the cursor took hold; same rule as the replay's)
            off = h - sim.tights.transform.TransformPoint(sim.PosePoint(sim.PullRest(active)));
            return true;
        }

        /// Shift + click: catch a loop with a fingernail (TightsSim.SnagAt) - a pinhole that may run into a ladder
        public bool TrySnag(Vector2 screen)
        {
            Ray ray = cam.ScreenPointToRay(screen * SheerSuperSample.Scale);
            int v = sim.Pick(ray, out Vector3 hit, out float dist);
            if (v < 0) return false;
            if (blockers != null)
                foreach (var b in blockers)
                    if (b && b.Raycast(ray, out var bh, dist - 0.002f)) return false;
            if (!sim.SnagAt(v)) { SheerFun.Boop(hit); return false; }
            return true;
        }

        Vector3 WorldAt(Vector2 screen)
        {
            Ray r = cam.ScreenPointToRay(screen * SheerSuperSample.Scale);
            return r.origin + r.direction * (d0 / Mathf.Max(Vector3.Dot(r.direction, cam.transform.forward), 1e-6f));
        }

        Vector2 grabScreen; Vector3 off;

        void Drag(Vector2 screen)
        {
            // (the drag as the cursor has moved ON SCREEN since the grab, in the camera's plane as it is NOW: while the camera
            //  orbits the plane of the grab turns away, and a fixed world point pulled the patch round behind the leg - the
            //  replay has done this since review round 8; free play now does the same)
            W0 = WorldAt(grabScreen);
            Vector3 D = WorldAt(screen) - W0;
            Vector3 v = sim.HandOffset(active, D, (cam.transform.position - h).normalized, liftTowardsViewer);
            if (off.sqrMagnitude > 1e-4f) v += off * Mathf.SmoothStep(0f, 1f, D.magnitude / 0.03f);
            if (v.magnitude > maxPull) v = v.normalized * maxPull;
            active.target = sim.tights.transform.InverseTransformVector(v);
            active.eye = sim.tights.transform.InverseTransformPoint(cam.transform.position); active.hasEye = true;
        }

        public bool Holding => active != null;
        public float Tension => active != null ? active.tension : 0f;
    }
}
