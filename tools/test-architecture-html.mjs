import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const resolverPath = process.env.PLAYWRIGHT_RESOLVE_FROM
  ? pathToFileURL(process.env.PLAYWRIGHT_RESOLVE_FROM).href
  : import.meta.url;
const require = createRequire(resolverPath);
const { chromium } = require("playwright");

const url = process.argv[2];
const outputPath = process.argv[3] || "output/playwright/architecture-html.png";

if (!url) {
  throw new Error("Usage: node tools/test-architecture-html.mjs <url> [screenshotPath]");
}

const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });

page.on("console", (message) => {
  if (message.type() !== "error") return;
  const text = message.text();
  if (text.includes("Failed to load resource") && text.includes("ERR_NETWORK_ACCESS_DENIED")) return;
  errors.push(text);
});
page.on("pageerror", (error) => errors.push(error.message));

await page.goto(url, { waitUntil: "load" });
await page.locator("text=Form System Kit Composer 系統架構圖").waitFor({ state: "visible", timeout: 8000 });
await page.locator("svg").waitFor({ state: "visible", timeout: 8000 });

const descCount = await page.locator(".desc-card").count();
if (descCount < 6) throw new Error(`Expected at least 6 description cards, found ${descCount}`);

const svgBox = await page.locator("svg").boundingBox();
if (!svgBox || svgBox.width < 900 || svgBox.height < 600) {
  throw new Error(`SVG appears too small: ${JSON.stringify(svgBox)}`);
}

await page.screenshot({ path: outputPath, fullPage: true });
await browser.close();

if (errors.length) throw new Error(errors.join("\n"));
console.log(`OK architecture HTML smoke: ${outputPath}`);
