// Browser test for web/catalog.html. Usage: node test-catalog-page.mjs <catalog.html> <progress.json>
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "/opt/node22/lib/node_modules/playwright");

const [src, progressFile] = process.argv.slice(2).map(p => path.resolve(p));
const dir = mkdtempSync(path.join(tmpdir(), "catalog-"));
writeFileSync(path.join(dir, "index.html"), `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>${readFileSync(src, "utf8")}</body></html>`);
const bad = path.join(dir, "bad.json"); writeFileSync(bad, '{"hello": 1}');
let pass = 0, fail = 0;
const check = (n, c, x = "") => { c ? pass++ : fail++; console.log(`${c ? "PASS" : "FAIL"} ${n}${!c && x ? "  -> " + x : ""}`); };
const browser = await chromium.launch();

for (const [label, vp, scheme] of [["desktop/light", { width: 1280, height: 900 }, "light"], ["phone/dark", { width: 390, height: 844 }, "dark"]]) {
  console.log(`\n== ${label} ==`);
  const ctx = await browser.newContext({ viewport: vp, colorScheme: scheme });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("console", m => m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text()) && errors.push(m.text()));
  await page.goto("file://" + path.join(dir, "index.html"));
  await page.waitForTimeout(300);
  const cards = () => page.locator("#grid .card").count();
  const noScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);

  check("loads without errors", errors.length === 0, errors.join(" | "));
  check("9 courses listed", (await cards()) === 9, String(await cards()));
  check("stats computed (324 lessons)", (await page.textContent("#stats")).includes("324"));
  check("no horizontal scroll", await noScroll());

  await page.click('#trackChips [data-track="ai"]');
  check("AI field filter -> 2 courses", (await cards()) === 2);
  await page.click('#trackChips [data-track="all"]');
  await page.click('#paths [data-path="ai-engineer"]');
  const steps = await page.locator("#grid .card .track").allTextContents();
  check("career path shows 4 ordered steps", steps.length === 4 && steps[0].startsWith("Step 1") && steps[3].startsWith("Step 4"), steps.join(","));
  check("path button pressed", (await page.getAttribute('#paths [data-path="ai-engineer"]', "aria-pressed")) === "true");
  await page.click('#paths [data-path="ai-engineer"]');
  check("clicking path again clears it", (await cards()) === 9);

  await page.fill("#search", "kubernetes");
  const kc = await cards();
  check("search 'kubernetes' narrows results", kc >= 2 && kc < 9, String(kc));
  await page.fill("#search", "zzzz-no-match");
  check("empty state shown", (await page.textContent("#grid")).includes("No course matches"));
  await page.fill("#search", "");

  await page.selectOption("#levelSel", "advanced");
  check("level ladder highlights 3 rungs", (await page.locator("#grid .card").first().locator(".ladder .on").count()) === 3);
  await page.click('#grid [data-course="devops"]');
  check("detail opens for DevOps", await page.isVisible("#detail") && (await page.textContent("#detail h2")) === "DevOps & Platform Engineering");
  check("detail opens on chosen level tab", (await page.getAttribute('#detail [data-tab="advanced"]', "aria-selected")) === "true");
  check("enrol command reflects level", (await page.textContent("#enrolCmd")) === "practica enrol devops --level advanced");
  await page.click('#detail [data-tab="beginner"]');
  check("beginner tab shows 9 lessons, ready badge and lesson link", (await page.locator("#detail .lessons li").count()) === 9 && (await page.locator("#detail .badge").count()) === 1 && (await page.getAttribute("#detail a.open", "href")).includes("PKNsaDxmRFk48Qq88CgjX1"));
  await page.click('#placement input[data-k="0"]');
  check("placement: one capstone ticked -> intermediate", (await page.textContent("#enrolCmd")) === "practica enrol devops --level intermediate");
  await page.click('#placement input[data-k="1"]'); await page.click('#placement input[data-k="2"]');
  check("placement: all ticked -> expert", (await page.textContent("#recommendation")).includes("Expert"));
  await page.click('#placement input[data-k="1"]');
  check("placement: gap -> intermediate", (await page.textContent("#recommendation")).includes("Intermediate"));
  check("no horizontal scroll with detail open", await noScroll());

  await page.setInputFiles("#progressFile", bad);
  await page.waitForTimeout(200);
  check("invalid progress file rejected clearly", (await page.textContent("#progressSummary")).includes("Could not read"));
  await page.setInputFiles("#progressFile", progressFile);
  await page.waitForTimeout(300);
  const summary = await page.textContent("#progressSummary");
  check("progress loaded summary", summary.includes("2 course(s), 2 lesson(s) passed"), summary);
  const devopsMeta = await page.locator('#grid [data-course="devops"] [data-progress]').textContent();
  check("DevOps card shows 1/36 passed", devopsMeta.includes("1/36 passed"), devopsMeta);
  const aiMeta = await page.locator('#grid [data-course="ai-engineering"] [data-progress]').textContent();
  check("AI card shows 1/36 passed", aiMeta.includes("1/36 passed"), aiMeta);
  await page.click('#grid [data-course="devops"]'); await page.click('#detail [data-tab="beginner"]');
  check("passed lesson ticked in roadmap", (await page.locator('#detail li[data-uid="devops/beginner/m01/l01"] .mark.passed').count()) === 1);
  check("detail progress line", (await page.textContent("#detailProgress")).includes("passed 1 of 36"));
  await page.click("#closeDetail");
  check("close hides detail", !(await page.isVisible("#detail")));
  await page.screenshot({ path: path.join(process.env.SHOT_DIR || dir, `catalog-${label.replace("/", "-")}.png`), fullPage: true });
  check("no errors after interaction", errors.length === 0, errors.join(" | "));
  await ctx.close();
}
await browser.close();
console.log(`\nResult: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
