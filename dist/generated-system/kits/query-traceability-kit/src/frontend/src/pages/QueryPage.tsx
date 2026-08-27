import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import "../styles/query-page.css";

interface RecordEntry {
  id: string;
  lot_no_raw: string;
  data: Record<string, unknown>;
  created_at: string | null;
}

interface StationResult {
  station_code: string;
  station_name: string;
  records: RecordEntry[];
}

interface TraceNode {
  station_code: string;
  station_name: string;
  record: RecordEntry;
  linked_to: TraceNode[];
}

type ViewMode = "search" | "trace";

export function QueryPage() {
  const { t } = useTranslation();
  const [lotNo, setLotNo] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("search");
  const [searchResults, setSearchResults] = useState<StationResult[] | null>(null);
  const [traceResults, setTraceResults] = useState<TraceNode[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runQuery = useCallback(async (q: string, mode: ViewMode) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setTraceResults(null);
    try {
      const endpoint = mode === "trace"
        ? `/api/v2/query/trace/${encodeURIComponent(q)}`
        : `/api/v2/query/lot/${encodeURIComponent(q)}`;
      const res = await fetch(endpoint);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as any).detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (mode === "trace") setTraceResults(data);
      else setSearchResults(data);
    } catch (e: any) {
      setError(e.message || t("query.error", "查詢失敗"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const handleSearch = () => runQuery(lotNo, viewMode);

  const hasResults =
    (searchResults !== null && searchResults.length > 0) ||
    (traceResults !== null && traceResults.length > 0);
  const isEmpty =
    (searchResults !== null && searchResults.length === 0) ||
    (traceResults !== null && traceResults.length === 0);

  return (
    <div className="query-page">
      <h2 className="query-title">{t("query.title", "資料查詢")}</h2>

      {/* Mode toggle */}
      <div className="query-mode-bar">
        <button
          className={`query-mode-btn${viewMode === "search" ? " active" : ""}`}
          onClick={() => setViewMode("search")}
        >
          {t("query.mode.search", "批號查詢")}
        </button>
        <button
          className={`query-mode-btn${viewMode === "trace" ? " active" : ""}`}
          onClick={() => setViewMode("trace")}
        >
          {t("query.mode.trace", "追溯路徑")}
        </button>
      </div>

      {/* Search bar */}
      <div className="query-bar">
        <input
          type="text"
          value={lotNo}
          onChange={(e) => setLotNo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder={t("query.placeholder", "請輸入批號")}
          className="query-input"
          disabled={loading}
        />
        <button
          onClick={handleSearch}
          disabled={loading || !lotNo.trim()}
          className="query-btn"
        >
          {loading ? t("query.searching", "查詢中…") : t("query.search", "查詢")}
        </button>
      </div>

      {/* Error */}
      {error && <div className="query-error">{error}</div>}

      {/* Empty */}
      {isEmpty && !loading && (
        <div className="query-empty">{t("query.noResults", "查無資料")}</div>
      )}

      {/* Search results */}
      {searchResults && searchResults.length > 0 && (
        <div className="query-results">
          {searchResults.map((station) => (
            <StationCard key={station.station_code} station={station} />
          ))}
        </div>
      )}

      {/* Trace results */}
      {traceResults && traceResults.length > 0 && (
        <div className="query-results">
          {traceResults.map((node, i) => (
            <TraceNodeCard key={i} node={node} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
}

function StationCard({ station }: { station: StationResult }) {
  return (
    <div className="station-card">
      <div className="station-header">
        <span className="station-name">{station.station_name}</span>
        <span className="station-code">{station.station_code}</span>
        <span className="station-count">{station.records.length} 筆</span>
      </div>
      {station.records.map((rec) => (
        <RecordRow key={rec.id} record={rec} />
      ))}
    </div>
  );
}

function RecordRow({ record }: { record: RecordEntry }) {
  const [expanded, setExpanded] = useState(false);
  const entries = Object.entries(record.data || {});
  const preview = entries.slice(0, 4);
  const rest = entries.slice(4);

  return (
    <div className="record-row">
      <div className="record-meta">
        <span className="record-lot">{record.lot_no_raw}</span>
        {record.created_at && (
          <span className="record-time">{new Date(record.created_at).toLocaleString()}</span>
        )}
      </div>
      <div className="record-fields">
        {preview.map(([k, v]) => (
          <span key={k} className="record-field">
            <span className="field-key">{k}</span>
            <span className="field-val">{String(v ?? "")}</span>
          </span>
        ))}
        {rest.length > 0 && !expanded && (
          <button className="expand-btn" onClick={() => setExpanded(true)}>
            +{rest.length} 個欄位
          </button>
        )}
        {expanded && rest.map(([k, v]) => (
          <span key={k} className="record-field">
            <span className="field-key">{k}</span>
            <span className="field-val">{String(v ?? "")}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function TraceNodeCard({ node, depth }: { node: TraceNode; depth: number }) {
  return (
    <div className="trace-node" style={{ marginLeft: depth * 20 }}>
      <div className="station-header">
        <span className="station-name">{node.station_name}</span>
        <span className="station-code">{node.station_code}</span>
      </div>
      <RecordRow record={node.record} />
      {node.linked_to?.map((child, i) => (
        <TraceNodeCard key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}
