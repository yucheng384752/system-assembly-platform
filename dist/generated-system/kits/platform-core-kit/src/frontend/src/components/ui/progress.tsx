export function Progress({ value = 0, className }: { value?: number; className?: string }) {
  return <div className={className} style={{ background:"#e5e7eb",borderRadius:4,height:8 }}><div style={{ width:`${Math.min(100,value)}%`,height:"100%",background:"#3b82f6",borderRadius:4 }} /></div>
}