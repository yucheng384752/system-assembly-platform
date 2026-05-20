import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const projectRoot = process.cwd();
const resolverPath = path.join(projectRoot, "output", "playwright", "runner", "package.json");
const require = createRequire(pathToFileURL(resolverPath).href);
const { chromium } = require("playwright");

const url = process.argv[2] || "http://127.0.0.1:4173/";
const outputDir = path.join(projectRoot, "dist", "gui-downloads");
const recipePath = path.join(projectRoot, "assembly", "gui-all-kits.recipe.json");
const screenshotPath = path.join(outputDir, "all-kits-gui.png");

await mkdir(outputDir, { recursive: true });

const manifest = JSON.parse(
  await readFile(path.join(projectRoot, "kits", "form-analysis.kit-manifest.json"), "utf8"),
);
const manifestKitIds = manifest.kits.map((kit) => kit.id);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });

const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(error.message));

await page.goto(url, { waitUntil: "networkidle" });
await page.waitForSelector("[data-kit-toggle]", { state: "attached", timeout: 10000 });

for (const kitId of manifestKitIds) {
  const locator = page.locator(`[data-kit-toggle="${kitId}"]`);
  if ((await locator.count()) !== 1) throw new Error(`Missing GUI kit checkbox: ${kitId}`);
  await page.evaluate((id) => {
    const input = document.querySelector(`[data-kit-toggle="${id}"]`);
    if (!input) throw new Error(`Missing GUI kit checkbox: ${id}`);
    if (input.checked) return;
    input.checked = true;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, kitId);
}

await page.evaluate(() => {
  const crcTable = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crcTable[n] = c >>> 0;
  }

  function crc32(bytes) {
    let c = 0xffffffff;
    for (const byte of bytes) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function dosDateTime(date) {
    const time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() / 2);
    const day = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    return { time: time & 0xffff, day: day & 0xffff };
  }

  function u16(value, out) {
    out.push(value & 0xff, (value >>> 8) & 0xff);
  }

  function u32(value, out) {
    out.push(value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff);
  }

  class BrowserZip {
    constructor() {
      this.entries = [];
    }

    file(name, content) {
      this.entries.push({ name, content: String(content) });
    }

    async generateAsync() {
      const encoder = new TextEncoder();
      const chunks = [];
      const central = [];
      let offset = 0;
      const now = dosDateTime(new Date());

      for (const entry of this.entries) {
        const nameBytes = encoder.encode(entry.name.replaceAll("\\", "/"));
        const data = encoder.encode(entry.content);
        const crc = crc32(data);
        const local = [];
        u32(0x04034b50, local);
        u16(20, local);
        u16(0x0800, local);
        u16(0, local);
        u16(now.time, local);
        u16(now.day, local);
        u32(crc, local);
        u32(data.length, local);
        u32(data.length, local);
        u16(nameBytes.length, local);
        u16(0, local);
        chunks.push(new Uint8Array(local), nameBytes, data);

        const header = [];
        u32(0x02014b50, header);
        u16(20, header);
        u16(20, header);
        u16(0x0800, header);
        u16(0, header);
        u16(now.time, header);
        u16(now.day, header);
        u32(crc, header);
        u32(data.length, header);
        u32(data.length, header);
        u16(nameBytes.length, header);
        u16(0, header);
        u16(0, header);
        u16(0, header);
        u16(0, header);
        u32(0, header);
        u32(offset, header);
        central.push(new Uint8Array(header), nameBytes);
        offset += local.length + nameBytes.length + data.length;
      }

      const centralOffset = offset;
      const centralSize = central.reduce((sum, chunk) => sum + chunk.length, 0);
      const end = [];
      u32(0x06054b50, end);
      u16(0, end);
      u16(0, end);
      u16(this.entries.length, end);
      u16(this.entries.length, end);
      u32(centralSize, end);
      u32(centralOffset, end);
      u16(0, end);
      return new Blob([...chunks, ...central, new Uint8Array(end)], { type: "application/zip" });
    }
  }

  window.JSZip = BrowserZip;
});

await page.locator('[data-view="generate"]').click();
await page.waitForSelector("#download-package", { state: "visible", timeout: 10000 });

const recipe = await page.evaluate(() => window.buildRecipe());
const missing = manifestKitIds.filter((kitId) => !recipe.enabledKits.includes(kitId));
if (missing.length) throw new Error(`Recipe is missing kits: ${missing.join(", ")}`);

await writeFile(recipePath, `${JSON.stringify(recipe, null, 2)}\n`, "utf8");

const downloadPromise = page.waitForEvent("download", { timeout: 10000 });
await page.locator("#download-package").click();
const download = await downloadPromise;
const downloadPath = path.join(outputDir, download.suggestedFilename());
await download.saveAs(downloadPath);
await page.screenshot({ path: screenshotPath, fullPage: true });
await browser.close();

if (consoleErrors.some((text) => !text.includes("form-analysis.kit-manifest.json") && !text.includes("404"))) {
  throw new Error(`Browser console errors:\n${consoleErrors.join("\n")}`);
}

console.log(JSON.stringify({
  recipePath,
  downloadPath,
  screenshotPath,
  enabledKits: recipe.enabledKits,
}, null, 2));
