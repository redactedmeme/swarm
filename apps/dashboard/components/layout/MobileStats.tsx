'use client'
import { useDashboard } from '@/context/DashboardContext'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, buyPressureColor } from '@/lib/calculations'

export function MobileStats() {
  const { poolsData, feeRatesMap } = useDashboard()

  const total24h = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const total6h  = poolsData.reduce((s, p) => s + getVolume(p, 'h6'), 0)
  const total1h  = poolsData.reduce((s, p) => s + getVolume(p, 'h1'), 0)
  const totalLiq = poolsData.reduce((s, p) => s + getLiquidity(p), 0)

  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  const fees7d  = fees24h * 7
  const feeApr  = totalLiq > 0 ? (fees24h * 365 / totalLiq) * 100 : 0
  const avgFeeRate = knownPools.length > 0
    ? knownPools.reduce((s, p) => s + (feeRatesMap[p.pairAddress] ?? 0), 0) / knownPools.length * 100
    : 0

  const totalBuys  = poolsData.reduce((s, p) => s + (p.txns?.h24?.buys  ?? 0), 0)
  const totalSells = poolsData.reduce((s, p) => s + (p.txns?.h24?.sells ?? 0), 0)
  const totalTxns  = totalBuys + totalSells
  const buyPct     = totalTxns > 0 ? Math.round((totalBuys / totalTxns) * 100) : 50

  const cells = [
    { label: '24h Volume',    value: fmt(total24h) },
    { label: 'Total Liq',     value: fmt(totalLiq) },
    { label: '6h Volume',     value: fmt(total6h) },
    { label: '1h Volume',     value: fmt(total1h) },
    { label: 'Est. 24h Fees', value: fmt(fees24h), accent: true },
    { label: 'Est. 7d Fees',  value: fmt(fees7d),  accent: true },
    { label: 'Fee APR',       value: feeApr > 0 ? feeApr.toFixed(1) + '%' : '--', accent: true },
    { label: `Avg Fee Rate`,  value: avgFeeRate.toFixed(2) + '%' },
  ]

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {cells.map(({ label, value, accent }) => (
          <div key={label} className="bg-bg-card border border-border rounded-xl p-3">
            <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1">{label}</div>
            <div className={`text-[13px] font-bold ${accent ? 'text-accent' : ''}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Txns row */}
      <div className="bg-bg-card border border-border rounded-xl p-3">
        <div className="text-[8px] text-text-muted uppercase tracking-widest mb-1">24h Transactions</div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[13px] font-bold">{fmtCompact(totalTxns)}</span>
          <div className="text-[9px]">
            <span className="text-pos">{fmtCompact(totalBuys)}B</span>
            <span className="text-text-muted"> / </span>
            <span className="text-neg">{fmtCompact(totalSells)}S</span>
          </div>
        </div>
        <div className="h-1.5 bg-bg-primary rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }} />
        </div>
        <div className="text-[8px] text-text-muted mt-1">{buyPct}% buy pressure</div>
      </div>
    </div>
  )
}
