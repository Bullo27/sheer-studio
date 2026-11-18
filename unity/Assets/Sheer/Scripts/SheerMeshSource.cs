// SHEER — puts a .smesh (see SheerMesh.cs) into this object's MeshFilter, also in edit mode.
using System;
using System.IO;
using UnityEngine;

namespace Sheer
{
    /// Puts a .smesh into this object's MeshFilter (also in edit mode, so the scene can be looked at).
    [ExecuteAlways, RequireComponent(typeof(MeshFilter))]
    public class SheerMeshSource : MonoBehaviour
    {
        public string file = "tights.smesh";
        public bool dynamicStretchUV3;
        [NonSerialized] public SheerMeshData data;
        [NonSerialized] public Mesh mesh;

        public void EnsureLoaded()
        {
            if (mesh != null) return;
            data = SheerMeshData.Load(file);
            // (lift: the toe-gap fill - tried, max 1.4 mm, no visible change: the stocking already bridges the gaps; the toes'
            //  shapes are the body's own)
            // (gentler than round 9's 12 mm: the toes fused into lumps; round 8's untouched toes were five separate bulbs)
            // (OFF since 2026-11-18: the toes are as tools/reshape_legs.py lays them - inflated, padded, bridged, the stocking
            //  0.2 mm out of the skin. These older load-time passes smoothed the two meshes differently: the stocking sank up to
            //  5 mm over the little toe's convex side, the skin less - pink flecks of skin through the nylon, review 11.
            //  -sheerToeSmooth brings them back)
            bool noTS = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-sheerToeSmooth") < 0;
            if (file == "tights.smesh" && !noTS) { data.SmoothToes(0.013f, 0.0008f, yzFacing: true, yLow: 0.004f); data.BridgeToes(lift: false); }   // (rounds 12 / 13: the nylon spans the toe gaps)   // (fabric bridges the gaps between the toes)
            // (the skin under the sheer instep too: its tendons and toe gaps showed through the nylon, review round 7)
            if (file == "body.smesh" && !noTS) { data.SmoothToes(0.013f, 0f, allowOut: false, yzFacing: true, yLow: 0.004f); data.BridgeToes(); }
            mesh = data.BuildMesh(Path.GetFileNameWithoutExtension(file), dynamicStretchUV3);
            mesh.hideFlags = HideFlags.DontSave;
            GetComponent<MeshFilter>().sharedMesh = mesh;
        }

        void OnEnable() { EnsureLoaded(); }
        void OnDisable()
        {
            if (mesh) { if (Application.isPlaying) Destroy(mesh); else DestroyImmediate(mesh); }
            mesh = null; data = null;
        }
    }
}
