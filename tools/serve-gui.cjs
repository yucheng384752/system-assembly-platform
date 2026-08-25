const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const opsLog = path.join(dataDir, "operations.jsonl");
const machinesFile = path.join(dataDir, "machines.json");
const port = Number(process.env.PORT || 4174);
const host = process.env.HOST || "127.0.0.1";

// ── System bundle 來源目錄解析 ────────────────────────────────────────────────
// install-wizard 需要 system/backend/requirements.txt 才能通過路徑驗證。
// 下載 zip 時把此目錄一併打包，避免使用者解壓後缺少 system/。
function resolveSystemDir() {
  // 1. 環境變數明確指定
  if (process.env.SYSTEM_DIR && fs.existsSync(path.join(process.env.SYSTEM_DIR, "backend", "requirements.txt"))) {
    return process.env.SYSTEM_DIR;
  }
  // 2. 自動偵測常見路徑（已組裝的 dist 部署包）
  const candidates = [
    path.join(root, "dist", "client-deploy-gui-selected-form-system", "system"),
    path.join(root, "dist", "generated-system"),
    path.join(root, "generated", "mvp-import-flow", "form-analysis-server"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "backend", "requirements.txt"))) return c;
  }
  return null;
}

// 打包時排除的目錄 / 副檔名
const BUNDLE_SKIP_DIRS = new Set(["node_modules", "__pycache__", ".venv", "logs", ".git"]);
const BUNDLE_SKIP_EXT = new Set([".pyc", ".pyo", ".log"]);
const BUNDLE_SKIP_FILES = new Set([".env"]);
const REQUIRED_ARTIFACTS = ["install-wizard.exe", "install-wizard.py"];

function packageManifest() {
  const artifacts = REQUIRED_ARTIFACTS.map((name) => {
    const filePath = path.join(__dirname, name);
    return { name, path: filePath, present: fs.existsSync(filePath) };
  });
  const missing = artifacts.filter((a) => !a.present).map((a) => a.name);
  return { ok: missing.length === 0, artifacts, missing };
}

function handlePackageManifest(res) {
  json(res, 200, packageManifest());
}

function readJsonRelative(relPath) {
  const filePath = path.join(root, relPath);
  const result = { path: relPath.replace(/\\/g, "/"), exists: fs.existsSync(filePath), data: null };
  if (!result.exists) return result;
  try {
    const bytes = fs.readFileSync(filePath);
    const isUtf16Le = (bytes[0] === 0xff && bytes[1] === 0xfe) || bytes.slice(0, 80).some((byte, index) => index % 2 === 1 && byte === 0);
    const text = bytes.toString(isUtf16Le ? "utf16le" : "utf8").replace(/^\uFEFF/, "");
    result.data = JSON.parse(text);
  } catch (err) {
    result.error = err.message;
  }
  return result;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function deriveKitEdges(kits) {
  const ids = new Set(kits.map((kit) => kit.id || kit.kit || kit));
  const edges = [];
  for (const kit of kits) {
    const target = kit.id || kit.kit || kit;
    const deps = asArray(kit.dependencies || kit.dependsOn || kit.requires);
    for (const dep of deps) {
      if (ids.has(dep)) edges.push({ from: dep, to: target });
    }
  }
  return edges;
}

function normalizeDbTables(dbPlan) {
  const tables = dbPlan?.tables;
  if (!tables) return [];
  if (Array.isArray(tables)) return tables;
  return Object.entries(tables).map(([name, value]) => ({ name, ...(value || {}) }));
}

function ensurePackageArtifacts(res) {
  const manifest = packageManifest();
  if (manifest.ok) return true;
  json(res, 422, {
    error: "Package incomplete",
    missing: manifest.missing,
    message: `Required files missing: ${manifest.missing.join(", ")}. Run build-wizard-exe.ps1 before packaging.`,
  });
  return false;
}

function walkSystemDir(baseDir, relDir = "") {
  const out = [];
  const absDir = path.join(baseDir, relDir);
  let entries;
  try { entries = fs.readdirSync(absDir, { withFileTypes: true }); }
  catch { return out; }
  for (const e of entries) {
    const relPath = relDir ? `${relDir}/${e.name}` : e.name;
    if (e.isDirectory()) {
      if (BUNDLE_SKIP_DIRS.has(e.name)) continue;
      out.push(...walkSystemDir(baseDir, relPath));
    } else if (e.isFile()) {
      if (BUNDLE_SKIP_EXT.has(path.extname(e.name))) continue;
      if (BUNDLE_SKIP_FILES.has(e.name)) continue;
      try {
        const buf = fs.readFileSync(path.join(absDir, e.name));
        out.push({ path: relPath, b64: buf.toString("base64") });
      } catch { /* skip unreadable */ }
    }
  }
  return out;
}

function handleSystemBundle(res) {
  if (!ensurePackageArtifacts(res)) return;
  const sysDir = resolveSystemDir();
  if (!sysDir) {
    json(res, 404, { error: "system dir not found (set SYSTEM_DIR or assemble a deploy package first)", available: false });
    return;
  }
  const files = walkSystemDir(sysDir);
  json(res, 200, { available: true, source: sysDir, count: files.length, files });
}

// ── License 簽發（偵測到 issuer 私鑰時啟用）────────────────────────────────────
// 必須使用 tools/keys/signing-private-key.pem —— 這是唯一跟每個生成套件
// license.py 內嵌公鑰配對的正式金鑰。舊檔名 issuer-private-key.pem 是另一組
// 不相干的金鑰，會簽出無法通過 backend license.py 驗證的 license.lic。
function resolveIssuerKey() {
  const candidates = [
    process.env.ISSUER_KEY_PATH,
    path.join(__dirname, "keys", "signing-private-key.pem"),
    path.join(dataDir, "signing-private-key.pem"),
  ].filter(Boolean);
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

function handleLicenseStatus(res) {
  json(res, 200, { available: resolveIssuerKey() !== null });
}

function handleIssueLicense(req, res) {
  let raw = "";
  req.on("data", (c) => { raw += c; });
  req.on("end", () => {
    const keyPath = resolveIssuerKey();
    if (!keyPath) {
      json(res, 404, { error: "issuer private key not configured (place signing-private-key.pem in tools/keys/, or run tools/generate-license-keys.ps1)" });
      return;
    }
    let body;
    try { body = JSON.parse(raw || "{}"); }
    catch { json(res, 400, { error: "invalid JSON" }); return; }

    const pubkey = String(body.pubkey || "").trim();
    const validationError = validatePublicKeyPem(pubkey);
    if (validationError) {
      json(res, 400, { error: validationError });
      return;
    }

    // Payload — 欄位需與 backend license.py 對齊
    const days = Number(body.days) > 0 ? Number(body.days) : 365;
    const expiresAt = new Date(Date.now() + days * 86400_000).toISOString();
    const payloadObj = {
      licensee: body.licensee || { name: "", email: "" },
      machinePublicKey: pubkey,
      issuedAt: new Date().toISOString(),
      expiresAt,
    };
    const payloadStr = JSON.stringify(payloadObj);

    try {
      const privateKeyPem = fs.readFileSync(keyPath, "utf8");
      const signer = crypto.createSign("RSA-SHA256");
      signer.update(payloadStr, "utf8");
      signer.end();
      const signature = signer.sign({
        key: privateKeyPem,
        padding: crypto.constants.RSA_PKCS1_PSS_PADDING,
        saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST,
      }, "base64");
      // license.lic 結構：{ payload, signature }（與 license.py verify_license() 對齊）
      json(res, 200, { ok: true, license: { payload: payloadStr, signature } });
    } catch (e) {
      json(res, 500, { error: `signing failed: ${e.message}` });
    }
  });
}

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

// Ensure data/ exists
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
}

function validatePublicKeyPem(pubkey) {
  if (!pubkey.includes("-----BEGIN PUBLIC KEY-----") || !pubkey.includes("-----END PUBLIC KEY-----")) {
    return "invalid pubkey (must use BEGIN/END PUBLIC KEY PEM format)";
  }
  try {
    const key = crypto.createPublicKey(pubkey);
    if (key.asymmetricKeyType !== "rsa") return "invalid pubkey (RSA public key required)";
    return "";
  } catch (err) {
    return `invalid pubkey (${err.message})`;
  }
}

function handleApiLog(req, res) {
  let raw = "";
  req.on("data", (chunk) => { raw += chunk; });
  req.on("end", () => {
    try {
      const body = JSON.parse(raw || "{}");
      const record = {
        ts: new Date().toISOString(),
        ip: req.socket.remoteAddress || "unknown",
        action: String(body.action || ""),
        recipeName: String(body.recipeName || ""),
        kits: Array.isArray(body.kits) ? body.kits : [],
        licensee: String(body.licensee || ""),
      };
      fs.appendFile(opsLog, JSON.stringify(record) + "\n", (err) => {
        if (err) { json(res, 500, { error: "write failed" }); return; }
        json(res, 200, { ok: true });
      });
    } catch {
      json(res, 400, { error: "invalid JSON" });
    }
  });
}

function handleApiMachines(res) {
  fs.readFile(machinesFile, "utf8", (err, data) => {
    let machines = [];
    if (!err) { try { machines = JSON.parse(data); } catch { /* skip */ } }
    json(res, 200, machines);
  });
}

function handleRegisterMachine(req, res) {
  let raw = "";
  req.on("data", (c) => { raw += c; });
  req.on("end", () => {
    try {
      const body = JSON.parse(raw || "{}");
      const pubkey = String(body.pubkey || "").trim();
      const validationError = validatePublicKeyPem(pubkey);
      if (validationError) {
        json(res, 400, { error: validationError });
        return;
      }
      fs.readFile(machinesFile, "utf8", (err, data) => {
        let machines = [];
        if (!err) { try { machines = JSON.parse(data); } catch { /* skip */ } }
        if (!machines.some((m) => m.pubkey === pubkey)) {
          machines.push({ pubkey, registeredAt: new Date().toISOString() });
        }
        fs.writeFile(machinesFile, JSON.stringify(machines, null, 2), (e) => {
          if (e) { json(res, 500, { error: "write failed" }); return; }
          json(res, 200, { ok: true });
        });
      });
    } catch {
      json(res, 400, { error: "invalid JSON" });
    }
  });
}

function handleApiLogs(res) {
  fs.readFile(opsLog, "utf8", (err, data) => {
    const lines = err ? [] : data.trim().split("\n").filter(Boolean);
    const records = [];
    for (const line of lines) {
      try { records.push(JSON.parse(line)); } catch { /* skip malformed */ }
    }
    json(res, 200, records);
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);
  const { pathname } = url;

  // API routes
  if (pathname === "/api/log" && req.method === "POST") {
    handleApiLog(req, res);
    return;
  }
  if (pathname === "/api/logs" && req.method === "GET") {
    handleApiLogs(res);
    return;
  }
  if (pathname === "/api/get-machine-pubkey-script" && req.method === "GET") {
    const p = path.join(__dirname, "get-machine-pubkey.sh");
    fs.readFile(p, (err, data) => {
      if (err) { res.writeHead(404); res.end("Not found"); return; }
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8", "Content-Disposition": 'attachment; filename="get-machine-pubkey.sh"' });
      res.end(data);
    });
    return;
  }
  if (pathname === "/api/machines" && req.method === "GET") {
    handleApiMachines(res);
    return;
  }
  if (pathname === "/api/register-machine" && req.method === "POST") {
    handleRegisterMachine(req, res);
    return;
  }
  if (pathname === "/api/wizard-py" && req.method === "GET") {
    const p = path.join(__dirname, "install-wizard.py");
    fs.readFile(p, (err, data) => {
      if (err) { res.writeHead(404); res.end("Not found"); return; }
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8", "Content-Length": data.length });
      res.end(data);
    });
    return;
  }
  if (pathname === "/api/wizard-exe" && req.method === "GET") {
    const p = path.join(__dirname, "install-wizard.exe");
    fs.readFile(p, (err, data) => {
      if (err) { res.writeHead(404); res.end("Not found"); return; }
      res.writeHead(200, { "Content-Type": "application/octet-stream", "Content-Length": data.length });
      res.end(data);
    });
    return;
  }
  if (pathname === "/api/system-bundle" && req.method === "GET") {
    handleSystemBundle(res);
    return;
  }
  if (pathname === "/api/package-manifest" && req.method === "GET") {
    handlePackageManifest(res);
    return;
  }
  if (pathname === "/api/license-status" && req.method === "GET") {
    handleLicenseStatus(res);
    return;
  }
  if (pathname === "/api/issue-license" && req.method === "POST") {
    handleIssueLicense(req, res);
    return;
  }

  // Kit manifest — gui/app.js fetches this from the repo-root kits/ directory, which sits
  // outside the gui/ static root below, so it needs its own route.
  if (pathname.startsWith("/kits/") && req.method === "GET") {
    const kitsRoot = path.join(root, "kits");
    const relPath = decodeURIComponent(pathname).replace(/^\/kits\//, "");
    const filePath = path.normalize(path.join(kitsRoot, relPath));
    if (!filePath.startsWith(kitsRoot)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
    fs.readFile(filePath, (error, data) => {
      if (error) { res.writeHead(404); res.end("Not found"); return; }
      res.writeHead(200, { "Content-Type": types[path.extname(filePath)] || "application/octet-stream" });
      res.end(data);
    });
    return;
  }

  // Static files — serve from gui/ as root so ./styles.css and ./app.js resolve correctly
  const guiRoot = path.join(root, "gui");
  const relPath = pathname === "/" ? "index.html" : decodeURIComponent(pathname).replace(/^\//, "");
  const filePath = path.normalize(path.join(guiRoot, relPath));
  if (!filePath.startsWith(guiRoot)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": types[path.extname(filePath)] || "application/octet-stream" });
    res.end(data);
  });
});

server.on("error", (err) => {
  if (err.code === "EADDRINUSE") {
    console.error(`\n錯誤：連接埠 ${port} 已被佔用。`);
    console.error(`請先關閉佔用該連接埠的程式，或指定其他連接埠：`);
    console.error(`  PORT=4174 node tools/serve-gui.cjs\n`);
    process.exit(1);
  }
  throw err;
});

server.listen(port, host, () => {
  console.log(`Serving ${root} at http://${host}:${port}/`);
  console.log(`API: POST /api/log  GET /api/logs`);
  console.log(`Logs: ${opsLog}`);
});
