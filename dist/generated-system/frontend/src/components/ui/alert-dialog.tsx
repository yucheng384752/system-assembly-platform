import type { ReactNode } from "react"
export function AlertDialog({ children, open }: { children?: ReactNode; open?: boolean }) { if (!open) return null; return <div style={{ position:"fixed",inset:0,background:"rgba(0,0,0,.4)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000 }}>{children}</div> }
export function AlertDialogContent({ children }: { children?: ReactNode }) { return <div style={{ background:"#fff",borderRadius:8,padding:24,minWidth:320 }}>{children}</div> }
export function AlertDialogHeader({ children }: { children?: ReactNode }) { return <div style={{ marginBottom:12 }}>{children}</div> }
export function AlertDialogFooter({ children }: { children?: ReactNode }) { return <div style={{ display:"flex",gap:8,justifyContent:"flex-end",marginTop:16 }}>{children}</div> }
export function AlertDialogTitle({ children }: { children?: ReactNode }) { return <h3 style={{ margin:0 }}>{children}</h3> }
export function AlertDialogDescription({ children }: { children?: ReactNode }) { return <p>{children}</p> }
export function AlertDialogAction({ children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...p}>{children}</button> }
export function AlertDialogCancel({ children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement>) { return <button {...p}>{children}</button> }