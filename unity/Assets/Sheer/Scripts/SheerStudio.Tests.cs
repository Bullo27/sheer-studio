// SHEER - the panel's TEST HARNESS (partial class of SheerStudio).
// -sheerStudioTest DIR: screenshots of the panel and of EVERY choice it offers (each stocking colour, the ends of the
//   thickness range, each skirt, skin and background, in both views), and logic checks: undo / redo, a look's JSON, the
//   mend, the classic inspector's controls, a UI monkey that clicks every button and moves every slider, the original's
//   replay with changes under it. Run it at the window sizes people use (-screen-width / -screen-height).
// -sheerShowcase DIR: the README's stills.
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.UI;

namespace Sheer
{
    public partial class SheerStudio
    {
        // ------------------------------------------------------------------ a pull held by the test
        IEnumerator HoldPull(float sx, float sy, Vector3 dragCam, float secs)
        {
            var camg = rig.GetComponent<Camera>(); var sp = new Vector2(Screen.width * sx, Screen.height * sy);
            int v = -1;
            // (the first point near the asked one that is on the stocking: the framing shifts with the panel's width)
            foreach (float oy in new[] { 0f, 0.05f, -0.05f })
            {
                foreach (float ox in new[] { 0f, -0.04f, 0.04f, -0.08f, 0.08f, -0.12f })
                {
                    sp = new Vector2(Screen.width * (sx + ox), Screen.height * (sy + oy));
                    v = sim.Pick(camg.ScreenPointToRay(sp * SheerSuperSample.Scale), out _, out _);
                    if (v >= 0) break;
                }
                if (v >= 0) break;
            }
            showPull = v >= 0 ? sim.Grab(v) : null;
            if (showPull == null) { Debug.Log($"[test] no fabric at {sx:0.00},{sy:0.00}"); yield break; }
            for (float tt = 0f; tt < secs && showPull.state == Pull.State.Held; tt += Time.deltaTime)
            {
                var d = camg.transform.right * dragCam.x + camg.transform.up * dragCam.y + camg.transform.forward * dragCam.z;
                showPull.target = sim.tights.transform.InverseTransformVector(d * Mathf.SmoothStep(0f, 1f, tt / (secs * 0.8f)));
                showPull.eye = sim.tights.transform.InverseTransformPoint(camg.transform.position); showPull.hasEye = true;
                yield return null;
            }
        }
        Pull showPull;
        void EndPull() { if (showPull != null && showPull.state == Pull.State.Held) sim.Release(showPull, false); showPull = null; }

        // ------------------------------------------------------------------ showcase (-sheerShowcase DIR): the README's stills
        IEnumerator Showcase(string dir)
        {
            Directory.CreateDirectory(dir);
            SheerFun.Quiet = true;
            yield return new WaitForSeconds(2.5f);
            void Shot(string n) => ScreenCapture.CaptureScreenshot(Path.Combine(dir, n + ".png"));
            // the panel beside a sail being drawn out, the original look
            look = new SheerLook(); ApplyAll(true); SetSkin(0); SetOpen(true); rig.SwitchTo(0); yield return new WaitForSeconds(3.0f);
            yield return StartCoroutine(HoldPull(0.27f, 0.47f, new Vector3(-0.085f, 0.01f, 0f), 1.4f)); yield return null;
            Shot("panel"); yield return null; yield return null; EndPull(); yield return new WaitForSeconds(1.2f);
            // the original's inspector beside a sail
            Repair(); SetSkin(1); yield return new WaitForSeconds(2.0f);
            yield return StartCoroutine(HoldPull(0.25f, 0.42f, new Vector3(-0.09f, 0.0f, 0f), 1.4f)); yield return null;
            Shot("classic"); yield return null; yield return null; EndPull(); yield return new WaitForSeconds(1.2f);
            SetSkin(0);
            // a few looks, panel closed, VIEW 01
            SetOpen(false);
            var combos = new[] { (0, 0, 0, 0), (1, 1, 0, 2), (2, 2, 2, 1), (4, 3, 0, 3), (5, 4, 3, 4), (6, 5, 0, 0) };   // yarn, skirt, skin, background
            for (int k = 0; k < combos.Length; k++)
            {
                var (yc, sk, st, bk) = combos[k];
                Repair(); look = new SheerLook { color = SheerLook.YarnMinimal[yc], skinTone = st }; SetSkirt(sk); SetBackground(bk); ApplyAll(true);
                rig.SwitchTo(0); yield return new WaitForSeconds(2.2f); Shot($"look_{k}"); yield return new WaitForSeconds(0.3f);
            }
            look = new SheerLook(); ApplyAll(true); rig.SwitchTo(1); yield return new WaitForSeconds(2.2f); Shot("feet"); yield return new WaitForSeconds(0.3f);
            Debug.Log("[showcase] done: " + dir);
            Application.Quit();
        }

        // ------------------------------------------------------------------ the UI monkey: every button, every slider, twice
        IEnumerator UiMonkey()
        {
            var rnd = new System.Random(5);
            int clicks = 0, slides = 0, fields = 0, menus = 0;
            SetSkin(0); SetOpen(true); yield return null;
            for (int pass = 0; pass < 3; pass++)
            {
                foreach (var b in panel.GetComponentsInChildren<Button>(true))
                {
                    if (!b || !b.gameObject.activeInHierarchy) continue;
                    var txt = b.GetComponentInChildren<Text>(true); string s = txt ? txt.text : "";
                    if (s.Contains("Photo")) continue;                 // (writes a file)
                    b.onClick.Invoke(); clicks++;
                    if (helpGo) ToggleHelp();
                    if (skin != 0) SetSkin(0);
                    if (!open || hidden) { SetHidden(false); SetOpen(true); }
                    if (clicks % 6 == 0) yield return null;
                }
                BuildForm(); yield return null;               // (the headers were clicked too: every section folded - open again)
                foreach (var sl in panel.GetComponentsInChildren<Slider>(true))
                {
                    if (!sl || !sl.gameObject.activeInHierarchy) continue;
                    sl.value = Mathf.Lerp(sl.minValue, sl.maxValue, (float)rnd.NextDouble()); slides++;
                    if (slides % 4 == 0) yield return null;
                }
                yield return null;
            }
            SetSkin(1); yield return null; yield return null;
            if (insp)
            {
                var root = insp.transform;
                foreach (var f in root.GetComponentsInChildren<InputField>(true))
                {
                    if (!f || !f.gameObject.activeInHierarchy) continue;
                    f.onEndEdit.Invoke(((float)rnd.NextDouble() * 40f - 5f).ToString(System.Globalization.CultureInfo.InvariantCulture)); fields++;
                    f.onEndEdit.Invoke("nonsense"); fields++;
                    if (fields % 8 == 0) yield return null;
                }
                foreach (var b in root.GetComponentsInChildren<Button>(true))
                {
                    if (!b || !b.gameObject.activeInHierarchy) continue;
                    var txt = b.GetComponentInChildren<Text>(true); string s = txt ? txt.text : "";
                    if (s.Contains("Studio")) continue;                // (the way back to the small panel: last)
                    b.onClick.Invoke(); clicks++;
                    // a menu opened: pick one of its items (or close it)
                    var menu = root.Find("InspectorCanvas/Menu");
                    if (menu)
                    {
                        var items = menu.GetComponentsInChildren<Button>(true);
                        if (items.Length > 1 && rnd.NextDouble() < 0.7) { var it = items[1 + rnd.Next(items.Length - 1)]; var tx = it.GetComponentInChildren<Text>(true); if (tx == null || !tx.text.Contains("Paste")) it.onClick.Invoke(); else items[0].onClick.Invoke(); }
                        else items[0].onClick.Invoke();
                        menus++;
                    }
                    yield return null;
                }
            }
            SetSkin(0); look = new SheerLook(); if (tension) tension.ResetToVideoValues(); ApplyAll(true); Time.timeScale = 1f; RefreshTab();
            Debug.Log($"[studio] ui monkey: {clicks} clicks, {slides} slider moves, {fields} typed fields, {menus} menus");
        }

        // ------------------------------------------------------------------ self-test (-sheerStudioTest dir)
        IEnumerator SelfTest(string dir)
        {
            Directory.CreateDirectory(dir);
            SheerFun.Quiet = true;
            yield return new WaitForSeconds(2f);
            IEnumerator Shot(string n, float settle = 0.9f) { yield return new WaitForSeconds(settle); ScreenCapture.CaptureScreenshot(Path.Combine(dir, n + ".png")); yield return new WaitForSeconds(0.35f); }
            // logic: undo / redo across a fabric change and a material-inspector change; a look's JSON round trip; parked fields
            {
                bool ok = true; void Check(bool c, string what) { if (!c) { ok = false; Debug.LogError("[studio] self-test FAILED: " + what); } }
                look = new SheerLook(); ApplyAll(true); look.tension.From(tension); lastJson = JsonUtility.ToJson(look); undo.Clear(); redo.Clear(); lastChange = -10f;
                yield return new WaitForSecondsRealtime(0.8f);
                look.denier = 60f; ApplyStockings(true); Changed(); yield return new WaitForSecondsRealtime(0.8f);
                tension.pearlStrength = 0.9f; Changed(); yield return new WaitForSecondsRealtime(0.8f);
                Undo(); Check(Mathf.Abs(tension.pearlStrength - 0.387f) < 1e-4f && Mathf.Abs(look.denier - 60f) < 1e-3f, $"undo 1 (pearl {tension.pearlStrength}, denier {look.denier})");
                Undo(); Check(Mathf.Abs(look.denier - 20f) < 1e-3f && Mathf.Abs(tension.frostBodyCoverage - 0.829f) < 1e-3f, $"undo 2 (denier {look.denier}, frost {tension.frostBodyCoverage})");
                Redo(); Check(Mathf.Abs(look.denier - 60f) < 1e-3f, $"redo 1 (denier {look.denier})");
                Redo(); Check(Mathf.Abs(tension.pearlStrength - 0.9f) < 1e-4f, $"redo 2 (pearl {tension.pearlStrength})");
                var L2 = SheerLook.FromJson(JsonUtility.ToJson(look)); Check(L2 != null && L2.tension.set && Mathf.Abs(L2.tension.pearlStrength - 0.9f) < 1e-4f, "json round trip");
                var junk = SheerLook.FromJson("{\"denier\":\"x\",\"tension\":{\"normalStrength\":1e30}}");
                if (junk != null) { junk.tension.To(tension); Check(tension.normalStrength <= 1.6f, "junk look clamped"); }
                var parked = SheerLook.FromJson("{\"style\":2,\"pattern\":2,\"finish\":4,\"lightPreset\":3,\"legShape\":3,\"motion\":4,\"plushie\":true,\"mascot\":true,\"denier\":200}");
                Check(parked != null && (SheerLook.Full || (parked.style == 0 && parked.pattern == 0 && parked.finish == 1 && parked.lightPreset == 0 && parked.legShape == 0 && parked.motion == 0 && !parked.plushie && !parked.mascot && parked.denier <= SheerLook.DenierMax)), "parked fields held");
                Debug.Log("[studio] self-test logic: " + (ok ? "PASS" : "FAIL"));
                look = new SheerLook(); tension.ResetToVideoValues(); ApplyAll(true);
            }
            // the panel: its top, its end, folded sections, the help card
            SetSkin(0); SetOpen(true); rig.SwitchTo(0);
            yield return Shot("panel_top", 1.5f);
            { var sr = content.GetComponentInParent<ScrollRect>(); if (sr) sr.verticalNormalizedPosition = 0f; }
            yield return Shot("panel_end", 0.5f);
            { var sr = content.GetComponentInParent<ScrollRect>(); if (sr) sr.verticalNormalizedPosition = 1f; }
            {
                // fold every section, then open them again
                var heads = new System.Collections.Generic.List<Button>();
                foreach (var b in content.GetComponentsInChildren<Button>(true)) if (b && b.gameObject.name == "Header") heads.Add(b);
                foreach (var b in heads) b.onClick.Invoke();
                int shown = 0; foreach (Transform c in content) if (c.gameObject.activeSelf) shown++;
                Debug.Log("[studio] sections fold: " + (heads.Count >= 5 && shown == heads.Count ? "PASS" : $"FAIL ({heads.Count} headers, {shown} rows shown)"));
                yield return Shot("panel_folded", 0.5f);
                foreach (var b in heads) b.onClick.Invoke();
            }
            ToggleHelp(); yield return Shot("help", 0.5f); ToggleHelp();
            // every choice, panel closed: VIEW 01, and the feet where the choice shows there
            SetOpen(false);
            for (int k = 0; k < SheerLook.YarnMinimal.Length; k++)
            {
                look = new SheerLook { color = SheerLook.YarnMinimal[k] }; ApplyAll(true);
                rig.SwitchTo(0); yield return Shot($"yarn_{k}_view1", 1.4f); rig.SwitchTo(1); yield return Shot($"yarn_{k}_view2", 1.4f);
            }
            foreach (float dn in new[] { SheerLook.DenierMin, 14f, 30f, 50f, SheerLook.DenierMax })
            {
                look = new SheerLook { denier = dn }; ApplyAll(true);
                rig.SwitchTo(0); yield return Shot($"denier_{dn:00}_view1", 1.4f); rig.SwitchTo(1); yield return Shot($"denier_{dn:00}_view2", 1.4f);
            }
            // (white at both ends of the range, black opaque: the extremes together)
            foreach (var (yc, dn, nm) in new[] { (4, SheerLook.DenierMin, "white_thin"), (4, SheerLook.DenierMax, "white_thick"), (1, SheerLook.DenierMax, "black_thick"), (2, SheerLook.DenierMin, "nude_thin") })
            {
                look = new SheerLook { color = SheerLook.YarnMinimal[yc], denier = dn }; ApplyAll(true);
                rig.SwitchTo(0); yield return Shot($"ends_{nm}_view1", 1.4f); rig.SwitchTo(1); yield return Shot($"ends_{nm}_view2", 1.4f);
            }
            rig.SwitchTo(0);
            for (int k = 0; k < Skirts.Length; k++) { look = new SheerLook(); SetSkirt(k); ApplyAll(true); yield return Shot($"skirt_{k}_{Skirts[k].name}", 1.2f); }
            for (int k = 0; k < SheerLook.SkinTones.Length; k++)
            {
                look = new SheerLook { skinTone = k }; ApplyAll(true);
                rig.SwitchTo(0); yield return Shot($"skin_{k}_view1", 1.4f); rig.SwitchTo(1); yield return Shot($"skin_{k}_view2", 1.4f);
            }
            for (int k = 0; k < Backs.Length; k++)
            {
                look = new SheerLook(); SetBackground(k); ApplyAll(true);
                rig.SwitchTo(0); yield return Shot($"back_{k}_{Backs[k].name}_view1", 1.4f); rig.SwitchTo(1); yield return Shot($"back_{k}_{Backs[k].name}_view2", 1.4f);
            }
            // mending: two tears with their ladders, then Repair - they shrink away over 0.9 s
            look = new SheerLook(); ApplyAll(true); rig.SwitchTo(0); yield return new WaitForSeconds(1.5f);
            sim.damage[1].Burst(0.47f, 0.40f, 1.3f); sim.damage[-1].Burst(0.55f, 0.50f, 1.2f); yield return new WaitForSeconds(1.8f);
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "mend_0.png")); yield return new WaitForSecondsRealtime(0.1f);
            Repair();
            for (int k = 1; k <= 4; k++) { yield return new WaitForSecondsRealtime(0.25f); ScreenCapture.CaptureScreenshot(Path.Combine(dir, $"mend_{k}.png")); }
            yield return new WaitForSecondsRealtime(0.5f);
            { int left = 0; foreach (var d in sim.damage.Values) left += d.holes.Count + d.runs.Count; Debug.Log("[studio] mend: " + (left == 0 && !sim.Mending ? "PASS" : $"FAIL ({left} left)")); }
            // a pull beside the panel, then a tear
            SetOpen(true); look = new SheerLook(); ApplyAll(true); yield return new WaitForSeconds(1.0f);
            yield return StartCoroutine(HoldPull(0.27f, 0.47f, new Vector3(-0.085f, 0.01f, 0f), 1.4f)); yield return null;
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "pull.png")); yield return null; yield return null; EndPull(); yield return new WaitForSeconds(1.0f);
            // the classic inspector (the original video's panel) and its hierarchy tab
            SetSkin(1); yield return Shot("classic", 1.8f);
            insp.ShowTip("Brightness of the sparkling glints - single fibres flashing in the key light.", new Vector2(Screen.width - 330, Screen.height * 0.35f));
            yield return null; ScreenCapture.CaptureScreenshot(Path.Combine(dir, "classic_tip.png")); yield return new WaitForSeconds(0.3f); insp.HideTip();
            { var r = insp.TestControls(); Debug.Log("[studio] classic inspector controls: " + (r.Length == 0 ? "PASS" : "FAIL" + r)); if (r.Length > 0) Debug.LogError("[studio] self-test FAILED: classic controls" + r); }
            insp.TestHierarchy(true); yield return Shot("classic_hier", 0.6f);
            insp.TestHierarchy(false); SetSkin(0);
            yield return StartCoroutine(UiMonkey());
            // the original's replay (P) with changes under it: a colour, a skirt, a repair, a background
            var rd = FindAnyObjectByType<ReplayDriver>();
            if (rd)
            {
                look = new SheerLook(); ApplyAll(true); rd.Play(); yield return new WaitForSeconds(2.5f);
                look.color = SheerLook.YarnMinimal[2]; ApplyStockings(false); yield return new WaitForSeconds(1.5f);
                Repair(); yield return new WaitForSeconds(1.5f);
                SetSkirt(2); SetBackground(1); ApplyAll(true); yield return new WaitForSeconds(2.5f);
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, "replay_changes.png")); yield return new WaitForSeconds(0.4f);
                Debug.Log("[studio] replay with changes: running " + rd.IsRunning);
            }
            Debug.Log("[studio] self-test done: " + dir);
            Application.Quit();
        }
    }
}
