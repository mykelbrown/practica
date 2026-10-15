// Records film.html to an MP4. Usage: node record.mjs [film.html] [out.mp4]
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH || "/opt/node22/lib/node_modules/playwright");

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(process.argv[2] || path.join(here, "film.html"));
const out = path.resolve(process.argv[3] || path.join(here, "lesson.mp4"));
const vidDir = mkdtempSync(path.join(tmpdir(), "film-"));
const size = { width: 1280, height: 720 };

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: size, recordVideo: { dir: vidDir, size } });
const page = await context.newPage();
const errors = [];
page.on("pageerror", e => errors.push(e.message));
page.on("console", m => m.type() === "error" && errors.push(m.text()));

const t0 = Date.now();
await page.goto("file://" + src);
await page.waitForFunction(() => window.FILM_DONE === true, null, { timeout: 180000 });
await page.waitForTimeout(800);
const lead = await page.evaluate(() => performance.timing.navigationStart);
await context.close();
await browser.close();

const webm = path.join(vidDir, readdirSync(vidDir).find(f => f.endsWith(".webm")));
// Trim the blank loading lead-in (approx.), encode H.264 for wide compatibility.
const trim = Math.max(0, (lead - t0) / 1000);
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", trim.toFixed(2), "-i", webm,
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium", "-movflags", "+faststart", out]);
rmSync(vidDir, { recursive: true, force: true });

if (errors.length) { console.error("Page errors:\n" + errors.join("\n")); process.exit(1); }
console.log("Wrote " + out);
