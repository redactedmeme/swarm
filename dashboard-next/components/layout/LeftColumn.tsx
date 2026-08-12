'use client'
import { useDashboard } from '@/context/DashboardContext'
import { fmt, fmtCompact } from '@/lib/formatters'
import { getEstimatedFees, getVolume, getLiquidity, getBuyPct, buyPressureColor } from '@/lib/calculations'

export function LeftColumn() {
  const { poolsData, feeRatesMap } = useDashboard()

  const total24h  = poolsData.reduce((s, p) => s + getVolume(p, 'h24'), 0)
  const total6h   = poolsData.reduce((s, p) => s + getVolume(p, 'h6'),  0)
  const total1h   = poolsData.reduce((s, p) => s + getVolume(p, 'h1'),  0)
  const totalLiq  = poolsData.reduce((s, p) => s + getLiquidity(p), 0)
  const knownPools = poolsData.filter(p => feeRatesMap[p.pairAddress] != null)
  const fees24h   = knownPools.reduce((s, p) => s + (getEstimatedFees(p, 'h24', feeRatesMap) ?? 0), 0)
  const fees7d    = fees24h * 7
  const avgFeeRate = knownPools.length > 0
    ? knownPools.reduce((s, p) => s + (feeRatesMap[p.pairAddress] ?? 0), 0) / knownPools.length * 100
    : 0
  const feeApr    = totalLiq > 0 ? (fees24h * 365 / totalLiq) * 100 : 0

  const totalBuys  = poolsData.reduce((s, p) => s + (p.txns?.h24?.buys  ?? 0), 0)
  const totalSells = poolsData.reduce((s, p) => s + (p.txns?.h24?.sells ?? 0), 0)
  const totalTxns  = totalBuys + totalSells
  const buyPct     = totalTxns > 0 ? Math.round((totalBuys / totalTxns) * 100) : 50

  const cards = [
    { label: '24h Volume', value: fmt(total24h), sub: `${poolsData.length} pools active` },
    { label: '6h / 1h Volume', value: fmt(total6h), sub: `1h: ${fmt(total1h)}` },
    { label: 'Total Liquidity', value: fmt(totalLiq) },
  ]

  return (
    <div className="space-y-2 p-4">
      {cards.map(({ label, value, sub }) => (
        <div key={label} className="bg-bg-card border border-border rounded-xl p-4">
          <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">{label}</div>
          <div className="text-lg font-bold">{value}</div>
          {sub && <div className="text-[10px] text-text-secondary mt-0.5">{sub}</div>}
        </div>
      ))}

      <div className="bg-bg-card border border-border rounded-xl p-4">
        <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">24h Transactions</div>
        <div className="text-lg font-bold">{fmtCompact(totalTxns)}</div>
        <div className="text-[10px] mt-0.5">
          <span className="text-pos">{fmtCompact(totalBuys)} buys</span>
          <span className="text-text-muted"> / </span>
          <span className="text-neg">{fmtCompact(totalSells)} sells</span>
        </div>
        <div className="mt-2 h-1.5 bg-bg-primary rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${buyPct}%`, background: buyPressureColor(buyPct) }} />
        </div>
        <div className="text-[9px] text-text-muted mt-1">{buyPct}% buy pressure</div>
      </div>

      <div className="h-px bg-border" />

      <div className="bg-bg-card border rounded-xl p-4" style={{ borderColor: 'rgba(184,147,74,0.2)' }}>
        <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">Est. 24h Fees</div>
        <div className="text-lg font-bold text-accent">{fmt(fees24h)}</div>
        <div className="text-[10px] text-text-secondary mt-0.5">avg {avgFeeRate.toFixed(2)}% · {knownPools.length} pools</div>
      </div>

      <div className="bg-bg-card border border-border rounded-xl p-4">
        <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">Est. 7d Fees</div>
        <div className="text-lg font-bold text-accent-bright">{fmt(fees7d)}</div>
        <div className="text-[10px] text-text-secondary mt-0.5">projected from 24h rate</div>
      </div>

      <div className="bg-bg-card border rounded-xl p-4" style={{ borderColor: 'rgba(184,147,74,0.15)' }}>
        <div className="text-[9px] text-text-muted uppercase tracking-widest mb-1">Fee APR (est.)</div>
        <div className="text-lg font-bold text-accent">{feeApr > 0 ? feeApr.toFixed(1) + '%' : '--'}</div>
        {feeApr > 0 && <div className="text-[10px] text-text-secondary mt-0.5">{fmt(fees24h * 365)} annualised</div>}
      </div>
    </div>
  )
}
