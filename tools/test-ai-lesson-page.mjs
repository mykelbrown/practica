// Browser test for the AI Engineering B1 lesson page. Usage: node test-ai-lesson-page.mjs <lesson.html>
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdtempSync, copyFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "/opt/node22/lib/node_modules/playwright");
const src = path.resolve(process.argv[2]);
const dir = mkdtempSync(path.join(tmpdir(), "ailesson-"));
writeFileSync(path.join(dir, "index.html"), `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>${readFileSync(src, "utf8")}</body></html>`);
for (const f of ["lesson.mp4", "lesson.webm", "poster.jpg"]) { const m = path.join(path.dirname(src), "media", f); if (existsSync(m)) copyFileSync(m, path.join(dir, f)); }
let pass = 0, fail = 0;
const check = (n, c, x = "") => { c ? pass++ : fail++; console.log(`${c ? "PASS" : "FAIL"} ${n}${!c && x ? "  -> " + x : ""}`); };
const browser = await chromium.launch();
for (const [label, vp, scheme] of [["desktop/light", { width: 1280, height: 900 }, "light"], ["phone/dark", { width: 390, height: 844 }, "dark"]]) {
  console.log(`\n== ${label} ==`);
  const ctx = await browser.newContext({ viewport: vp, colorScheme: scheme });
  const page = await ctx.newPage(); const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text()) && errors.push(m.text()));
  await page.goto("file://" + path.join(dir, "index.html")); await page.waitForTimeout(300);
  const t = id => page.textContent("#" + id);
  check("no errors on load", errors.length === 0, errors.join(" | "));
  check("no horizontal scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  check("default sample (fenced) valid", (await t("inspectResult")).startsWith("Returns") && (await t("steps")).includes("fenced block"));
  const expect = { clean: "Returns", trap: "Returns", bool: "priority must be an integer", extra: "unexpected key(s): confidence", trunc: "no JSON object found" };
  for (const [k, want] of Object.entries(expect)) { await page.click(`#samples [data-s="${k}"]`); const r = await t("inspectResult"); check(`sample ${k} -> ${want}`, r.includes(want), r); }
  await page.fill("#reply", '{"intent":"refund","priority":4,"summary":"   "}');
  check("typed blank summary rejected", (await t("inspectResult")).includes("summary"));
  await page.fill("#reply", "no json here");
  check("typed text without JSON rejected", (await t("inspectResult")).includes("no JSON object"));
  const scn = { first: ["returned after 1 call", 1], retry: ["returned after 2 calls", 2], never: ["RuntimeError", 3], timeout: ["TimeoutError", 1] };
  for (const [k, [want, n]] of Object.entries(scn)) {
    await page.click(`#loopScn [data-scn="${k}"]`);
    await page.waitForFunction(k => document.getElementById("loopTerm").dataset.done === k, k, { timeout: 15000 }).catch(() => {});
    const badge = await t("loopBadge"), count = await page.locator("#attempts .attempt").count();
    check(`loop ${k}: ${want}, ${n} attempt(s)`, badge === want && count === n, `${badge} / ${count}`);
  }
  await page.click('#loopScn [data-scn="retry"]'); await page.waitForFunction(() => document.getElementById("loopTerm").dataset.done === "retry", null, { timeout: 15000 }).catch(() => {});
  check("feedback line present", (await t("loopTerm")).includes("previous reply was invalid: priority must be an integer 1-5, got 9"));
  await page.click('#loopScn [data-scn="never"]'); await page.click('#loopScn [data-scn="first"]');
  await page.waitForTimeout(2500);
  check("switching scenarios mid-run keeps only latest", (await t("loopBadge")) === "returned after 1 call" && (await page.locator("#attempts .attempt").count()) === 1);
  await page.check("#c-0"); await page.reload(); await page.waitForTimeout(200);
  check("checklist persists", await page.isChecked("#c-0"));
  check("video playable", await page.evaluate(() => new Promise(res => { const v = document.getElementById("film"); if (v.readyState >= 1) return res(v.duration > 30); v.onloadedmetadata = () => res(v.duration > 30); setTimeout(() => res(false), 5000); })));
  check("no errors after interaction", errors.length === 0, errors.join(" | "));
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || dir, `ai-${label.replace("/", "-")}.png`), fullPage: true });
  await ctx.close();
}
await browser.close(); console.log(`\nResult: ${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0);
