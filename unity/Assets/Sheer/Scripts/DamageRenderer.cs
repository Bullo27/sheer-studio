// SHEER — uploads the tear state of one leg to the GPU and rasterises it (DamageRaster.compute).
using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace Sheer
{
    public class DamageRenderer : IDisposable
    {
        [StructLayout(LayoutKind.Sequential)] struct HoleG { public float u, z, rx, ry, angle, rough, seed, skew, pw, cut, group, pad; }
        [StructLayout(LayoutKind.Sequential)] struct RunG { public float u, lo, hi, hw, age, seed, wobble, taper, fanTop, fanBot, pad0, pad1; }
        [StructLayout(LayoutKind.Sequential)] struct MarkG { public float u, z, radius, s; }

        const int MaxHoles = 512, MaxRuns = 128, MaxMarks = 128;
        readonly ComputeShader cs;
        readonly int kernel;
        readonly ComputeBuffer holes, runs, marks, circ, wide;
        readonly HoleG[] h = new HoleG[MaxHoles];
        readonly RunG[] r = new RunG[MaxRuns];
        readonly MarkG[] m = new MarkG[MaxMarks];
        public readonly RenderTexture Texture, TextureB, TextureC;     // see DamageRaster.compute for the channels

        public DamageRenderer(ComputeShader shader, Func<float, float> circumference, Func<float, float> openWidth, string name)
        {
            cs = shader; kernel = cs.FindKernel("Raster");
            holes = new ComputeBuffer(MaxHoles, Marshal.SizeOf<HoleG>());
            runs = new ComputeBuffer(MaxRuns, Marshal.SizeOf<RunG>());
            marks = new ComputeBuffer(MaxMarks, Marshal.SizeOf<MarkG>());
            circ = new ComputeBuffer(SheerDamage.TexH, sizeof(float));
            var c = new float[SheerDamage.TexH];
            // (texture row i is at z = ZMin + (i + 0.5) / TexH: the maps run from the toes' wales to the hem)
            for (int i = 0; i < c.Length; i++) c[i] = circumference(SheerDamage.ZMin + (i + 0.5f) / SheerDamage.TexH);
            circ.SetData(c);
            wide = new ComputeBuffer(SheerDamage.TexH, sizeof(float));
            for (int i = 0; i < c.Length; i++) c[i] = openWidth(SheerDamage.ZMin + (i + 0.5f) / SheerDamage.TexH);
            wide.SetData(c);
            RenderTexture Make(string n)
            {
                var rt = new RenderTexture(SheerDamage.TexW, SheerDamage.TexH, 0, RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear)
                { enableRandomWrite = true, wrapModeU = TextureWrapMode.Repeat, wrapModeV = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = n };
                rt.Create(); return rt;
            }
            Texture = Make(name); TextureB = Make(name + "_flow"); TextureC = Make(name + "_ends");
        }

        /// new circumference / opening tables (the body shape changed the legs)
        public void UpdateTables(Func<float, float> circumference, Func<float, float> openWidth)
        {
            var c = new float[SheerDamage.TexH];
            for (int i = 0; i < c.Length; i++) c[i] = circumference(SheerDamage.ZMin + (i + 0.5f) / SheerDamage.TexH);
            circ.SetData(c);
            for (int i = 0; i < c.Length; i++) c[i] = openWidth(SheerDamage.ZMin + (i + 0.5f) / SheerDamage.TexH);
            wide.SetData(c);
        }

        public void Render(SheerDamage d)
        {
            int nh = Mathf.Min(d.holes.Count, MaxHoles), nr = Mathf.Min(d.runs.Count, MaxRuns), nm = Mathf.Min(d.marks.Count, MaxMarks);
            for (int i = 0; i < nh; i++) { var x = d.holes[i]; h[i] = new HoleG { u = x.u, z = x.z, rx = x.rx, ry = x.ry, angle = x.angle, rough = x.rough, seed = x.seed, skew = x.skew, pw = x.pw, cut = x.cut, group = x.group }; }
            for (int i = 0; i < nr; i++) { var x = d.runs[i]; r[i] = new RunG { u = x.u, lo = x.lo, hi = x.hi, hw = x.hw, age = x.age, seed = x.seed, wobble = x.wobble, taper = x.taper, fanTop = x.up.fan, fanBot = x.dn.fan }; }
            for (int i = 0; i < nm; i++) { var x = d.marks[i]; m[i] = new MarkG { u = x.u, z = x.z, radius = x.radius, s = x.s }; }
            if (nh > 0) holes.SetData(h, 0, 0, nh);
            if (nr > 0) runs.SetData(r, 0, 0, nr);
            if (nm > 0) marks.SetData(m, 0, 0, nm);
            cs.SetBuffer(kernel, "_Holes", holes); cs.SetBuffer(kernel, "_Runs", runs); cs.SetBuffer(kernel, "_Marks", marks);
            cs.SetBuffer(kernel, "_Circ", circ); cs.SetTexture(kernel, "_Out", Texture);
            cs.SetTexture(kernel, "_OutB", TextureB); cs.SetTexture(kernel, "_OutC", TextureC);
            cs.SetInt("_NHoles", nh); cs.SetInt("_NRuns", nr); cs.SetInt("_NMarks", nm);
            cs.SetInt("_W", SheerDamage.TexW); cs.SetInt("_H", SheerDamage.TexH); cs.SetFloat("_Range", SheerDamage.RANGE); cs.SetFloat("_ZMin", SheerDamage.ZMin); cs.SetBuffer(kernel, "_Wide", wide);
            cs.Dispatch(kernel, (SheerDamage.TexW + 7) / 8, (SheerDamage.TexH + 7) / 8, 1);
            d.dirty = false;
        }

        public void Dispose() { holes?.Release(); runs?.Release(); marks?.Release(); circ?.Release(); wide?.Release(); if (Texture) Texture.Release(); if (TextureB) TextureB.Release(); if (TextureC) TextureC.Release(); }
    }
}
