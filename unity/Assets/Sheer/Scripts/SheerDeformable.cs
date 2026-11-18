// SHEER — a deformable render mesh driven by Burst jobs: rest data, welded adjacency (seam duplicates share
// normals), per-frame face normals + areal stretch, per-vertex normal/tangent/stretch, one upload per frame.
using System;
using System.Runtime.InteropServices;
using Unity.Burst;
using Unity.Collections;
using Unity.Jobs;
using Unity.Mathematics;
using UnityEngine;
using UnityEngine.Rendering;

namespace Sheer
{
    [StructLayout(LayoutKind.Sequential)]
    public struct VtxS { public float3 pos; public float3 nrm; public float4 tan; public float2 uv3; }     // with stretch (tights)
    [StructLayout(LayoutKind.Sequential)]
    public struct VtxP { public float3 pos; public float3 nrm; public float4 tan; }                          // plain (body)

    [BurstCompile]
    struct FaceJob : IJobParallelFor
    {
        [ReadOnly] public NativeArray<float3> pos;
        [ReadOnly] public NativeArray<int> tris;
        [ReadOnly] public NativeArray<float> area0;
        [WriteOnly] public NativeArray<float3> faceN;   // area-weighted
        [WriteOnly] public NativeArray<float> ratio;
        public void Execute(int t)
        {
            float3 a = pos[tris[3 * t]], b = pos[tris[3 * t + 1]], c = pos[tris[3 * t + 2]];
            float3 cr = math.cross(b - a, c - a);
            faceN[t] = cr;
            ratio[t] = 0.5f * math.length(cr) / area0[t];
        }
    }

    [BurstCompile]
    struct VertJobS : IJobParallelFor
    {
        [ReadOnly] public NativeArray<int> weld, adjStart, adjTri;
        [ReadOnly] public NativeArray<float3> pos, faceN;
        [ReadOnly] public NativeArray<float4> restTan;
        [ReadOnly] public NativeArray<float> ratio;
        [WriteOnly] public NativeArray<VtxS> outV;
        public void Execute(int i)
        {
            int w = weld[i], a = adjStart[w], b = adjStart[w + 1];
            float3 n = float3.zero; float s = 0f;
            for (int k = a; k < b; k++) { int t = adjTri[k]; n += faceN[t]; s += ratio[t]; }
            n = math.normalizesafe(n, new float3(0, 1, 0));
            float4 rt = restTan[i];
            float3 t3 = math.normalizesafe(rt.xyz - n * math.dot(n, rt.xyz), new float3(1, 0, 0));
            outV[i] = new VtxS { pos = pos[i], nrm = n, tan = new float4(t3, rt.w), uv3 = new float2(b > a ? s / (b - a) : 1f, 0f) };
        }
    }

    [BurstCompile]
    struct VertJobP : IJobParallelFor
    {
        [ReadOnly] public NativeArray<int> weld, adjStart, adjTri;
        [ReadOnly] public NativeArray<float3> pos, faceN;
        [ReadOnly] public NativeArray<float4> restTan;
        [WriteOnly] public NativeArray<VtxP> outV;
        public void Execute(int i)
        {
            int w = weld[i], a = adjStart[w], b = adjStart[w + 1];
            float3 n = float3.zero;
            for (int k = a; k < b; k++) n += faceN[adjTri[k]];
            n = math.normalizesafe(n, new float3(0, 1, 0));
            float4 rt = restTan[i];
            float3 t3 = math.normalizesafe(rt.xyz - n * math.dot(n, rt.xyz), new float3(1, 0, 0));
            outV[i] = new VtxP { pos = pos[i], nrm = n, tan = new float4(t3, rt.w) };
        }
    }

    public class SheerDeformable : IDisposable
    {
        public readonly Mesh mesh;
        public readonly SheerMeshData data;
        public readonly int n, nt;
        public NativeArray<float3> rest, restN, pos;
        public NativeArray<float4> restTan;
        public NativeArray<int> tris, weld, adjStart, adjTri;
        public NativeArray<float> area0, ratio;
        public NativeArray<float3> faceN;
        NativeArray<VtxS> outS; NativeArray<VtxP> outP;
        readonly bool withStretch;
        const MeshUpdateFlags Flags = MeshUpdateFlags.DontValidateIndices | MeshUpdateFlags.DontRecalculateBounds | MeshUpdateFlags.DontResetBoneBounds;

        public SheerDeformable(SheerMeshSource src, bool withStretch)
        {
            src.EnsureLoaded();
            mesh = src.mesh; data = src.data; this.withStretch = withStretch;
            // (the meshes are uploaded ONCE now - pose and cloth are applied in the vertex shaders - so their buffers are static;
            //  -sheerDynMesh keeps them 'dynamic' as when the CPU deformed them every frame, for profiling)
            if (Array.IndexOf(Environment.GetCommandLineArgs(), "-sheerDynMesh") >= 0) mesh.MarkDynamic();
            n = data.vertexCount;
            rest = new NativeArray<float3>(n, Allocator.Persistent); restN = new NativeArray<float3>(n, Allocator.Persistent);
            pos = new NativeArray<float3>(n, Allocator.Persistent); restTan = new NativeArray<float4>(n, Allocator.Persistent);
            var p = data.f["position"]; var nn = data.f["normal"]; var tg = data.f["tangent"];
            for (int i = 0; i < n; i++)
            {
                rest[i] = new float3(p[3 * i], p[3 * i + 1], p[3 * i + 2]);
                restN[i] = new float3(nn[3 * i], nn[3 * i + 1], nn[3 * i + 2]);
                restTan[i] = new float4(tg[4 * i], tg[4 * i + 1], tg[4 * i + 2], tg[4 * i + 3]);
            }
            pos.CopyFrom(rest);
            int total = 0; foreach (var s in data.submeshes) total += s.Length;
            var t = new int[total]; int off = 0;
            foreach (var s in data.submeshes) { Array.Copy(s, 0, t, off, s.Length); off += s.Length; }
            nt = total / 3;
            tris = new NativeArray<int>(t, Allocator.Persistent);
            var w = data.Weld();
            weld = new NativeArray<int>(w, Allocator.Persistent);
            // adjacency over the welded topology (CSR)
            var cnt = new int[n + 1];
            for (int k = 0; k < t.Length; k++) cnt[w[t[k]] + 1]++;
            for (int k = 0; k < n; k++) cnt[k + 1] += cnt[k];
            var fill = (int[])cnt.Clone(); var adj = new int[t.Length];
            for (int tri = 0; tri < nt; tri++) for (int c = 0; c < 3; c++) adj[fill[w[t[3 * tri + c]]]++] = tri;
            adjStart = new NativeArray<int>(cnt, Allocator.Persistent);
            adjTri = new NativeArray<int>(adj, Allocator.Persistent);
            area0 = new NativeArray<float>(nt, Allocator.Persistent); ratio = new NativeArray<float>(nt, Allocator.Persistent);
            faceN = new NativeArray<float3>(nt, Allocator.Persistent);
            for (int tri = 0; tri < nt; tri++)
            {
                float3 a = rest[t[3 * tri]], b = rest[t[3 * tri + 1]], c = rest[t[3 * tri + 2]];
                area0[tri] = math.max(0.5f * math.length(math.cross(b - a, c - a)), 1e-12f);
            }
            if (withStretch) outS = new NativeArray<VtxS>(n, Allocator.Persistent);
            else outP = new NativeArray<VtxP>(n, Allocator.Persistent);
        }

        /// After 'pos' was written (by a job that 'dependsOn'): normals, tangents, stretch, upload.
        public void Finish(JobHandle dependsOn)
        {
            var f = new FaceJob { pos = pos, tris = tris, area0 = area0, faceN = faceN, ratio = ratio }.Schedule(nt, 4096, dependsOn);
            if (withStretch)
            {
                new VertJobS { weld = weld, adjStart = adjStart, adjTri = adjTri, pos = pos, faceN = faceN, restTan = restTan, ratio = ratio, outV = outS }
                    .Schedule(n, 4096, f).Complete();
                mesh.SetVertexBufferData(outS, 0, 0, n, 0, Flags);
            }
            else
            {
                new VertJobP { weld = weld, adjStart = adjStart, adjTri = adjTri, pos = pos, faceN = faceN, restTan = restTan, outV = outP }
                    .Schedule(n, 4096, f).Complete();
                mesh.SetVertexBufferData(outP, 0, 0, n, 0, Flags);
            }
        }

        /// Closest ray hit on the current (deformed) surface, in this mesh's local space. Returns triangle or -1.
        public int Raycast(float3 o, float3 d, out float tHit, out float3 bary)
        {
            var res = new NativeArray<float4>(nt, Allocator.TempJob);
            new RayJob { pos = pos, tris = tris, o = o, d = d, res = res }.Schedule(nt, 8192).Complete();
            int best = -1; tHit = float.MaxValue; bary = 0;
            for (int i = 0; i < nt; i++) if (res[i].x > 0 && res[i].x < tHit) { tHit = res[i].x; best = i; bary = new float3(1 - res[i].y - res[i].z, res[i].y, res[i].z); }
            res.Dispose();
            return best;
        }

        [BurstCompile]
        struct RayJob : IJobParallelFor
        {
            [ReadOnly] public NativeArray<float3> pos;
            [ReadOnly] public NativeArray<int> tris;
            public float3 o, d;
            [WriteOnly] public NativeArray<float4> res;
            public void Execute(int t)
            {
                float3 a = pos[tris[3 * t]], b = pos[tris[3 * t + 1]], c = pos[tris[3 * t + 2]];
                float3 e1 = b - a, e2 = c - a, pv = math.cross(d, e2);
                float det = math.dot(e1, pv);
                res[t] = new float4(-1, 0, 0, 0);
                if (math.abs(det) < 1e-12f) return;
                float inv = 1f / det; float3 tv = o - a;
                float u = math.dot(tv, pv) * inv; if (u < 0 || u > 1) return;
                float3 qv = math.cross(tv, e1);
                float v = math.dot(d, qv) * inv; if (v < 0 || u + v > 1) return;
                float tt = math.dot(e2, qv) * inv;
                if (tt > 0) res[t] = new float4(tt, u, v, 0);
            }
        }

        public void Dispose()
        {
            if (rest.IsCreated) rest.Dispose(); if (restN.IsCreated) restN.Dispose(); if (pos.IsCreated) pos.Dispose();
            if (restTan.IsCreated) restTan.Dispose(); if (tris.IsCreated) tris.Dispose(); if (weld.IsCreated) weld.Dispose();
            if (adjStart.IsCreated) adjStart.Dispose(); if (adjTri.IsCreated) adjTri.Dispose();
            if (area0.IsCreated) area0.Dispose(); if (ratio.IsCreated) ratio.Dispose(); if (faceN.IsCreated) faceN.Dispose();
            if (outS.IsCreated) outS.Dispose(); if (outP.IsCreated) outP.Dispose();
        }
    }
}
