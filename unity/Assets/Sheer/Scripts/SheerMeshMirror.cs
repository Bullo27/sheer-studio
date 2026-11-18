// SHEER — renders another SheerMeshSource's mesh (same instance: the simulation's per-frame deformation and stretch
// stream come for free), e.g. the stockings' additive fibre-sheen pass.
using UnityEngine;

namespace Sheer
{
    [ExecuteAlways, RequireComponent(typeof(MeshFilter))]
    public class SheerMeshMirror : MonoBehaviour
    {
        public SheerMeshSource source;
        MeshFilter mf;

        void OnEnable() { mf = GetComponent<MeshFilter>(); Sync(); }
        void LateUpdate() => Sync();

        void Sync()
        {
            if (!source || !mf) return;
            var m = source.mesh != null ? source.mesh : source.GetComponent<MeshFilter>().sharedMesh;
            if (m && mf.sharedMesh != m) mf.sharedMesh = m;
        }
    }
}
