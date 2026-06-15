import type { ReactNode } from "react"
interface ModalProps { open?: boolean; onClose?: () => void; children?: ReactNode; title?: string }
export function Modal({ open, children, onClose }: ModalProps) {
  if (!open) return null
  return (
    <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,.4)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000 }}>
      <div style={{ background:"#fff",borderRadius:8,padding:24,minWidth:320,maxWidth:"90vw" }}>
        {children}
        {onClose && <button onClick={onClose} style={{ marginTop:16 }}>Close</button>}
      </div>
    </div>
  )
}
export default Modal