import { useEffect, useMemo, useState } from "react";
import { getApiKeyHeaderName, getApiKeyValue } from "../services/auth";
import { TENANT_STORAGE_KEY } from "../services/tenant";

type FormDef = { id: string; code: string; name?: string };
type RecordRow = { id: string; data?: Record<string, unknown>; created_at?: string };
type FormStats = { form: FormDef; records: RecordRow[] };
type Granularity = "day" | "week" | "month";
type TrendBucket = { bucket_start: string; count: number; sum: number | null; avg: number | null };
type UploadJob = {
  process_id: string;
  filename: string;
  status: "PENDING" | "VALIDATED" | "IMPORTED";
  total_rows: number | null;
  valid_rows: number | null;
  invalid_rows: number | null;
  created_at: string | null;
  actor: string | null;
};
type HistoryResponse = { total: number; page: number; page_size: number; items: UploadJob[] };

function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  const key = getApiKeyValue();
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  if (key) headers[getApiKeyHeaderName()] = key;
  return headers;
}

function numberValue(value: unknown): number | null {
  const n = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function dateString(offsetDays = 0): string {
  const value = new Date();
  value.setDate(value.getDate() + offsetDays);
  return value.toISOString().slice(0, 10);
}

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
}

export function AnalyticsPage() {
  const [items, setItems] = useState<FormStats[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [dateFrom, setDateFrom] = useState(() => dateString(-29));
  const [dateTo, setDateTo] = useState(() => dateString());
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [trend, setTrend] = useState<TrendBucket[]>([]);
  const [history, setHistory] = useState<HistoryResponse>({ total: 0, page: 1, page_size: 50, items: [] });
  const [historyPage, setHistoryPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [trendError, setTrendError] = useState("");
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const formsRes = await fetch("/api/forms", { headers: apiHeaders() });
        if (!formsRes.ok) throw new Error(`forms HTTP ${formsRes.status}`);
        const formsData = await formsRes.json();
        const forms = (Array.isArray(formsData) ? formsData : formsData.forms ?? formsData.items ?? []) as FormDef[];
        const stats = await Promise.all(
          forms.map(async (form) => {
            const res = await fetch(`/api/forms/${encodeURIComponent(form.code)}/records?page=1&page_size=200`, {
              headers: apiHeaders(),
            });
            if (!res.ok) return { form, records: [] };
            const data = await res.json();
            return { form, records: (Array.isArray(data) ? data : data.records ?? data.items ?? []) as RecordRow[] };
          }),
        );
        if (!cancelled) {
          setItems(stats);
          setSelectedCode((current) => current || forms[0]?.code || "");
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedCode) return;
    let cancelled = false;
    async function loadTrend() {
      setTrendError("");
      const params = queryString({ code: selectedCode, date_from: dateFrom, date_to: dateTo, granularity });
      try {
        const res = await fetch(`/api/analytics/trend?${params}`, { headers: apiHeaders() });
        if (!res.ok) throw new Error(`trend HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setTrend(Array.isArray(data.buckets) ? data.buckets : []);
      } catch (err) {
        if (!cancelled) {
          setTrend([]);
          setTrendError(err instanceof Error ? err.message : String(err));
        }
      }
    }
    loadTrend();
    return () => {
      cancelled = true;
    };
  }, [selectedCode, dateFrom, dateTo, granularity]);

  useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      setHistoryError("");
      const params = queryString({
        date_from: dateFrom,
        date_to: dateTo,
        page: historyPage,
        page_size: 50,
      });
      try {
        const res = await fetch(`/api/analytics/upload-history?${params}`, { headers: apiHeaders() });
        if (!res.ok) throw new Error(`upload history HTTP ${res.status}`);
        const data = (await res.json()) as HistoryResponse;
        if (!cancelled) setHistory(data);
      } catch (err) {
        if (!cancelled) {
          setHistory({ total: 0, page: historyPage, page_size: 50, items: [] });
          setHistoryError(err instanceof Error ? err.message : String(err));
        }
      }
    }
    loadHistory();
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, historyPage]);

  const filteredItems = useMemo(
    () =>
      items
        .filter((item) => !selectedCode || item.form.code === selectedCode)
        .map((item) => ({
          ...item,
          records: item.records.filter((record) => {
            const day = record.created_at?.slice(0, 10);
            return !day || ((!dateFrom || day >= dateFrom) && (!dateTo || day <= dateTo));
          }),
        })),
    [items, selectedCode, dateFrom, dateTo],
  );
  const totalRecords = filteredItems.reduce((sum, item) => sum + item.records.length, 0);

  async function exportCsv() {
    setHistoryError("");
    const params = queryString({ date_from: dateFrom, date_to: dateTo });
    try {
      const res = await fetch(`/api/analytics/upload-history/export?${params}`, { headers: apiHeaders() });
      if (!res.ok) throw new Error(`export HTTP ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "upload-history.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section style={{ padding: "1.5rem", maxWidth: 1200 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>資料分析</h2>
        <span style={{ color: "#64748b" }}>{loading ? "載入中..." : `${filteredItems.length} 張表，${totalRecords} 筆資料`}</span>
      </div>

      {error ? <div style={errorStyle}>載入失敗：{error}。請先登入或確認 API key。</div> : null}

      <div style={{ ...cardStyle, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end", marginBottom: 18 }}>
        <label style={labelStyle}>
          表單
          <select value={selectedCode} onChange={(event) => { setSelectedCode(event.target.value); setHistoryPage(1); }} style={inputStyle}>
            {items.map((item) => <option key={item.form.code} value={item.form.code}>{item.form.name || item.form.code}</option>)}
          </select>
        </label>
        <label style={labelStyle}>開始日期<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} style={inputStyle} /></label>
        <label style={labelStyle}>結束日期<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} style={inputStyle} /></label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 18 }}>
        {filteredItems.map((item) => (
          <div key={item.form.code} style={cardStyle}>
            <div style={{ color: "#64748b", fontSize: 13 }}>{item.form.name || item.form.code}</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{item.records.length}</div>
            <div style={{ color: "#64748b", fontSize: 13 }}>筆資料</div>
          </div>
        ))}
      </div>

      <section style={{ ...cardStyle, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>匯入趨勢</h3>
          <div style={{ display: "flex", gap: 6 }}>
            {(["day", "week", "month"] as Granularity[]).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setGranularity(value)}
                style={{ ...tabStyle, background: granularity === value ? "#2563eb" : "#e2e8f0", color: granularity === value ? "#fff" : "#334155" }}
              >
                {{ day: "日", week: "週", month: "月" }[value]}
              </button>
            ))}
          </div>
        </div>
        {trendError ? <div style={errorStyle}>趨勢載入失敗：{trendError}</div> : <TrendChart buckets={trend} />}
      </section>

      <div style={{ display: "grid", gap: 14, marginBottom: 18 }}>
        {filteredItems.map((item) => <FormAnalysis key={item.form.code} item={item} />)}
      </div>

      <section style={{ ...cardStyle, overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 12 }}>
          <h3 style={{ margin: 0 }}>上傳紀錄</h3>
          <button type="button" onClick={exportCsv} style={buttonStyle}>匯出 CSV</button>
        </div>
        <div style={{ color: "#64748b", fontSize: 12, marginBottom: 8 }}>只依日期區間篩選（檔案上傳工作沒有對應單一表單，跟上方表單下拉無關）。</div>
        {historyError ? <div style={errorStyle}>上傳紀錄載入失敗：{historyError}</div> : null}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead><tr style={{ background: "#f8fafc", textAlign: "left" }}>
              {["建立時間", "工作序號", "檔名", "狀態", "總筆數", "有效筆數", "無效筆數", "操作者"].map((heading) => <th key={heading} style={thStyle}>{heading}</th>)}
            </tr></thead>
            <tbody>
              {history.items.map((job, index) => (
                <tr key={`${job.process_id}-${index}`} style={{ borderTop: "1px solid #eef2f7" }}>
                  <td style={tdStyle}>{job.created_at ? new Date(job.created_at).toLocaleString() : "—"}</td>
                  <td style={tdStyle} title={job.process_id}>{job.process_id.slice(0, 8)}</td><td style={tdStyle}>{job.filename}</td><td style={tdStyle}>{job.status}</td>
                  <td style={tdStyle}>{job.total_rows ?? "—"}</td><td style={tdStyle}>{job.valid_rows ?? "—"}</td><td style={tdStyle}>{job.invalid_rows ?? "—"}</td>
                  <td style={tdStyle}>{job.actor || "—"}</td>
                </tr>
              ))}
              {!history.items.length ? <tr><td colSpan={8} style={{ ...tdStyle, textAlign: "center", color: "#64748b" }}>沒有上傳紀錄</td></tr> : null}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, paddingTop: 12 }}>
          <button type="button" disabled={history.page <= 1} onClick={() => setHistoryPage((page) => Math.max(1, page - 1))}>上一頁</button>
          <span>第 {history.page} 頁，共 {history.total} 筆</span>
          <button type="button" disabled={history.page * history.page_size >= history.total} onClick={() => setHistoryPage((page) => page + 1)}>下一頁</button>
        </div>
      </section>
    </section>
  );
}

function TrendChart({ buckets }: { buckets: TrendBucket[] }) {
  if (!buckets.length) return <div style={{ color: "#64748b", padding: 24, textAlign: "center" }}>此區間沒有資料</div>;
  const width = 900;
  const height = 260;
  const padding = 36;
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);
  const step = (width - padding * 2) / Math.max(buckets.length, 1);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="匯入筆數趨勢圖" style={{ width: "100%", minHeight: 220 }}>
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#cbd5e1" />
      {buckets.map((bucket, index) => {
        const barHeight = (bucket.count / max) * (height - padding * 2);
        const x = padding + index * step + step * 0.15;
        return (
          <g key={bucket.bucket_start}>
            <title>{`${bucket.bucket_start}: ${bucket.count}`}</title>
            <rect x={x} y={height - padding - barHeight} width={Math.max(step * 0.7, 2)} height={barHeight} fill="#2563eb" rx="2" />
            {(buckets.length <= 12 || index % Math.ceil(buckets.length / 12) === 0) ? (
              <text x={x + step * 0.35} y={height - 12} textAnchor="middle" fontSize="10" fill="#64748b">{bucket.bucket_start.slice(5)}</text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

function FormAnalysis({ item }: { item: FormStats }) {
  const rows = useMemo(() => {
    const fields = new Map<string, number[]>();
    item.records.forEach((record) => {
      Object.entries(record.data || {}).forEach(([key, value]) => {
        const n = numberValue(value);
        if (n == null) return;
        fields.set(key, [...(fields.get(key) || []), n]);
      });
    });
    return Array.from(fields.entries()).map(([field, values]) => {
      const sum = values.reduce((a, b) => a + b, 0);
      return { field, count: values.length, sum, avg: sum / values.length, min: Math.min(...values), max: Math.max(...values) };
    });
  }, [item.records]);

  return (
    <section style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "12px 14px", borderBottom: "1px solid #e5e7eb", fontWeight: 700 }}>{item.form.name || item.form.code}</div>
      <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead><tr style={{ background: "#f8fafc", textAlign: "left" }}>{["數值欄位", "筆數", "總和", "平均", "最小", "最大"].map((heading) => <th key={heading} style={thStyle}>{heading}</th>)}</tr></thead>
        <tbody>
          {rows.map((row) => <tr key={row.field} style={{ borderTop: "1px solid #eef2f7" }}>
            <td style={tdStyle}>{row.field}</td><td style={tdStyle}>{row.count}</td><td style={tdStyle}>{row.sum.toFixed(2)}</td>
            <td style={tdStyle}>{row.avg.toFixed(2)}</td><td style={tdStyle}>{row.min.toFixed(2)}</td><td style={tdStyle}>{row.max.toFixed(2)}</td>
          </tr>)}
          {!rows.length ? <tr><td colSpan={6} style={{ ...tdStyle, textAlign: "center", color: "#64748b" }}>沒有可統計的數值欄位</td></tr> : null}
        </tbody>
      </table></div>
    </section>
  );
}

const cardStyle: React.CSSProperties = { background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, padding: 14 };
const errorStyle: React.CSSProperties = { marginBottom: 12, padding: "10px 12px", borderRadius: 8, background: "#fee2e2", color: "#991b1b" };
const labelStyle: React.CSSProperties = { display: "grid", gap: 4, color: "#475569", fontSize: 13 };
const inputStyle: React.CSSProperties = { minHeight: 36, padding: "6px 8px", border: "1px solid #cbd5e1", borderRadius: 6 };
const buttonStyle: React.CSSProperties = { minHeight: 36, padding: "6px 12px", border: 0, borderRadius: 6, background: "#2563eb", color: "#fff", cursor: "pointer" };
const tabStyle: React.CSSProperties = { padding: "6px 12px", border: 0, borderRadius: 6, cursor: "pointer" };
const thStyle: React.CSSProperties = { padding: "10px 12px", whiteSpace: "nowrap", borderBottom: "1px solid #e5e7eb" };
const tdStyle: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap", verticalAlign: "top" };
