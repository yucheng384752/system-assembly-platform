import { useEffect, useMemo, useState } from "react";
import { getApiKeyHeaderName, getApiKeyValue } from "../services/auth";

type FormDef = { code: string; name?: string };
type RecordRow = { id: string; data?: Record<string, unknown> };
type FormStats = { form: FormDef; records: RecordRow[] };

function apiHeaders(): HeadersInit {
  const key = getApiKeyValue();
  return key ? { [getApiKeyHeaderName()]: key } : {};
}

function numberValue(value: unknown): number | null {
  const n = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

export function AnalyticsPage() {
  const [items, setItems] = useState<FormStats[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const formsRes = await fetch("/api/forms", { headers: apiHeaders() });
        if (!formsRes.ok) throw new Error(`forms HTTP ${formsRes.status}`);
        const formsData = await formsRes.json();
        const allForms = (Array.isArray(formsData) ? formsData : formsData.forms ?? formsData.items ?? []) as FormDef[];
        const forms = allForms.filter((f) => String(f.code || "").startsWith("daihui_"));
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
        if (!cancelled) setItems(stats);
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

  const totalRecords = items.reduce((sum, item) => sum + item.records.length, 0);

  return (
    <section style={{ padding: "1.5rem", maxWidth: 1200 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>資料分析</h2>
        <span style={{ color: "#64748b" }}>{loading ? "載入中..." : `${items.length} 張表，${totalRecords} 筆資料`}</span>
      </div>

      {error ? <div style={errorStyle}>載入失敗：{error}。請先登入或確認 API key。</div> : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 18 }}>
        {items.map((item) => (
          <div key={item.form.code} style={cardStyle}>
            <div style={{ color: "#64748b", fontSize: 13 }}>{item.form.name || item.form.code}</div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>{item.records.length}</div>
            <div style={{ color: "#64748b", fontSize: 13 }}>筆資料</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gap: 14 }}>
        {items.map((item) => (
          <FormAnalysis key={item.form.code} item={item} />
        ))}
      </div>
    </section>
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
      return {
        field,
        count: values.length,
        sum,
        avg: values.length ? sum / values.length : 0,
        min: Math.min(...values),
        max: Math.max(...values),
      };
    });
  }, [item.records]);

  return (
    <section style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "12px 14px", borderBottom: "1px solid #e5e7eb", fontWeight: 700 }}>
        {item.form.name || item.form.code}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f8fafc", textAlign: "left" }}>
              {["數值欄位", "筆數", "總和", "平均", "最小", "最大"].map((h) => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.field} style={{ borderTop: "1px solid #eef2f7" }}>
                <td style={tdStyle}>{row.field}</td>
                <td style={tdStyle}>{row.count}</td>
                <td style={tdStyle}>{row.sum.toFixed(2)}</td>
                <td style={tdStyle}>{row.avg.toFixed(2)}</td>
                <td style={tdStyle}>{row.min.toFixed(2)}</td>
                <td style={tdStyle}>{row.max.toFixed(2)}</td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ ...tdStyle, textAlign: "center", color: "#64748b" }}>
                  沒有可統計的數值欄位
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 14,
};
const errorStyle: React.CSSProperties = {
  marginBottom: 12,
  padding: "10px 12px",
  borderRadius: 8,
  background: "#fee2e2",
  color: "#991b1b",
};
const thStyle: React.CSSProperties = { padding: "10px 12px", whiteSpace: "nowrap", borderBottom: "1px solid #e5e7eb" };
const tdStyle: React.CSSProperties = { padding: "9px 12px", whiteSpace: "nowrap", verticalAlign: "top" };
