import { createContext, useContext, useState, useCallback, type ReactNode } from "react"

type ToastType = "success" | "error" | "info" | string

interface Toast {
  id: number
  type: ToastType
  message: string
}

interface ToastCtx {
  showToast: (type: ToastType, message: string, options?: { key?: string; durationMs?: number | null }) => void
  toasts: Toast[]
}

const ToastContext = createContext<ToastCtx>({
  showToast: () => {},
  toasts: [],
})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((type: ToastType, message: string) => {
    const id = Date.now() * 1000 + Math.floor(Math.random() * 1000)
    setToasts((t) => [...t, { id, type, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ showToast, toasts }}>
      {children}
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
