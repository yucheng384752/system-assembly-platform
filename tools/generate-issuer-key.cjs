#!/usr/bin/env node
/**
 * generate-issuer-key.cjs — 產生 License 簽發者 (issuer) 金鑰對
 *
 * 流程：
 *   1. 產生 RSA-2048 金鑰對
 *   2. 私鑰寫入 tools/issuer-private-key.pem（serve-gui.cjs 簽發 license 用，勿外流）
 *   3. 公鑰自動寫入所有 license.py 的 _PUBLIC_KEY_PEM（後端驗證 license 簽名用）
 *
 * 用法：node tools/generate-issuer-key.cjs [--force]
 *   --force：覆蓋已存在的私鑰（會使既有 license 失效）
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const root = path.resolve(__dirname, "..");
const privPath = path.join(__dirname, "issuer-private-key.pem");
const force = process.argv.includes("--force");

if (fs.existsSync(privPath) && !force) {
  console.error(`私鑰已存在：${privPath}`);
  console.error(`如需重新產生請加 --force（注意：會使既有 license.lic 全部失效）`);
  process.exit(1);
}

console.log("產生 RSA-2048 issuer 金鑰對...");
const { publicKey, privateKey } = crypto.generateKeyPairSync("rsa", {
  modulusLength: 2048,
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});

// 1. 寫私鑰
fs.writeFileSync(privPath, privateKey, { mode: 0o600 });
console.log(`✓ 私鑰已寫入：${privPath}`);

// 2. 找出所有 license.py 並更新 _PUBLIC_KEY_PEM
const licensePyPaths = [
  path.join(root, "kits", "platform-core-kit", "src", "backend", "app", "core", "license.py"),
  path.join(root, "dist", "client-deploy-gui-selected-form-system", "system", "backend", "app", "core", "license.py"),
  path.join(root, "dist", "generated-system", "backend", "app", "core", "license.py"),
];

const pubTrimmed = publicKey.trim();
let patched = 0;
for (const p of licensePyPaths) {
  if (!fs.existsSync(p)) continue;
  let src = fs.readFileSync(p, "utf8");
  // 取代 _PUBLIC_KEY_PEM = """..."""
  const re = /_PUBLIC_KEY_PEM = """[\s\S]*?-----END PUBLIC KEY-----"""/;
  if (re.test(src)) {
    src = src.replace(re, `_PUBLIC_KEY_PEM = """${pubTrimmed}"""`);
    fs.writeFileSync(p, src, "utf8");
    console.log(`✓ 已更新公鑰：${path.relative(root, p)}`);
    patched++;
  } else {
    console.warn(`⚠ 找不到 _PUBLIC_KEY_PEM 區塊：${path.relative(root, p)}`);
  }
}

console.log("");
console.log("=".repeat(60));
console.log(`完成：私鑰 1 個，公鑰同步 ${patched} 個 license.py`);
console.log("=".repeat(60));
console.log("");
console.log("公鑰（已嵌入 license.py）：");
console.log(pubTrimmed);
console.log("");
console.log("注意事項：");
console.log("  - issuer-private-key.pem 勿提交 git、勿外流");
console.log("  - 重新產生金鑰會使所有既有 license.lic 失效");
console.log("  - 之後 serve-gui.cjs 下載 zip 時會自動簽發 license.lic");
