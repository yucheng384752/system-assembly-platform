import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const resolverPath = process.env.PLAYWRIGHT_RESOLVE_FROM
  ? pathToFileURL(process.env.PLAYWRIGHT_RESOLVE_FROM).href
  : import.meta.url;
const require = createRequire(resolverPath);
const { chromium } = require("playwright");

const url = process.argv[2];
const outputPath = process.argv[3] || "output/playwright/gui-smoke.png";

if (!url) {
  throw new Error("Usage: node tools/test-gui-browser.mjs <url> [screenshotPath]");
}

const consoleErrors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });

page.on("console", (message) => {
  if (message.type() !== "error") return;
  const text = message.text();
  if (text.includes("Fetch API cannot load file:") && text.includes("form-analysis.kit-manifest.json")) return;
  consoleErrors.push(text);
});
page.on("pageerror", (error) => {
  consoleErrors.push(error.message);
});

await page.goto(url, { waitUntil: "networkidle" });

await expectVisible(page, "text=用問題引導使用者構思系統");
await expectCountAtLeast(page, ".kit-card", 4, "kit cards");
await expectCountAtLeast(page, "[data-guide-choice]", 6, "guide choices");

await page.click('[data-view="runtime"]');
await expectVisible(page, "text=解壓腳本後就是一個系統");
await expectVisible(page, "text=scripts/check-prerequisites.ps1");
await expectVisible(page, "text=backend/requirements.txt 或 pyproject.toml");

await page.click('[data-view="preview"]');
await expectVisible(page, "text=系統預覽");
await expectCountAtLeast(page, ".preview-tab", 1, "preview tabs");

await page.click('[data-view="generate"]');
await expectVisible(page, "text=輸出與文件串聯");
await expectVisible(page, "text=dist/generated-system");
await expectVisible(page, "text=Recipe JSON");
await expectVisible(page, "#recipe-output");
await expectVisible(page, "text=Assembly 指令");
const recipe = await page.evaluate(() => buildRecipe());
if (recipe.name !== "gui-selected-form-system") {
  throw new Error(`Unexpected GUI recipe name: ${recipe.name}`);
}
if (!recipe.sourceManifest || !Array.isArray(recipe.enabledKits) || !recipe.enabledKits.length) {
  throw new Error("GUI recipe export is missing required recipe fields.");
}

await mkdir(path.dirname(outputPath), { recursive: true });
await page.screenshot({ path: outputPath, fullPage: true });

await browser.close();

if (consoleErrors.length) {
  throw new Error(`Browser console errors:\n${consoleErrors.join("\n")}`);
}

console.log(`OK browser GUI smoke: ${outputPath}`);

async function expectVisible(page, selector) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: "visible", timeout: 8000 });
}

async function expectCountAtLeast(page, selector, minimum, label) {
  const count = await page.locator(selector).count();
  if (count < minimum) {
    throw new Error(`Expected at least ${minimum} ${label}, found ${count}`);
  }
}
