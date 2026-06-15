import { useToast } from "./ToastContext"

const COLORS: Record<string, string> = {
  success: "#16a34a",
  error: "#dc2626",
  info: "#2563eb",
}

export function ToastContainer() {
  const { toasts } = useToast()
  if (!toasts.length) return null
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
      {toasts.map((t) => (
        <div key={t.id} style={{
          padding: "10px 16px",
          borderRadius: 6,
          background: COLORS[t.type] ?? "#374151",
          color: "#fff",
          fontSize: 14,
          maxWidth: 360,
          boxShadow: "0 2px 8px rgba(0,0,0,.2)",
        }}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
