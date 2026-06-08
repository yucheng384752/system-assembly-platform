const http = require("http");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const opsLog = path.join(dataDir, "operations.jsonl");
const port = Number(process.env.PORT || 4174);
const host = process.env.HOST || "127.0.0.1";

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
