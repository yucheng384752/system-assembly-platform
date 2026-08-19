#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8000";
const TENANT_API_KEY =
  process.env.TENANT_API_KEY || "r-GwQLiW-b5j1o4iOazD4fxzWlUJd6l96WI8wyFZ2nM";
const CSV_DIR =
  process.env.CSV_DIR || "C:\\Users\\gslab\\Desktop\\岱暉資料表\\處理完畢";

const FILES = [
  { filenames: ["entry.csv", "entry_horizontal.csv"], tableCode: "daihui_entry" },
  { filenames: ["inspection.csv", "inspection_horizontal.csv"], tableCode: "daihui_inspection" },
  { filenames: ["material.csv", "material_horizontal.csv"], tableCode: "daihui_material" },
  { filenames: ["production.csv", "production_horizontal.csv"], tableCode: "daihui_production" },
  { filenames: ["quality.csv", "quality_horizontal.csv"], tableCode: "daihui_quality" },
];

let pass = 0;
let fail = 0;

function ok(message) {
  pass += 1;
  console.log(`  [PASS] ${message}`);
}

function bad(message) {
  fail += 1;
  console.log(`  [FAIL] ${message}`);
}

function headers(extra = {}) {
  return { "X-API-Key": TENANT_API_KEY, ...extra };
}

async function request(method, apiPath, options = {}) {
  const response = await fetch(`${BASE_URL}${apiPath}`, {
    method,
    headers: options.headers ?? headers(),
    body: options.body,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  return { status: response.status, data };
}

function resolveCsvFile(filenames) {
  for (const filename of filenames) {
    const fullPath = path.join(CSV_DIR, filename);
    if (existsSync(fullPath)) return { filename, fullPath };
  }
  return { filename: filenames[0], fullPath: path.join(CSV_DIR, filenames[0]) };
}

async function uploadCsv(fileSpec) {
  const { filename, fullPath } = resolveCsvFile(fileSpec.filenames);
  if (!existsSync(fullPath)) {
    throw new Error(`CSV not found: ${fullPath}`);
  }
  const bytes = await readFile(fullPath);
  const form = new FormData();
  form.append("table_code", fileSpec.tableCode);
  form.append("allow_duplicate", "true");
  form.append("files", new Blob([bytes], { type: "text/csv" }), filename);
  const result = await request("POST", "/api/v2/import/jobs", {
    headers: headers(),
    body: form,
  });
  return { ...result, filename };
}

async function waitForStatus(jobId, statuses, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = {};
  while (Date.now() < deadline) {
    const result = await request("GET", `/api/v2/import/jobs/${jobId}`);
    last = result.data;
    if (statuses.has(last.status)) return last;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return last;
}

async function main() {
  console.log("=".repeat(60));
  console.log("  Daihui CSV Upload E2E Test");
  console.log("=".repeat(60));
  console.log(`Backend: ${BASE_URL}`);
  console.log(`CSV_DIR: ${CSV_DIR}`);

  try {
    const health = await request("GET", "/healthz");
    if (health.status === 200) {
      ok(`GET /healthz -> HTTP ${health.status}`);
    } else {
      bad(`GET /healthz -> HTTP ${health.status}`);
      process.exit(1);
    }
  } catch (error) {
    bad(`Backend is not reachable at ${BASE_URL}: ${error.message}`);
    process.exit(1);
  }

  const readyJobs = [];
  console.log("\n[Phase 1] Upload CSVs and wait for READY");
  for (const fileSpec of FILES) {
    try {
      const upload = await uploadCsv(fileSpec);
      if (![200, 201].includes(upload.status) || !upload.data.id) {
        bad(`${fileSpec.tableCode}: upload HTTP ${upload.status} ${JSON.stringify(upload.data)}`);
        continue;
      }
      ok(`${upload.filename} -> ${fileSpec.tableCode} job ${String(upload.data.id).slice(0, 8)}`);
      const state = await waitForStatus(upload.data.id, new Set(["READY", "FAILED", "COMPLETED"]), 30000);
      if (state.status === "READY") {
        readyJobs.push({ ...fileSpec, filename: upload.filename, jobId: upload.data.id });
        ok(`${upload.filename} -> READY (error_count=${state.error_count ?? "?"})`);
      } else {
        bad(`${upload.filename} -> ${state.status ?? "UNKNOWN"} (expected READY)`);
      }
    } catch (error) {
      bad(`${fileSpec.tableCode}: ${error.message}`);
    }
  }

  console.log("\n[Phase 2] Commit jobs");
  for (const job of readyJobs) {
    const result = await request("POST", `/api/v2/import/jobs/${job.jobId}/commit`, {
      headers: headers({ "Content-Type": "application/json" }),
      body: "{}",
    });
    if (![200, 202].includes(result.status)) {
      bad(`${job.filename}: commit HTTP ${result.status} ${JSON.stringify(result.data)}`);
      continue;
    }
    const state = await waitForStatus(job.jobId, new Set(["COMPLETED", "FAILED"]), 20000);
    if (state.status === "COMPLETED") {
      ok(`${job.filename} -> COMPLETED (committed_count=${state.committed_count ?? "?"})`);
    } else {
      bad(`${job.filename} -> ${state.status ?? "UNKNOWN"} after commit`);
    }
  }

  console.log("\n[Phase 3] Verify generic_records via API");
  for (const fileSpec of FILES) {
    const result = await request("GET", `/api/forms/${fileSpec.tableCode}/records`);
    if (result.status !== 200) {
      bad(`${fileSpec.tableCode}: GET records HTTP ${result.status}`);
      continue;
    }
    const records = Array.isArray(result.data)
      ? result.data
      : result.data.records ?? result.data.items ?? [];
    const total = Number(result.data.total ?? records.length ?? 0);
    if (total > 0) {
      ok(`${fileSpec.tableCode}: ${total} persisted record(s)`);
    } else {
      bad(`${fileSpec.tableCode}: 0 persisted records`);
    }
  }

  console.log(`\n${"=".repeat(60)}`);
  console.log(`  PASS: ${pass}  FAIL: ${fail}`);
  console.log("=".repeat(60));
  process.exit(fail === 0 ? 0 : 1);
}

main().catch((error) => {
  bad(error.stack || error.message);
  process.exit(1);
});
