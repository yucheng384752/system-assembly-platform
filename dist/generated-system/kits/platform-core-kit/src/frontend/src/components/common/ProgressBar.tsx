interface ProgressBarProps { value?: number; max?: number; className?: string }
export function ProgressBar({ value = 0, max = 100, className }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className={className} style={{ background:"#e5e7eb",borderRadius:4,height:8,overflow:"hidden" }}>
      <div style={{ width:"100%",height:"100%",background:"#3b82f6",borderRadius:4,transform:`scaleX(${pct/100})`,transformOrigin:"left",transition:"transform .2s" }} />
    </div>
  )
}
export default ProgressBar