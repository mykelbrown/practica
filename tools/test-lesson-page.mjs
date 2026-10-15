// Browser test for an interactive lesson page. Usage: node test-lesson-page.mjs <lesson.html>
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdtempSync, copyFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "/opt/node22/lib/node_modules/playwright");

const src = path.resolve(process.argv[2]);
// Mirror the publish skeleton (doctype + viewport) so the test runs in standards mode.
const dir = mkdtempSync(path.join(tmpdir(), "lesson-"));
writeFileSync(path.join(dir, "index.html"), `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>${readFileSync(src, "utf8")}</body></html>`);
for (const f of ["lesson.mp4", "lesson.webm", "poster.jpg"]) { const m = path.join(path.dirname(src), "media", f); if (existsSync(m)) copyFileSync(m, path.join(dir, f)); }

let pass = 0, fail = 0;
const check = (name, cond, extra = "") => { cond ? pass++ : fail++; console.log(`${cond ? "PASS" : "FAIL"} ${name}${!cond && extra ? "  -> " + extra : ""}`); };
const browser = await chromium.launch();

for (const [label, vp, scheme] of [["desktop/light", { width: 1280, height: 900 }, "light"], ["phone/dark", { width: 390, height: 844 }, "dark"]]) {
  console.log(`\n== ${label} ==`);
  const ctx = await browser.newContext({ viewport: vp, colorScheme: scheme });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text()) && errors.push(m.text()));
  await page.goto("file://" + path.join(dir, "index.html"));
  await page.waitForTimeout(400);
  const txt = id => page.locator("#" + id).textContent();

  check("no script errors on load", errors.length === 0, errors.join(" | "));
  check("no horizontal page scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    String(await page.evaluate(() => document.documentElement.scrollWidth)));
  check("body has theme background", await page.evaluate(() => getComputedStyle(document.body).backgroundColor !== "rgba(0, 0, 0, 0)"));

  // Permission calculator
  check("initial mode 750", (await txt("octal")) === "750" && (await txt("symbolic")) === "-rwxr-x---");
  await page.click('button[data-mode="600"]');
  check("preset 600 -> -rw-------", (await txt("octal")) === "600" && (await txt("symbolic")) === "-rw-------");
  check("preset 600 pressed state", (await page.getAttribute('button[data-mode="600"]', "aria-pressed")) === "true");
  await page.click('button[data-mode="777"]');
  check("777 shows world-writable warning", await page.isVisible("#permWarn"));
  await page.click('button[data-mode="644"]');
  check("644 hides warning", !(await page.isVisible("#permWarn")) && (await txt("symbolic")) === "-rw-r--r--");
  await page.click("#b-others-x", { force: true });
  check("toggle others-x -> 645", (await txt("octal")) === "645" && (await page.inputValue("#octalInput")) === "645");
  await page.fill("#octalInput", "640");
  check("typed 640 updates bits", (await txt("symbolic")) === "-rw-r-----" && await page.isChecked("#b-group-r") && !(await page.isChecked("#b-others-x")));
  await page.fill("#octalInput", "98");
  check("invalid mode shows error, keeps last valid", (await txt("octalErr")).includes("three digits") && (await txt("octal")) === "640");
  check("plain-English sentence", (await txt("permSentence")) === "The owner can read and write. The group can read. Everyone else can do nothing.", await txt("permSentence"));

  // Health-check simulator
  for (const [scn, code, node, needle] of [["healthy", 0, "n-ok", "OK env=development"], ["missing", 2, "n-e2", "ERROR: missing"], ["badport", 3, "n-e3", "not a number"]]) {
    await page.click(`button[data-scn="${scn}"]`);
    await page.waitForFunction(c => document.getElementById("exitBadge").textContent === "exit " + c, code, { timeout: 5000 }).catch(() => {});
    const cls = await page.getAttribute("#" + node, "class");
    check(`scenario ${scn}: exit ${code}, end node marked, output`,
      (await txt("exitBadge")) === `exit ${code}` && /done-(ok|bad)/.test(cls) && (await txt("simTerm")).includes(needle), `${await txt("exitBadge")} / ${cls}`);
  }
  // rapid switching must not leave stale highlights from the earlier run
  await page.click('button[data-scn="healthy"]'); await page.click('button[data-scn="missing"]');
  await page.waitForTimeout(2600);
  check("rapid switch: only latest path highlighted",
    (await page.locator("#flow .done-ok, #flow .done-bad").count()) === 1 && (await page.getAttribute("#n-ok", "class")) === "box" && (await txt("exitBadge")) === "exit 2");

  // Terminal replay
  await page.click("#replayPlay");
  await page.waitForTimeout(700);
  await page.click("#replayPlay"); // pause
  const paused = await txt("replay"); await page.waitForTimeout(500);
  check("replay pauses", paused === (await txt("replay")));
  await page.click("#replayPlay"); // resume
  await page.waitForFunction(() => document.getElementById("replay").dataset.done === "1", null, { timeout: 30000 }).catch(() => {});
  const r = await txt("replay");
  check("replay completes with real outputs", r.includes("600 demo/secret") && r.includes("exit=2") && r.includes("rm -rf demo"));
  await page.click("#replayRestart"); await page.waitForTimeout(300);
  check("restart clears and replays", !(await txt("replay")).includes("rm -rf demo") && (await page.textContent("#replayPlay")) === "Pause");

  // Checklist persistence
  await page.check("#c-0"); await page.check("#c-1");
  check("progress bar 20%", (await page.getAttribute("#bar", "style")).includes("20%"));
  await page.reload(); await page.waitForTimeout(300);
  check("checklist survives reload", await page.isChecked("#c-0") && await page.isChecked("#c-1") && !(await page.isChecked("#c-2")));

  check("video element has duration", await page.evaluate(() => new Promise(res => { const v = document.getElementById("film");
    if (v.readyState >= 1) return res(v.duration > 30); v.onloadedmetadata = () => res(v.duration > 30); v.onerror = () => res(false); setTimeout(() => res(false), 5000); })));
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || dir, `lesson-${label.replace("/", "-")}.png`), fullPage: true });
  check("no script errors after interaction", errors.length === 0, errors.join(" | "));
  await ctx.close();
}
await browser.close();
console.log(`\nResult: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
