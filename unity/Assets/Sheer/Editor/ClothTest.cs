// SHEER — numerical check of the compute cloth against its reference (tools/sim/leash.py):
//   python3 tools/sim/compare_unity.py gen      -> <dir>/path.bin (one pinch position per substep) + expected states
//   Unity -batchmode -force-vulkan -projectPath unity -executeMethod SheerEditor.ClothTest.Run -sheerClothTest <dir>
//   python3 tools/sim/compare_unity.py cmp      -> differences per checkpoint
// path.bin: i32 side, j, i, nsub, nrelease, ncheck, i32 check[ncheck] (substep counts), f32 A[nsub * 3]
using System;
using System.IO;
using Sheer;
using UnityEditor;
using UnityEngine;

namespace SheerEditor
{
    public static class ClothTest
    {
        public static void Run()
        {
            string dir = null; var args = Environment.GetCommandLineArgs();
            for (int k = 0; k + 1 < args.Length; k++) if (args[k] == "-sheerClothTest") dir = args[k + 1];
            int code = 0;
            try
            {
                var b = File.ReadAllBytes(Path.Combine(dir, "path.bin"));
                int side = BitConverter.ToInt32(b, 0), j = BitConverter.ToInt32(b, 4), i = BitConverter.ToInt32(b, 8);
                int nsub = BitConverter.ToInt32(b, 12), nrel = BitConverter.ToInt32(b, 16), ncheck = BitConverter.ToInt32(b, 20);
                var check = new int[ncheck]; Buffer.BlockCopy(b, 24, check, 0, 4 * ncheck);
                var A = new float[3 * nsub]; Buffer.BlockCopy(b, 24 + 4 * ncheck, A, 0, 12 * nsub);
                var cs = AssetDatabase.LoadAssetAtPath<ComputeShader>("Assets/Sheer/Shaders/SheerCloth.compute");
                // (the stocking is one lattice per leg from the toes now - tools/sim/export_sock_lattice.py; leash.py, the reference,
                //  still models the old leg-only lattice, so its node indices and states no longer line up: the benchmark below
                //  is what this test is still good for)
                var lat = ClothLattice.Load(Path.Combine(Application.streamingAssetsPath, "sock_lattice.bin"));
                var prm = new ClothParams();
                var cl = new TightsCloth(cs, lat, prm);
                var sw = System.Diagnostics.Stopwatch.StartNew();
                cl.BeginGrab(side, j, i);
                int ci = 0;
                for (int s = 0; s < nsub; s++)
                {
                    if (s == nrel) cl.EndGrab(side);
                    if (s < nrel) cl.Step(side, new Vector3(A[3 * s], A[3 * s + 1], A[3 * s + 2])); else cl.StepFree(side);
                    bool chk = ci < ncheck && s + 1 == check[ci];
                    if ((s + 1) % 64 == 0 || chk || s + 1 == nsub) cl.Flush();
                    if (chk)
                    {
                        var st = cl.ReadState(side);
                        var o = new byte[4 * st.Length]; Buffer.BlockCopy(st, 0, o, 0, o.Length);
                        File.WriteAllBytes(Path.Combine(dir, $"unity_{check[ci]}.bin"), o);
                        ci++;
                    }
                }
                var fin = cl.ReadState(side);
                Debug.Log($"[ClothTest] {nsub} substeps on {lat.NU} x {lat.NV} nodes, {ci} checkpoints written to {dir}");
                // benchmark: 30 frames' worth of held substeps (the same hand positions again), CPU time to submit them and
                // total time until the GPU has finished them
                cl.BeginGrab(side, j, i);
                for (int s = 0; s < 64; s++) cl.Step(side, new Vector3(A[3 * s], A[3 * s + 1], A[3 * s + 2]));
                cl.Flush(); cl.ReadState(side);
                sw.Restart(); double cpu = 0; int nb = 0;
                for (int f = 1; f <= 30; f++)
                {
                    for (int s = 64 * f; s < 64 * (f + 1); s++) cl.Step(side, new Vector3(A[3 * s], A[3 * s + 1], A[3 * s + 2]));
                    double t0 = sw.Elapsed.TotalMilliseconds; nb += cl.Flush(); cpu += sw.Elapsed.TotalMilliseconds - t0;
                }
                cl.ReadState(side);
                Debug.Log($"[ClothTest] bench: {nb} substeps, {sw.Elapsed.TotalMilliseconds / 30:0.00} ms per 64 substeps in total, {cpu / 30:0.00} ms of it CPU (command submission)");
                cl.Dispose();
            }
            catch (Exception e) { Debug.LogError("[ClothTest] " + e); code = 1; }
            EditorApplication.Exit(code);
        }
    }
}
