interface StatCardProps {
  label: string
  value: string
  sub?: string
  accent?: boolean
  cyan?: boolean
  children?: React.ReactNode
}

export function StatCard({ label, value, sub, accent, cyan, children }: StatCardProps) {
  return (
    <div className="bg-bg-card border border-border rounded-lg p-4">
      <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-xl font-bold ${accent ? 'text-accent' : cyan ? 'text-accent-bright' : 'text-text-primary'}`}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-text-secondary mt-0.5">{sub}</div>}
      {children}
    </div>
  )
}

interface MiniStatProps {
  label: string
  value: string
  sub?: string
  valueClass?: string
}

export function MiniStat({ label, value, sub, valueClass }: MiniStatProps) {
  return (
    <div className="text-center">
      <div className="text-[9px] text-text-muted uppercase tracking-wider">{label}</div>
      <div className={`text-sm font-semibold mt-0.5 ${valueClass ?? 'text-text-primary'}`}>{value}</div>
      {sub && <div className="text-[9px] text-text-muted mt-0.5">{sub}</div>}
    </div>
  )
}
