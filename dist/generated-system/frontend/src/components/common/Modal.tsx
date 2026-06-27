import type { ReactNode } from "react"

interface ModalProps {
  open?: boolean
  title?: string
  children?: ReactNode
  onClose?: () => void
  onConfirm?: () => void
  confirmText?: string
  cancelText?: string
  maxWidth?: string
}

export function Modal({
  open,
  title,
  children,
  onClose,
  onConfirm,
  confirmText = "確認",
  cancelText = "取消",
  maxWidth = "540px",
}: ModalProps) {
  if (!open) return null

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={(e) => { if (e.target === e.currentTarget && onClose) onClose() }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 8,
          padding: "24px 28px",
          minWidth: 320,
          maxWidth: maxWidth ?? "min(540px, 92vw)",
          width: "100%",
          boxShadow: "0 8px 32px rgba(0,0,0,.18)",
        }}
      >
        {title && (
          <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600, color: "#1e293b" }}>
            {title}
          </h3>
        )}

        <div style={{ marginBottom: 24 }}>{children}</div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                padding: "8px 18px",
                border: "1px solid #cbd5e1",
                borderRadius: 6,
                background: "#fff",
                color: "#475569",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 500,
              }}
            >
              {cancelText}
            </button>
          )}
          {onConfirm && (
            <button
              onClick={onConfirm}
              style={{
                padding: "8px 18px",
                border: "none",
                borderRadius: 6,
                background: "#2563eb",
                color: "#fff",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
              }}
            >
              {confirmText}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default Modal
